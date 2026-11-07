"""Apply the owner's task actions – Do now, Done, a note – saved from any board page.

Every open task card carries *Do now*, *Done* and a note box (`page_js.py`). The page keeps the
choice in the browser; saving hands it over in one of two files, both found by
`apply_events.py` in the same folders as verdicts (Downloads and each folder directly inside it):

- a board's verdicts file, whose `tasks` array rides beside its `verdicts`;
- `task-actions-<savedAt>.json` from the personal, an automatic or a shared board's own task
  page, schema `owner-board/task-actions/v1`, board `tasks`.

Each entry is `{id, action, note, shots, title}` and is applied through the tasks skill's own
functions (`tasks.complete`, `tasks.do_now`, `tasks.add_note`), the one way a task changes. They
find the task in whichever store holds it (`task_stores.find`: the owner store, a node's, a
pointer node's private one or a repository's `brain/tasks/`), refuse a store that may not be
written now (a repository is fetched first and refused when behind, on another branch or
unmerged), and name this brain's author in the History entry, so a change one brain makes to a
shared task says who made it:

- `done`    status completed, an attributed History entry with the note, record to completed/,
            the store's STATE.md regenerated;
- `do_now`  priority high, status ready unless already in progress, an entry "asked for now";
- no action, a note or screenshots only: an attributed "note" entry.

Screenshots go to the `img/` folder of the task's own store; only png, jpeg, webp and gif data
are kept. An unknown task id, a task in two places or a refused store is reported and skipped.
A task already completed is never changed, because a page drawn from a stale checkout offers it
again: `done` on it is reported as `repeat: TASK-x is already completed (on <date>)`, any other
action as `conflict: TASK-x was completed on <date>; this file asks <action> – not applied, ask
the owner`, in a dry run as well. `apply_events.py` counts the two apart and lists every
conflict again at the end under "Ask the owner".
An applied task-actions file moves to `/memory/tasks/actions-applied/`.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tasks" / "scripts"))

import page_js  # noqa: E402
import task_history  # noqa: E402
import tasks as task_store  # noqa: E402

WORDS = {"done": "done", "do_now": "do now", "": "note"}
REPEAT = "repeat: "
CONFLICT = "conflict: "


class Refused(Exception):
    """The file is not a task-actions file."""


def saved_files(folders: list) -> list:
    found: list = []
    for folder in folders:
        found += glob.glob(os.path.join(str(folder), page_js.TASK_PREFIX + "*.json"))
    return sorted(set(found), key=os.path.getmtime)


def closed_on(task) -> str | None:
    """The date a task in completed/ was closed: the newest History entry that completed or
    cancelled it, otherwise its `updated` date. None when neither says."""
    status = task.get("status") or "completed"
    try:
        found = [e for e in task_history.entries(Path(task.path).read_text(encoding="utf-8"))
                 if e.what.startswith("done") or status in e.what]
    except OSError:
        found = []
    if found:
        return max(found, key=lambda e: e.at).at.date().isoformat()
    day = task.day("updated")
    return day.isoformat() if day else None


def already_closed(task, tid: str, action: str) -> str | None:
    """A line for an action on a task already in completed/: a repeat when the owner asks for
    what was done, a conflict for anything else. None for a task still open."""
    if task.folder != "completed":
        return None
    status = task.get("status") or "completed"
    day = closed_on(task)
    if action == "done" and status == "completed":
        return REPEAT + tid + " is already completed" + (" (on " + day + ")" if day else "")
    return (CONFLICT + tid + " was " + status + (" on " + day if day else "") + "; this file asks "
            + WORDS[action] + " – not applied, ask the owner")


def is_repeat(line: str) -> bool:
    return line.startswith(REPEAT)


def is_conflict(line: str) -> bool:
    return line.startswith(CONFLICT)


def apply_entries(store: Path, entries: list, saved_at: str = "", dry_run: bool = False) -> tuple:
    """Apply task actions. Returns (applied lines, skipped lines, do-now list of (id, title, note)).
    An action on a task already completed is not applied: its line, among the skipped, starts
    `repeat: ` or `conflict: ` (`is_repeat`, `is_conflict`)."""
    applied, skipped, now_list = [], [], []
    for entry in entries or []:
        if not isinstance(entry, dict):
            skipped.append("a task entry that is not an object")
            continue
        tid = str(entry.get("id") or "")
        action = str(entry.get("action") or "")
        note = str(entry.get("note") or "")
        shots = [s for s in entry.get("shots") or [] if isinstance(s, str)]
        if action not in WORDS:
            skipped.append(tid + ": unknown action " + action)
            continue
        if not action and not note.strip() and not any(task_store.decode_image(s) for s in shots):
            skipped.append(tid + ": nothing to do")
            continue
        try:
            task = task_store.find_task(store, tid)
        except LookupError as err:
            # The tasks skill names the stores it could not read; the task may be in one of them.
            unread = str(err).strip("'").partition("; not read: ")[2]
            skipped.append(tid + ": no task with that id" + ((" (not read: " + unread + ")") if unread else ""))
            continue
        except ValueError as err:
            skipped.append(str(err).strip("'"))
            continue
        title = task.get("title") or str(entry.get("title") or tid)
        closed = already_closed(task, tid, action)
        if closed:
            # Decided again from a stale page: neither changes the task, in a dry run or not.
            skipped.append(closed)
            continue
        if dry_run:
            applied.append(WORDS[action].ljust(8) + " " + tid + " (dry run)")
        else:
            try:
                task_store.ACTIONS[action or "note"](store, tid, note=note, shots=shots, shot_stamp=saved_at or None)
            except (LookupError, ValueError, task_store.WriteRefused) as err:
                said = str(err).strip("'")
                skipped.append(said if said.startswith(tid) else tid + ": " + said)
                continue
            applied.append(WORDS[action].ljust(8) + " " + tid)
        if action == "do_now":
            now_list.append((tid, title, note.strip()))
    return applied, skipped, now_list


def read(path: str) -> dict:
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(saved, dict) or saved.get("schema") != page_js.TASK_SCHEMA:
        raise Refused("Not a task-actions file: " + path)
    return saved


def apply_file(store: Path, path: str, dry_run: bool = False) -> tuple:
    """Apply one task-actions file and file it under `<store>/actions-applied/` unless dry."""
    saved = read(path)
    result = apply_entries(store, saved.get("tasks") or [], saved.get("savedAt") or "", dry_run)
    if not dry_run:
        done = Path(store) / "actions-applied"
        done.mkdir(parents=True, exist_ok=True)
        os.replace(path, str(done / os.path.basename(path)))
    return result


def report_conflicts(conflicts: list) -> None:
    """Said again at the very end: an action that contradicts a completed task waits for the owner."""
    if not conflicts:
        return
    print("Ask the owner:")
    for line in conflicts:
        print("  " + line)


def report_now(now_list: list) -> None:
    """The list the conductor acts on first: what the owner asked for now."""
    if not now_list:
        return
    print("Do now (asked for by the owner):")
    for tid, title, note in now_list:
        print("  " + tid + "  " + title + ((" – " + note.replace("\n", " ")) if note else ""))
