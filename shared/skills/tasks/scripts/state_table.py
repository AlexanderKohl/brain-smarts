"""The review of open tasks: what needs attention today, across every store it is given.

STATE.md is no longer edited row by row; task_state.py generates it from the records (P23).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from task_records import Task, id_sort_key


def review(tasks: list[Task], today: date, horizon: int) -> list[dict[str, Any]]:
    """One row per inbox or open task that needs attention, each naming its store."""
    rows: list[dict[str, Any]] = []
    limit = today + timedelta(days=horizon)
    for task in tasks:
        if task.folder not in ("inbox", "open", "recurring"):
            continue
        status = task.get("status") or "unknown"
        reasons: list[str] = []
        dates: list[date] = []
        if task.problem:
            reasons.append(task.problem)
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
                    "store": task.store.label if task.store is not None else "",
                    "path": task.path.as_posix(),
                }
            )
    # Undated items (inbox, blocked) first, then earliest date, then identifier.
    return sorted(rows, key=lambda r: (r["date"] != "", r["date"], id_sort_key(r["id"])))
