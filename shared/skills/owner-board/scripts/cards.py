"""One card, one file – and every board is generated from them.

A card is the record of one thing the owner asked for: a Markdown file under
`<node>/status/cards/<id>.md` whose front matter the repository validator checks like any
other record. What belongs to the board rather than to one card (tracks and their parent
tasks, closed versions, abandoned branches, product identifiers used to build links) lives in
`<node>/status/board.md`, in its fenced JSON block.

There is no generated `status.json`: a generated copy of the truth is still a second list.

    data = cards.load(board)      # the shape build_status.py and reconcile.py want
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
# the board, then when it moved, then where the owner goes to look.
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

# A screenshot the owner pasted when sending a card back is an image line in that section.
SHOT_LINE = re.compile(r"^!\[[^\]]*\]\(([^)\s]+)\)\s*$", re.M)

SCALARS = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
SENT_BACK = re.compile(r"^## (?:.+ )?sent it back\s*\n(.*?)(?=\n## |\Z)", re.S | re.M | re.I)


def cards_folder(board: dict) -> str:
    return os.path.join(str(board["folder"]), "cards")


def board_file(board: dict) -> str:
    return os.path.join(str(board["folder"]), "board.md")


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
    `verdicts.py` refuses a verdict whose signature no longer matches the card. `area` and
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


def write(board: dict, card: dict) -> str:
    """Write one card to its own file, creating `cards/` if it is not there yet."""
    os.makedirs(cards_folder(board), exist_ok=True)
    where = card.get("where") or {}
    flat = dict(card)
    flat.pop("where", None)
    flat.pop("sig", None)
    flat["where_text"] = where.get("text", "")
    flat["where_view"] = where.get("view", "")
    flat["where_href"] = where.get("href", "")
    flat["type"] = "board_card"
    flat["schema_version"] = "0.2"
    flat["contract"] = "/CONTRACT.md"
    flat["parent"] = board.get("node") or ""
    flat["owner"] = board.get("owner") or "brain-owner"
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
    path = os.path.join(cards_folder(board), card["id"] + ".md")
    # Render fully before opening: opening with "w" truncates, so a failure while rendering
    # must happen before anything on disk has changed.
    text = "\n".join(str(line) for line in lines)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def read_board_json(board: dict) -> tuple[str, re.Match, dict]:
    text = Path(board_file(board)).read_text(encoding="utf-8")
    found = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not found:
        raise ValueError(board_file(board) + " has no fenced json block")
    return text, found, json.loads(found.group(1))


def load(board: dict) -> dict:
    """The board, assembled from `board.md` and every file under `cards/`.

    Card order is the order the owner asked for them – `asked`, then `id` – so a board read
    twice reads the same way and a card added today does not reshuffle yesterday's.
    """
    _, _, data = read_board_json(board)
    items = []
    folder = cards_folder(board)
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".md"):
                items.append(_card_from_file(os.path.join(folder, name)))
    items.sort(key=lambda c: (str(c.get("asked") or ""), str(c.get("id") or "")))
    data["items"] = items
    return sign(data)


def close_in_board(board: dict, version: str, title: str, dry: bool) -> None:
    """Record an accepted card's version under `closed` in `board.md`."""
    text, found, data = read_board_json(board)
    data.setdefault("closed", {})
    if version and version not in data["closed"]:
        data["closed"][version] = title
    if not dry:
        with open(board_file(board), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text[:found.start(1)] + json.dumps(data, indent=2, ensure_ascii=False) + text[found.end(1):])
