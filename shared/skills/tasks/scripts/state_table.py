"""The review of open tasks, and the task table in a node's STATE.md that shows it.

Moved unchanged from tasks.py. tasks.py imports these names back, so everything that uses tasks sees
the same names.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from task_records import load_tasks


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
