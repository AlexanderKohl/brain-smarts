"""Claiming and releasing task cards between team threads (see /shared/schemas/task-schema.md).

Several conductor threads (teams) can pull cards from one board. A card's `team` names the
thread that works it; `claimed_by` and `claimed_at` say which session holds it and since when.
The two are set together when the card enters `in_progress` and cleared together when it leaves.
A card is found in any store (task_stores.find) and changed through task_write.change, so a
claim in a repository is attributed, fetched first and committed on its own by the conductor.

    claim(store, tid, by, team=None)   status in_progress, claimed_by, claimed_at from the clock
    release(store, tid)                claimed_by and claimed_at cleared, status ready
    cleared(task)                      the fields `done` clears when a held card completes
    warnings(task, where)              what `tasks.py check` says about a card's claim
"""

from __future__ import annotations

import re
from pathlib import Path

from task_records import Task
from task_write import change, locate, stamp

TEAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def check_team(label: str) -> str:
    """A team label is short and lowercase: letters, digits and hyphens, up to 32 characters."""
    label = (label or "").strip()
    if not TEAM_RE.match(label):
        raise ValueError(f"team {label!r} is not a short lowercase label (letters, digits, hyphens)")
    return label


def cleared(task: Task) -> dict[str, None]:
    """The claim fields to clear on a card that holds one; nothing on a card that never had them."""
    return {key: None for key in ("claimed_by", "claimed_at") if task.get(key)}


def warnings(task: Task, where: str) -> list[str]:
    """A claim that does not fit the status: said, never an error (the record is still a task)."""
    status, by, at = task.get("status"), task.get("claimed_by"), task.get("claimed_at")
    out = []
    if by and status != "in_progress":
        out.append(f"{where}: claimed_by {by} on a card that is {status or 'without a status'}, not in_progress")
    if status == "in_progress" and by and not at:
        out.append(f"{where}: claimed_by {by} without claimed_at")
    if at and not by:
        out.append(f"{where}: claimed_at without claimed_by")
    team = task.get("team")
    if team and not TEAM_RE.match(team):
        out.append(f"{where}: team {team} is not a short lowercase label")
    return out


def claim(store: Path, tid: str, by: str, team: str | None = None, note: str | None = None,
          now: str | None = None, offline: bool = False) -> tuple[Path, list[str]]:
    """A session takes a card: status in_progress, claimed_by and claimed_at (the clock) set
    together, an attributed History entry, and STATE.md regenerated. Refused while another
    session holds the card; claiming again by the same session only renews the time."""
    by = (by or "").strip()
    if not by:
        raise ValueError("claim needs --by, the session name of the thread taking the card")
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    holder = task.get("claimed_by")
    if holder and holder != by:
        raise ValueError(f"{tid} is held by {holder} since {task.get('claimed_at') or 'an unknown time'}; "
                         f"it must be released first")
    at, _ = stamp(root, now)
    fields: dict[str, str | None] = {"status": "in_progress", "claimed_by": by, "claimed_at": at}
    if team:
        fields["team"] = check_team(team)
    label = fields.get("team") or task.get("team")
    what = f"claimed by {by}" + (f" for team {label}" if label else "") + " (in_progress)"
    target, said = change(root, task, fields, what, note=note, folder="open", now=at, offline=offline)
    return target, [f"claimed {tid} by {by}: {target}"] + said


def release(store: Path, tid: str, note: str | None = None, now: str | None = None,
            offline: bool = False) -> tuple[Path, list[str]]:
    """The holder lets a card go: claimed_by and claimed_at cleared, status ready, an attributed
    History entry, and STATE.md regenerated. The team stays, so the card remains in its lane."""
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    holder = task.get("claimed_by")
    fields: dict[str, str | None] = {"status": "ready", "claimed_by": None, "claimed_at": None}
    what = ("released by " + holder if holder else "released, no session held it") + " (ready)"
    target, said = change(root, task, fields, what, note=note, folder="open", now=now, offline=offline)
    return target, [f"released {tid}: {target}"] + said
