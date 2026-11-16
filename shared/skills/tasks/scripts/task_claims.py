"""Claiming and releasing task cards between team threads (see /shared/schemas/task-schema.md).

Several conductor threads (teams) can pull cards from one board. A card's `team` names the
thread that works it; `claimed_by` and `claimed_at` say which session holds it and since when.
The two are set together when the card enters `in_progress` and cleared together when it leaves.
A card is found in any store (task_stores.find) and changed through task_write.change, so a
claim in a repository is attributed, fetched first and committed on its own by the conductor.

    claim(store, tid, by, team=None)   status in_progress, claimed_by, claimed_at from the clock
    release(store, tid)                claimed_by and claimed_at cleared, status ready
    lapsed(task, at)                   the claim is older than CLAIM_HOURS and no longer holds the card
    held_by_others(root, at)           live and lapsed claims of other brains, for session start

A claim holds a card for CLAIM_HOURS (6). The holder renews it by claiming again; after that
time another session may take the card over, and the History says whose lapsed claim it took. In
a repository store, which several people's brains share, the holder is written as
`<author>/<session>`, and the claim is committed and pushed at once (task_claim_sync.py) so the
others see it; a memory store belongs to one owner and keeps the bare session name.
    cleared(task)                      the fields `done` clears when a held card completes
    warnings(task, where)              what `tasks.py check` says about a card's claim
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import task_claim_sync
import task_stores
from task_history import brain_author
from task_records import Task
from task_write import change, locate, stamp

TEAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
CLAIM_HOURS = 6


def _when(value) -> datetime.datetime | None:
    """An ISO 8601 stamp as an aware time; one without an offset is read as UTC."""
    try:
        found = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=datetime.timezone.utc)


def lapses_at(task: Task) -> datetime.datetime | None:
    start = _when(task.get("claimed_at")) if task.get("claimed_by") else None
    return start + datetime.timedelta(hours=CLAIM_HOURS) if start else None


def lapsed(task: Task, at: str | datetime.datetime | None = None) -> bool:
    """True when the card's claim is older than CLAIM_HOURS at `at` (default: now). A claim
    without a readable time never lapses on its own; `check` already warns about it."""
    end = lapses_at(task)
    now = at if isinstance(at, datetime.datetime) else _when(at) if at else None
    return bool(end and (now or datetime.datetime.now(datetime.timezone.utc)) >= end)


def holder_name(store, author: str, by: str) -> str:
    """How a holder is written: `<author>/<session>` where several brains read the card."""
    if store.kind != "repository" or by.startswith(author + "/"):
        return by
    return f"{author}/{by}"


def _publish(store, task: Task, target: Path, subject: str, offline: bool) -> list[str]:
    if store.kind != "repository" or offline:
        return []
    return task_claim_sync.publish(store, [target, task.path, store.path / "STATE.md"], subject)


def held_by_others(root: Path, at: str | None = None) -> list[str]:
    """One line per card another brain holds in a repository store, live claims first by time,
    then lapsed ones: what a session reads before it picks work."""
    author = brain_author(root)
    live, old = [], []
    for task in task_stores.load_all(root):
        holder, store = task.get("claimed_by"), task.store
        if not holder or store is None or store.kind != "repository" or str(holder).startswith(author + "/"):
            continue
        since = task.get("claimed_at") or "an unknown time"
        if lapsed(task, at):
            old.append((str(since), f"{task.tid} ({store.repository}): claim of {holder} lapsed, since {since}; free to take"))
        else:
            end = lapses_at(task)
            until = f", until {end.isoformat(timespec='minutes')}" if end else ""
            live.append((str(since), f"{task.tid} ({store.repository}): held by {holder} since {since}{until}"))
    return [line for _, line in sorted(live)] + [line for _, line in sorted(old)]


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
    if status == "in_progress" and by and lapsed(task):
        out.append(f"{where}: the claim of {by} lapsed (older than {CLAIM_HOURS} h): claim again to renew it, or release it")
    team = task.get("team")
    if team and not TEAM_RE.match(team):
        out.append(f"{where}: team {team} is not a short lowercase label")
    return out


def claim(store: Path, tid: str, by: str, team: str | None = None, note: str | None = None,
          now: str | None = None, offline: bool = False) -> tuple[Path, list[str]]:
    """A session takes a card: status in_progress, claimed_by and claimed_at (the clock) set
    together, an attributed History entry, and STATE.md regenerated. Refused while another
    session's claim is live; a lapsed claim is taken over; claiming again by the same session
    renews the time. In a repository store the claim is committed and pushed at once."""
    by = (by or "").strip()
    if not by:
        raise ValueError("claim needs --by, the session name of the thread taking the card")
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    home = task.store or task_stores.owner_store(root)
    by = holder_name(home, brain_author(root), by)
    at, _ = stamp(root, now)
    holder = task.get("claimed_by")
    took = ""
    if holder and holder != by:
        if not lapsed(task, at):
            end = lapses_at(task)
            raise ValueError(f"{tid} is held by {holder} since {task.get('claimed_at') or 'an unknown time'}; it must "
                             "be released first" + (f", or lapses at {end.isoformat(timespec='minutes')}" if end else ""))
        took = f", taking over the lapsed claim of {holder}"
    fields: dict[str, str | None] = {"status": "in_progress", "claimed_by": by, "claimed_at": at}
    if team:
        fields["team"] = check_team(team)
    label = fields.get("team") or task.get("team")
    what = f"claimed by {by}" + (f" for team {label}" if label else "") + took + " (in_progress)"
    target, said = change(root, task, fields, what, note=note, folder="open", now=at, offline=offline)
    said += _publish(home, task, target, f"Claim {tid} by {by}", offline)
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
    said += _publish(task.store or task_stores.owner_store(root), task, target, f"Release {tid}", offline)
    return target, [f"released {tid}: {target}"] + said
