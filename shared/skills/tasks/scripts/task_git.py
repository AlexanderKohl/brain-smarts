"""Conflict detection and fetch-before-write for task stores (P23, P25).

    conflicted(text)                 a line beginning `<<<<<<< ` or `>>>>>>> `
    unmerged_paths(checkout, inside) paths Git reports as unmerged below `inside`
    ready_to_write(store, ...)       raises WriteRefused with the reason and the fixing command

A repository store is written only when its checkout is on the store branch, `git fetch origin
<branch>` succeeded, the checkout is not behind origin, and nothing in brain/tasks/ is unmerged.
A failed fetch refuses unless `offline` is passed, which an agent does only after the owner
agrees (SMART-RULE-0034); offline skips the fetch and compares with what was fetched last.
Memory stores are not fetched: they are written in a session copy (SMART-RULE-0038). Every store
refuses a record that carries a conflict marker.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MARKER_RE = re.compile(r"^(<<<<<<< |>>>>>>> )", re.M)
UNMERGED = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})
GIT_TIMEOUT_S = 120


class WriteRefused(ValueError):
    """A task write that must not happen yet; the message names the reason and the fix."""


def conflicted(text: str) -> bool:
    return bool(MARKER_RE.search(text or ""))


def _git(checkout: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_S)


def unmerged_paths(checkout: Path, inside: Path) -> list[Path]:
    """Unmerged paths below `inside`, from `git status --porcelain` (DD AU UD UA DU AA UU)."""
    done = _git(checkout, "status", "--porcelain", "--untracked-files=no", "--", str(inside))
    if done.returncode != 0:
        raise WriteRefused(f"git status failed in {checkout.as_posix()}: {done.stderr.strip()}")
    found = []
    for line in done.stdout.splitlines():
        if line[:2] in UNMERGED:
            found.append(checkout / line[3:].strip().strip('"'))
    return sorted(found)


def ready_to_write(store, offline: bool = False, record: Path | None = None) -> list[str]:
    """Raise WriteRefused unless the store may be written now; returns notes to show."""
    notes: list[str] = []
    if not store.reachable:
        raise WriteRefused(f"{store.label} cannot be written: {store.reason}")
    if record is not None and record.is_file() and conflicted(record.read_text(encoding="utf-8")):
        raise WriteRefused(f"{record.as_posix()} has a Git conflict marker: resolve it by hand, keeping the "
                           "History entries of both sides in time order (P23), then try again")
    if store.kind != "repository":
        return notes
    checkout, branch, fix = store.checkout, store.branch, f"git -C {store.checkout.as_posix()}"
    if not branch:
        raise WriteRefused(f"{store.label}: no store branch is named (brain/JOINING.md working_branch, "
                           "else the pointer's default_branch)")
    current = _git(checkout, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode != 0 or current.stdout.strip() != branch:
        raise WriteRefused(f"{store.label}: the checkout is on {current.stdout.strip() or 'no branch'}, not the "
                           f"store branch {branch}; run `{fix} switch {branch}`")
    if offline:
        notes.append(f"{store.label}: offline, not fetched; compared with origin/{branch} as last fetched")
    else:
        fetched = _git(checkout, "fetch", "origin", branch)
        if fetched.returncode != 0:
            raise WriteRefused(f"{store.label}: `{fix} fetch origin {branch}` failed ({fetched.stderr.strip()}); "
                               "fix the connection, or pass --offline once the owner agrees")
    stuck = unmerged_paths(checkout, store.path)
    if stuck:
        raise WriteRefused(f"{store.label}: unmerged in Git: " + ", ".join(p.as_posix() for p in stuck)
                           + "; resolve them by hand (P23), then run `tasks.py state --store " + store.label + "`")
    behind = _git(checkout, "rev-list", "--count", f"HEAD..origin/{branch}")
    if behind.returncode == 0 and behind.stdout.strip() not in ("", "0"):
        raise WriteRefused(f"{store.label}: the checkout is {behind.stdout.strip()} commit(s) behind origin/{branch}; "
                           f"run `{fix} pull --ff-only` first")
    return notes
