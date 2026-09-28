"""Scheduled, read-only review: what has come due, written where the owner board can show it.

Runs with no model and changes nothing that Git tracks, so it can run from a scheduler while
sessions work in the same tree. Output: /temp/due.md (ignored by every brain repository).

  python shared/skills/tasks/scripts/scheduled_review.py            write /temp/due.md
  python shared/skills/tasks/scripts/scheduled_review.py --register register a daily Windows task

CONTRACT §14: an agent may claim follow-up only when a scheduler is actually configured; this is
that scheduler. The same scripts run at session start through the hook list.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def brain_root(start: Path) -> Path:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file():
            return folder
    raise SystemExit("CONTRACT.md not found above " + str(start))


def run(root: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return (result.stdout + result.stderr).strip()


def review(root: Path) -> str:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    sections = [("Tasks due, blocked or waiting", ["shared/skills/tasks/scripts/tasks.py", "review"]),
                ("Skill exchange", ["shared/skills/skill-exchange/scripts/skill_exchange.py", "due"]),
                ("Repository preflight", ["shared/skills/repository-preflight/scripts/preflight.py"])]
    lines = [f"# Due – {now}", "", "Written by the scheduled review; read-only, regenerated each run.", ""]
    for title, args in sections:
        lines += [f"## {title}", "", "```", run(root, *args)[-6000:] or "(nothing)", "```", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", action="store_true", help="register a daily 07:00 Windows task")
    args = parser.parse_args(argv)
    root = brain_root(Path(__file__).resolve().parent)
    if args.register:
        command = f'"{sys.executable}" "{Path(__file__).resolve()}"'
        subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", "07:00", "/TN", "BrainScheduledReview",
                        "/TR", command], check=True)
        print("registered BrainScheduledReview, daily at 07:00")
        return 0
    out = root / "temp" / "due.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(review(root), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
