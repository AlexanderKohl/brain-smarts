"""Attributed History entries and the one writer of a change to a task record (P23).

Every change to a record, in every store, sets `updated` and appends one entry with the same
timestamp:

    - <timestamp> – <author>: <what changed>

`<timestamp>` is ISO 8601 with seconds and an offset (CONTRACT §8.2); `<author>` is the brain's
author name (below). Lines indented two spaces below an entry belong to it: a note kept verbatim,
screenshot links. An entry without an author is a legacy entry; it is read, never written.

    brain_author(root)   this brain's author name, from owner_short_name in /memory/OWNER.md
    owner_now(root)      the current time in the owner's timezone (OWNER.md `timezone`)
    entries(text)        every entry under `## History`, legacy ones included
    newest_attributed    the newest attributed entry, by timestamp
    entry(...)           one entry, with its indented lines
    apply_change(...)    set fields, set `updated`, append the entry: the one writer of a change
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python before 3.9
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]

from task_records import add_history, parse_front_matter, set_fields

STAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})"
ENTRY_RE = re.compile(rf"^- (?P<at>{STAMP}) – (?P<author>[a-z][a-z0-9-]{{0,31}}): (?P<what>\S.*)$")
LEGACY_RE = re.compile(rf"^- (?P<at>{STAMP}|\d{{4}}-\d{{2}}-\d{{2}})(?: – |: | - )(?P<what>.*)$")
AUTHOR_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
PROFILE = Path("memory") / "OWNER.md"


@dataclass(frozen=True)
class Entry:
    at: datetime
    author: str | None     # None: a legacy entry
    what: str
    line: int              # 1-based line number in the record


def author_name(value: str) -> str:
    """A name as an author name: lower case, every run of other characters one hyphen."""
    name = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    if name and not name[0].isalpha():
        name = "a-" + name
    return name[:32].rstrip("-")


def _profile(root: Path) -> dict:
    path = root / PROFILE
    if not path.is_file():
        return {}
    return parse_front_matter(path.read_text(encoding="utf-8")) or {}


def brain_author(root: Path) -> str:
    """This brain's author name. Raises when the profile has none, and every write then refuses."""
    raw = _profile(root).get("owner_short_name")
    name = author_name(raw) if raw and raw != "OWNER_SHORT_NAME" else ""
    if not AUTHOR_RE.match(name):
        raise ValueError(f"no owner_short_name in {(root / PROFILE).as_posix()}: a task change names its "
                         "author, so nothing is written until the owner profile has one")
    return name


def owner_now(root: Path) -> tuple[str, str | None]:
    """The current time in the owner's timezone (OWNER.md `timezone`), and a note when it is not.

    `timezone` holds an IANA name, optionally followed by its offsets, for example
    `Europe/Example (+01:00)`. Without a zone database for that name, the machine's zone is
    used; the note says so when the machine's offset is not one of the listed offsets.
    """
    machine = datetime.now().astimezone().replace(microsecond=0)
    value = str(_profile(root).get("timezone") or "").strip()
    name = value.split("(")[0].strip()
    if not name or name == "IANA_ZONE":
        return machine.isoformat(), None
    if name in ("UTC", "Etc/UTC", "GMT", "Etc/GMT"):
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat(), None
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(name)).replace(microsecond=0).isoformat(), None
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    offsets = re.findall(r"[+-]\d{2}:\d{2}", value)
    offset = machine.isoformat()[-6:]
    if offset in offsets:
        return machine.isoformat(), None
    return machine.isoformat(), (f"timestamp: {name} from OWNER.md cannot be resolved here (no zone "
                                 f"database; `python -m pip install tzdata` adds one), so the "
                                 f"machine's zone {offset} was used")


def parse_stamp(value: str) -> datetime | None:
    """A timestamp or a date as an aware datetime (a bare date is midnight UTC); None otherwise."""
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def entries(text: str) -> list[Entry]:
    """Every entry under `## History`, in file order; legacy entries carry author None."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^## History[ \t]*$", line)), None)
    if start is None:
        return []
    found: list[Entry] = []
    for n in range(start + 1, len(lines)):
        line = lines[n]
        if line.startswith("## "):
            break
        match = ENTRY_RE.match(line)
        author = match.group("author") if match else None
        match = match or LEGACY_RE.match(line)
        at = parse_stamp(match.group("at")) if match else None
        if match and at is not None:
            found.append(Entry(at=at, author=author, what=match.group("what"), line=n + 1))
    return found


def newest_attributed(text: str) -> Entry | None:
    """The attributed entry with the latest timestamp (the last of equals), or None."""
    attributed = [e for e in entries(text) if e.author]
    return max(attributed, key=lambda e: (e.at, e.line)) if attributed else None


def entry(at: str, author: str, what: str, note: str | None = None, images: list[str] | tuple = ()) -> str:
    """One History entry: what changed, then the note verbatim and the screenshot links."""
    if not AUTHOR_RE.match(author or ""):
        raise ValueError(f"author {author!r} is not an author name")
    if not re.fullmatch(STAMP, at or ""):
        raise ValueError(f"timestamp {at!r} is not ISO 8601 with seconds and an offset")
    what = " ".join(str(what).split())
    parts = [f"- {at} – {author}: {what}"]
    text = (note or "").strip()
    if text:
        parts.append("  Note: " + text.replace("\r\n", "\n").replace("\n", "\n  "))
    for n, rel in enumerate(images, 1):
        parts.append(f"  ![Screenshot {n}](../{rel})")
    return "\n".join(parts)


def apply_change(text: str, fields: dict, what: str, author: str, at: str,
                 note: str | None = None, images: list[str] | tuple = (),
                 after: dict[str, str] | None = None) -> str:
    """Set the fields, set `updated` to `at`, and append the entry with the same `at`."""
    line = entry(at, author, what, note, images)
    return add_history(set_fields(text, dict(fields, updated=at), after=after), line)
