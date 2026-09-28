"""Scheduled, read-only review: what has come due, written where the owner can see it.

Runs with no model and changes nothing that Git tracks, so it can run from the operating system's
own scheduler while sessions work in the same tree. Output: /temp/due.md (ignored by every brain
repository), and a desktop notification when something needs attention.

  python shared/skills/tasks/scripts/scheduled_review.py              write /temp/due.md and notify
  python shared/skills/tasks/scripts/scheduled_review.py --no-notify  write /temp/due.md only
  python shared/skills/tasks/scripts/scheduled_review.py --register   run it daily from the OS scheduler

CONTRACT §14: an agent may claim follow-up only when a scheduler is actually configured; once
registered, this is that scheduler. It needs no model and no AI host: Windows Task Scheduler on
Windows, cron elsewhere. The same scripts run at session start through the hook list.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TASK_NAME = "BrainScheduledReview"
DAILY_AT = "07:00"
REPOSITORIES = [(".", "mechanics"), ("library", "skill library"), ("memory", "memory")]
DIGEST_INDEX = "memory/projects/brain-development/data/learning/index.md"
DIGEST_DUE = re.compile(r"next is due (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})")
TASK_COUNT = re.compile(r"^(\d+) task\(s\) need attention", re.MULTILINE)


def brain_root(start: Path) -> Path:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file():
            return folder
    raise SystemExit("CONTRACT.md not found above " + str(start))


def owner_brain_root(root: Path) -> Path:
    """The shared checkout named in the owner profile; a session copy is removed when it finishes."""
    owner = root / "memory" / "OWNER.md"
    if owner.is_file():
        match = re.search(r"^brain_root:\s*(.+)$", owner.read_text(encoding="utf-8"), re.MULTILINE)
        if match and (Path(match.group(1).strip()) / "CONTRACT.md").is_file():
            return Path(match.group(1).strip())
    return root


def run(root: Path, *args: str) -> str:
    # A Windows child writes to a pipe in the console code page unless told otherwise.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True, env=env,
                            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return (result.stdout + result.stderr).strip()


def freshness(root: Path) -> list[str]:
    """Fetch and compare with origin; the working tree and branches are left as they are."""
    lines = []
    for folder, label in REPOSITORIES:
        path = root / folder
        if not (path / ".git").exists():
            continue
        fetch = subprocess.run(["git", "fetch", "--quiet", "origin"], cwd=path, capture_output=True, text=True)
        counts = subprocess.run(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd=path,
                                capture_output=True, text=True)
        if counts.returncode != 0:
            lines.append(f"- {label}: no upstream to compare with")
            continue
        ahead, behind = (int(n) for n in counts.stdout.split())
        state = ("up to date" if not ahead and not behind else
                 f"behind origin by {behind}" if not ahead else
                 f"{ahead} commit(s) not on origin" if not behind else
                 f"diverged: {ahead} local and {behind} remote commits")
        note = "" if fetch.returncode == 0 else " (fetch failed; compared with the last fetch)"
        lines.append(f"- {label}: {state}{note}")
    return lines


def digest_due(root: Path, now: datetime) -> str | None:
    index = root / DIGEST_INDEX
    if not index.is_file():
        return None
    match = DIGEST_DUE.search(index.read_text(encoding="utf-8"))
    if not match:
        return None
    due = datetime.fromisoformat(match.group(1))
    return f"due since {match.group(1)}" if due <= now else None


def review(root: Path, now: datetime) -> tuple[str, list[str]]:
    """The report, and the short reasons it needs the owner's attention (empty when nothing does)."""
    stamp = now.isoformat(timespec="seconds")
    tasks = run(root, "shared/skills/tasks/scripts/tasks.py", "review")
    preflight = run(root, "shared/skills/repository-preflight/scripts/preflight.py")
    sections = [("Tasks due, blocked or waiting", tasks),
                ("Skill exchange", run(root, "shared/skills/skill-exchange/scripts/skill_exchange.py", "due")),
                ("Repository preflight", preflight)]
    fresh = freshness(root)
    digest = digest_due(root, now)
    lines = [f"# Due – {stamp}", "", "Written by the scheduled review; read-only, regenerated each run.", "",
             "## Checkout compared with origin", "", *(fresh or ["- no repositories found"]), ""]
    if any("up to date" not in line for line in fresh):
        lines += ["The lists below are read from this checkout, so they may miss work that is only on origin.", ""]
    lines += ["## Weekly learning digest", "", f"- {digest}" if digest else "- not due", ""]
    for title, text in sections:
        lines += [f"## {title}", "", "```", text[-6000:] or "(nothing)", "```", ""]
    reasons = []
    count = TASK_COUNT.search(tasks)
    if count and int(count.group(1)):
        reasons.append(f"{count.group(1)} task(s) need attention")
    if digest:
        reasons.append("weekly learning digest due")
    if not preflight.startswith("PASS"):
        reasons.append("preflight not passing")
    return "\n".join(lines), reasons


def notify(title: str, message: str) -> bool:
    """A desktop notification through the operating system; False when none is available."""
    if sys.platform == "win32":
        # A tray balloon, which Windows 10 and 11 show as a notification; it needs no registered app id.
        script = ("Add-Type -AssemblyName System.Windows.Forms, System.Drawing;"
                  "$n = New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true;"
                  "$n.ShowBalloonTip(10000, $env:BRAIN_TITLE, $env:BRAIN_MESSAGE, 'Info');"
                  "Start-Sleep -Seconds 8; $n.Dispose()")
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    elif sys.platform == "darwin":
        command = ["osascript", "-e", "display notification (system attribute \"BRAIN_MESSAGE\") "
                   "with title (system attribute \"BRAIN_TITLE\")"]
    elif shutil.which("notify-send"):
        command = ["notify-send", title, message]
    else:
        return False
    env = {**os.environ, "BRAIN_TITLE": title, "BRAIN_MESSAGE": message}
    return subprocess.run(command, env=env, capture_output=True).returncode == 0


def schedule_command(script: Path) -> list[str]:
    """The command that registers a daily run; on Windows a missed run starts when the computer is next on."""
    python = Path(sys.executable)
    root = script.parents[4]
    if sys.platform == "win32":
        pythonw = python.with_name("pythonw.exe")
        runner = pythonw if pythonw.is_file() else python
        ps = (f"$a = New-ScheduledTaskAction -Execute '{runner}' -Argument '\"{script}\"' -WorkingDirectory '{root}';"
              f"$t = New-ScheduledTaskTrigger -Daily -At {DAILY_AT};"
              "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
              "-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10);"
              f"Register-ScheduledTask -TaskName {TASK_NAME} -Action $a -Trigger $t -Settings $s -Force > $null")
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]
    hour, minute = DAILY_AT.split(":")
    line = f"{int(minute)} {int(hour)} * * * cd '{root}' && '{python}' '{script}'  # {TASK_NAME}"
    return ["sh", "-c", f"(crontab -l 2>/dev/null | grep -v '# {TASK_NAME}'; echo \"{line}\") | crontab -"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", action="store_true", help=f"run daily at {DAILY_AT} from the OS scheduler")
    parser.add_argument("--no-notify", action="store_true", help="write the report without a notification")
    args = parser.parse_args(argv)
    root = brain_root(Path(__file__).resolve().parent)
    if args.register:
        shared = owner_brain_root(root)
        script = shared / "shared" / "skills" / "tasks" / "scripts" / "scheduled_review.py"
        subprocess.run(schedule_command(script), check=True)
        print(f"registered {TASK_NAME}: daily at {DAILY_AT}, running {script}")
        return 0
    report, reasons = review(root, datetime.now().astimezone())
    out = root / "temp" / "due.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    if reasons and not args.no_notify:
        shown = notify("Brain: " + "; ".join(reasons), f"Details in {out}")
        print("notified" if shown else "no desktop notification available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
