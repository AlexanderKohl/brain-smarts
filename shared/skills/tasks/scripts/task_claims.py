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
`<author>/<session>`, and a claim or release either reaches origin at once or is not made
(task_claim_sync.py); a memory store belongs to one owner and keeps the bare session name. A
holder written before the prefix existed (a bare name in a repository store) belongs to the
author whose History entry made the claim. Only its own author releases a live claim.

The six hours are counted from the holder's own clock, as written in `claimed_at`, against the
reader's clock: a computer whose clock is wrong by hours shortens or lengthens its own claims.
    cleared(task)                      the fields `done` clears when a held card completes
    warnings(task, where)              what `tasks.py check` says about a card's claim
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import task_claim_sync
import task_state
import task_stores
from task_history import brain_author
from task_records import Task
from task_write import change, locate, stamp

TEAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
CLAIM_HOURS = 6


def _when(value) -> datetime.datetime | None:
    """An ISO 8601 stamp as an aware time; one without an offset is read in this computer's
    zone, as the boards read it (team_lanes.parse_stamp), so both say the same thing."""
    try:
        found = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.astimezone()


def _claimed_by_author(task: Task) -> str | None:
    """The author of the History entry that made the card's present claim, lowercased."""
    holder = task.get("claimed_by")
    try:
        text = task.path.read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.findall(r"^- \S+ \S (\S+): claimed by " + re.escape(str(holder)) + r"\b", text, re.M)
    return found[-1].lower() if found else None


def own(task: Task, author: str) -> bool:
    """True when this brain's author holds the card: by the prefix, or, for a bare name written
    before the prefix existed, by the History entry that made the claim."""
    holder = str(task.get("claimed_by") or "")
    if not holder:
        return False
    if "/" in holder:
        return holder.startswith(author + "/")
    return _claimed_by_author(task) == author.lower()


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


def _shared(store, offline: bool) -> bool:
    return store.kind == "repository" and not offline


def _settle_first(store, offline: bool) -> list[str]:
    """Refuse a shared change the checkout is not ready for, before the card is read; an earlier
    change of this tool's that was never confirmed is published first (task_claim_sync.ready)."""
    if not _shared(store, offline):
        return []
    return task_claim_sync.ready(store, lambda: task_state.write(store))


def _publish(root: Path, store, task: Task, target: Path, subject: str, offline: bool, holder: str | None) -> list[str]:
    """Send the change to origin, or undo it and raise (task_claim_sync). `holder` is who the
    card must still name once origin is merged in: the claimant, or nobody after a release."""
    if not _shared(store, offline):
        return ["offline: only this computer sees this change until it is committed and pushed"] if offline and store.kind == "repository" else []

    def still_ours() -> bool:
        return task_stores.find(root, task.tid).get("claimed_by") == holder

    return task_claim_sync.publish(store, [target, task.path, store.path / "STATE.md"], subject,
                                   rebuild=lambda: task_state.write(store), still_ours=still_ours)


def held_by_others(root: Path, at: str | None = None) -> list[str]:
    """One line per card another brain holds in a repository store, live claims first by time,
    then lapsed ones: what a session reads before it picks work."""
    author = brain_author(root)
    live, old = [], []
    for task in task_stores.load_all(root):
        holder, store = task.get("claimed_by"), task.store
        if not holder or store is None or store.kind != "repository" or own(task, author):
            continue
        since = task.get("claimed_at") or "an unknown time"
        key = (_when(since) or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc), task.tid)
        if lapsed(task, at):
            old.append((key, f"{task.tid} ({store.repository}): claim of {holder} lapsed, since {since}; free to take"))
        else:
            end = lapses_at(task)
            until = f", until {end.isoformat(timespec='minutes')}" if end else ""
            live.append((key, f"{task.tid} ({store.repository}): held by {holder} since {since}{until}"))
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
    settled = _settle_first(home, offline)
    if _shared(home, offline):      # the checkout may just have taken in origin: always read the card again
        root, task = locate(store, tid)
        if task.folder == "completed":
            raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    author = brain_author(root)
    bare, by = by, holder_name(home, author, by)
    at, _ = stamp(root, now)
    holder = task.get("claimed_by")
    took = ""
    renewing = holder == by or (holder == bare and home.kind == "repository" and own(task, author))
    if holder and not renewing:
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
    said = settled + said + _publish(root, home, task, target, f"Claim {tid} by {by}", offline, by)
    return target, [f"claimed {tid} by {by}: {target}"] + said


def release(store: Path, tid: str, note: str | None = None, now: str | None = None,
            offline: bool = False) -> tuple[Path, list[str]]:
    """The holder lets a card go: claimed_by and claimed_at cleared, status ready, an attributed
    History entry, and STATE.md regenerated. The team stays, so the card remains in its lane.
    In a repository store a live claim is released only by the author who holds it; a lapsed
    one by anyone."""
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    home = task.store or task_stores.owner_store(root)
    settled = _settle_first(home, offline)
    if _shared(home, offline):      # the checkout may just have taken in origin: always read the card again
        root, task = locate(store, tid)
        if task.folder == "completed":
            raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    holder = task.get("claimed_by")
    at, _ = stamp(root, now)
    if holder and home.kind == "repository" and not own(task, brain_author(root)) and not lapsed(task, at):
        end = lapses_at(task)
        raise ValueError(f"{tid} is held by {holder}, and only its holder releases a live claim"
                         + (f"; it lapses at {end.isoformat(timespec='minutes')}" if end else ""))
    fields: dict[str, str | None] = {"status": "ready", "claimed_by": None, "claimed_at": None}
    what = ("released by " + holder if holder else "released, no session held it") + " (ready)"
    target, said = change(root, task, fields, what, note=note, folder="open", now=at, offline=offline)
    said = settled + said + _publish(root, home, task, target, f"Release {tid}", offline, None)
    return target, [f"released {tid}: {target}"] + said
