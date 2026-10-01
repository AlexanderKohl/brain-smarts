"""Claiming and releasing task cards between team threads (see /shared/schemas/task-schema.md).

Several conductor threads (teams) can pull cards from one board. A card's `team` names the
thread that works it; `claimed_by` and `claimed_at` say which session holds it and since when.
The two are set together when the card enters `in_progress` and cleared together when it leaves.

    claim(store, tid, by, team=None)   status in_progress, claimed_by, claimed_at from the clock
    release(store, tid)                claimed_by and claimed_at cleared, status ready
    cleared(task)                      the fields `done` clears when a held card completes
    warnings(task, where)              what `tasks.py check` says about a card's claim

tasks.py wires these into its CLI and imports this module; the few helpers taken from tasks.py
(the clock, the History line, the STATE.md write) are imported lazily to avoid a cycle.
"""

from __future__ import annotations

import re
from pathlib import Path

from state_table import state_update
from task_records import Task, add_history, find_task, set_fields

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


def _move_to_open(store: Path, task: Task, text: str) -> Path:
    target = store / "open" / task.path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    if target != task.path:
        task.path.unlink()
    return target


def claim(store: Path, tid: str, by: str, team: str | None = None, note: str | None = None,
          now: str | None = None) -> tuple[Path, list[str]]:
    """A session takes a card: status in_progress, claimed_by and claimed_at (the clock) set
    together, a History line, and the STATE.md row refreshed. Refused while another session
    holds the card; claiming again by the same session only renews the time."""
    import tasks  # lazy: tasks.py imports this module

    by = (by or "").strip()
    if not by:
        raise ValueError("claim needs --by, the session name of the thread taking the card")
    task = find_task(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    holder = task.get("claimed_by")
    if holder and holder != by:
        raise ValueError(f"{tid} is held by {holder} since {task.get('claimed_at') or 'an unknown time'}; "
                         f"it must be released first")
    stamp, said = tasks._stamp(store, now)
    fields: dict[str, str | None] = {"status": "in_progress", "claimed_by": by, "claimed_at": stamp,
                                     "updated": stamp}
    if team:
        fields["team"] = check_team(team)
    label = fields.get("team") or task.get("team")
    what = f"Claimed by {by}" + (f" for team {label}" if label else "") + " (in_progress)."
    text = add_history(set_fields(task.path.read_text(encoding="utf-8"), fields), tasks._entry(stamp, what, note, []))
    target = _move_to_open(store, task, text)
    said.append(f"claimed {tid} by {by}: {target}")
    row = dict(task.meta, id=tid, status="in_progress", title=task.get("title") or tid)
    if tasks._write_state(store, lambda t: state_update(t, row)) is not None:
        said.append(f"STATE.md: row for {tid} is in_progress")
    return target, said


def release(store: Path, tid: str, note: str | None = None, now: str | None = None) -> tuple[Path, list[str]]:
    """The holder lets a card go: claimed_by and claimed_at cleared, status ready, a History line,
    and the STATE.md row refreshed. The team stays, so the card remains in its lane."""
    import tasks  # lazy: tasks.py imports this module

    task = find_task(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    stamp, said = tasks._stamp(store, now)
    holder = task.get("claimed_by")
    fields: dict[str, str | None] = {"status": "ready", "claimed_by": None, "claimed_at": None, "updated": stamp}
    what = ("Released by " + holder if holder else "Released, no session held it") + " (ready)."
    text = add_history(set_fields(task.path.read_text(encoding="utf-8"), fields), tasks._entry(stamp, what, note, []))
    target = _move_to_open(store, task, text)
    said.append(f"released {tid}: {target}")
    row = dict(task.meta, id=tid, status="ready", title=task.get("title") or tid)
    if tasks._write_state(store, lambda t: state_update(t, row)) is not None:
        said.append(f"STATE.md: row for {tid} is ready")
    return target, said
