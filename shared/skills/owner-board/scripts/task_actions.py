"""Apply the owner's task actions – Do now, Done, a note – saved from any board page.

Every open task card carries *Do now*, *Done* and a note box (`page_js.py`). The page keeps the
choice in the browser; saving hands it over in one of two files, both found by
`apply_verdicts.py` in the same folders as verdicts (each board's `verdicts-in/`, Downloads and
each folder directly inside it):

- a board's verdicts file, whose `tasks` array rides beside its `verdicts`;
- `task-actions-<savedAt>.json` from the personal or an automatic task page, schema
  `owner-board/task-actions/v1`, board `tasks`.

Each entry is `{id, action, note, shots, title}` and is applied through the tasks skill's own
functions (`tasks.complete`, `tasks.do_now`, `tasks.add_note`), the one way a task changes:

- `done`    status completed, History with the owner's note, record to completed/, STATE.md row out;
- `do_now`  priority high, status ready unless already in progress, History "Asked for now";
- no action, a note or screenshots only: a History entry.

Screenshots go to `<store>/img/`; only png, jpeg, webp and gif data are kept. An unknown task id
is reported and skipped. An applied task-actions file moves to `<store>/actions-applied/`.
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
import tasks as task_store  # noqa: E402

WORDS = {"done": "done", "do_now": "do now", "": "note"}


class Refused(Exception):
    """The file is not a task-actions file."""


def saved_files(folders: list) -> list:
    found: list = []
    for folder in folders:
        found += glob.glob(os.path.join(str(folder), page_js.TASK_PREFIX + "*.json"))
    return sorted(set(found), key=os.path.getmtime)


def apply_entries(store: Path, entries: list, saved_at: str = "", dry_run: bool = False) -> tuple:
    """Apply task actions. Returns (applied lines, skipped lines, do-now list of (id, title, note))."""
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
        except LookupError:
            skipped.append(tid + ": no task with that id")
            continue
        title = task.get("title") or str(entry.get("title") or tid)
        if dry_run:
            applied.append(WORDS[action].ljust(8) + " " + tid + " (dry run)")
        else:
            try:
                task_store.ACTIONS[action or "note"](store, tid, note=note, shots=shots, shot_stamp=saved_at or None)
            except (LookupError, ValueError) as err:
                skipped.append(str(err).strip("'"))
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


def report_now(now_list: list) -> None:
    """The list the conductor acts on first: what the owner asked for now."""
    if not now_list:
        return
    print("Do now (asked for by the owner):")
    for tid, title, note in now_list:
        print("  " + tid + "  " + title + ((" – " + note.replace("\n", " ")) if note else ""))
