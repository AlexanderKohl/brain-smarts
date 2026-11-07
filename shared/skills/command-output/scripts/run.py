"""Wrapper: runs one command and prints its output, shortened when it is long.

  python shared/skills/command-output/scripts/run.py -- <program> [arguments ...]
  python shared/skills/command-output/scripts/run.py --shell bash -- "<command line>"
  python shared/skills/command-output/scripts/run.py --shell powershell -- "<command line>"

For hosts whose hooks cannot replace a command's output: the agent puts this in front of a noisy
command. Standard output and standard error are captured together, in order. The wrapper exits with
the command's own exit code, so a failure is never reported as a success. Output from a command no
family recognises gets the generic filter, because asking for the wrapper is asking for the filter.
COMMAND_OUTPUT=off prints the output unchanged.

Standard library only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import filtering  # noqa: E402

def bash() -> str:
    """Git for Windows' bash on Windows, never WSL's: Windows looks in System32 before PATH, so a bare
    "bash" starts WSL, which has none of this computer's programs on its path."""
    found = shutil.which("bash")
    if os.name != "nt" or (found and "system32" not in found.lower()):
        return found or "bash"
    git = shutil.which("git")
    if git:
        for candidate in (Path(git).parents[1] / "bin" / "bash.exe", Path(git).parents[1] / "usr" / "bin" / "bash.exe"):
            if candidate.is_file():
                return str(candidate)
    return found or "bash"


SHELLS = {
    "bash": lambda line: [bash(), "-c", line],
    "sh": lambda line: ["sh", "-c", line],
    "powershell": lambda line: [shutil.which("pwsh") or "powershell", "-NoProfile", "-Command", line],
    "cmd": lambda line: ["cmd", "/d", "/s", "/c", line],
}


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command and print its output, shortened when long.")
    parser.add_argument("--shell", choices=sorted(SHELLS), help="run the command line through this shell")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="after --: the program and its arguments")
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("no command given; put it after --")
    return args


def command_line(args: argparse.Namespace) -> tuple[list[str], str]:
    """The argument list to start, and the command as the filter and the saved file show it."""
    if args.shell:
        line = " ".join(args.command)
        return SHELLS[args.shell](line), line
    program = shutil.which(args.command[0]) or args.command[0]  # finds npm.cmd and the like on Windows
    return [program, *args.command[1:]], subprocess.list2cmdline(args.command) if os.name == "nt" \
        else " ".join(args.command)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse(argv)
    start, shown = command_line(args)
    try:
        done = subprocess.run(start, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as error:
        print(f"command-output: could not start {start[0]}: {error}", file=sys.stderr)
        return 127
    text = done.stdout.decode("utf-8", errors="replace")
    short = filtering.shrink(shown, text, done.returncode, explicit=True, cwd=os.getcwd(), host="wrapper")
    sys.stdout.write(text if short is None else short + "\n")
    sys.stdout.flush()
    return done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
