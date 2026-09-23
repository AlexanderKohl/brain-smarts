"""Task review and record checks for the task store (see /shared/skills/tasks/SKILL.md).

Commands:
    review   tasks that need attention today: inbox items, reviews due, deadlines near, blocked
    check    required fields, folder placement, identifier and date formats
    next-id  the next free TASK-YYYY-NNNN number

The store is `--tasks` (a repository-root path such as /memory/tasks, or an absolute path),
default /memory/tasks. Standard library only. Nothing is written.

Status validity per record, `next_review` on waiting and scheduled tasks, and the
/memory/tasks/STATE.md listing are also enforced by /shared/skills/repository-preflight/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

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
    args = parser.parse_args(argv)

    store = resolve_store(args.tasks, cwd or Path.cwd())
    if not store.is_dir():
        print(f"ERROR: task store not found: {store}")
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
