"""Events: the append-only record of what each person decided, and the fold that derives state.

A board shared between two brains (CONTRACT section 16.2) is a set of files that never clash:

- every card and every event is one file named `<author>-<UTC stamp>` (`ann-20260105T090000Z`),
  the author being `owner_short_name` from that brain's `/memory/OWNER.md`, lowercased; two
  saves by one author in one second get `-2`, `-3`. Two authors cannot produce one name.
- an event under `<board>/events/` is written once and never edited, moved or deleted;
  "applied" is not a place a file is moved to, it is a fact each brain derives.
- the card states, the `closed` register and the page are **derived** by `fold`, which reads the
  whole event log on every build, so both brains compute one answer whatever order the files
  arrived in. Events sort by `(saved_at, author, file name)`; cards by `(created, author)`.

Kinds, each naming `card`, `by`, `saved_at`, the card signature and `seen_through`:
`accept`, `reject`, `defer`, `amend`, `released`, `resolve`.

When both act on one card, **the earliest event decides**; a later event with a different
outcome does not change the state but marks the card `conflict` until a `resolve` names every
conflicting event id and the outcome. A same-outcome duplicate is not a conflict: it is drawn
as "also accepted by <author>".

An outcome applies while the card still carries the signature it was decided against. Once
the card's author acts on it (sets it building again after a reject, say) the signature moves
on and the old event no longer overlays the card.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cards  # noqa: E402

SCHEMA = "owner-board/events/v1"
OUTCOMES = ("accept", "reject", "defer")
KINDS = OUTCOMES + ("amend", "released", "resolve")
ENVIRONMENTS = ("testing", "production")
STALE = "pull, rebuild, decide again"

ID_RE = re.compile(r"^([a-z0-9]+)-(\d{8}T\d{6}Z)(?:-(\d+))?$")


# ---------------------------------------------------------------- ids and time

def author_of(name: str) -> str:
    """An author id from an owner's short name: lowercase letters and digits only."""
    author = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if not author:
        raise ValueError("owner_short_name in /memory/OWNER.md is needed to name cards and events")
    return author


def utc(value: str | datetime.datetime | None = None) -> datetime.datetime:
    """A moment as an aware UTC datetime, to the second; now when nothing is given."""
    if value is None:
        moment = datetime.datetime.now(datetime.timezone.utc)
    elif isinstance(value, datetime.datetime):
        moment = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        moment = datetime.datetime.fromisoformat(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
    return moment.astimezone(datetime.timezone.utc).replace(microsecond=0)


def stamp(moment: datetime.datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def iso(moment: datetime.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(author: str, moment: datetime.datetime, taken) -> str:
    """`<author>-<stamp>`, then `-2`, `-3` while a name is taken. `taken` is a container of ids."""
    base = author_of(author) + "-" + stamp(moment)
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = base + "-" + str(n)
    return candidate


def parse_id(event_id: str) -> tuple[str, str, int]:
    found = ID_RE.match(str(event_id or ""))
    if not found:
        raise ValueError("not an author-prefixed UTC id: " + str(event_id))
    return found.group(1), found.group(2), int(found.group(3) or 1)


# ---------------------------------------------------------------- files

def folder(board: dict) -> str:
    return os.path.join(str(board["folder"]), "events")


def ids_in(board: dict) -> set:
    path = folder(board)
    if not os.path.isdir(path):
        return set()
    return {name[:-5] for name in os.listdir(path) if name.endswith(".json")}


def read_all(board: dict) -> list:
    """Every event file, in the one order both brains agree on. An unreadable file raises."""
    path = folder(board)
    out = []
    if not os.path.isdir(path):
        return out
    for name in sorted(os.listdir(path)):
        if not name.endswith(".json"):
            continue
        full = os.path.join(path, name)
        try:
            event = json.loads(Path(full).read_text(encoding="utf-8"))
        except Exception as err:
            raise ValueError("event " + full + " cannot be read: " + str(err)) from err
        event.setdefault("id", name[:-5])
        if event.get("id") != name[:-5]:
            raise ValueError("event " + full + " carries id " + str(event.get("id")) + ", not its file name")
        out.append(event)
    return sorted(out, key=order_key)


def order_key(event: dict) -> tuple:
    return (str(event.get("saved_at") or ""), str(event.get("by") or ""), str(event.get("id") or ""))


def write(board: dict, event: dict, dry_run: bool = False) -> str:
    """Write one event under its own id. Refuses to overwrite: an event is never edited."""
    for key in ("id", "kind", "by", "saved_at"):
        if not event.get(key):
            raise ValueError("an event needs " + key)
    if event["kind"] not in KINDS:
        raise ValueError("unknown event kind " + str(event["kind"]))
    event = dict(event, schema=SCHEMA)
    path = os.path.join(folder(board), event["id"] + ".json")
    if os.path.exists(path):
        raise FileExistsError("event " + event["id"] + " already exists and is never rewritten")
    if not dry_run:
        os.makedirs(folder(board), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(event, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def make(board: dict, kind: str, by: str, saved_at=None, taken=None, **fields) -> dict:
    """A new event record with its id and schema, not yet written."""
    moment = utc(saved_at)
    taken = set(taken if taken is not None else ids_in(board))
    event = {"id": new_id(by, moment, taken), "schema": SCHEMA, "kind": kind, "by": author_of(by),
             "saved_at": iso(moment)}
    event.update({k: v for k, v in fields.items() if v is not None})
    return event


# ---------------------------------------------------------------- the fold

def version_key(version: str) -> tuple:
    """Three-number versions in their order; anything else after them, as text."""
    found = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return (0, *map(int, found.groups())) if found else (1, str(version or ""))


def _applies(event: dict, item: dict) -> bool:
    """An outcome taken against the card as it was: its signature matches, or none was kept."""
    return not event.get("sig") or not item.get("sig") or event["sig"] == item["sig"]


def fold(items: list, events: list) -> dict:
    """Derive the state of every card from the event log.

    Returns `{"items": [open cards with overlays], "closed": {version: title}, "retired": [cards],
    "conflicts": [cards in conflict], "last_event": id or ""}`. Each open card gains:
    `events` (its events, in order), `last_event`, `decided` (`{kind, by, at, id}` or None),
    `also_by`, `conflict` (the competing events, when any), `fold` (`conflict`, `released` or
    ``), `amendments`, `released_to` ({env: version}), and for a reject the owner's words as
    `sent_back` and `sent_back_images` when the card file does not carry them yet.
    """
    by_card: dict = {}
    for event in events:
        by_card.setdefault(event.get("card"), []).append(event)
    closed: dict = {}
    # Closed versions recorded without a card: a register carried over from before the move.
    for event in by_card.get(None, []):
        if event.get("kind") in ("accept", "released") and event.get("version"):
            closed.setdefault(event["version"], event.get("title") or "")
    open_items, retired, conflicts = [], [], []
    for item in items:
        mine = by_card.get(item["id"], [])
        item["events"] = mine
        item["last_event"] = mine[-1]["id"] if mine else ""
        item["amendments"] = [e for e in mine if e.get("kind") == "amend"]
        item["released_to"] = {}
        for e in mine:
            if e.get("kind") == "released" and e.get("env") in ENVIRONMENTS:
                item["released_to"][e["env"]] = e.get("version") or ""
        decided, also, competing = _decide(item, mine)
        item["decided"] = decided
        item["also_by"] = also
        item["conflict"] = competing
        item["fold"] = "conflict" if competing else ("released" if item["released_to"] else "")
        if competing:
            # Both are kept and the card stays in play, in the Conflict fold, until resolved;
            # only a file already moved to cards/closed/ stays closed.
            conflicts.append(item)
        settled = not competing and ((decided and decided["kind"] == "accept") or "production" in item["released_to"])
        if item.get("closed") or settled:
            if item.get("version"):
                closed.setdefault(item["version"], (item.get("title") or "")[:80])
            retired.append(item)
            continue
        if decided and decided["kind"] == "reject":
            item["state"] = "rework"
            if not item.get("sent_back"):
                item["sent_back"] = decided.get("why") or "Sent back with no reason given."
                item["sent_back_images"] = list(decided.get("shots") or [])
        elif decided and decided["kind"] == "defer":
            item["deferred"] = decided
        open_items.append(item)
    last = events[-1]["id"] if events else ""
    return {"items": open_items, "closed": closed, "retired": retired, "conflicts": conflicts, "last_event": last}


def _decide(item: dict, mine: list) -> tuple:
    """(the deciding event as `{kind, by, at, id, why, shots}`, also-by authors, competing events)."""
    outcomes = [e for e in mine if e.get("kind") in OUTCOMES and _applies(e, item)]
    if not outcomes:
        return None, [], []
    first = outcomes[0]
    competing = [e for e in outcomes[1:] if e.get("kind") != first.get("kind")]
    winner = first
    if competing:
        named = {first["id"]} | {e["id"] for e in competing}
        for e in mine:
            if e.get("kind") == "resolve" and named <= set(e.get("resolves") or []) and e.get("outcome") in OUTCOMES:
                winner = dict(e, kind=e["outcome"])
                competing = []
                break
    also = sorted({e["by"] for e in outcomes if e.get("kind") == winner.get("kind") and e["by"] != winner["by"]
                   and e is not winner})
    decided = {"kind": winner["kind"], "by": winner["by"], "at": winner.get("saved_at"), "id": winner["id"],
               "why": winner.get("why") or "", "shots": winner.get("shots") or []}
    return decided, also, competing


def state(board: dict, data: dict | None = None) -> dict:
    """The derived board: `board.json`, the open cards with their overlays, `closed`, `retired`,
    `conflicts` and `last_event`, from the card files and the whole event log."""
    data = data if data is not None else cards.load(board)
    folded = fold(data["items"], read_all(board))
    out = dict(data)
    out.update(folded)
    return out


def conflicting_ids(item: dict) -> list:
    """Every event id a `resolve` on this card must name: the deciding one and each competitor."""
    if not item.get("conflict"):
        return []
    return [item["decided"]["id"]] + [e["id"] for e in item["conflict"]]


def check_fences(item: dict | None, event: dict) -> str | None:
    """Why an event may not be written: the card is gone, changed, or decided against a stale
    page. Returns the reason, or None when it may."""
    if item is None:
        return "no card with that id any more"
    if event.get("kind") in OUTCOMES + ("amend",) and event.get("sig") and item.get("sig") and event["sig"] != item["sig"]:
        return "the card changed after the verdict was given"
    if "seen_through" in event and (event.get("seen_through") or "") != (item.get("last_event") or ""):
        return "decided from a page that had not seen " + (item.get("last_event") or "the latest event") + ": " + STALE
    if event.get("kind") == "resolve":
        needed = set(conflicting_ids(item))
        if not needed:
            return "nothing to resolve on this card"
        if not needed <= set(event.get("resolves") or []):
            return "a resolve must name every conflicting event: " + ", ".join(sorted(needed))
        if event.get("outcome") not in OUTCOMES:
            return "a resolve needs an outcome: " + ", ".join(OUTCOMES)
    return None
