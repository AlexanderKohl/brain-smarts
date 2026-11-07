"""Scheduled, read-only review: what has come due, written where the owner can see it.

Runs with no model and changes nothing that Git tracks, so it can run from the operating system's
own scheduler while sessions work in the same tree. Output: /temp/due.md (ignored by every brain
repository), and a desktop notification when something needs attention. Its task section runs
`tasks.py review`, which reads every task store the brain can reach (owner, node, pointer-private
and checked-out repository stores) and names the ones it could not read.

  python shared/skills/tasks/scripts/scheduled_review.py              write /temp/due.md, run the morning jobs, notify
  python shared/skills/tasks/scripts/scheduled_review.py --no-notify  the same without a notification
  python shared/skills/tasks/scripts/scheduled_review.py --no-jobs    the same without the morning jobs
  python shared/skills/tasks/scripts/scheduled_review.py --register   run it daily from the OS scheduler
  python shared/skills/tasks/scripts/scheduled_review.py --status     show the registered daily run
  python shared/skills/tasks/scripts/scheduled_review.py --unregister remove it

After its own report the review runs the owner's morning jobs (morning_jobs.py: the commands in
/memory/skills/tasks/config/morning-jobs.json, each from the brain root, output to
/temp/morning/<name>.log) and reports one line per job; a job that fails or times out is named in
the notification and never stops the review or the other jobs. One scheduled run, one hook
(SMART-RULE-0018): a second daily job is not registered for them.

CONTRACT §14: an agent may claim follow-up only when a scheduler is actually configured; once
registered, this is that scheduler. It needs no model and no AI host: Windows Task Scheduler, a
launchd agent on macOS, a systemd user timer on Linux, or cron where systemd is not available.
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

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import morning_jobs  # noqa: E402

TASK_NAME = "BrainScheduledReview"
DAILY_AT = "07:00"
# The Windows task is stopped at this limit, so the morning jobs' timeouts together stay under it.
EXECUTION_LIMIT_MINUTES = 30
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


def review(root: Path, now: datetime, jobs: bool = True) -> tuple[str, list[str], list[str]]:
    """The report, the short reasons it needs the owner's attention (empty when nothing does), and
    the lines of the morning jobs that failed, for the notification's text."""
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
    # The morning jobs run last, after the review's own report is complete.
    results, problem = morning_jobs.run_jobs(root) if jobs else ([], "skipped (--no-jobs)")
    lines += ["## Morning jobs", "", *morning_jobs.report_lines(results, problem), ""]
    reasons = []
    count = TASK_COUNT.search(tasks)
    if count and int(count.group(1)):
        reasons.append(f"{count.group(1)} task(s) need attention")
    if digest:
        reasons.append("weekly learning digest due")
    if not preflight.startswith("PASS"):
        reasons.append("preflight not passing")
    reasons += morning_jobs.reasons(results)
    return "\n".join(lines), reasons, [result.line() for result in morning_jobs.failures(results)]


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


LAUNCHD_LABEL = "local.brain.scheduled-review"


class Plan:
    """What registering, checking or removing the daily run does on one operating system: files to
    write or delete, then commands to run. Built without side effects, so it can be shown and tested."""

    def __init__(self, scheduler: str, write: dict[Path, str] | None = None, delete: list[Path] | None = None,
                 commands: list[list[str]] | None = None):
        self.scheduler, self.write, self.delete, self.commands = scheduler, write or {}, delete or [], commands or []

    def apply(self) -> None:
        for path, text in self.write.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for path in self.delete:
            path.unlink(missing_ok=True)
        for command in self.commands:
            subprocess.run(command, check=True)


def platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux-systemd" if shutil.which("systemctl") and os.environ.get("XDG_RUNTIME_DIR") else "linux-cron"


def plan(action: str, script: Path, python: Path, home: Path, system: str, uid: int | None = None) -> Plan:
    """action: register, status or unregister. A missed 07:00 run starts when the computer is next
    on (Windows start-when-available, launchd after sleep, a persistent systemd timer); cron cannot."""
    root = script.parents[4]
    hour, minute = (int(part) for part in DAILY_AT.split(":"))
    if system == "windows":
        if action == "status":
            return Plan("Windows Task Scheduler", commands=[["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]])
        if action == "unregister":
            return Plan("Windows Task Scheduler", commands=[["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]])
        pythonw = python.with_name("pythonw.exe")
        runner = pythonw if pythonw.is_file() else python
        ps = (f"$a = New-ScheduledTaskAction -Execute '{runner}' -Argument '\"{script}\"' -WorkingDirectory '{root}';"
              f"$t = New-ScheduledTaskTrigger -Daily -At {DAILY_AT};"
              "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
              f"-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes {EXECUTION_LIMIT_MINUTES});"
              f"Register-ScheduledTask -TaskName {TASK_NAME} -Action $a -Trigger $t -Settings $s -Force > $null")
        return Plan("Windows Task Scheduler", commands=[["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]])
    if system == "macos":
        # A LaunchAgent runs in the owner's login session, so its notification is shown.
        agent = home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        target = f"gui/{uid if uid is not None else os.getuid()}"
        if action == "status":
            return Plan("launchd", commands=[["launchctl", "print", f"{target}/{LAUNCHD_LABEL}"]])
        if action == "unregister":
            return Plan("launchd", delete=[agent],
                        commands=[["sh", "-c", f"launchctl bootout {target}/{LAUNCHD_LABEL} 2>/dev/null || true"]])
        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f"  <key>Label</key><string>{LAUNCHD_LABEL}</string>\n"
            f"  <key>ProgramArguments</key><array><string>{python}</string><string>{script}</string></array>\n"
            f"  <key>WorkingDirectory</key><string>{root}</string>\n"
            f"  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{hour}</integer>"
            f"<key>Minute</key><integer>{minute}</integer></dict>\n"
            "</dict>\n</plist>\n")
        return Plan("launchd", write={agent: plist}, commands=[
            ["sh", "-c", f"launchctl bootout {target}/{LAUNCHD_LABEL} 2>/dev/null || true"],
            ["launchctl", "bootstrap", target, str(agent)]])
    if system == "linux-systemd":
        # A user timer runs in the owner's session (notify-send reaches the desktop); Persistent catches up.
        folder = home / ".config" / "systemd" / "user"
        service, timer = folder / "brain-scheduled-review.service", folder / "brain-scheduled-review.timer"
        if action == "status":
            return Plan("systemd user timer", commands=[["systemctl", "--user", "list-timers", "brain-scheduled-review.timer"]])
        if action == "unregister":
            return Plan("systemd user timer", delete=[service, timer], commands=[
                ["sh", "-c", "systemctl --user disable --now brain-scheduled-review.timer || true"],
                ["systemctl", "--user", "daemon-reload"]])
        return Plan("systemd user timer", write={
            service: ("[Unit]\nDescription=Brain scheduled review\n\n[Service]\nType=oneshot\n"
                      f"WorkingDirectory={root}\nExecStart={python} {script}\n"),
            timer: ("[Unit]\nDescription=Brain scheduled review, daily\n\n[Timer]\n"
                    f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")},
            commands=[["systemctl", "--user", "daemon-reload"],
                      ["systemctl", "--user", "enable", "--now", "brain-scheduled-review.timer"]])
    # cron: no catch-up, and a notification needs the desktop session's environment.
    if action == "status":
        return Plan("cron", commands=[["sh", "-c", f"crontab -l | grep '# {TASK_NAME}'"]])
    keep = f"crontab -l 2>/dev/null | grep -v '# {TASK_NAME}'"
    if action == "unregister":
        return Plan("cron", commands=[["sh", "-c", f"({keep}) | crontab -"]])
    line = f"{minute} {hour} * * * cd '{root}' && '{python}' '{script}'  # {TASK_NAME}"
    return Plan("cron", commands=[["sh", "-c", f"({keep}; echo \"{line}\") | crontab -"]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--register", action="store_true", help=f"run daily at {DAILY_AT} from the OS scheduler")
    group.add_argument("--status", action="store_true", help="show the registered daily run")
    group.add_argument("--unregister", action="store_true", help="remove the daily run")
    parser.add_argument("--no-notify", action="store_true", help="write the report without a notification")
    parser.add_argument("--no-jobs", action="store_true", help="write the report without running the morning jobs")
    args = parser.parse_args(argv)
    root = brain_root(Path(__file__).resolve().parent)
    action = "register" if args.register else "status" if args.status else "unregister" if args.unregister else None
    if action:
        script = owner_brain_root(root) / "shared" / "skills" / "tasks" / "scripts" / "scheduled_review.py"
        chosen = plan(action, script, Path(sys.executable), Path.home(), platform_name())
        chosen.apply()
        if action != "status":
            print(f"{action}: {TASK_NAME} with {chosen.scheduler}, daily at {DAILY_AT}, running {script}")
        return 0
    report, reasons, failed_jobs = review(root, datetime.now().astimezone(), jobs=not args.no_jobs)
    out = root / "temp" / "due.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    for line in failed_jobs:
        print(line)
    if reasons and not args.no_notify:
        shown = notify("Brain: " + "; ".join(reasons), "\n".join([f"Details in {out}", *failed_jobs]))
        print("notified" if shown else "no desktop notification available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
