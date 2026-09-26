"""Apply every saved verdicts file to the board it came from.

A browser remembers one download folder, so a folder per board would need the owner to
remember which board goes where – and a verdict applied to the wrong board would look like it
worked, because card ids are only unique within a board. So the file says which board it came
from, in its name and its body, and this routes it. The owner saves wherever the browser
offers; the conductor runs one command however many boards exist.

A file whose board is not registered is reported and left alone. A file that names no board
goes to the only registered board, or is reported when there is more than one.

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
import verdicts  # noqa: E402


def candidates(config: board_config.Config, extra: list | None = None) -> list:
    folders = verdicts.downloads_folders() + [verdicts.inbox(b) for b in config.boards] + list(extra or [])
    found: set = set()
    for board in config.boards:
        found.update(verdicts.saved_files(board, folders))
    return sorted(found, key=os.path.getmtime)


def route(config: board_config.Config, dry_run: bool = False, folders: list | None = None) -> list:
    """Apply each file. Returns the ids of the boards that changed."""
    boards = {b["id"]: b for b in config.boards}
    changed: list = []
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
