"""Generate a board's `status.html` from its card files – a kanban of what is in play.

The card lifecycle, enforced by `reconcile.py` rather than remembered:

    queued -> building -> needs_review -> (the owner accepts) -> closed
                              |
                              +-> rework -> building

A card is never deleted because the work landed. A merge moves the card to `needs_review` and
sets its version; only the owner's verdict retires it, and retiring writes the version into
`closed` so the reconciliation knows it was seen rather than lost.

The page inlines the data rather than fetching it, because a `file://` page cannot fetch a
sibling file and the owner opens the board by double-clicking it. The inlined copy is
generated on every run, never kept by hand. After writing the page, the directory above every
board (`build_boards.py`) is regenerated too, so it can never be older than any board.

    python build_status.py [--board <id>] [--no-fetch]
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import build_boards  # noqa: E402
import cards  # noqa: E402
import page_js  # noqa: E402
import reconcile  # noqa: E402
import task_board  # noqa: E402
from page_html import PAGE  # noqa: E402

def page_config(board: dict) -> dict:
    """Everything the page needs that is not card data, from the board's configuration."""
    owner = board.get("owner") or ""
    return {
        "board": board["id"],
        "copyOnly": list(board.get("copy_only_prefixes") or []),
        "label": board["label"],
        "labels": {
            "accepted": (owner + " accepted") if owner else "Accepted",
            "needsReview": ("Needs " + owner + "'s review") if owner else "Needs your review",
            "ownerTurn": owner or "You",
            "sentBack": cards.sent_back_heading(board),
            "yours": (owner + " does elsewhere") if owner else "Yours elsewhere",
        },
        "prefix": board["verdict_prefix"],
        "schema": board["verdict_schema"],
        "storage": board["storage_prefix"],
    }


def view_href(template: str, view: str, data: dict) -> str:
    """Build a card's address from `where_view_href` and the board's own fields.

    `{view}` is the card's `where_view`; any other `{name}` is a top-level field of the
    board's JSON block. A part in square brackets is left out when a field it uses is empty;
    a missing field outside brackets means no address can be built, and the card keeps its
    plain words.
    """
    def value(name: str) -> str:
        raw = view if name == "view" else data.get(name)
        return urllib.parse.quote(str(raw), safe="-_.!~*'()") if raw not in (None, "") else ""

    def fill(part: str) -> str | None:
        names = re.findall(r"\{([A-Za-z_]+)\}", part)
        if any(not value(n) for n in names):
            return None
        return re.sub(r"\{([A-Za-z_]+)\}", lambda m: value(m.group(1)), part)

    optional = re.sub(r"\[([^\]]*)\]", lambda m: fill(m.group(1)) or "", template)
    return fill(optional) or ""


def resolve_links(board: dict, data: dict) -> None:
    template = board.get("where_view_href")
    for item in data["items"]:
        where = item.get("where") or {}
        if where.get("href") or not where.get("view") or not template:
            continue
        where["href"] = view_href(template, where["view"], data)


def inline_images(board: dict, data: dict) -> int:
    """Turn each card's `image` path into a data URI, so the page survives being sent as one file.

    A path that does not exist is reported rather than left as a broken image.
    """
    done = 0
    for item in data["items"]:
        shots = []
        for rel in item.get("sent_back_images") or []:
            path = os.path.join(str(board["folder"]), rel)
            if not os.path.exists(path):
                print("  MISSING screenshot for " + item["id"] + ": " + rel)
                continue
            mime = mimetypes.guess_type(path)[0] or "image/png"
            with open(path, "rb") as fh:
                shots.append("data:" + mime + ";base64," + base64.b64encode(fh.read()).decode("ascii"))
            done += 1
        item["sent_back_images"] = shots
        src = item.get("image")
        if not src or src.startswith("data:"):
            continue
        path = os.path.join(str(board["folder"]), src)
        if not os.path.exists(path):
            print("  MISSING image for " + item["id"] + ": " + src)
            item.pop("image", None)
            continue
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as fh:
            item["image"] = "data:" + mime + ";base64," + base64.b64encode(fh.read()).decode("ascii")
        done += 1
    return done


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def build(config: board_config.Config, board: dict, directory: bool = True) -> dict:
    """Write `status.html` for one board and, unless told not to, the directory page.

    Below the cards, the page draws the task records routed to this board (`task_board.py`):
    read from `/memory/tasks/` on every build, never copied into cards.
    """
    data = cards.load(board)
    tasks_html = ""
    if task_board.enabled(config):
        routed = task_board.route(config)
        tasks_html = task_board.section(routed[board["id"]], Path(board["folder"]))
    # Run every time, so the conductor cannot choose not to; a reconciliation that cannot run
    # must say so rather than vanish.
    try:
        data["adrift"] = reconcile.check(board, data)
    except Exception as err:
        data["adrift"] = ["The reconciliation against git could not run: " + str(err)]
    resolve_links(board, data)
    inlined = inline_images(board, data)
    out = os.path.join(str(board["folder"]), "status.html")
    page = (
        PAGE.replace("__TOKENS__", task_board.TOKENS)
        .replace("__TASKCSS__", task_board.CSS + page_js.CSS)
        .replace("__SHAREDJS__", page_js.SHARED_JS + "\n" + page_js.TASKS_JS)
        .replace("__FAVICON__", board_config.favicon_link(config, board))
        .replace("__TITLE__", html.escape(board["title"]))
        .replace("__MAIN__", html.escape(board.get("main") or "main"))
        .replace("__VERSION__", html.escape(str(data.get("mainVersion", "?"))))
        .replace("__GENERATED__", html.escape(str(data.get("generated", "?"))[:16].replace("T", " ")))
        .replace("__CONFIG__", _json(page_config(board)))
        .replace("__TASKS__", tasks_html)
        .replace("__DATA__", _json(data))
    )
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    counts: dict = {}
    for item in data["items"]:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    print("wrote", out, "(" + str(inlined) + " image(s) embedded)")
    print(", ".join(k + ": " + str(v) for k, v in sorted(counts.items())))
    if data["adrift"]:
        print("  " + str(len(data["adrift"])) + " thing(s) adrift - see the top of the page")
    if directory:
        # The directory refreshes whenever any board does, reusing this board's answer.
        build_boards.build(config, known={board["id"]: data})
    return data


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", help="board id (default: the board whose folder holds the current directory, or the only one)")
    p.add_argument("--all", action="store_true", help="rebuild every registered board")
    args = p.parse_args(argv)
    config = board_config.load(args)
    boards = config.boards if args.all else [config.board(args.board)]
    known = {board["id"]: build(config, board, directory=False) for board in boards}
    build_boards.build(config, known=known)
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
