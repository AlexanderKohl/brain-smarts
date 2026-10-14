"""Morning jobs: the commands the scheduled review runs after its own report, from the owner's config.

The owner lists them in /memory/skills/tasks/config/morning-jobs.json:

    {"jobs": [{"name": "example-page", "command": ["python", "library/skills/example/scripts/daily.py"],
               "timeout_s": 300, "needs": "what the job depends on, shown when it fails"}]}

Each job runs in order as a subprocess from the brain root, its output captured to
/temp/morning/<name>.log, and gets one line in the review's report: whether it ran, its exit code,
its seconds and the last line it printed. A missing or invalid config means no jobs and one line
that says so. A job that fails, times out or cannot start never stops the review or the jobs
after it; a timeout kills the job and every process it started. A command whose first word is
`python` or `python3` runs with the interpreter running the review, so the scheduler's PATH does
not choose it.

Imported by scheduled_review.py; standard library only.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CONFIG = "memory/skills/tasks/config/morning-jobs.json"
LOG_DIR = "temp/morning"
# A job's name is its log file name: letters, digits, dot, dash and underscore only.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_TIMEOUT_S = 24 * 60 * 60
COLLECT_AFTER_KILL_S = 10
LAST_LINE_CHARS = 200
PYTHON_WORDS = ("python", "python3")


@dataclass
class Job:
    name: str
    command: list[str]
    timeout_s: int
    needs: str | None = None


@dataclass
class Result:
    """What one job did. `ran` means its process started; `exit_code` is None when it did not
    finish on its own (timed out) or never started."""

    name: str
    ran: bool
    exit_code: int | None
    seconds: float
    last_line: str
    timed_out: bool = False
    needs: str | None = None

    @property
    def failed(self) -> bool:
        return not self.ran or self.timed_out or self.exit_code != 0

    def line(self) -> str:
        """One line for the report and, when the job failed, for the notification."""
        if self.timed_out:
            state = f"timed out after {self.seconds:.0f} s, killed"
        elif self.ran:
            state = f"ran, exit {self.exit_code}, {self.seconds:.1f} s"
        else:
            state = "not started"
        text = f"- {self.name}: {state} – {self.last_line}"
        if self.failed and self.needs:
            text += f" (needs: {self.needs})"
        return text


def _job(index: int, item: object, seen: set[str]) -> Job | str:
    """A Job from one config entry, or the one line that says what is wrong with it."""
    where = f"job {index + 1}"
    if not isinstance(item, dict):
        return f"{where} must be an object"
    name = item.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        return f'{where}: "name" must match {NAME.pattern}'
    where = f'job "{name}"'
    if name in seen:
        return f"{where} is listed twice"
    command = item.get("command")
    if (not isinstance(command, list) or not command
            or not all(isinstance(word, str) and word for word in command)):
        return f'{where}: "command" must be a non-empty list of strings'
    timeout_s = item.get("timeout_s")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or not 0 < timeout_s <= MAX_TIMEOUT_S:
        return f'{where}: "timeout_s" must be a whole number of seconds between 1 and {MAX_TIMEOUT_S}'
    needs = item.get("needs")
    if needs is not None and not isinstance(needs, str):
        return f'{where}: "needs" must be text'
    seen.add(name)
    return Job(name, list(command), timeout_s, needs or None)


def load_jobs(root: Path, config: Path | None = None) -> tuple[list[Job], str | None]:
    """The jobs the config lists, or no jobs and the one line that says why."""
    path = config or root / CONFIG
    shown = "/" + path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    if not path.is_file():
        return [], f"no morning jobs: {shown} not found"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], f"no morning jobs: {shown} is not valid JSON ({exc})"
    items = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return [], f'no morning jobs: {shown} must be an object with a "jobs" list'
    jobs: list[Job] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        job = _job(index, item, seen)
        if isinstance(job, str):
            return [], f"no morning jobs: {shown}: {job}"
        jobs.append(job)
    if not jobs:
        return [], f"no morning jobs: {shown} lists none"
    return jobs, None


def _text(value: object) -> str:
    """Captured output as text, whether it came back as text, bytes or nothing."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _last_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    last = lines[-1]
    return last if len(last) <= LAST_LINE_CHARS else last[:LAST_LINE_CHARS - 1] + "…"


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill the job and every process it started: a job's real work is often in a child of its
    own (a credential wrapper around a script), and a pipe held open by a survivor would block."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.kill()


def _start(command: list[str], root: Path, env: dict[str, str]) -> subprocess.Popen:
    # Its own process group (Windows) or session (POSIX), so a timeout can kill the whole tree.
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
             else {"start_new_session": True})
    return subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", **group)


def run_job(root: Path, job: Job, log_dir: Path) -> Result:
    """Run one job from the brain root, write its log, and say what happened; never raises."""
    command = [sys.executable, *job.command[1:]] if job.command[0] in PYTHON_WORDS else job.command
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    clock = time.monotonic()
    timed_out = False
    exit_code: int | None = None
    ran = True
    try:
        process = _start(command, root, env)
    except OSError as exc:
        # The command could not start: not found, not executable, a bad working directory.
        output, ran = f"{exc}\n", False
    else:
        try:
            output = _text(process.communicate(timeout=job.timeout_s)[0])
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            try:
                output = _text(process.communicate(timeout=COLLECT_AFTER_KILL_S)[0])
            except subprocess.TimeoutExpired:
                output = "(output not collected: a process the job started kept its output open)\n"
    seconds = time.monotonic() - clock
    result = Result(job.name, ran, exit_code, seconds, _last_line(output), timed_out, job.needs)
    ending = (f"timed out after {job.timeout_s} s, killed" if timed_out else
              f"exit {exit_code}" if ran else "not started")
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{job.name}.log").write_text(
        f"# morning job {job.name}\n# started {started}\n# command: {subprocess.list2cmdline(command)}\n\n"
        f"{output}\n# {ending} after {seconds:.1f} s\n", encoding="utf-8")
    return result


def run_jobs(root: Path, config: Path | None = None, log_dir: Path | None = None) -> tuple[list[Result], str | None]:
    """Every job in the config's order; a failure is reported in its line and the next job still runs."""
    jobs, problem = load_jobs(root, config)
    if problem:
        return [], problem
    folder = log_dir or root / LOG_DIR
    return [run_job(root, job, folder) for job in jobs], None


def report_lines(results: list[Result], problem: str | None) -> list[str]:
    """The lines of the review's Morning jobs section, in the order the jobs ran."""
    if problem:
        return [f"- {problem}"]
    return [f"Output of each job is in /{LOG_DIR}/<name>.log.", "", *(result.line() for result in results)]


def failures(results: list[Result]) -> list[Result]:
    return [result for result in results if result.failed]


def reasons(results: list[Result]) -> list[str]:
    """Short reasons for the notification's title, one per failed job."""
    return [f"morning job {result.name} " + ("timed out" if result.timed_out else
                                             "failed" if result.ran else "did not start")
            for result in failures(results)]
