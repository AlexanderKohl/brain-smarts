"""Generate the directory above every board: `/memory/<directory folder>/index.html`.

The owner bookmarks this one page. It lists every registered board and how many cards on each
are waiting, read from each board's own card files at the moment it runs, so a project nobody
has opened in a fortnight cannot go quiet without the count saying so.

Boards are registered in `/memory/skills/owner-board/config/boards.json`. A board missing from
the registry never appears here, and a board that never appears here is one nobody opens.
`build_status.py` calls this after every board regeneration, so nobody has to remember to.

    python build_boards.py [--no-fetch]
"""

from __future__ import annotations

import argparse
import datetime
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import cards  # noqa: E402
import reconcile  # noqa: E402

# Pill order: what the owner has to do, then what is coming toward them, then what is not moving.
STATES = [
    ("needs_review", "Needs you"),
    ("rework", "Sent back"),
    ("building", "Being built"),
    ("yours", "Yours elsewhere"),
    ("queued", "Queued"),
]

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg:#f6f7f8; --card:#fff; --ink:#15191c; --ink-2:#5a646c; --line:#dde2e6;
  --accent:#1f7a5a; --warn:#b06a00; --sunk:#eef1f3;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#14181b; --card:#1b2024; --ink:#eef2f4; --ink-2:#9aa6ae; --line:#2b3238;
  --accent:#4cc39a; --warn:#e0a24b; --sunk:#20262b;
} }
:root[data-theme="dark"] {
  --bg:#14181b; --card:#1b2024; --ink:#eef2f4; --ink-2:#9aa6ae; --line:#2b3238;
  --accent:#4cc39a; --warn:#e0a24b; --sunk:#20262b;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:860px; margin:0 auto; padding:34px 16px 60px; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
.sub { color:var(--ink-2); font-size:13px; margin-bottom:26px; }
.b { background:var(--card); border:1px solid var(--line); border-radius:11px;
  padding:17px 19px; margin-bottom:14px; border-left:4px solid var(--line); }
.b.act { border-left-color:var(--accent); }
.b h2 { font-size:18px; margin:0 0 3px; }
.b h2 a { color:inherit; text-decoration:none; border-bottom:2px solid var(--accent); }
.b h2 a:hover { color:var(--accent); }
.blurb { color:var(--ink-2); font-size:13px; margin:0 0 12px; }
.counts { display:flex; flex-wrap:wrap; gap:8px; }
.n { background:var(--sunk); border:1px solid var(--line); border-radius:7px;
  padding:6px 11px; font-size:12.5px; color:var(--ink-2); }
.n b { color:var(--ink); font-size:14px; margin-right:5px; }
.n.you { background:var(--accent); border-color:var(--accent); color:#fff; }
.n.you b { color:#fff; }
.n.back { background:var(--warn); border-color:var(--warn); color:#fff; }
.n.back b { color:#fff; }
.n.zero { opacity:0.5; }
.adrift { color:var(--warn); font-size:12.5px; margin-top:10px; }
.none { color:var(--ink-2); font-size:13px; }
.foot { color:var(--ink-2); font-size:12px; margin-top:26px; }
code { background:var(--sunk); padding:1px 5px; border-radius:4px; font-size:12px; }
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">__GENERATED__ &middot; every board, and how much of it is waiting for you</div>
__BODY__
<p class="foot">A new project registers its board in <code>/memory/skills/owner-board/config/boards.json</code>.
A board that is not listed here is one nobody opens.</p>
</div></body></html>
"""


def read_board(board: dict) -> dict:
    data = cards.load(board)
    try:
        data["adrift"] = reconcile.check(board, data)
    except Exception as err:
        data["adrift"] = ["The reconciliation could not run: " + str(err)]
    return data


def block(config: board_config.Config, board: dict, data: dict) -> str:
    counts: dict = {}
    for card in data["items"]:
        counts[card.get("state")] = counts.get(card.get("state"), 0) + 1
    href = os.path.relpath(os.path.join(str(board["folder"]), "status.html"),
                           str(config.directory_folder)).replace(os.sep, "/")
    waiting = counts.get("needs_review", 0) + counts.get("rework", 0)
    pills = []
    for key, label in STATES:
        n = counts.get(key, 0)
        cls = "n" + (" you" if key == "needs_review" and n else
                     " back" if key == "rework" and n else
                     " zero" if not n else "")
        pills.append('<span class="' + cls + '"><b>' + str(n) + "</b>" + html.escape(label) + "</span>")
    adrift = data.get("adrift") or []
    return ('<div class="b' + (" act" if waiting else "") + '">'
            '<h2><a href="' + html.escape(href) + '">' + html.escape(board["label"]) + "</a></h2>"
            '<p class="blurb">' + html.escape(board.get("blurb", "")) + "</p>"
            '<div class="counts">' + "".join(pills) + "</div>"
            + ('<p class="adrift">' + str(len(adrift)) + " thing(s) adrift - open the board</p>" if adrift else "")
            + "</div>")


def build(config: board_config.Config, known: dict | None = None, now: str | None = None) -> str:
    """Write the directory page. `known` holds board data already loaded this run, by id."""
    known = known or {}
    blocks = []
    for board in config.boards:
        try:
            data = known.get(board["id"]) or read_board(board)
        except Exception as err:
            blocks.append('<div class="b"><h2>' + html.escape(board["label"]) + "</h2>"
                          '<p class="blurb">' + html.escape(board.get("blurb", "")) + "</p>"
                          '<p class="adrift">This board could not be read: ' + html.escape(str(err)) + "</p></div>")
            continue
        blocks.append(block(config, board, data))
    if not blocks:
        blocks = ['<p class="none">No boards registered yet.</p>']
    stamp = now or datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    page = (PAGE.replace("__TITLE__", html.escape(config.directory["title"]))
            .replace("__GENERATED__", html.escape(stamp))
            .replace("__BODY__", "\n".join(blocks)))
    os.makedirs(str(config.directory_folder), exist_ok=True)
    out = os.path.join(str(config.directory_folder), "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    print("wrote", out, "(" + str(len(config.boards)) + " board(s))")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    args = p.parse_args(argv)
    build(board_config.load(args))
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
