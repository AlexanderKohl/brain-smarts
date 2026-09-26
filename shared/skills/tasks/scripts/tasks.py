"""Task review and record checks for the task store (see /shared/skills/tasks/SKILL.md).

Commands:
    review   tasks that need attention today: inbox items, reviews due, deadlines near, blocked
    check    required fields, folder placement, identifier and date formats
    next-id  the next free TASK-YYYY-NNNN number
    new      create a task record from the store's template with the next number, add its
             STATE.md row, and refresh the owner board that shows it
    done     complete a task: status, History, move to completed/, STATE.md row out
    do-now   ask for a task now: priority high, status ready (unless in progress), History
    note     add the owner's note to a task's History

The store is `--tasks` (a repository-root path such as /memory/tasks, or an absolute path),
default /memory/tasks. Standard library only. `new`, `done`, `do-now` and `note` write: the
record, its STATE.md row (and the open-task count in that table's heading), screenshots under
<store>/img/, and (through /shared/skills/owner-board/scripts/task_board.py, when the owner board
is set up) the generated board pages. `complete`, `do_now` and `add_note` are also the functions
the owner board applies the owner's saved task actions through, so a task changes one way only.

Timestamps from `new` are in the owner's timezone, the IANA name in `timezone` in
/memory/OWNER.md. Python resolves that name only where the operating system or the `tzdata`
package supplies the zone database (Windows usually has neither); otherwise `new` stamps the
machine's zone and says so when its offset is not one OWNER.md lists.

Git Bash on Windows rewrites an argument that starts with `/` into a Windows path, so
`--project /memory/...` would arrive as `C:/Program Files/Git/memory/...`. `new` refuses such a
value; run the command with `MSYS_NO_PATHCONV=1` in front.

Status validity per record, `next_review` on waiting and scheduled tasks, and the
/memory/tasks/STATE.md listing are also enforced by /shared/skills/repository-preflight/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python before 3.9
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]

DEFAULT_STORE = "/memory/tasks"
FOLDER_STATUSES = {
    "inbox": {"inbox"},
    "open": {"ready", "in_progress", "waiting", "scheduled", "blocked"},
    "completed": {"completed", "cancelled"},
}
REQUIRED = ("id", "title", "type", "contract", "status", "owner", "created", "updated")
ID_RE = re.compile(r"^TASK-(\d{4})-(\d{4})$")
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


def brain_root(start: Path) -> Path | None:
    for parent in (start.resolve(), *start.resolve().parents):
        if (parent / "CONTRACT.md").is_file():
            return parent
    return None


MSYS_HINT = ("Git Bash rewrites an argument that starts with / into a Windows path; "
             "run the command with MSYS_NO_PATHCONV=1 in front")


def looks_path_converted(value: str) -> bool:
    """True for a repository-root path that Git Bash (MSYS) has turned into a Windows path."""
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) and (
        bool(os.environ.get("MSYSTEM")) or bool(re.search(r"[\\/]Git[\\/]", value, re.I)))


def check_project_ref(value: str, root: Path | None) -> None:
    """A --project value must be a repository-root path: /memory/..., or an existing /<path>."""
    if value.startswith("/memory/"):
        return
    if value.startswith("/") and root is not None and (root / value.strip("/")).exists():
        return
    hint = f" ({MSYS_HINT})" if looks_path_converted(value) else ""
    raise ValueError(f"--project {value} is not a repository-root path starting with /memory/{hint}")


def resolve_store(store: str | None, cwd: Path) -> Path:
    candidate = store or DEFAULT_STORE
    path = Path(candidate)
    if path.is_absolute() and path.exists():
        return path
    root = brain_root(cwd) or brain_root(Path(__file__).resolve().parent)
    if candidate.startswith("/") and root is not None:
        return root / candidate.lstrip("/")
    return (cwd / candidate).resolve()


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


# ---------------------------------------------------------------- review


def review(store: Path, today: date, horizon: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    limit = today + timedelta(days=horizon)
    for task in load_tasks(store, ("inbox", "open")):
        status = task.get("status") or "unknown"
        reasons: list[str] = []
        dates: list[date] = []
        if task.folder == "inbox" or status == "inbox":
            reasons.append("inbox: process it")
        next_review = task.day("next_review")
        if next_review and next_review <= today:
            reasons.append(f"review due {next_review.isoformat()}")
            dates.append(next_review)
        due = task.day("due")
        if due and due < today:
            reasons.append(f"overdue since {due.isoformat()}")
            dates.append(due)
        elif due and due <= limit:
            reasons.append(f"due {due.isoformat()}")
            dates.append(due)
        if status == "blocked":
            reasons.append("blocked")
        if status in {"waiting", "scheduled"} and not next_review:
            reasons.append("no next_review")
        if reasons:
            rows.append(
                {
                    "id": task.tid,
                    "status": status,
                    "priority": task.get("priority") or "",
                    "reasons": reasons,
                    "date": min(dates).isoformat() if dates else "",
                    "waiting_on": task.get("waiting_on") or "",
                    "title": task.get("title") or "",
                    "path": task.path.as_posix(),
                }
            )
    # Undated items (inbox, blocked) first, then earliest date, then id.
    return sorted(rows, key=lambda r: (r["date"] != "", r["date"], r["id"]))


# ---------------------------------------------------------------- check


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(store: Path) -> Report:
    report = Report()
    if not store.is_dir():
        report.errors.append(f"{store}: task store not found")
        return report
    for task in load_tasks(store):
        where = f"{task.folder}/{task.path.name}"
        if not task.meta:
            report.errors.append(f"{where}: missing front matter")
            continue
        missing = [key for key in REQUIRED if not task.get(key)]
        if missing:
            report.errors.append(f"{where}: missing {', '.join(missing)}")
        if task.get("type") not in (None, "task"):
            report.errors.append(f"{where}: type must be task")
        tid = task.get("id")
        if tid and not ID_RE.match(tid):
            report.errors.append(f"{where}: id {tid} is not TASK-YYYY-NNNN")
        elif tid and not task.path.stem.startswith(tid):
            report.errors.append(f"{where}: file name does not start with {tid}")
        status = task.get("status")
        if status and status not in FOLDER_STATUSES[task.folder]:
            allowed = ", ".join(sorted(FOLDER_STATUSES[task.folder]))
            report.errors.append(f"{where}: status {status} does not belong in {task.folder}/ ({allowed})")
        for key in ("due", "next_review"):
            if task.get(key) and task.day(key) is None:
                report.errors.append(f"{where}: {key} {task.get(key)} is not a date")
        if status == "waiting" and not task.get("waiting_on"):
            report.warnings.append(f"{where}: waiting without waiting_on")
        if not task.get("priority") and task.folder != "completed":
            report.warnings.append(f"{where}: no priority")
    return report


def next_id(store: Path, year: int) -> str:
    highest = 0
    for task in load_tasks(store):
        match = ID_RE.match(task.tid)
        if match and int(match.group(1)) == year:
            highest = max(highest, int(match.group(2)))
    return f"TASK-{year}-{highest + 1:04d}"


# ---------------------------------------------------------------- new

NEW_STATUSES = ("inbox", "ready", "in_progress", "waiting", "scheduled", "blocked")
TEMPLATE = Path("templates") / "TASK_TEMPLATE.md"
BOARD_SCRIPT = Path(__file__).resolve().parents[2] / "owner-board" / "scripts" / "task_board.py"  # a core sibling
PLACEHOLDER_OWNERS = {"", "OWNER_SHORT_NAME", "null"}


def slugify(title: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0]
    return slug or "task"


def _yaml_scalar(value: str) -> str:
    """A value that would change meaning as plain YAML is written quoted."""
    if re.search(r":\s|\s#|^[\[\]{}>|*&!%@`'\"-]", value) or value in ("null", "true", "false", ""):
        return json.dumps(value, ensure_ascii=False)
    return value


def _owner_default(store: Path, template_owner: str | None) -> str:
    if template_owner and template_owner not in PLACEHOLDER_OWNERS:
        return template_owner
    profile = store.parent / "OWNER.md"
    if profile.is_file():
        meta = parse_front_matter(profile.read_text(encoding="utf-8")) or {}
        if meta.get("owner_short_name"):
            return str(meta["owner_short_name"])
    return "brain-owner"


def render_new(template: str, fields: dict[str, Any]) -> str:
    """Fill the template's front matter and body. Keys the template lacks are added at the end."""
    match = FRONT_MATTER_RE.match(template)
    if not match:
        raise ValueError("the task template has no front matter")
    out: list[str] = []
    skipping = False
    done: set[str] = set()
    for raw in match.group(1).splitlines():
        key = raw.split(":", 1)[0].strip() if raw and not raw[0].isspace() and ":" in raw else None
        if key is None and skipping and raw.lstrip().startswith("- "):
            continue
        skipping = False
        if key in fields:
            value = fields[key]
            done.add(key)
            if isinstance(value, list):
                out.append(f"{key}:" + ("".join(f"\n  - {v}" for v in value) if value else " []"))
                skipping = True
            else:
                out.append(f"{key}: {'null' if value is None else _yaml_scalar(str(value))}")
            continue
        out.append(raw)
    for key, value in fields.items():
        if key not in done and not key.startswith("_") and not isinstance(value, list):
            out.append(f"{key}: {'null' if value is None else _yaml_scalar(str(value))}")
    body = template[match.end():]
    body = re.sub(r"^# .*$", lambda _: f"# {fields['title']}", body, count=1, flags=re.M)
    for heading, text in (("Outcome", fields.get("_outcome")), ("Next action", fields.get("_next_action"))):
        if not text:
            continue
        if re.search(rf"^## {heading}[ \t]*$", body, flags=re.M):
            body = re.sub(rf"^## {heading}[ \t]*\r?\n", lambda m: f"{m.group(0)}\n{text}\n", body, count=1, flags=re.M)
        elif re.search(r"^## History[ \t]*$", body, flags=re.M):
            body = re.sub(r"^## History", lambda m: f"## {heading}\n\n{text}\n\n{m.group(0)}", body, count=1, flags=re.M)
        else:
            body = body.rstrip("\n") + f"\n\n## {heading}\n\n{text}\n"
    history = f"- {fields['created']} – captured with `tasks.py new` ({fields['status']})."
    if re.search(r"^## History[ \t]*$", body, flags=re.M):
        body = re.sub(r"^## History[ \t]*\r?\n?", lambda m: f"## History\n\n{history}\n", body, count=1, flags=re.M)
    else:
        body = body.rstrip("\n") + f"\n\n## History\n\n{history}\n"
    front = "\n".join(line for line in out)
    return f"---\n{front}\n---\n{body}"


def _row_text(cells: list[str], fields: dict[str, Any]) -> str:
    """One STATE.md row, its cells in the order of the table's own header."""
    review = []
    if fields.get("next_review"):
        review.append(f"review {fields['next_review']}")
    if fields.get("waiting_on"):
        review.append(f"waiting on {fields['waiting_on']}")
    row = []
    for name in cells:
        if name == "task":
            row.append(f"`{fields['id']}`")
        elif name == "status":
            row.append(f"**{fields['status']}**")
        elif name == "priority":
            row.append(str(fields.get("priority") or "-"))
        elif "review" in name or "waiting" in name:
            row.append("; ".join(review) or "-")
        elif name == "title":
            row.append(str(fields["title"]))
        else:
            row.append("-")
    return "| " + " | ".join(cell.replace("|", "/") for cell in row) + " |"


def _recount(lines: list[str], header: int, end: int) -> None:
    """Set the count in the nearest `Open tasks (N` heading above a table to its row count."""
    rows = sum(1 for line in lines[header + 2:end] if line.lstrip().startswith("|"))
    for j in range(header - 1, -1, -1):
        if lines[j].startswith("#"):
            lines[j] = re.sub(r"^(#+ Open tasks \()\d+", lambda m: f"{m.group(1)}{rows}", lines[j], count=1)
            break


def _state_table(lines: list[str]) -> tuple[int, int, list[str]] | None:
    """The first `| Task | Status |` table: (header line, first line after it, header cells)."""
    for i, line in enumerate(lines):
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] != "task" or cells[1] != "status":
            continue
        end = i + 1
        while end < len(lines) and lines[end].lstrip().startswith("|"):
            end += 1
        return i, end, cells
    return None


def _row_index(lines: list[str], start: int, end: int, tid: str) -> int | None:
    for k in range(start, end):
        if lines[k].strip().strip("|").split("|")[0].strip().strip("`") == tid:
            return k
    return None


def state_remove(state_text: str, tid: str) -> tuple[str, bool]:
    """Remove a task's row from the STATE.md table and correct the open-task count above it."""
    lines = state_text.split("\n")
    found = _state_table(lines)
    if not found:
        return state_text, False
    i, end, _ = found
    k = _row_index(lines, i + 2, end, tid)
    if k is None:
        return state_text, False
    del lines[k]
    _recount(lines, i, end - 1)
    return "\n".join(lines), True


def state_update(state_text: str, fields: dict[str, Any]) -> tuple[str, bool]:
    """Rewrite a task's row in place (its status or priority changed); add it when missing."""
    lines = state_text.split("\n")
    found = _state_table(lines)
    if not found:
        return state_text, False
    i, end, cells = found
    k = _row_index(lines, i + 2, end, str(fields["id"]))
    if k is None:
        return state_row(state_text, fields)
    lines[k] = _row_text(cells, fields)
    return "\n".join(lines), True


def state_recently_completed(state_text: str, tid: str, title: str, day: str) -> tuple[str, bool]:
    """Put a line at the top of a `Recently completed` section (newest first), where one exists."""
    lines = state_text.split("\n")
    for i, line in enumerate(lines):
        if not re.match(r"^#+ Recently completed\b", line):
            continue
        at = i + 1
        while at < len(lines) and not lines[at].strip():
            at += 1
        entry = f"- `{tid}` {title} ({day})"
        if at >= len(lines) or not lines[at].lstrip().startswith("- "):
            lines[i + 1:at] = ["", entry, ""] if at < len(lines) else ["", entry]
        else:
            lines.insert(at, entry)
        return "\n".join(lines), True
    return state_text, False


def state_row(state_text: str, fields: dict[str, Any]) -> tuple[str, bool]:
    """Add the open task's row to the first table in STATE.md headed `| Task | Status |`.

    Cells follow that table's own header: Task, Status, Priority, a review or waiting column,
    Title; anything else gets `-`. The row goes at the end of the table: a new task has the
    highest number, and the table is ordered by number. The count in the nearest heading above
    the table (`## Open tasks (N, ...`) becomes the table's row count, and an older
    `Next free number:` line, where a store still keeps one, is moved on.
    """
    lines = state_text.split("\n")
    found = _state_table(lines)
    if found:
        i, end, cells = found
        lines.insert(end, _row_text(cells, fields))
        _recount(lines, i, end + 1)
        text = "\n".join(lines)
        if fields.get("_next_free"):
            text = re.sub(r"(Next free number: `)TASK-[0-9Y]{4}-\d{4}(`)",
                          lambda m: f"{m.group(1)}{fields['_next_free']}{m.group(2)}", text)
        return text, True
    return state_text, False


def owner_now(store: Path) -> tuple[str, str | None]:
    """The current time in the owner's timezone (OWNER.md `timezone`), and a note when it is not.

    `timezone` holds an IANA name, optionally followed by its offsets, for example
    `Australia/Brisbane (+10:00)`. Without a zone database for that name, the machine's zone is
    used; the note says so when the machine's offset is not one of the listed offsets.
    """
    machine = datetime.now().astimezone().replace(microsecond=0)
    profile = store.parent / "OWNER.md"
    meta = parse_front_matter(profile.read_text(encoding="utf-8")) if profile.is_file() else None
    value = str((meta or {}).get("timezone") or "").strip()
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


def create(store: Path, title: str, status: str = "inbox", priority: str = "normal",
           projects: list[str] | None = None, skills: list[str] | None = None,
           due: str | None = None, next_review: str | None = None, waiting_on: str | None = None,
           owner: str | None = None, slug: str | None = None, outcome: str | None = None,
           next_action: str | None = None, now: str | None = None, year: int | None = None,
           update_state: bool = True) -> tuple[Path, list[str]]:
    """Write one new task record and its STATE.md row. Returns the path and what was said."""
    if status not in NEW_STATUSES:
        raise ValueError(f"status {status} is not one of {', '.join(NEW_STATUSES)}")
    for key, value in (("due", due), ("next_review", next_review)):
        if value and not DATE_RE.match(value):
            raise ValueError(f"{key} {value} is not a date")
    if status in ("waiting", "scheduled") and not next_review:
        raise ValueError(f"a {status} task needs --next-review (CONTRACT §9.3)")
    if status == "waiting" and not waiting_on:
        raise ValueError("a waiting task needs --waiting-on")
    template_path = store / TEMPLATE
    if not template_path.is_file():
        raise ValueError(f"no task template at {template_path}")
    root = brain_root(store)
    for ref in projects or []:
        check_project_ref(ref, root)
    template = template_path.read_text(encoding="utf-8")
    note = None
    if now:
        stamp = now
    else:
        stamp, note = owner_now(store)
    tid = next_id(store, year or int(stamp[:4]))
    template_meta = parse_front_matter(template) or {}
    fields: dict[str, Any] = {
        "id": tid, "title": title, "status": status,
        "owner": owner or _owner_default(store, template_meta.get("owner")),
        "priority": priority, "created": stamp, "updated": stamp,
        "due": due, "next_review": next_review, "waiting_on": waiting_on,
        "project_refs": list(projects or []), "skill_refs": list(skills or []),
    }
    folder = "inbox" if status == "inbox" else "open"
    path = store / folder / f"{tid}-{slug or slugify(title)}.md"
    text = render_new(template, dict(fields, _outcome=outcome, _next_action=next_action))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    said = [f"created {tid}: {path}"] + ([note] if note else [])
    if folder == "open" and update_state:
        state = store / "STATE.md"
        if state.is_file():
            prefix, number = tid.rsplit("-", 1)
            next_free = f"{prefix}-{int(number) + 1:04d}"
            updated, added = state_row(state.read_text(encoding="utf-8"), dict(fields, _next_free=next_free))
            if added:
                state.write_text(updated, encoding="utf-8", newline="\n")
                said.append(f"STATE.md: row added for {tid}")
            else:
                said.append(f"STATE.md: no `| Task | Status |` table found; add the {tid} row yourself")
        else:
            said.append(f"STATE.md: not found; add the {tid} row when the file exists")
    return path, said


# ---------------------------------------------------------------- done, do-now, note

# A screenshot is kept only when it is plainly one of these images; anything else is dropped.
IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$")


def decode_image(data_uri: str) -> tuple[str, bytes] | None:
    """A pasted screenshot as (file extension, bytes), or None when it is not a plain image."""
    import base64
    import binascii
    found = IMAGE_RE.match(str(data_uri))
    if not found:
        return None
    try:
        raw = base64.b64decode(found.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None
    return ("jpg" if found.group(1) == "jpeg" else found.group(1)), raw


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


def save_images(store: Path, tid: str, stamp: str, shots: list[str] | None) -> list[str]:
    """Write pasted screenshots to <store>/img/<TID>-<stamp>-<n>.<ext>; returns store-relative paths."""
    digits = re.sub(r"[^0-9]", "", stamp)[:14] or "undated"
    paths = []
    for n, shot in enumerate(shots or [], 1):
        image = decode_image(shot)
        if not image:
            continue
        rel = f"img/{tid}-{digits}-{n}.{image[0]}"
        (store / "img").mkdir(parents=True, exist_ok=True)
        (store / rel).write_bytes(image[1])
        paths.append(rel)
    return paths


def _entry(stamp: str, what: str, note: str | None, images: list[str]) -> str:
    """One History line: what happened, then the owner's note verbatim and the screenshots."""
    parts = [f"- {stamp} – {what}"]
    text = (note or "").strip()
    if text:
        parts.append("  The owner's note: " + text.replace("\n", "\n  "))
    for n, rel in enumerate(images, 1):
        parts.append(f"  ![Screenshot {n}](../{rel})")
    return "\n".join(parts)


def _stamp(store: Path, now: str | None) -> tuple[str, list[str]]:
    if now:
        return now, []
    stamp, note = owner_now(store)
    return stamp, [note] if note else []


def _write_state(store: Path, change) -> str | None:
    state = store / "STATE.md"
    if not state.is_file():
        return None
    updated, changed = change(state.read_text(encoding="utf-8"))
    if changed:
        state.write_text(updated, encoding="utf-8", newline="\n")
    return updated if changed else None


def complete(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
             now: str | None = None, shot_stamp: str | None = None) -> tuple[Path, list[str]]:
    """Mark a task completed: status and `updated`, a History entry with the owner's note, the
    record moved to completed/, its STATE.md row removed (and the count corrected), and a line
    under STATE.md's `Recently completed` when that section exists."""
    task = find_task(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    stamp, said = _stamp(store, now)
    images = save_images(store, tid, shot_stamp or stamp, shots)
    text = task.path.read_text(encoding="utf-8")
    text = add_history(set_fields(text, {"status": "completed", "updated": stamp}),
                       _entry(stamp, "done, marked by the owner on the board.", note, images))
    target = store / "completed" / task.path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    if target != task.path:
        task.path.unlink()
    said.append(f"completed {tid}: {target}")
    if _write_state(store, lambda t: state_remove(t, tid)) is not None:
        said.append(f"STATE.md: row removed for {tid}")
    title = task.get("title") or tid
    if _write_state(store, lambda t: state_recently_completed(t, tid, title, stamp[:10])) is not None:
        said.append(f"STATE.md: {tid} listed under Recently completed")
    return target, said


def do_now(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
           now: str | None = None, shot_stamp: str | None = None) -> tuple[Path, list[str]]:
    """The owner asks for a task now: priority high; status ready unless already in progress
    (an inbox task moves to open/ and gains its STATE.md row); a History entry with the note."""
    task = find_task(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}; reopen it by hand")
    stamp, said = _stamp(store, now)
    images = save_images(store, tid, shot_stamp or stamp, shots)
    status = "in_progress" if task.get("status") == "in_progress" else "ready"
    text = task.path.read_text(encoding="utf-8")
    text = add_history(set_fields(text, {"priority": "high", "status": status, "updated": stamp}),
                       _entry(stamp, f"Asked for now by the owner (priority high, {status}).", note, images))
    target = store / "open" / task.path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    if target != task.path:
        task.path.unlink()
    said.append(f"do now {tid}: {target}")
    fields = dict(task.meta, id=tid, status=status, priority="high", title=task.get("title") or tid)
    if _write_state(store, lambda t: state_update(t, fields)) is not None:
        said.append(f"STATE.md: row for {tid} is {status}, high")
    return target, said


def add_note(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
             now: str | None = None, shot_stamp: str | None = None) -> tuple[Path, list[str]]:
    """Add the owner's note (and screenshots) to a task's History; nothing else changes."""
    task = find_task(store, tid)
    stamp, said = _stamp(store, now)
    images = save_images(store, tid, shot_stamp or stamp, shots)
    if not (note or "").strip() and not images:
        raise ValueError(f"{tid}: an empty note")
    text = task.path.read_text(encoding="utf-8")
    text = add_history(set_fields(text, {"updated": stamp}), _entry(stamp, "Note from the owner.", note, images))
    task.path.write_text(text, encoding="utf-8", newline="\n")
    said.append(f"note on {tid}: {task.path}")
    return task.path, said


ACTIONS = {"done": complete, "do_now": do_now, "note": add_note}


def refresh_board(path: Path, store: Path) -> list[str]:
    """Regenerate the owner board that shows the new task, when the owner board is set up.

    Runs the owner-board skill's own script, so the routing lives in one place. Without that
    skill, or without its configuration, the task is still created and this says what to run.
    """
    root = brain_root(store)
    if not BOARD_SCRIPT.is_file() or root is None:
        return ["board: the owner-board skill is not installed; nothing to refresh"]
    command = [sys.executable, str(BOARD_SCRIPT), "--root", str(root), "--no-fetch", "build", "--for", str(path)]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    if done.returncode == 0:
        return ["board: " + line for line in lines]
    return ["board: not refreshed (" + ("; ".join(lines) or f"exit {done.returncode}") + ")",
            f"board: after fixing it, run python {BOARD_SCRIPT.as_posix()} build --for {path.name}"]


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", help="task store path (repository-root or absolute)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("review", help="tasks that need attention")
    r.add_argument("--today", help="YYYY-MM-DD, default the local date")
    r.add_argument("--horizon", type=int, default=7, help="days ahead for deadlines (default 7)")
    sub.add_parser("check", help="validate task records")
    n = sub.add_parser("next-id", help="next free task number")
    n.add_argument("--year", type=int, help="default the current year")
    c = sub.add_parser("new", help="create a task record and show it on its board")
    c.add_argument("--title", required=True, help="the outcome or next action, in the owner's words")
    c.add_argument("--status", default="inbox", choices=NEW_STATUSES,
                   help="default inbox (captured, not yet processed)")
    c.add_argument("--priority", default="normal", help="default normal")
    c.add_argument("--project", action="append", default=[], metavar="NODE",
                   help="a project_refs entry such as /memory/projects/<node>, repeatable; the first one "
                        "with a board decides the board (Git Bash: put MSYS_NO_PATHCONV=1 in front)")
    c.add_argument("--skill", action="append", default=[], metavar="SKILL", help="a skill_refs entry, repeatable")
    c.add_argument("--due", help="YYYY-MM-DD, only for a real deadline")
    c.add_argument("--next-review", help="YYYY-MM-DD; required for waiting and scheduled")
    c.add_argument("--waiting-on", help="who or what is expected to move it; required for waiting")
    c.add_argument("--owner", help="default the template's owner, else owner_short_name in /memory/OWNER.md")
    c.add_argument("--slug", help="file name after the id; default from the title")
    c.add_argument("--outcome", help="text for the Outcome section")
    c.add_argument("--next-action", help="text for the Next action section")
    c.add_argument("--now", help="the creation timestamp, ISO 8601 with offset; default now")
    c.add_argument("--no-state", action="store_true", help="do not add the STATE.md row")
    c.add_argument("--no-board", action="store_true", help="do not refresh the owner board")
    for name, text in (("done", "complete a task and move it to completed/"),
                       ("do-now", "ask for a task now: priority high, status ready unless in progress"),
                       ("note", "add the owner's note to a task's History")):
        a = sub.add_parser(name, help=text)
        a.add_argument("task", help="the task id, TASK-YYYY-NNNN")
        a.add_argument("--note", required=name == "note", help="the owner's words, kept verbatim in History")
        a.add_argument("--now", help="the timestamp, ISO 8601 with offset; default now")
        a.add_argument("--no-board", action="store_true", help="do not refresh the owner board")
    args = parser.parse_args(argv)

    store = resolve_store(args.tasks, cwd or Path.cwd())
    if not store.is_dir():
        hint = f" ({MSYS_HINT})" if args.tasks and looks_path_converted(args.tasks) else ""
        print(f"ERROR: task store not found: {store}{hint}")
        return 2

    if args.command == "review":
        today = date.fromisoformat(args.today) if args.today else date.today()
        rows = review(store, today, args.horizon)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        print(f"Task review {today.isoformat()} (deadlines within {args.horizon} days)\n")
        print("| Task | Status | Priority | Why | Waiting on | Title |")
        print("|---|---|---|---|---|---|")
        for row in rows:
            cells = [row["id"], row["status"], row["priority"], "; ".join(row["reasons"]),
                     row["waiting_on"] or "-", row["title"]]
            print("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")
        print(f"\n{len(rows)} task(s) need attention")
        return 0

    if args.command == "new":
        try:
            path, said = create(store, args.title, status=args.status, priority=args.priority,
                                projects=args.project, skills=args.skill, due=args.due,
                                next_review=args.next_review, waiting_on=args.waiting_on,
                                owner=args.owner, slug=args.slug, outcome=args.outcome,
                                next_action=args.next_action, now=args.now,
                                update_state=not args.no_state)
        except ValueError as err:
            print(f"ERROR: {err}")
            return 1
        if not args.no_board:
            said += refresh_board(path, store)
        if args.json:
            print(json.dumps({"path": path.as_posix(), "notes": said}, indent=2))
        else:
            print("\n".join(said))
        return 0

    if args.command in ("done", "do-now", "note"):
        try:
            path, said = ACTIONS[args.command.replace("-", "_")](store, args.task, note=args.note, now=args.now)
        except (LookupError, ValueError) as err:
            print(f"ERROR: {str(err).strip(chr(39))}")
            return 1
        if not args.no_board:
            said += refresh_board(path, store)
        if args.json:
            print(json.dumps({"path": path.as_posix(), "notes": said}, indent=2))
        else:
            print("\n".join(said))
        return 0

    if args.command == "check":
        report = check(store)
        if args.json:
            print(json.dumps({"errors": report.errors, "warnings": report.warnings}, indent=2))
        else:
            for line in report.errors:
                print(f"ERROR: {line}")
            for line in report.warnings:
                print(f"WARN: {line}")
            print(f"{'FAIL' if report.errors else 'PASS'}: {len(report.errors)} error(s), "
                  f"{len(report.warnings)} warning(s)")
        return 1 if report.errors else 0

    print(next_id(store, args.year or date.today().year))
    return 0


if __name__ == "__main__":
    sys.exit(main())
