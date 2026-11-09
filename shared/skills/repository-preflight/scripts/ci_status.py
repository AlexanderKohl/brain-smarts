"""The latest GitHub Actions run of each repository's current branch, for the session-start hook.

A red build after a push once went unnoticed for three versions. At session start the hook asks
`gh run list --branch <branch> --limit 1` for each brain repository and for the project repository
of the session's working folder, and says one line per repository whose latest completed run
failed. It says nothing when the run passed, is still running, or there is none; nothing when `gh`
is not installed or not signed in, when the repository has no GitHub `origin`, or when a call does
not answer in time. It never raises: the hook must stay silent and fast when all is well.

  python shared/skills/repository-preflight/scripts/ci_status.py [<repository> ...]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Each gh call waits at most this long, and never past the hook's own deadline.
TIMEOUT_SECONDS = 8.0
FIELDS = "status,conclusion,workflowName,url,headSha"
FAILED = {"failure", "timed_out", "startup_failure"}
GITHUB = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def github_repository(repo: Path) -> str | None:
    """owner/name of the GitHub `origin`, read as configured (not rewritten by insteadOf)."""
    match = GITHUB.search(_git(repo, "config", "--get", "remote.origin.url"))
    return f"{match.group(1)}/{match.group(2)}" if match else None


def toplevel(folder: Path) -> Path | None:
    """The Git working tree that holds `folder`, or None."""
    if not folder.is_dir():
        return None
    top = _git(folder, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def latest_run(gh: str, repository: str, branch: str, timeout: float) -> dict | None:
    """The latest run as gh reports it, or None: no run, gh failed (not signed in) or too slow."""
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"}
    try:
        proc = subprocess.Popen([gh, "run", "list", "--repo", repository, "--branch", branch, "--limit", "1",
                                 "--json", FIELDS], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=env)
    except OSError:
        return None
    try:
        out, _ = proc.communicate(timeout=max(timeout, 0.1))
    except subprocess.TimeoutExpired:
        # Killed and left: waiting for its pipes again could outlast the budget (a wrapper's child).
        proc.kill()
        try:
            proc.wait(timeout=1)  # the process itself, not its pipes
        except subprocess.TimeoutExpired:
            pass
        return None
    if proc.returncode:
        return None
    try:
        runs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    return runs[0] if isinstance(runs, list) and runs and isinstance(runs[0], dict) else None


def failure_line(name: str, branch: str, run: dict | None, tips: set[str] | None = None) -> str | None:
    """One line for a failed completed run, or None. With `tips` (the local and upstream commits of the
    branch), a failure on an older commit is not reported: a repository whose checks moved off GitHub
    would otherwise repeat a stale failure at every session start."""
    if not run or run.get("status") != "completed" or run.get("conclusion") not in FAILED:
        return None
    if tips and str(run.get("headSha") or "") not in tips:
        return None
    sha = str(run.get("headSha") or "")[:7] or "?"
    return (f"{name}: the latest CI run on {branch} failed – {run.get('workflowName') or 'workflow'} "
            f"at {sha}: {run.get('url') or '(no url)'}")


class Check:
    """The checks, started at once in the background; lines() collects what came back in time."""

    def __init__(self, repositories: list[tuple[str, Path]], deadline: float):
        self.deadline = deadline
        self.results: dict[int, str | None] = {}
        self.threads: list[threading.Thread] = []
        gh = shutil.which("gh")
        if not gh:
            return
        seen: set[Path] = set()
        for index, (name, repo) in enumerate(repositories):
            try:
                key = repo.resolve()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            thread = threading.Thread(target=self._one, args=(index, gh, name, repo), daemon=True)
            thread.start()
            self.threads.append(thread)

    def _one(self, index: int, gh: str, name: str, repo: Path) -> None:
        try:
            repository = github_repository(repo)
            branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
            if not repository or not branch or branch == "HEAD":
                return
            left = min(TIMEOUT_SECONDS, self.deadline - time.monotonic())
            if left <= 0:
                return
            tips = {_git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "@{u}")} - {""}
            self.results[index] = failure_line(name, branch, latest_run(gh, repository, branch, left), tips)
        except Exception:  # noqa: BLE001 – the hook stays silent on anything unexpected
            return

    def lines(self) -> list[str]:
        for thread in self.threads:
            thread.join(max(0.0, self.deadline - time.monotonic()))
        return [line for _index, line in sorted(self.results.copy().items()) if line]


def repositories(brain: list[tuple[str, Path]], cwd: str | None) -> list[tuple[str, Path]]:
    """The brain repositories, and the working folder's own repository when it is another one."""
    found = list(brain)
    if cwd:
        top = toplevel(Path(cwd))
        if top and all(top != repo.resolve() for _name, repo in brain):
            found.append((top.name, top))
    return found


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    repos = [(Path(a).resolve().name, Path(a).resolve()) for a in argv] or [(Path.cwd().name, Path.cwd())]
    lines = Check(repos, time.monotonic() + TIMEOUT_SECONDS + 2).lines()
    print("\n".join(lines) if lines else "no failed CI run found (or gh unavailable)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
