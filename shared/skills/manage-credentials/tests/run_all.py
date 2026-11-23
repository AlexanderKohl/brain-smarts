"""Run every test file of this folder in its own process, several at once, from a throwaway brain.

  python run_all.py [--jobs N] [--folder PATH] [--pattern GLOB] [--rerun-limit N] [--timeout SECONDS] [--keep]

The same tests as `python -m unittest discover -s <folder>`, none skipped: each file runs as
`python -m unittest <file stem>` with the folder as its working directory. One line per file as it
finishes, then the whole output of every failing file, then one total line. Exit code 1 when a
file fails, runs no test or times out, when no file matches, or when the container stays behind.

A failing file is run once more, alone, after every other file has finished, so nothing competes
with it for the machine. One that passes then counts as passed and is named in the output; one
that fails again fails the run. More failures than --rerun-limit (5) are a fault and are not rerun.

Plan R24: the files never run in the checkout itself. A container (a new temporary folder) holds a
throwaway brain one level down: CONTRACT.md, a copy of shared/ (the skill that holds the folder, the
other skills and templates the tests read), and the library's connector scripts when the brain has a
library; no memory, so the store
is off unless a test builds its own configuration, and the clone path the code derives beside the
brain stays in the container. Every test process, and every child it starts, gets the barriers of
barrier_environment: host folders in the container, no cloud-drive variable, a refusing keyring, a
test-only agent pipe name (hermetic_site/sitecustomize.py) and a refusing gh first on PATH. The whole
container is removed afterwards (--keep leaves it, and says where it is).
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import site
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

HERE = Path(__file__).resolve().parent
RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
RERUN_LIMIT = 5
TIMEOUT = 1800.0

CONTAINER_VARIABLE = "BRAIN_TEST_CONTAINER"
PIPE_VARIABLE = "BRAIN_TEST_PIPE_NAME"  # the same name as in hermetic_site/sitecustomize.py
PIPE_PREFIX = "PortableAIBrainVaultAgent-test-"
REFUSING_KEYRING = "keyring.backends.fail.Keyring"  # every operation raises NoKeyringError
SITE_FOLDER = HERE / "hermetic_site"
SHARED = Path("shared")
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
# Removed from every test process's environment, compared in upper case (Windows names ignore case):
# the old vault's passphrase and path, GitHub tokens and host, Python start-up settings.
DROPPED_VARIABLES = frozenset({
    "GH_ENTERPRISE_TOKEN", "GH_HOST", "GH_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GITHUB_TOKEN",
    "PORTABLE_VAULT_PASSPHRASE", "PORTABLE_VAULT_PATH", "PYTHONHOME", "PYTHONSTARTUP",
})
CLOUD_PREFIX = "ONEDRIVE"  # OneDrive, OneDriveConsumer, OneDriveCommercial (store_ops.recovery_package_place)
GH_REFUSAL = ("gh refused: this is a credential test run (tests/run_all.py, plan R24) and no test reaches "
              "GitHub; a test that needs gh puts its own fake first on PATH")
GIT_IDENTITY = "[user]\n\tname = hermetic test\n\temail = person@example.com\n"


@dataclass
class Result:
    name: str
    passed: bool
    tests: int
    seconds: float
    output: str
    why: str = ""


# -- the container and its barriers ------------------------------------------------------------------
def find_brain(folder: Path) -> Path | None:
    """The folder holding CONTRACT.md at or above folder, as the code under test finds its brain."""
    for candidate in [folder, *folder.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    return None


def build_brain(folder: Path, container: Path) -> Path:
    """Copy what the tests read into container/brain and return the copy of folder. A folder outside
    any brain (the stand-in files of test_run_all.py) is copied alone."""
    target = container / "brain"
    source = find_brain(folder)
    if source is None:
        shutil.copytree(folder, target / folder.name, ignore=IGNORED)
        return target / folder.name
    skill = folder.parent
    target.mkdir(parents=True)
    shutil.copy2(source / "CONTRACT.md", target / "CONTRACT.md")
    if (source / SHARED).is_dir():  # tests read other shared skills and templates (tasks, memory-skeleton)
        shutil.copytree(source / SHARED, target / SHARED, ignore=IGNORED)
    if not (target / skill.relative_to(source)).exists():
        shutil.copytree(skill, target / skill.relative_to(source), ignore=IGNORED)
    library = source / "library" / "skills"
    if library.is_dir():  # the connectors' scripts only (test_credential_paths, test_secret_store_connectors)
        for scripts in sorted(library.glob("*/scripts")):
            shutil.copytree(scripts, target / scripts.relative_to(source), ignore=IGNORED)
    if (target / "memory").exists():
        raise SystemExit(f"run_all: the throwaway brain {target} holds a memory folder; refusing to run")
    return target / folder.relative_to(source)


def _gh_shim(folder: Path) -> Path:
    """A gh that prints why it refuses and exits 1: a shell script, or on Windows an .exe made with
    pip's script launcher, because Windows finds a bare `gh` only as gh.exe."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        shim = folder / "gh"
        shim.write_text(f"#!/bin/sh\necho '{GH_REFUSAL}' >&2\nexit 1\n", "utf-8")
        shim.chmod(0o755)
        return shim
    source = folder.parent / "gh-source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "gh.py").write_text(f"#!python\nimport sys\nsys.stderr.write({GH_REFUSAL + chr(10)!r})\n"
                                  "raise SystemExit(1)\n", "utf-8")
    try:
        from pip._vendor.distlib.scripts import ScriptMaker
    except ImportError:
        raise SystemExit("run_all: pip's script launcher is missing, so no refusing gh.exe can be made; "
                         "refusing to run") from None
    maker = ScriptMaker(str(source), str(folder))
    maker.executable = sys.executable
    made = [Path(p) for p in maker.make("gh.py")]
    if [p.name.lower() for p in made] != ["gh.exe"]:
        raise SystemExit("run_all: the refusing gh.exe was not made; refusing to run")
    return made[0]


def prepare_container(container: Path) -> None:
    """The host folders, the refusing gh, the pipe-name hook and a git identity of no one."""
    home = container / "home"
    for folder in (home / "AppData" / "Local", home / "AppData" / "Roaming", home / ".config" / "gh",
                   home / ".local" / "share", home / ".local" / "state", home / ".cache", container / "tmp"):
        folder.mkdir(parents=True, exist_ok=True)
    (container / "run").mkdir(mode=0o700, exist_ok=True)
    (home / ".gitconfig").write_text(GIT_IDENTITY, "utf-8")
    _gh_shim(container / "bin")
    shutil.copytree(SITE_FOLDER, container / "site", ignore=IGNORED, dirs_exist_ok=True)


def new_pipe_name(run_id: str, index: int) -> str:
    return f"{PIPE_PREFIX}{run_id}-{index}"


def barrier_environment(container: Path, pipe: str, base: Mapping[str, str]) -> dict[str, str]:
    """The environment of a test process: base without the dropped and cloud-drive variables, with
    the container's host folders, the refusing keyring, the pipe name and the refusing gh first."""
    home = container / "home"
    path = next((v for k, v in base.items() if k.upper() == "PATH"), "")
    values = {
        CONTAINER_VARIABLE: str(container),
        PIPE_VARIABLE: pipe,
        "HOME": str(home), "USERPROFILE": str(home),
        "LOCALAPPDATA": str(home / "AppData" / "Local"), "APPDATA": str(home / "AppData" / "Roaming"),
        "XDG_RUNTIME_DIR": str(container / "run"), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"), "XDG_STATE_HOME": str(home / ".local" / "state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TEMP": str(container / "tmp"), "TMP": str(container / "tmp"), "TMPDIR": str(container / "tmp"),
        "PYTHON_KEYRING_BACKEND": REFUSING_KEYRING,
        "PYTHONPATH": str(container / "site"),
        "PYTHONUSERBASE": site.getuserbase(),  # packages installed for the user stay importable
        "PATH": str(container / "bin") + (os.pathsep + path if path else ""),
        "GH_CONFIG_DIR": str(home / ".config" / "gh"),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    }
    replaced = {key.upper() for key in values} | DROPPED_VARIABLES
    environment = {k: v for k, v in base.items()
                   if k.upper() not in replaced and not k.upper().startswith(CLOUD_PREFIX)}
    environment.update(values)
    return environment


def _writable_retry(function, path, _info) -> None:
    """rmtree's error handler: git writes its objects read-only, which Windows will not delete."""
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except OSError:
        pass


def remove_container(container: Path) -> bool:
    """Remove the whole container; True when it is gone."""
    for _attempt in range(3):
        if sys.version_info >= (3, 12):
            shutil.rmtree(container, onexc=_writable_retry)
        else:
            shutil.rmtree(container, onerror=_writable_retry)
        if not container.exists():
            return True
        time.sleep(1.0)  # a child that has only just ended may still hold a file
    return False


# -- running the files -------------------------------------------------------------------------------
def run_file(folder: Path, name: str, timeout: float, env: dict[str, str] | None = None) -> Result:
    started = time.monotonic()
    try:
        done = subprocess.run([sys.executable, "-m", "unittest", Path(name).stem], cwd=folder, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace", env=env)
        output, code = done.stdout or "", done.returncode
    except subprocess.TimeoutExpired as exc:
        output, code = (exc.stdout or "") if isinstance(exc.stdout, str) else "", None
    seconds = time.monotonic() - started
    found = RAN.findall(output)
    tests = int(found[-1]) if found else 0
    if code is None:
        return Result(name, False, tests, seconds, output, f"no result within {timeout:.0f} s")
    if code != 0:
        return Result(name, False, tests, seconds, output, f"exit {code}")
    if tests == 0:
        return Result(name, False, 0, seconds, output, "ran no test")
    return Result(name, True, tests, seconds, output)


def line(result: Result, note: str = "") -> str:
    if result.passed:
        return f"ok    {result.name}: {result.tests} tests, {result.seconds:.1f} s{note}"
    return f"FAIL  {result.name}: {result.why}, {result.tests} tests, {result.seconds:.1f} s{note}"


def default_jobs() -> int:
    return max(1, min(8, (os.cpu_count() or 2) // 2))


def run_files(folder: Path, names: list[str], args: argparse.Namespace,
              env_for: dict[str, dict[str, str]]) -> tuple[dict[str, Result], list[str]]:
    results: dict[str, Result] = {}
    # Lines appear in the order the files finish, so a long run shows its progress.
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_file, folder, name, args.timeout, env_for[name]) for name in names]
        for future in as_completed(futures):
            result = future.result()
            results[result.name] = result
            print(line(result), flush=True)
    failed = sorted(n for n, r in results.items() if not r.passed)
    rerun_passed: list[str] = []
    if failed and len(failed) <= args.rerun_limit:
        for name in failed:  # alone, one after another, in file-name order
            result = run_file(folder, name, args.timeout, env_for[name])
            print(line(result, " (rerun alone)"), flush=True)
            if result.passed:
                results[name] = result
                rerun_passed.append(name)
    return results, rerun_passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", default=str(HERE), help="the folder of test files")
    parser.add_argument("--pattern", default="test_*.py", help="which files are test files")
    parser.add_argument("--jobs", type=int, default=default_jobs(), help="files run at once")
    parser.add_argument("--rerun-limit", type=int, default=RERUN_LIMIT,
                        help="rerun failing files alone only when no more than this many failed")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help="seconds allowed for one file")
    parser.add_argument("--keep", action="store_true", help="leave the container in place afterwards")
    args = parser.parse_args(argv)
    source = Path(args.folder).resolve()
    names = sorted(p.name for p in source.glob(args.pattern) if p.is_file())
    if not names:
        print(f"FAIL  no test files match {args.pattern} in {source}")
        return 1
    started = time.monotonic()
    container = Path(tempfile.mkdtemp(prefix="brain-tests-"))
    try:
        folder = build_brain(source, container)
        prepare_container(container)
        run_id = secrets.token_hex(4)
        env_for = {name: barrier_environment(container, new_pipe_name(run_id, index), os.environ)
                   for index, name in enumerate(names, start=1)}
        print(f"throwaway brain: {folder} (container {container})", flush=True)
        results, rerun_passed = run_files(folder, names, args, env_for)
    finally:
        removed = False if args.keep else remove_container(container)
    failed = sorted(n for n, r in results.items() if not r.passed)
    for name in failed:  # file-name order
        print(f"\n---- {name} ----\n{results[name].output.rstrip()}")
    if failed:
        print()
    if rerun_passed:
        print("passed when rerun alone: " + ", ".join(rerun_passed))
    if args.keep:
        print(f"container kept: {container}")
    elif removed:
        print(f"container removed: {container}")
    else:
        print(f"FAIL  the container could not be removed: {container}")
    total = sum(r.tests for r in results.values())
    tail = f"{len(failed)} failed" + (": " + ", ".join(failed) if failed else "")
    print(f"Total: {len(names)} files, {total} tests, {tail} ({time.monotonic() - started:.0f} s, {args.jobs} at once)")
    return 1 if failed or not (removed or args.keep) else 0


if __name__ == "__main__":
    raise SystemExit(main())
