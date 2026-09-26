"""Apply every saved verdicts file to the board it came from.

A browser remembers one download folder, so a folder per board would need the owner to
remember which board goes where – and a verdict applied to the wrong board would look like it
worked, because card ids are only unique within a board. So the file says which board it came
from, in its name and its body, and this routes it. The owner saves wherever the browser
offers; the conductor runs one command however many boards exist.

A file whose board is not registered is reported and left alone. A file that names no board
goes to the only registered board, or is reported when there is more than one.

The owner's task actions (Do now, Done, a note) are applied too: the `tasks` array of a verdicts
file, and every `task-actions-*.json` saved from the personal or an automatic task page, found in
the same folders. They change task records through the tasks skill (`task_actions.py`), and the
owner's *Do now* list is printed at the end for the conductor.

    python apply_verdicts.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import page_js  # noqa: E402
import task_actions  # noqa: E402
import verdicts  # noqa: E402


def candidates(config: board_config.Config, extra: list | None = None) -> list:
    """Every saved verdicts file and task-actions file, oldest first."""
    folders = verdicts.downloads_folders() + [verdicts.inbox(b) for b in config.boards] + list(extra or [])
    found: set = set(task_actions.saved_files(folders))
    for board in config.boards:
        found.update(verdicts.saved_files(board, folders))
    return sorted(found, key=os.path.getmtime)


def route(config: board_config.Config, dry_run: bool = False, folders: list | None = None) -> list:
    """Apply each file. Returns the ids of the boards that changed.

    Task actions (in a verdicts file's `tasks`, or a task-actions file) are applied through the
    tasks skill; a task that changed can be drawn on any board, so then every board is rebuilt.
    The owner's *Do now* list is printed last, for the conductor to act on.
    """
    boards = {b["id"]: b for b in config.boards}
    changed: list = []
    now_list: list = []
    tasks_changed = False
    files = candidates(config, folders)
    if not files:
        print("  nothing saved - press Save my verdicts on a board first")
        return changed
    for path in files:
        name = os.path.basename(path)
        try:
            saved = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as err:
            print("  UNREADABLE " + name + ": " + str(err))
            continue
        if name.startswith(page_js.TASK_PREFIX):
            print("  " + name + " -> tasks")
            try:
                applied, skipped, asked = task_actions.apply_file(config.task_store, path, dry_run)
            except task_actions.Refused as err:
                print("  " + str(err))
                continue
            verdicts.report(applied, skipped, dry_run)
            now_list += asked
            tasks_changed = tasks_changed or bool(applied)
            continue
        which = saved.get("board") or ""
        if not which:
            if len(boards) != 1:
                print("  SKIPPED " + name + ": it names no board and there are " + str(len(boards))
                      + ", so there is nothing to infer from")
                continue
            which = next(iter(boards))
            print("  " + name + " names no board; there is only one, so " + which)
        if which not in boards:
            print("  SKIPPED " + name + ": board " + which + " is not registered")
            continue
        board = boards[which]
        print("  " + name + " -> " + board["label"])
        try:
            applied, skipped = verdicts.apply(board, path, dry_run)
        except verdicts.Refused as err:
            print("  " + str(err))
            continue
        verdicts.report(applied, skipped, dry_run)
        if not dry_run and which not in changed:
            changed.append(which)
        if saved.get("tasks"):
            applied, skipped, asked = task_actions.apply_entries(
                config.task_store, saved["tasks"], saved.get("savedAt") or "", dry_run)
            verdicts.report(applied, skipped, dry_run)
            now_list += asked
            tasks_changed = tasks_changed or bool(applied)
    if tasks_changed and not dry_run:
        changed += [b for b in boards if b not in changed]
    task_actions.report_now(now_list)
    return changed


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    args = p.parse_args(argv)
    config = board_config.load(args)
    changed = route(config, args.dry_run)
    if changed:
        import build_boards
        import build_status
        known = {}
        for board in config.boards:
            if board["id"] in changed:
                known[board["id"]] = build_status.build(config, board, directory=False)
        build_boards.build(config, known=known)
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
