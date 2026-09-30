"""Reading and writing task records: front matter, the Task record, and field and history updates.

Moved unchanged from tasks.py. tasks.py imports these names back, so everything that uses tasks sees
the same names.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))?$")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


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

    def get(self, key: str) -> str | None:
        value = self.meta.get(key)
        if value in (None, "", []):
            return None
        return str(value)

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


def load_tasks(store: Path, folders: tuple[str, ...] = ("inbox", "open", "completed")) -> list[Task]:
    tasks: list[Task] = []
    for folder in folders:
        directory = store / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md" or path.name.startswith("_"):
                continue
            meta = parse_front_matter(path.read_text(encoding="utf-8"))
            tasks.append(Task(path=path, folder=folder, meta=meta or {}))
    return tasks


def _yaml_scalar(value: str) -> str:
    """A value that would change meaning as plain YAML is written quoted."""
    if re.search(r":\s|\s#|^[\[\]{}>|*&!%@`'\"-]", value) or value in ("null", "true", "false", ""):
        return json.dumps(value, ensure_ascii=False)
    return value


def find_task(store: Path, tid: str) -> Task:
    for task in load_tasks(store):
        if task.tid == tid:
            return task
    raise LookupError(f"no task {tid} in {store}")


def set_fields(text: str, fields: dict[str, str]) -> str:
    """Replace top-level front-matter scalars in place; keys not yet there are added at the end."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError("the record has no front matter")
    lines = match.group(1).splitlines()
    done: set[str] = set()
    for n, raw in enumerate(lines):
        key = raw.split(":", 1)[0].strip() if raw and not raw[0].isspace() and ":" in raw else None
        if key in fields:
            lines[n] = f"{key}: {_yaml_scalar(fields[key])}"
            done.add(key)
    lines += [f"{k}: {_yaml_scalar(v)}" for k, v in fields.items() if k not in done]
    return "---\n" + "\n".join(lines) + "\n---\n" + text[match.end():]


def add_history(text: str, entry: str) -> str:
    """Append one entry at the end of the History section (made when the record has none)."""
    found = re.search(r"^## History[ \t]*$", text, flags=re.M)
    if not found:
        return text.rstrip("\n") + f"\n\n## History\n\n{entry}\n"
    after = re.search(r"^## ", text[found.end():], flags=re.M)
    end = found.end() + after.start() if after else len(text)
    section = text[found.end():end].rstrip("\n")
    tail = text[end:]
    return text[:found.end()] + section + ("\n" if section.strip() else "\n\n") + entry + "\n" + ("\n" + tail if tail else "")
