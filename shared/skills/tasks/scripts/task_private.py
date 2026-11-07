"""What never enters a repository: the companion file of a task, and the flags on private lines.

Privacy is a place, not a flag (CONTRACT §9, P10). An owner-private note about a task kept in a
repository lives in `/memory/tasks/private/<task id>.md`, which names the task and its store and
is never drawn into the repository. It is not a task record and is never loaded as one (it is
outside every store folder).

    companion_path(root, tid)   where the companion file of a task lives
    add_private(...)            create the companion file or append one entry to its `## Notes`
    flags(text, root)           why a text may be private: a /memory/ path, an amount, a contact
                                detail, a personal-data pattern, an owner term

`flags` reads its patterns and the owner's terms from the repository preflight's personal-data
check (`personal_data.PATTERNS`, `personal_data.owner_terms`), the one implementation of them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from task_history import entry
from task_records import _field_lines, add_history, parse_front_matter, set_fields, write_atomic

PREFLIGHT_SCRIPTS = Path(__file__).resolve().parents[2] / "repository-preflight" / "scripts"
MEMORY_PATH = re.compile(r"(?<![\w.])/memory/")
AMOUNT = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:AUD|EUR|GBP|NZD|USD)\b)")


def companion_path(root: Path, tid: str) -> Path:
    return root / "memory" / "tasks" / "private" / f"{tid}.md"


def add_private(root: Path, tid: str, store_label: str, author: str, at: str, what: str,
                lines: list[str] | None = None, memory_refs: list[str] | None = None) -> Path:
    """Append one attributed entry to the task's companion file, made on first use.

    `lines` are kept verbatim under the entry; `memory_refs` join the file's list once each."""
    path = companion_path(root, tid)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        known = (parse_front_matter(text) or {}).get("memory_refs") or []
        refs = list(known) + [r for r in (memory_refs or []) if r not in known]
        text = set_fields(text, {"updated": at, "memory_refs": refs, "store": store_label})
    else:
        front = ["---", f"id: {tid}-private", f"title: Private notes – {tid}", "type: task_private_note",
                 "schema_version: 0.2", "contract: /CONTRACT.md", "status: active", f"owner: {author}",
                 f"task: {tid}", f"store: {store_label}"]
        front += _field_lines("memory_refs", list(dict.fromkeys(memory_refs or [])))
        front += [f"created: {at}", f"updated: {at}", "---", "", f"# Private notes – {tid}", "",
                  f"The owner's private notes about `{tid}` in {store_label}. This file stays in memory and is "
                  "never drawn into the repository.", "", "## Notes", ""]
        text = "\n".join(front) + "\n"
    note = "\n".join(lines) if lines else None
    write_atomic(path, add_history(text, entry(at, author, what, note), section="Notes"))
    return path


def _personal_data():
    if str(PREFLIGHT_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(PREFLIGHT_SCRIPTS))
    import personal_data  # the repository preflight's one implementation of the patterns
    return personal_data


def flags(text: str, root: Path, terms: list[str] | None = None) -> list[str]:
    """The reasons, alphabetical, why this text may not belong in a repository."""
    found: set[str] = set()
    if MEMORY_PATH.search(text):
        found.add("/memory/ path")
    if AMOUNT.search(text):
        found.add("amount")
    try:
        personal = _personal_data()
    except ImportError:
        return sorted(found | {"personal-data check not installed"})
    for kind, pattern in personal.PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            if kind == "phone" and personal.not_a_phone(match.group(0)):
                continue
            found.add({"email": "contact detail", "phone": "contact detail"}.get(kind, kind))
    for term in personal.owner_terms(root) if terms is None else terms:
        name = term[len(personal.NAME):] if term.startswith(personal.NAME) else term
        flags_ = 0 if term.startswith(personal.NAME) else re.I
        if re.search(r"(?<![\w@.])" + re.escape(name) + r"(?![\w])", text, flags_):
            found.add("owner term")
            break
    return sorted(found)
