"""Work that goes on after the reply: a job in a process of its own, and the record of how it ended.

    python shared/skills/repository-preflight/scripts/background.py list
    python shared/skills/repository-preflight/scripts/background.py run <record>     (internal)

`session.py finish <name> --background` starts the ordinary finish through `start` and returns at
once, so the reply to the owner does not wait for the merge, the checks and the pushes. Each job
has a record, `/temp/background/<kind>-<name>.json` in the shared checkout, and its output in a
`.log` beside it (local scratch, CONTRACT §3.5). `hooks.py background-report`, which the host runs
on every prompt, reads the records through `report`:

- a job that failed is reported once, with the end of its log and the command that repeats it;
- a job still running is named, so no session writes into a copy that is being merged;
- a job that ended well says nothing, and its record is removed.

A job whose process is gone without a result counts as failed. The pre-commit hook refuses a
commit in a session copy whose finish is running (`running`); the job's own commits pass, because
its process carries BRAIN_BACKGROUND_JOB.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FOLDER = Path("temp") / "background"
JOB_ENV = "BRAIN_BACKGROUND_JOB"     # set in a job's own process and inherited by its children
TAIL_LINES = 15                      # of a failed job's log, shown in the report
STALE_HOURS = 2                      # a "running" record older than this is not believed
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")


def now() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def record_path(root: Path, kind: str, name: str) -> Path:
    if not SAFE_NAME.match(kind) or not SAFE_NAME.match(name):
        raise ValueError(f"not a job name: {kind} {name}")
    return root / FOLDER / f"{kind}-{name}.json"


def read(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def write(path: Path, record: dict) -> None:
    """Replace the record whole, so a reader never sees half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(f".{os.getpid()}.tmp")
    scratch.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(scratch, path)


def alive(pid: object) -> bool:
    """Whether a process with this id exists. Never signals it: on Windows os.kill ends a process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        answered = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(answered) and code.value == 259            # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def state(record: dict) -> str:
    """`running`, `done` or `failed`; a record that says running without a live process has failed."""
    if record.get("state") != "running":
        return "done" if record.get("state") == "done" else "failed"
    try:
        age = datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(str(record.get("started")))
    except ValueError:
        return "failed"
    if age > datetime.timedelta(hours=STALE_HOURS):
        return "failed"
    # Between `start` and the job's first write there is no process id yet: believed for a minute.
    if record.get("pid") is None:
        return "running" if age < datetime.timedelta(minutes=1) else "failed"
    return "running" if alive(record.get("pid")) else "failed"


def running(root: Path, kind: str, name: str) -> bool:
    try:
        record = read(record_path(root, kind, name))
    except ValueError:
        return False
    return record is not None and state(record) == "running"


def start(root: Path, kind: str, name: str, command: list[str], cwd: Path) -> Path:
    """Start `command` as a job of its own and return its record. Refuses while the same job runs."""
    path = record_path(root, kind, name)
    if running(root, kind, name):
        raise RuntimeError(f"{kind} of {name} is already running in the background")
    log = path.with_suffix(".log")
    write(path, {"kind": kind, "name": name, "state": "running", "started": now(), "pid": None,
                 "command": command, "cwd": str(cwd), "log": str(log)})
    options: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                     "cwd": str(root), "close_fds": True}
    if os.name == "nt":
        # No console window, and a process group of its own, so it outlives the shell that started it.
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", str(path)], **options)
    return path


def run(path: Path) -> int:
    """The job's own process: run the command, keep its output, record how it ended."""
    record = read(path)
    if record is None:
        return 2
    record["pid"] = os.getpid()
    write(path, record)
    env = {**os.environ, JOB_ENV: str(path), "PYTHONIOENCODING": "utf-8"}
    try:
        with open(record["log"], "w", encoding="utf-8", errors="replace") as log:
            code = subprocess.run(record["command"], cwd=record["cwd"], stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, env=env).returncode
    except OSError as error:
        code = 1
        Path(record["log"]).write_text(f"could not run: {error}\n", encoding="utf-8")
    record.update(state="done" if code == 0 else "failed", exit=code, finished=now())
    write(path, record)
    return code


def tail(log: str) -> list[str]:
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ["(its log could not be read)"]
    return [line for line in lines if line.strip()][-TAIL_LINES:]


def report(root: Path) -> str:
    """What the next reply must carry about background jobs, or "" when there is nothing to say.
    Jobs are listed by name. A failure is told once: its record is marked, and kept for `list`."""
    folder = root / FOLDER
    lines: list[str] = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        record = read(path)
        if record is None or record.get("reported"):
            continue
        what = f"{record.get('kind')} of `{record.get('name')}`"
        found = state(record)
        if found == "done":
            path.unlink(missing_ok=True)
        elif found == "running":
            lines.append(f"Background {what} is still running (started {record.get('started')}): "
                         "do not write or commit in that session copy until it has ended.")
        else:
            ended = (f"failed with exit code {record.get('exit')} at {record.get('finished')}"
                     if record.get("state") == "failed" else "stopped without a result (its process is gone)")
            lines.append(f"BACKGROUND {what.upper()} FAILED: it {ended}. Its work is committed locally and may "
                         "not be merged or pushed. Tell the owner in this reply, fix the cause, and run it "
                         f"again in the foreground: {subprocess.list2cmdline(record.get('command') or [])} "
                         f"(without --background). Full output: {record.get('log')}. Its last lines:")
            lines += ["    " + line for line in tail(str(record.get("log")))]
            record["reported"] = True
            write(path, record)
    return "\n".join(lines)


def listing(root: Path) -> str:
    folder = root / FOLDER
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        record = read(path)
        if record is not None:
            rows.append(f"{record.get('kind')} {record.get('name')}: {state(record)}, started "
                        f"{record.get('started')}, log {record.get('log')}")
    return "\n".join(rows) or "no background jobs on record"


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "run":
        return run(Path(argv[1]))
    if argv == ["list"]:
        for folder in [Path.cwd(), *Path.cwd().parents]:
            if (folder / "CONTRACT.md").is_file():
                print(listing(folder))
                return 0
        print("CONTRACT.md not found; run inside the brain")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
