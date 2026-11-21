"""Run every test file of this folder in its own process, several at once.

  python run_all.py [--jobs N] [--folder PATH] [--pattern GLOB] [--rerun-limit N] [--timeout SECONDS]

The same tests as `python -m unittest discover -s <folder>`, none skipped: each file runs as
`python -m unittest <file stem>` with the folder as its working directory. One line per file as it
finishes, then the whole output of every failing file, then one total line. Exit code 1 when a
file fails, runs no test or times out, or when no file matches.

A failing file is run once more, alone, after every other file has finished, so nothing competes
with it for the machine. One that passes then counts as passed and is named in the output; one
that fails again fails the run. More failures than --rerun-limit (5) are a fault and are not rerun.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
RERUN_LIMIT = 5
TIMEOUT = 1800.0


@dataclass
class Result:
    name: str
    passed: bool
    tests: int
    seconds: float
    output: str
    why: str = ""


def run_file(folder: Path, name: str, timeout: float) -> Result:
    started = time.monotonic()
    try:
        done = subprocess.run([sys.executable, "-m", "unittest", Path(name).stem], cwd=folder, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", default=str(Path(__file__).resolve().parent), help="the folder of test files")
    parser.add_argument("--pattern", default="test_*.py", help="which files are test files")
    parser.add_argument("--jobs", type=int, default=default_jobs(), help="files run at once")
    parser.add_argument("--rerun-limit", type=int, default=RERUN_LIMIT,
                        help="rerun failing files alone only when no more than this many failed")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help="seconds allowed for one file")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    names = sorted(p.name for p in folder.glob(args.pattern) if p.is_file())
    if not names:
        print(f"FAIL  no test files match {args.pattern} in {folder}")
        return 1
    started = time.monotonic()
    results: dict[str, Result] = {}
    # Lines appear in the order the files finish, so a long run shows its progress.
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for future in as_completed([pool.submit(run_file, folder, name, args.timeout) for name in names]):
            result = future.result()
            results[result.name] = result
            print(line(result), flush=True)
    failed = sorted(n for n, r in results.items() if not r.passed)
    rerun_passed: list[str] = []
    if failed and len(failed) <= args.rerun_limit:
        for name in failed:  # alone, one after another, in file-name order
            result = run_file(folder, name, args.timeout)
            print(line(result, " (rerun alone)"), flush=True)
            if result.passed:
                results[name] = result
                rerun_passed.append(name)
    failed = sorted(n for n, r in results.items() if not r.passed)
    for name in failed:  # file-name order
        print(f"\n---- {name} ----\n{results[name].output.rstrip()}")
    if failed:
        print()
    if rerun_passed:
        print("passed when rerun alone: " + ", ".join(rerun_passed))
    total = sum(r.tests for r in results.values())
    tail = f"{len(failed)} failed" + (": " + ", ".join(failed) if failed else "")
    print(f"Total: {len(names)} files, {total} tests, {tail} ({time.monotonic() - started:.0f} s, {args.jobs} at once)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
