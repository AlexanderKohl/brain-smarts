"""Apply a verdicts file the owner saved from a board back onto that board's cards.

**Save my verdicts** writes into the board's own `status/verdicts-in/`, a folder the owner
chooses once and the page remembers. Where it cannot, it hands the browser a download, so the
owner's Downloads folder and each folder directly inside it are read too: a browser that asks
where to save offers whichever folder it used last. A screenshot pasted with a *rework* is
written to the board's `img/` and shown under the owner's words. The owner still sends one short message: the conductor only exists
between messages, so a file saved silently would sit unread.

- *accepted* retires the card: its version and title go under `closed` in `board.md` and the
  card file is deleted. That is the only way a card leaves the board.
- *rework* sets the card to `rework` and keeps the owner's words verbatim under their own
  heading.
- A verdict whose signature no longer matches the card is reported and skipped, and a file
  saved from a different board is refused: card ids are only unique within a board.

Applied files move to `status/verdicts-applied/`, which is the record of what was decided.

    python verdicts.py [--board <id>] [<file>] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import glob
import re
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import cards  # noqa: E402


def downloads() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads")


def downloads_folders() -> list:
    """Downloads and each folder directly inside it: a browser that asks where to save offers
    the last folder it used, so a verdict lands in whichever subfolder that was."""
    top = downloads()
    try:
        subs = [e.path for e in os.scandir(top) if e.is_dir()]
    except OSError:
        subs = []
    return [top] + sorted(subs)


def inbox(board: dict) -> str:
    return os.path.join(str(board["folder"]), "verdicts-in")


def saved_files(board: dict, folders: list | None = None) -> list:
    found: list = []
    for folder in folders or [inbox(board)] + downloads_folders():
        found += glob.glob(os.path.join(folder, board["verdict_prefix"] + "*.json"))
    return sorted(set(found), key=os.path.getmtime)


class Refused(Exception):
    """The file is not a verdicts file for this board."""


def read(board: dict, path: str) -> dict:
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if saved.get("schema") != board["verdict_schema"]:
        raise Refused("Not a verdicts file for this board: " + path)
    came_from = saved.get("board") or ""
    if came_from and came_from != board["id"]:
        raise Refused("That file was saved from the " + came_from + " board, not " + board["id"]
                      + ". Run apply_verdicts.py, which sends it to the right one.")
    return saved


SHOT = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$")


def save_shots(board: dict, card_id: str, saved_at: str, shots: list, dry_run: bool) -> list:
    """Write the screenshots pasted with a verdict into the board's `img/` and return their
    paths relative to the board folder. Anything that is not a plain image is dropped."""
    stamp = re.sub(r"[^0-9]", "", saved_at)[:14] or "undated"
    paths = []
    for n, shot in enumerate(shots, 1):
        found = SHOT.match(str(shot))
        if not found:
            continue
        ext = "jpg" if found.group(1) == "jpeg" else found.group(1)
        rel = "img/" + card_id + "-" + stamp + "-" + str(n) + "." + ext
        if not dry_run:
            os.makedirs(os.path.join(str(board["folder"]), "img"), exist_ok=True)
            Path(os.path.join(str(board["folder"]), rel)).write_bytes(base64.b64decode(found.group(2)))
        paths.append(rel)
    return paths


def apply(board: dict, path: str, dry_run: bool = False) -> tuple:
    """Apply one file. Returns (applied lines, skipped lines). Moves the file unless dry."""
    saved = read(board, path)
    data = cards.load(board)
    by_id = {c["id"]: c for c in data["items"]}
    applied, skipped = [], []
    for v in saved.get("verdicts", []):
        card = by_id.get(v.get("id"))
        if not card:
            skipped.append(str(v.get("id")) + ": no card with that id any more")
            continue
        if v.get("sig") and card.get("sig") and v["sig"] != card["sig"]:
            skipped.append(v["id"] + ": the card changed after the verdict was given")
            continue
        if v.get("verdict") == "accepted":
            cards.close_in_board(board, card.get("version") or v.get("version") or "",
                                 (card.get("title") or "")[:80], dry_run)
            if not dry_run:
                os.remove(os.path.join(cards.cards_folder(board), card["id"] + ".md"))
            applied.append("accepted  " + card["id"] + " (" + (card.get("version") or "-") + ")")
        elif v.get("verdict") == "rework":
            card["state"] = "rework"
            card["sent_back"] = v.get("why") or "Sent back with no reason given."
            card["sent_back_images"] = save_shots(board, card["id"], saved.get("savedAt") or "",
                                                  v.get("shots") or [], dry_run)
            if not dry_run:
                cards.write(board, card)
            applied.append("sent back " + card["id"])
        else:
            skipped.append(v["id"] + ": unknown verdict " + str(v.get("verdict")))
    if not dry_run:
        done = os.path.join(str(board["folder"]), "verdicts-applied")
        os.makedirs(done, exist_ok=True)
        os.replace(path, os.path.join(done, os.path.basename(path)))
    return applied, skipped


def report(applied: list, skipped: list, dry_run: bool) -> None:
    for line in applied:
        print("  " + line)
    for line in skipped:
        print("  SKIPPED " + line)
    print(str(len(applied)) + " applied, " + str(len(skipped)) + " skipped"
          + (" (dry run, nothing written)" if dry_run else ""))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", help="board id (default: the board whose folder holds the current directory, or the only one)")
    p.add_argument("path", nargs="?", help="a particular verdicts file (default: the newest saved one)")
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    args = p.parse_args(argv)
    config = board_config.load(args)
    board = config.board(args.board)
    path = args.path
    if not path:
        files = saved_files(board)
        if not files:
            print("No " + board["verdict_prefix"] + "*.json in " + inbox(board) + " or " + downloads()
                  + " - press Save my verdicts on the board first.")
            return 1
        path = files[-1]
    try:
        applied, skipped = apply(board, path, args.dry_run)
    except Refused as err:
        print(str(err))
        return 1
    report(applied, skipped, args.dry_run)
    if not args.dry_run:
        print("  filed under " + os.path.join(str(board["folder"]), "verdicts-applied"))
        import build_status
        build_status.build(config, board)
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
