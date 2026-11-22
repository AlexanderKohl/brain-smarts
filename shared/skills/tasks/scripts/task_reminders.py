"""Reminders and repeating tasks: the two front-matter fields and the lines that show them.

A **reminder** is a task with `reminder: true` and a `next_review` date, the day it is due: a
promise to the owner that must reach him, so the review, the daily report and the session start
show it apart from the other tasks. A **repeating** task carries `repeat_days: <positive whole
number>` and lives in its store's `recurring/`; `tasks.py done` re-arms it (`next_review` = the day
of completion plus `repeat_days`) and `done --final` completes it for good.

    is_reminder(task)          True for `reminder: true`
    repeat_days(task)          the whole number of days, None when the field is absent; ValueError
                               when it is present and not a positive whole number
    split(rows, today)         (due reminders, every other row) of state_table.review's rows
    line(row)                  `reminder: <title> – <ID>, due <date>; when done: <command>`
                               (tasks.py reminders, sync.py, the session-start hook)
    entry(row)                 `- <title> – <ID>, due <date>, <store>; when done: <command>`
                               (tasks.py review, /temp/due.md)
    unreadable(reason)         `reminder: could not be read (<reason>)`

Standard library only.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from task_records import Task

DONE_COMMAND = "python shared/skills/tasks/scripts/tasks.py done {tid}"


def is_reminder(task: Task) -> bool:
    return str(task.meta.get("reminder") or "").strip().lower() == "true"


def repeat_days(task: Task) -> int | None:
    value = task.meta.get("repeat_days")
    if value in (None, "", []):
        return None
    text = str(value).strip()
    if not text.isdigit() or int(text) < 1:
        raise ValueError(f"repeat_days {text} is not a positive whole number of days")
    return int(text)


def split(rows: list[dict[str, Any]], today: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rows of reminders whose day has come, and the rest, each in the review's order (the
    reminders therefore earliest due first, then by identifier)."""
    def due(row: dict[str, Any]) -> bool:
        return bool(row.get("reminder")) and bool(row.get("next_review")) and row["next_review"] <= today.isoformat()
    return [r for r in rows if due(r)], [r for r in rows if not due(r)]


def _done(row: dict[str, Any]) -> str:
    return DONE_COMMAND.format(tid=row["id"])


def line(row: dict[str, Any]) -> str:
    return f"reminder: {row['title']} – {row['id']}, due {row['next_review']}; when done: {_done(row)}"


def entry(row: dict[str, Any]) -> str:
    return f"- {row['title']} – {row['id']}, due {row['next_review']}, {row['store']}; when done: {_done(row)}"


def unreadable(reason: str) -> str:
    return f"reminder: could not be read ({' '.join(str(reason).split())})"
