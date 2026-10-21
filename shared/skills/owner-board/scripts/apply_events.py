"""Turn what the owner saved into events, fold them, and do this brain's share of the effects.

**Save my verdicts** hands the browser a download, because a page opened from disk cannot
write a file. So the owner's Downloads folder and each folder directly inside it are read: a
browser that asks where to save offers whichever folder it used last. The file says which
board it came from, in its name and its body, and this routes it: card ids are only unique
within a board, and a verdict applied to the wrong board would look like it worked.

Each verdict in a saved file becomes one event file under `<board>/events/`, written by this
brain under its own author, after three fences (`events.check_fences`): the card still exists,
its signature is the one the verdict was given against, and the page had seen the card's
latest event (`seen_through`) – otherwise the verdict is refused with "pull, rebuild, decide
again". A `resolve` must name every conflicting event. Release-note choices saved with the
verdicts go to the release-notes skill as events of their own; task actions change this
brain's own task records through the tasks skill.

Then the fold runs and the side effects that belong to the brain running it are done, each
idempotent: a card retired by an event of this author is moved to `cards/closed/` (the other
brain receives the move by pull); the words of a reject are written into the card when this
brain is the card's author. A card already in `cards/closed/` is left alone.

    python apply_events.py [--dry-run] [--from <folder>]        # every saved file, then settle
    python apply_events.py --board <id> <file> [--dry-run]       # one file to one board
    python apply_events.py --settle [--board <id>]               # effects only, after a pull
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402
import page_js  # noqa: E402
import task_actions  # noqa: E402

VERDICT_KINDS = {"accepted": "accept", "accept": "accept", "rework": "reject", "reject": "reject",
                 "defer": "defer", "amend": "amend", "resolve": "resolve"}


class Refused(Exception):
    """The file is not a verdicts file for this board."""


# ---------------------------------------------------------------- finding saved files

def downloads() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads")


def downloads_folders() -> list:
    top = downloads()
    try:
        subs = [e.path for e in os.scandir(top) if e.is_dir()]
    except OSError:
        subs = []
    return [top] + sorted(subs)


def saved_files(board: dict, folders: list | None = None) -> list:
    found: list = []
    for folder in folders if folders is not None else downloads_folders():
        found += glob.glob(os.path.join(folder, board["verdict_prefix"] + "*.json"))
    return sorted(set(found), key=os.path.getmtime)


def candidates(config: board_config.Config, extra: list | None = None) -> list:
    """Every saved verdicts file and task-actions file, oldest first."""
    folders = downloads_folders() + list(extra or [])
    found: set = set(task_actions.saved_files(folders))
    for board in config.boards:
        found.update(saved_files(board, folders))
    return sorted(found, key=os.path.getmtime)


def applied_folder(config: board_config.Config) -> Path:
    """Where a saved file goes once its events are written: this brain's own memory, never a board."""
    return config.memory / "skills" / "owner-board" / "applied"


def read(board: dict, path: str) -> dict:
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if saved.get("schema") != board["verdict_schema"]:
        raise Refused("Not a verdicts file for this board: " + path)
    came_from = saved.get("board") or ""
    if came_from and came_from != board["id"]:
        raise Refused("That file was saved from the " + came_from + " board, not " + board["id"]
                      + ". Run apply_events.py, which sends it to the right one.")
    return saved


# ---------------------------------------------------------------- verdicts to events

def save_shots(board: dict, event_id: str, shots: list, dry_run: bool) -> list:
    """Write the screenshots pasted with a verdict into the board's `img/`, named by the event
    so two brains cannot write one name, and return their paths relative to the board folder."""
    paths = []
    for n, shot in enumerate(shots, 1):
        image = task_actions.task_store.decode_image(shot)
        if not image:
            continue
        rel = "img/" + event_id + "-" + str(n) + "." + image[0]
        if not dry_run:
            os.makedirs(os.path.join(str(board["folder"]), "img"), exist_ok=True)
            Path(os.path.join(str(board["folder"]), rel)).write_bytes(image[1])
        paths.append(rel)
    return paths


def to_events(board: dict, saved: dict, dry_run: bool = False) -> tuple:
    """Write one event per verdict in a saved file. Returns (applied lines, skipped lines)."""
    derived = events.state(board)
    # A card retired by the fold but still on disk can still be disagreed with: the later
    # different outcome becomes a conflict rather than a refusal.
    by_id = {c["id"]: c for c in derived["items"] + derived["retired"]}
    taken = events.ids_in(board)
    applied, skipped = [], []
    for v in saved.get("verdicts", []):
        kind = VERDICT_KINDS.get(str(v.get("verdict") or ""))
        if not kind:
            skipped.append(str(v.get("id")) + ": unknown verdict " + str(v.get("verdict")))
            continue
        item = by_id.get(v.get("id"))
        fields = {"card": v.get("id"), "sig": v.get("sig") or None, "why": v.get("why") or None,
                  "version": v.get("version") or (item or {}).get("version") or None,
                  "seen_through": v.get("seen_through") or ""}
        if kind == "resolve":
            fields.update({"resolves": list(v.get("resolves") or []), "outcome": VERDICT_KINDS.get(str(v.get("outcome") or ""))})
        event = events.make(board, kind, board["author"], saved.get("savedAt"), taken, **fields)
        reason = events.check_fences(item, event)
        if reason:
            skipped.append(str(v.get("id")) + ": " + reason)
            continue
        if v.get("shots"):
            event["shots"] = save_shots(board, event["id"], v["shots"], dry_run)
        events.write(board, event, dry_run)
        taken.add(event["id"])
        applied.append(kind.ljust(9) + " " + item["id"] + " (" + (item.get("version") or "-") + ") as " + event["id"])
    return applied, skipped


def release_choices_module(config: board_config.Config):
    scripts = config.brain / "library" / "skills" / "release-notes" / "scripts"
    if not (scripts / "release_choices.py").is_file():
        return None
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import release_choices  # noqa: E402  (the library skill, present only when checked out)
    return release_choices


def apply_file(config: board_config.Config, board: dict, path: str, dry_run: bool = False) -> tuple:
    """One saved file: its verdicts, release-note choices and task actions. Files the file."""
    saved = read(board, path)
    applied, skipped = to_events(board, saved, dry_run)
    notes = saved.get("releaseNotes") or {}
    if notes.get("notes") or notes.get("commits"):
        module = release_choices_module(config)
        if module is None:
            skipped.append("release-note choices: the release-notes skill is not checked out under /library/")
        else:
            applied += module.apply_choices(module.load_config(config.brain), notes, board["author"],
                                            saved.get("savedAt") or "", dry_run)
    now_list: list = []
    if saved.get("tasks"):
        t_applied, t_skipped, now_list = task_actions.apply_entries(
            config.task_store, saved["tasks"], saved.get("savedAt") or "", dry_run)
        applied += t_applied
        skipped += t_skipped
    if not dry_run:
        done = applied_folder(config)
        done.mkdir(parents=True, exist_ok=True)
        shutil.move(path, str(done / os.path.basename(path)))
    return applied, skipped, now_list


# ---------------------------------------------------------------- this brain's effects

def _git_mv(folder: str, src: str, dst: str) -> bool:
    """`git mv` when the folder is in a repository, so the move is staged for the conductor."""
    try:
        out = subprocess.run(["git", "-C", folder, "mv", "-k", src, dst], capture_output=True, text=True)
        return out.returncode == 0 and not os.path.exists(src)
    except OSError:
        return False


def settle(board: dict, dry_run: bool = False) -> list:
    """Do the side effects that belong to this brain, after a fold. Returns one line each."""
    me = board["author"]
    derived = events.state(board)
    done: list = []
    for item in derived["retired"]:
        if item.get("closed"):
            continue   # already in cards/closed/
        retiring = [e for e in item.get("events", []) if e.get("kind") in ("accept", "released")
                    and (e.get("kind") == "accept" or e.get("env") == "production")]
        if not any(e.get("by") == me for e in retiring):
            continue   # the other author moves it; it arrives by pull
        src = os.path.join(cards.cards_folder(board), item["id"] + ".md")
        dst = os.path.join(cards.closed_folder(board), item["id"] + ".md")
        if not dry_run:
            os.makedirs(cards.closed_folder(board), exist_ok=True)
            if not _git_mv(str(board["folder"]), src, dst):
                os.replace(src, dst)
        done.append(("would move " if dry_run else "moved ") + item["id"] + " to cards/closed/")
    for item in derived["items"]:
        decided = item.get("decided") or {}
        if decided.get("kind") != "reject" or item.get("author") != me:
            continue
        fresh = next((c for c in cards.load(board)["items"] if c["id"] == item["id"]), None)
        if fresh is None or fresh.get("sent_back"):
            continue   # the card already carries the words
        fresh["state"] = "rework"
        fresh["sent_back"] = decided.get("why") or "Sent back with no reason given."
        fresh["sent_back_images"] = list(decided.get("shots") or [])
        if not dry_run:
            cards.write(board, fresh)
        done.append(("would write" if dry_run else "wrote") + " the words of " + decided["by"] + " into " + item["id"])
    return done


def report(applied: list, skipped: list, dry_run: bool) -> None:
    for line in applied:
        print("  " + line)
    for line in skipped:
        print("  SKIPPED " + line)
    print(str(len(applied)) + " applied, " + str(len(skipped)) + " skipped"
          + (" (dry run, nothing written)" if dry_run else ""))


# ---------------------------------------------------------------- routing

def route(config: board_config.Config, dry_run: bool = False, folders: list | None = None) -> list:
    """Apply each saved file to the board it names. Returns the ids of the boards that changed."""
    boards = {b["id"]: b for b in config.boards}
    changed: list = []
    now_list: list = []
    tasks_changed = False
    files = candidates(config, folders)
    if not files:
        print("  nothing saved - press Save my verdicts on a board first")
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
            report(applied, skipped, dry_run)
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
        if which not in boards:
            print("  SKIPPED " + name + ": board " + which + " is not registered")
            continue
        board = boards[which]
        print("  " + name + " -> " + board["label"])
        try:
            applied, skipped, asked = apply_file(config, board, path, dry_run)
        except Refused as err:
            print("  " + str(err))
            continue
        report(applied, skipped, dry_run)
        now_list += asked
        tasks_changed = tasks_changed or bool(asked) or bool(saved.get("tasks"))
        if which not in changed:
            changed.append(which)
    for board in config.boards:
        for line in settle(board, dry_run):
            print("  " + line)
            if board["id"] not in changed:
                changed.append(board["id"])
    if tasks_changed and not dry_run:
        changed += [b for b in boards if b not in changed]
    task_actions.report_now(now_list)
    return changed


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", help="board id, with a file: apply that one file to that board")
    p.add_argument("path", nargs="?", help="a particular saved file (with --board)")
    p.add_argument("--from", dest="extra", action="append", default=[], help="another folder to read saved files from")
    p.add_argument("--settle", action="store_true", help="do this brain's side effects only, after a pull")
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    args = p.parse_args(argv)
    config = board_config.load(args)
    if args.settle:
        boards = [config.board(args.board)] if args.board else config.boards
        changed = []
        for board in boards:
            for line in settle(board, args.dry_run):
                print("  " + line)
                changed.append(board["id"])
    elif args.path:
        board = config.board(args.board)
        try:
            applied, skipped, now_list = apply_file(config, board, args.path, args.dry_run)
        except Refused as err:
            print(str(err))
            return 1
        report(applied, skipped, args.dry_run)
        for line in settle(board, args.dry_run):
            print("  " + line)
        task_actions.report_now(now_list)
        changed = [board["id"]]
    else:
        changed = route(config, args.dry_run, args.extra)
    if changed and not args.dry_run:
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
