"""Generate a board's `status.html` and `state.json` from its cards and events.

The card lifecycle, enforced by `reconcile.py` rather than remembered:

    queued -> building -> needs_review -> (a verdict, or the production release) -> closed
                              |
                              +-> rework -> building

A card is never deleted because the work landed. A merge moves the card to `needs_review` and
sets its version; a verdict or a release retires it, and retiring puts the version into the
derived `closed` register so the reconciliation knows it was seen rather than lost.

The state is folded from the event log on every build (`events.fold`), so two brains that share
a board derive the same page from the same files. Both outputs are generated, never kept by
hand, and on a repository board are ignored by Git and rebuilt after every pull. A repository board draws the tasks of
its repository's own store (`brain/tasks/`, linked relative to the repository) and carries
nothing from `/memory/`: the build refuses to write a page that would (CONTRACT section 16.2). After writing the page, the directory above every board
(`build_boards.py`) is regenerated too, so it can never be older than any board.

    python build_status.py [--board <id> | --all] [--no-fetch]
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
import card_detail  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402
import page_js  # noqa: E402
import page_notes  # noqa: E402
import reconcile  # noqa: E402
import task_board  # noqa: E402
from page_html import PAGE  # noqa: E402

MEMORY_PATH = re.compile(r"/memory/")
GENERATED = ("status.html", "state.json")


def memory_mentions(folder) -> list:
    """Files a repository board holds (board.json, cards, events) that say /memory/.

    A collaborator cannot resolve such a path. The generated page is checked as it is built.
    """
    folder = Path(folder)
    hits = []
    for path in sorted(folder.rglob("*")):
        if (path.is_file() and path.suffix in (".md", ".json") and path.name not in GENERATED
                and MEMORY_PATH.search(path.read_text(encoding="utf-8", errors="replace"))):
            hits.append(path.relative_to(folder).as_posix())
    return hits


class Refused(Exception):
    """The page would carry something a repository board may not hold."""


def page_config(board: dict, derived: dict) -> dict:
    """Everything the page needs that is not card data, from the board's configuration."""
    owner = board.get("owner") or ""
    return {
        "author": board["author"],
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
        "seenThrough": {"lastEvent": derived.get("last_event", ""), "commit": board_config.git_head(board["folder"])},
        "shared": bool(board.get("shared")),
        "storage": board["storage_prefix"],
    }


def view_href(template: str, view: str, data: dict) -> str:
    """Build a card's address from `where_view_href` and the board's own fields.

    `{view}` is the card's `where_view`; any other `{name}` is a top-level field of the
    board's JSON. A part in square brackets is left out when a field it uses is empty; a
    missing field outside brackets means no address can be built, and the card keeps its
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


def _data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fh:
        return "data:" + mime + ";base64," + base64.b64encode(fh.read()).decode("ascii")


def inline_images(board: dict, data: dict) -> int:
    """Turn each card's image paths into data URIs, so the page survives being sent as one file.

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
            shots.append(_data_uri(path))
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
        item["image"] = _data_uri(path)
        done += 1
    return done


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _slim(event: dict) -> dict:
    return {k: event.get(k) for k in ("id", "kind", "by", "saved_at", "why", "outcome") if event.get(k) is not None}


def page_data(derived: dict) -> dict:
    """What the page inlines: the open cards with compact overlays, never the whole event log."""
    out = {k: v for k, v in derived.items() if k not in ("items", "retired", "conflicts")}
    out["items"] = []
    for item in derived["items"]:
        slim = {k: v for k, v in item.items() if k not in ("events", "closed")}
        slim["conflict"] = [_slim(e) for e in item.get("conflict") or []]
        slim["amendments"] = [_slim(e) for e in item.get("amendments") or []]
        out["items"].append(slim)
    out["conflicts"] = [i["id"] for i in derived.get("conflicts", [])]
    out["retired"] = [i["id"] for i in derived.get("retired", [])]
    return out


def build(config: board_config.Config, board: dict, directory: bool = True) -> dict:
    """Write `status.html` and `state.json` for one board and, unless told not to, the directory.

    Every board draws the task records routed to it (`task_board.py`) below the cards. On a
    repository board those are the records of that repository's store only; the owner's private
    tasks about the project are drawn on the owner's page for the board, in memory.
    """
    derived = events.state(board)
    tasks_html = ""
    if task_board.enabled(config):
        routed = task_board.route(config)
        tasks_html = task_board.section(routed[board["id"]], Path(board["folder"]))
    # Run every time, so the conductor cannot choose not to; a reconciliation that cannot run
    # must say so rather than vanish.
    try:
        derived["adrift"] = reconcile.check(board, derived)
    except Exception as err:
        derived["adrift"] = ["The reconciliation against git could not run: " + str(err)]
    store_problem = task_board.shared_store_problem(config, board)
    if store_problem:
        derived["adrift"].append(store_problem)
    # The version on the page is git's, read now; board.json keeps no copy of it.
    if board.get("repo"):
        try:
            derived["mainVersion"] = reconcile.repo_version(board) or "?"
        except Exception:
            derived["mainVersion"] = "?"
    notes_html, problems = page_notes.section(config, board)
    derived["adrift"] += problems
    resolve_links(board, derived)
    inlined = inline_images(board, derived)
    shown = page_data(derived)
    card_detail.attach(config, board, shown, derived)
    out = os.path.join(str(board["folder"]), "status.html")
    page = (
        PAGE.replace("__TOKENS__", task_board.TOKENS)
        .replace("__TASKCSS__", task_board.CSS + page_js.CSS + page_notes.CSS + card_detail.CSS)
        .replace("__SHAREDJS__", page_js.SHARED_JS + "\n" + page_js.TASKS_JS + "\n" + card_detail.JS)
        .replace("__FAVICON__", board_config.favicon_link(config, board))
        .replace("__TITLE__", html.escape(board["title"]))
        .replace("__MAIN__", html.escape(board.get("main") or "main"))
        .replace("__VERSION__", html.escape(str(derived.get("mainVersion", "?"))))
        .replace("__GENERATED__", html.escape(cards._now()[:16].replace("T", " ")))
        .replace("__CONFIG__", _json(page_config(board, derived)))
        .replace("__TASKS__", tasks_html + notes_html)
        .replace("__DATA__", _json(shown))
    )
    if board.get("shared"):
        # A collaborator cannot resolve a /memory/ path, and the owner's memory is private: the
        # page may carry the repository's own tasks, never anything from memory.
        leaked = memory_mentions(board["folder"])
        if leaked:
            raise Refused("refused to write " + out + ": " + ", ".join(leaked)
                          + " mention /memory/; a repository board may carry no /memory/ path")
        if MEMORY_PATH.search(page):
            raise Refused("refused to write " + out + ": a repository board may carry no /memory/ path"
                          " (a task record of the repository that names one is fixed in the record)")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    cards.write_state(board, derived)
    counts: dict = {}
    for item in derived["items"]:
        key = item.get("fold") or item["state"]
        counts[key] = counts.get(key, 0) + 1
    print("wrote", out, "(" + str(inlined) + " image(s) embedded)")
    print(", ".join(k + ": " + str(v) for k, v in sorted(counts.items())) or "no open cards")
    if derived["adrift"]:
        print("  " + str(len(derived["adrift"])) + " thing(s) adrift - see the top of the page")
    if directory:
        # The directory refreshes whenever any board does, reusing this board's answer.
        build_boards.build(config, known={board["id"]: derived})
    return derived


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
