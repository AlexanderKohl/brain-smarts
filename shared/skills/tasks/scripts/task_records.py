"""Reading and writing task records: identifiers, front matter, the Task record, field and
History updates, and the one atomic file write every task command uses.

tasks.py imports these names back, so everything that uses tasks sees the same names. The
identifier patterns here are the one definition (SMART-RULE-0018): the owner board, the
reconciliation and the preflight import `ID_RE` and `ID_IN_TEXT` instead of keeping their own.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))?$")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

# A new task is TASK-<author>-YYYY-NNNN; a legacy TASK-YYYY-NNNN keeps its form wherever it moves.
ID_RE = re.compile(r"^TASK-(?:(?P<author>[a-z][a-z0-9-]{0,31})-)?(?P<year>\d{4})-(?P<number>\d{4})$")
ID_IN_TEXT = re.compile(r"\bTASK-(?:[a-z][a-z0-9-]{0,31}-)?\d{4}-\d{4}\b")

STORE_FOLDERS = ("inbox", "open", "recurring", "completed")
OPEN_STATUSES = frozenset({"ready", "in_progress", "waiting", "scheduled", "blocked"})
FOLDER_STATUSES = {
    "inbox": {"inbox"},
    "open": set(OPEN_STATUSES),
    "recurring": set(OPEN_STATUSES),
    "completed": {"completed", "cancelled"},
}
CONFLICT_RE = re.compile(r"^(<<<<<<< |>>>>>>> )", re.M)


def parse_id(tid: str) -> tuple[str | None, int, int] | None:
    """(author, or None for a legacy identifier, year, number); None when it is no task id."""
    match = ID_RE.match(tid or "")
    if not match:
        return None
    return match.group("author"), int(match.group("year")), int(match.group("number"))


def id_sort_key(tid: str) -> tuple:
    """Year, legacy identifiers first, then author, then number; anything else sorts last."""
    parsed = parse_id(tid)
    if parsed is None:
        return (9999, 2, "", 0, tid)
    author, year, number = parsed
    return (year, 0 if author is None else 1, author or "", number, tid)


def parse_front_matter(text: str) -> dict[str, Any] | None:
    """Top-level scalars of brain front matter; block lists are kept as lists."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None
    result: dict[str, Any] = {}
    list_key: str | None = None
    for raw in match.group(1).splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and list_key is not None:
            result[list_key].append(stripped[2:].strip().strip("'\""))
            continue
        if line[0].isspace() or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if value == "":
            result[key] = []
            list_key = key
            continue
        list_key = None
        if value in ("null", "~"):
            result[key] = None
        elif value == "[]":
            result[key] = []
        else:
            result[key] = value.strip("'\"")
    return result


@dataclass
class Task:
    path: Path
    folder: str
    meta: dict[str, Any]
    store: Any = None            # the task_stores.Store that holds it; None for a lone store
    problem: str | None = None   # "unreadable: ..." or "conflicted: resolve by hand"

    def get(self, key: str) -> str | None:
        value = self.meta.get(key)
        if value in (None, "", []):
            return None
        return str(value)

    def refs(self, key: str = "project_refs") -> list[str]:
        value = self.meta.get(key)
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        return [str(value)] if value not in (None, "") else []

    @property
    def tid(self) -> str:
        return self.get("id") or self.path.stem

    def day(self, key: str) -> date | None:
        value = self.get(key)
        match = DATE_RE.match(value) if value else None
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None


def load_tasks(store: Path, folders: tuple[str, ...] = STORE_FOLDERS, owner: Any = None) -> list[Task]:
    """Every record in the store's folders. An unreadable record is kept with its problem, so a
    caller reports it by path while the rest load; a conflicted one is flagged the same way."""
    tasks: list[Task] = []
    for folder in folders:
        directory = store / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md" or path.name.startswith("_"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                tasks.append(Task(path=path, folder=folder, meta={}, store=owner, problem=f"unreadable: {err}"))
                continue
            problem = "conflicted: resolve by hand" if CONFLICT_RE.search(text) else None
            tasks.append(Task(path=path, folder=folder, meta=parse_front_matter(text) or {}, store=owner,
                              problem=problem))
    return tasks


def _yaml_scalar(value: str) -> str:
    """A value that would change meaning as plain YAML is written quoted."""
    if re.search(r":\s|\s#|^[\[\]{}>|*&!%@`'\"-]", value) or value in ("null", "true", "false", ""):
        return json.dumps(value, ensure_ascii=False)
    return value


def find_task(store: Path, tid: str) -> Task:
    """A task in one store (task_stores.find looks in every store)."""
    for task in load_tasks(store):
        if task.tid == tid:
            return task
    raise LookupError(f"no task {tid} in {store}")


def _scalar_or_null(value: str | None) -> str:
    return "null" if value is None else _yaml_scalar(value)


def _field_lines(key: str, value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [f"{key}: []"] if not value else [f"{key}:"] + [f"  - {_yaml_scalar(str(v))}" for v in value]
    return [f"{key}: {_scalar_or_null(value)}"]


def set_fields(text: str, fields: dict[str, Any], after: dict[str, str] | None = None) -> str:
    """Replace top-level front-matter fields in place; a list value is written as a block list.

    A key not yet there goes after the key `after` names for it, when that key is present, else
    at the end. A value of None writes a bare `null` (a cleared field), where the text "null"
    would be quoted."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError("the record has no front matter")
    out: list[str] = []
    done: set[str] = set()
    skipping = False
    for raw in match.group(1).splitlines():
        key = raw.split(":", 1)[0].strip() if raw and not raw[0].isspace() and ":" in raw else None
        if key is None and skipping and raw.lstrip().startswith("- "):
            continue
        skipping = False
        if key in fields:
            out += _field_lines(key, fields[key])
            done.add(key)
            skipping = True
            continue
        out.append(raw)
    for key, value in fields.items():
        if key in done:
            continue
        anchor = (after or {}).get(key)
        at = next((i for i, line in enumerate(out) if anchor and line.split(":", 1)[0] == anchor), None)
        if at is None:
            out += _field_lines(key, value)
            continue
        at += 1
        while at < len(out) and out[at].startswith("  - "):
            at += 1
        out[at:at] = _field_lines(key, value)
    return "---\n" + "\n".join(out) + "\n---\n" + text[match.end():]


def merge_sections(text: str, section: str = "History") -> str:
    """One `## <section>` per record: the contents of a second or later heading of that name are
    moved, in file order, to the end of the first, so a new entry goes after every older one and
    a reader of the section sees them all. Text without a repeated heading is returned unchanged."""
    found = list(re.finditer(rf"^## {re.escape(section)}[ \t]*$", text, flags=re.M))
    if len(found) < 2:
        return text
    spans = []
    for match in found:
        after = re.search(r"^## ", text[match.end():], flags=re.M)
        end = match.end() + after.start() if after else len(text)
        spans.append((match.start(), end, text[match.end():end].strip("\n")))
    kept, cursor = [], 0
    for start, end, _ in spans[1:]:
        kept.append(text[cursor:start])
        cursor = end
    stripped = "".join(kept) + text[cursor:]
    first_start, first_end, _ = spans[0]      # before every removed span, so its offsets still hold
    extra = "\n".join(body for _, _, body in spans[1:] if body)
    merged = stripped[first_start:first_end].rstrip("\n") + ("\n" + extra if extra else "") + "\n"
    tail = stripped[first_end:].lstrip("\n")
    return (stripped[:first_start] + merged + ("\n" + tail if tail.strip() else "")).rstrip("\n") + "\n"


def add_history(text: str, entry: str, section: str = "History") -> str:
    """Append one entry at the end of the History section (made when the record has none)."""
    text = merge_sections(text, section)
    found = re.search(rf"^## {re.escape(section)}[ \t]*$", text, flags=re.M)
    if not found:
        return text.rstrip("\n") + f"\n\n## {section}\n\n{entry}\n"
    after = re.search(r"^## ", text[found.end():], flags=re.M)
    end = found.end() + after.start() if after else len(text)
    section = text[found.end():end].rstrip("\n")
    tail = text[end:]
    return text[:found.end()] + section + ("\n" if section.strip() else "\n\n") + entry + "\n" + ("\n" + tail if tail else "")


def write_atomic(path: Path, text: str) -> None:
    """Write through a temporary file in the same folder and os.replace, so a reader never sees
    half a record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def move_record(source: Path, target: Path, text: str) -> Path:
    """Write the record at its target first, then remove the source. A failure between the two
    leaves two copies, which task_stores.find and the preflight both report by path."""
    write_atomic(target, text)
    if target.resolve() != source.resolve():
        source.unlink()
    return target


def slugify(title: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0]
    return slug or "task"
