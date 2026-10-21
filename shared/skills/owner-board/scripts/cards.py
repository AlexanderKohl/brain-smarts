"""One card, one file – and every board is derived from them and the events.

A card is the record of one thing the owner asked for: a Markdown file under
`<board>/cards/<id>.md` whose front matter the repository validator checks like any other
record. Its id is `<author>-<UTC stamp>` (`events.new_id`), and its body is edited only by its
author; another author who wants a change saves an `amend` event. What belongs to the board
rather than to one card – the tracks and their parent tasks, the `production` branch, the
release-notes projects the board draws, abandoned branches, identifiers links are built from –
is `<board>/board.json`, edited by hand and rarely. A retired card is moved to
`<board>/cards/closed/` by the author of the event that retired it.

The card states, the `closed` register and the page are derived (`events.fold`) and written to
`<board>/state.json`, which is generated on every build and never merged or edited.

    data = cards.load(board)      # board.json plus every card, open and closed, signed
    cards.write(board, card)      # create or update a single card

Loading is tolerant of field order and strict about nothing else: a card that cannot be
parsed raises rather than being skipped, because a card that vanishes quietly is the failure
this machinery exists to end.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from pathlib import Path

# The order a card's front matter is written in: identity first, then where the card sits on
# the board, then when it moved, then where the owner goes to look. `author` and
# `release_note` follow alphabetically with any other key (`/shared/schemas/card-schema.md`).
FIELD_ORDER = [
    "id", "title", "type", "schema_version", "contract", "parent",
    "created", "updated", "owner",
    "track", "state", "version", "branch", "increment",
    "asked", "startedAt",
    "area", "where_text", "where_view", "where_href", "image",
]

# Front matter keys that are record metadata rather than card content; rebuilt on every write.
META = {"type", "schema_version", "contract", "parent", "title"}

# Fields that are genuinely lists. Any other empty value is an empty string.
LIST_FIELDS = {"area"}

# What a person edits by hand in board.json. Anything derived is refused there (check 9).
BOARD_KEYS = ("id", "label", "tracks", "production", "release_notes", "abandoned", "elsewhere")
DERIVED_KEYS = ("closed", "generated", "mainVersion")

# A screenshot the owner pasted when sending a card back is an image line in that section.
SHOT_LINE = re.compile(r"^!\[[^\]]*\]\(([^)\s]+)\)\s*$", re.M)

SCALARS = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
SENT_BACK = re.compile(r"^## (?:.+ )?sent it back\s*\n(.*?)(?=\n## |\Z)", re.S | re.M | re.I)


def cards_folder(board: dict) -> str:
    return os.path.join(str(board["folder"]), "cards")


def closed_folder(board: dict) -> str:
    return os.path.join(cards_folder(board), "closed")


def board_file(board: dict) -> str:
    return os.path.join(str(board["folder"]), "board.json")


def state_file(board: dict) -> str:
    return os.path.join(str(board["folder"]), "state.json")


def sent_back_heading(board: dict) -> str:
    return (board.get("owner") or "The owner") + " sent it back"


def _now() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _stamp(value) -> str:
    """A date written as `2026-09-17`, promoted to a timestamp the validator accepts."""
    text = str(value or "")
    if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", text):
        local = datetime.datetime.now().astimezone().tzinfo
        return datetime.datetime.fromisoformat(text).replace(tzinfo=local).isoformat()
    return text or _now()


def sign(data: dict) -> dict:
    """Give each card a signature over what a reader would notice.

    The page remembers a verdict as handed over until the signature changes, and
    `apply_events.py` refuses an event whose signature no longer matches the card. `area` and
    `increment` are left out: moving a card between workers does not make a verdict stale.
    """
    for item in data["items"]:
        parts = [
            item.get("state", "") or "", item.get("version") or "", item.get("title", "") or "",
            item.get("landed", "") or "", item.get("review", "") or "", (item.get("image") or "")[:64],
        ]
        item["sig"] = hashlib.sha256(chr(0).join(parts).encode("utf-8")).hexdigest()[:12]
    return data


def parse(text: str) -> dict:
    """Front matter plus the body sections, as one flat dict."""
    if not text.startswith("---"):
        raise ValueError("no front matter")
    end = text.index("\n---", 3)
    head, body = text[3:end], text[end + 4:]
    out: dict = {}
    key = None
    for line in head.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and key:
            out.setdefault(key, []).append(line[4:].strip())
            continue
        found = SCALARS.match(line)
        if not found:
            continue
        key, value = found.group(1), found.group(2).strip()
        if value == "[]":
            value = ""
        if value == "":
            # A bare `key:` is a list about to be indented under it or an empty field; which
            # one is only known once the whole block has been read.
            out[key] = []
        elif value == "null":
            out[key] = None
        else:
            out[key] = value.strip('"')
    # An empty list is not an empty string: in the page's JSON `[]` is truthy, so a
    # `where_href: []` would render as a link to nowhere.
    for key, value in list(out.items()):
        if value == [] and key not in LIST_FIELDS:
            out[key] = ""
    for name, field in (("What landed", "landed"), ("To check", "review")):
        found = re.search(r"^## " + name + r"\s*\n(.*?)(?=\n## |\Z)", body, re.S | re.M)
        out[field] = " ".join(found.group(1).split()) if found else ""
    found = SENT_BACK.search(body)
    said = found.group(1) if found else ""
    out["sent_back_images"] = SHOT_LINE.findall(said)
    out["sent_back"] = " ".join(SHOT_LINE.sub("", said).split())
    return out


def _card_from_file(path: str) -> dict:
    try:
        raw = parse(Path(path).read_text(encoding="utf-8"))
    except Exception as err:
        raise ValueError("card " + path + " cannot be read: " + str(err)) from err
    card = {k: v for k, v in raw.items() if k not in META}
    card["title"] = raw.get("title", "")
    # Compare the whole record: `where` has three parts, and a reader that forgot `view` once
    # cost every card built from it its link.
    card["where"] = {"text": raw.get("where_text", ""), "href": raw.get("where_href", ""),
                     "view": raw.get("where_view", "")}
    for gone in ("where_text", "where_href", "where_view"):
        card.pop(gone, None)
    if isinstance(card.get("area"), str):
        card["area"] = [card["area"]]
    card.setdefault("area", [])
    if not card.get("author"):
        card["author"] = str(card.get("id", "")).split("-", 1)[0]
    return card


def _dump(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        # An empty list is a bare key, never the two characters `[]`, which read back as the
        # string "[]" and would not be recognised as empty anywhere downstream.
        return "\n" + "\n".join("  - " + str(v) for v in value) if value else ""
    text = str(value)
    if text == "":
        return ""
    return '"' + text + '"' if (":" in text or text.startswith(("[", "{", "*", "&", "#"))) else text


def write(board: dict, card: dict, closed: bool = False) -> str:
    """Write one card to its own file, creating the folder if it is not there yet."""
    target = closed_folder(board) if closed or card.get("closed") else cards_folder(board)
    os.makedirs(target, exist_ok=True)
    where = card.get("where") or {}
    flat = dict(card)
    for derived in ("where", "sig", "closed", "events", "last_event", "decided", "also_by", "conflict",
                    "fold", "amendments", "released_to", "deferred"):
        flat.pop(derived, None)
    flat["where_text"] = where.get("text", "")
    flat["where_view"] = where.get("view", "")
    flat["where_href"] = where.get("href", "")
    flat["type"] = "board_card"
    flat["schema_version"] = "0.2"
    flat["contract"] = "/CONTRACT.md"
    flat["parent"] = board.get("card_parent") or board.get("node") or ""
    flat["owner"] = board.get("owner") or "brain-owner"
    flat["author"] = flat.get("author") or str(card["id"]).split("-", 1)[0]
    # `created` is the moment the owner asked and is kept for the life of the card; `updated`
    # moves on every write. The validator requires both.
    flat["created"] = flat.get("created") or _stamp(flat.get("startedAt") or flat.get("asked"))
    flat["updated"] = _now()
    landed = flat.pop("landed", "")
    review = flat.pop("review", "")
    sent_back = flat.pop("sent_back", "")
    shots = flat.pop("sent_back_images", None) or []
    for name, value in (("landed", landed), ("review", review), ("sent_back", sent_back)):
        if not isinstance(value, str):
            raise TypeError("card %s: %s must be text, not %s - a trailing comma makes a tuple"
                            % (card["id"], name, type(value).__name__))

    lines = ["---"]
    for key in FIELD_ORDER + sorted(k for k in flat if k not in FIELD_ORDER):
        if key in flat:
            dumped = _dump(flat[key])
            lines.append(key + ":" + ("" if dumped.startswith("\n") else " ") + dumped)
    lines += ["---", "", "# " + str(card.get("title", card["id"])), "",
              "## What landed", "", landed or "Not landed yet.", "",
              "## To check", "", review or "Not landed yet.", ""]
    # The owner's words, verbatim and under their own heading: a reason folded into the
    # conductor's text stops being the owner's.
    if sent_back:
        lines += ["## " + sent_back_heading(board), "", sent_back, ""]
        lines += ["![Screenshot " + str(n) + "](" + rel + ")" for n, rel in enumerate(shots, 1)]
        if shots:
            lines.append("")
    path = os.path.join(target, card["id"] + ".md")
    # Render fully before opening: opening with "w" truncates, so a failure while rendering
    # must happen before anything on disk has changed.
    text = "\n".join(str(line) for line in lines)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def read_board(board: dict) -> dict:
    """`board.json`: what a person keeps by hand. A board still on `board.md` is told to migrate."""
    path = board_file(board)
    if not os.path.isfile(path):
        old = os.path.join(str(board["folder"]), "board.md")
        hint = (" - it still has board.md: run migrate_board.py --board " + str(board.get("id", "")))\
            if os.path.isfile(old) else ""
        raise ValueError("no board.json at " + path + hint)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as err:
        raise ValueError(path + " is not valid JSON: " + str(err)) from err
    data.setdefault("tracks", {})
    return data


def write_board(board: dict, data: dict) -> str:
    path = board_file(board)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path


def load(board: dict) -> dict:
    """The board, assembled from `board.json` and every file under `cards/` and `cards/closed/`.

    Card order is `(created, author)`, the same on every machine, so a board read twice reads
    the same way and a card added today does not reshuffle yesterday's.
    """
    data = read_board(board)
    items = []
    for sub, closed in ((cards_folder(board), False), (closed_folder(board), True)):
        if not os.path.isdir(sub):
            continue
        for name in sorted(os.listdir(sub)):
            if name.endswith(".md"):
                card = _card_from_file(os.path.join(sub, name))
                card["closed"] = closed
                items.append(card)
    items.sort(key=lambda c: (str(c.get("created") or ""), str(c.get("author") or ""), str(c.get("id") or "")))
    data["items"] = items
    return sign(data)


def write_state(board: dict, state: dict) -> str:
    """The derived state, for a reader or a tool; regenerated on every build, never merged."""
    slim = {
        "board": board["id"],
        "generated": _now(),
        "last_event": state.get("last_event", ""),
        "closed": state.get("closed", {}),
        "items": [{k: item.get(k) for k in ("id", "author", "title", "state", "version", "branch", "track",
                                            "fold", "decided", "also_by", "last_event", "released_to", "sig")}
                  for item in state.get("items", [])],
        "conflicts": [item["id"] for item in state.get("conflicts", [])],
        "retired": [item["id"] for item in state.get("retired", [])],
        "adrift": state.get("adrift", []),
    }
    path = state_file(board)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(slim, indent=2, ensure_ascii=False) + "\n")
    return path
