"""Tasks on the boards: every task record is shown on exactly one board.

The task record under `/memory/tasks/` is the single source (CONTRACT section 9). A board never
copies a task into a card: this module reads the records each time a page is generated and
draws them, so a status changed in the record is what the board shows at the next regeneration.
Tasks carry no verdict; the owner changes a task by changing its record, and every task on a
board links to its file.

Routing, in one place so every page gives the same answer:

1. Walk the task's `project_refs` in order. The first reference that belongs to a registered
   board (the board's `node`, or a folder beneath it; the deepest such node wins) decides.
2. With `tasks.auto_boards` on, the first reference under one of `tasks.auto_roots` that has
   no registered board gets a generated task-only board of its own.
3. Anything else – no `project_refs`, or projects without a board – goes to the owner's
   personal board.

Where each board is drawn:

- a registered board: a "Tasks" section at the foot of its own `status.html`;
- the personal board: `/memory/<directory>/<personal.page>` (default `personal.html`);
- an automatic board: `/memory/<directory>/<auto_folder>/<slug>.html`.

The personal and automatic pages are written by `build_boards.py` on every regeneration of any
board, beside the directory, so they cannot be older than it.

    python task_board.py route [--json]          which board each open task is on
    python task_board.py build [--for <task>]    regenerate the pages that show tasks
    python task_board.py check                   parse the pages: each open task once, on its board
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The task store has one reader, the tasks skill's own (SMART-RULE-0018); it sits beside this
# skill under /shared/skills/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tasks" / "scripts"))

import board_config  # noqa: E402
import tasks as task_store  # noqa: E402

# Left to right is the way a task travels. The action columns come first; `completed` shows
# only what finished within `tasks.completed_days`.
COLUMNS = [
    ("inbox", "Inbox"),
    ("ready", "Ready"),
    ("in_progress", "In progress"),
    ("waiting", "Waiting"),
    ("scheduled", "Scheduled"),
    ("blocked", "Blocked"),
    ("completed", "Completed recently"),
]
OPEN_STATUSES = [key for key, _ in COLUMNS if key != "completed"]
# Waiting and scheduled work is picked up on its review date, so those columns run by date.
BY_REVIEW = {"waiting", "scheduled"}
PRIORITY_RANK = {"critical": 0, "urgent": 0, "high": 1, "medium": 2, "normal": 2, "low": 3}

# The colour tokens every generated board page uses. `build_status.py` draws with the same ones.
TOKENS = """:root {
  --bg:#f3f5f7; --surface:#fff; --surface-2:#e9edf1; --ink:#16202a; --muted:#5d6b78;
  --line:#d8dee4; --accent:#0f7060; --warn:#b3261e; --shadow:0 1px 2px rgba(16,32,42,.08);
  --col:#eceff2;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#0f141a; --surface:#1a222b; --surface-2:#243039; --ink:#e7edf2; --muted:#9db0c0;
    --line:#2f3c48; --accent:#4fd1b5; --warn:#ff8a80; --shadow:none; --col:#161d24;
  }
}
:root[data-theme="dark"] {
  --bg:#0f141a; --surface:#1a222b; --surface-2:#243039; --ink:#e7edf2; --muted:#9db0c0;
  --line:#2f3c48; --accent:#4fd1b5; --warn:#ff8a80; --shadow:none; --col:#161d24;
}"""

CSS = """
.tasks { margin-top:28px; }
.tasks h2 { font-size:16px; margin:0 0 4px; display:flex; gap:10px; align-items:baseline; }
.tasks h2 .n { color:var(--muted); font-size:12.5px; font-weight:400; }
.tnote { color:var(--muted); font-size:12.5px; margin:0 0 12px; }
.tboard { display:flex; gap:12px; align-items:flex-start; overflow-x:auto; padding-bottom:8px; }
.tcol { background:var(--col); border:1px solid var(--line); border-radius:10px; padding:10px;
  flex:1 1 0; min-width:210px; }
.tcol h3 { display:flex; gap:7px; align-items:baseline; margin:2px 4px 10px; font-size:11.5px;
  text-transform:uppercase; letter-spacing:.07em; font-weight:700; color:var(--muted); }
.tcol h3 .n { background:var(--surface); border:1px solid var(--line); border-radius:20px;
  padding:0 7px; font-size:11px; letter-spacing:0; color:var(--ink); }
.tcol.alarm { border-color:var(--warn); }
.task { background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:8px; padding:9px 11px; margin-bottom:8px; box-shadow:var(--shadow); }
.task.pr-high, .task.pr-urgent, .task.pr-critical { border-left-color:var(--accent); }
.task.late { border-left-color:var(--warn); }
.task .ask { margin:0; font-weight:600; font-size:13.5px; }
.task .ask a { color:inherit; text-decoration:none; border-bottom:1px solid var(--line); }
.task .ask a:hover { color:var(--accent); border-bottom-color:var(--accent); }
.task .tmeta { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:6px; }
.task .tag { font-size:10px; letter-spacing:.04em; text-transform:uppercase; font-weight:700;
  background:var(--surface-2); color:var(--muted); border-radius:4px; padding:2px 6px; }
.task .tag.warn { background:var(--warn); color:#fff; }
.task .tid, .task .wait { color:var(--muted); font-size:12px; margin:5px 0 0; }
.tempty { color:var(--muted); font-size:12.5px; padding:2px 4px 6px; }
@media (max-width:900px) { .tboard { display:block; overflow-x:visible; } .tcol { min-width:0; margin-bottom:12px; } }
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
__FAVICON__
<style>
__TOKENS__
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { padding:20px 16px 60px; max-width:1800px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; letter-spacing:-.01em; }
.sub { color:var(--muted); font-size:12.5px; }
.sub a { color:var(--accent); }
.tasks { margin-top:18px; }
__CSS__
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">updated __GENERATED__ &middot; <a href="__INDEX__">every board</a></div>
__SECTION__
</div>
<script>
// The page is regenerated whenever a task or a board changes; a page left open reloads itself.
setInterval(function () { location.reload(); }, 60000);
</script>
</body></html>
"""


# ---------------------------------------------------------------- reading and routing


def local_today() -> datetime.date:
    """Today's date, the one place a page asks for it (tests replace this)."""
    return datetime.date.today()


def _norm(ref: str) -> str:
    return "/" + str(ref).strip().strip("/")


def _day(task: task_store.Task, *keys: str) -> datetime.date | None:
    for key in keys:
        found = task.day(key)
        if found:
            return found
    return None


def enabled(config: board_config.Config) -> bool:
    """Tasks are drawn when the configuration allows it and the task store exists."""
    return bool(config.tasks.get("enabled", True)) and config.task_store.is_dir()


def load(config: board_config.Config) -> list[task_store.Task]:
    """Every task record the boards can show: inbox, open and completed."""
    if not enabled(config):
        return []
    return task_store.load_tasks(config.task_store)


def is_open(task: task_store.Task) -> bool:
    return task.folder in ("inbox", "open")


def _node_title(config: board_config.Config, node: str) -> str:
    """The title in a node's README, or the last part of its path."""
    rel = node[len("/memory/"):] if node.startswith("/memory/") else node.lstrip("/")
    meta = board_config.front_matter(config.memory.joinpath(*rel.split("/"), "README.md"))
    return meta.get("title") or rel.rsplit("/", 1)[-1]


def boards(config: board_config.Config) -> dict[str, dict]:
    """Every board a task can land on, by key: registered boards, then the personal board."""
    folder = config.directory_folder
    out: dict[str, dict] = {}
    for board in config.boards:
        out[board["id"]] = {"key": board["id"], "kind": "registered", "label": board["label"],
                            "node": _norm(board["node"]), "blurb": board.get("blurb", ""),
                            "page": Path(board["folder"]) / "status.html"}
    p = config.personal
    out[p["id"]] = {"key": p["id"], "kind": "personal", "label": p["label"], "node": None,
                    "blurb": p.get("blurb", ""), "page": folder / p["page"]}
    return out


def _auto_board(config: board_config.Config, ref: str) -> dict | None:
    for root in config.tasks.get("auto_roots") or []:
        root = _norm(root) + "/"
        if ref.startswith(root) and len(ref) > len(root):
            slug = ref[len(root):].replace("/", "-")
            return {"key": "auto:" + slug, "kind": "auto", "label": _node_title(config, ref), "node": ref,
                    "blurb": ref, "page": config.directory_folder / config.tasks["auto_folder"] / (slug + ".html")}
    return None


def board_for(config: board_config.Config, task: task_store.Task, known: dict[str, dict]) -> tuple[dict, str | None]:
    """The one board a task is shown on, and the reference that put it there."""
    refs = task.meta.get("project_refs") or []
    if isinstance(refs, str):
        refs = [refs]
    registered = [b for b in known.values() if b["kind"] == "registered"]
    for raw in refs:
        ref = _norm(raw)
        owners = [b for b in registered if ref == b["node"] or ref.startswith(b["node"] + "/")]
        if owners:
            return max(owners, key=lambda b: len(b["node"])), ref
        if config.tasks.get("auto_boards"):
            auto = _auto_board(config, ref)
            if auto:
                return known.setdefault(auto["key"], auto), ref
    return known[config.personal["id"]], (_norm(refs[0]) if refs else None)


def route(config: board_config.Config, records: list[task_store.Task] | None = None,
          today: datetime.date | None = None) -> dict[str, dict]:
    """Every board with the tasks it shows: `{key: {board fields..., "tasks": [(task, ref)]}}`.

    Open tasks are always routed. A completed or cancelled task is routed only while it is
    recent, by the date in `completed`, else `updated`.
    """
    today = today or local_today()
    known = boards(config)
    records = load(config) if records is None else records
    since = today - datetime.timedelta(days=int(config.tasks.get("completed_days", 14)))
    placed: dict[str, list] = {}
    for task in records:
        if not is_open(task):
            finished = _day(task, "completed", "updated")
            if not finished or finished < since:
                continue
        board, ref = board_for(config, task, known)
        placed.setdefault(board["key"], []).append((task, ref))
    for key, board in known.items():
        board["tasks"] = placed.get(key, [])
    return known


# ---------------------------------------------------------------- drawing


def column_of(task: task_store.Task) -> str:
    status = task.get("status") or ""
    if task.folder == "completed" or status in ("completed", "cancelled"):
        return "completed"
    if task.folder == "inbox":
        return "inbox"
    return status


def sort_key(column: str, task: task_store.Task):
    """The order inside a column.

    Action columns (inbox, ready, in progress, blocked): priority, then the nearest real
    deadline, then task number – what to do next is at the top. Waiting and scheduled: the
    nearest review date first, because that is when they come back. Completed: newest first.
    """
    far = datetime.date.max
    rank = PRIORITY_RANK.get((task.get("priority") or "").lower(), 4)
    if column in BY_REVIEW:
        return ((task.day("next_review") or far).toordinal(), rank, task.tid)
    if column == "completed":
        return (-(_day(task, "completed", "updated") or datetime.date.min).toordinal(), task.tid)
    return (rank, (task.day("due") or far).toordinal(), task.tid)


def _href(page_dir: Path, target: Path) -> str:
    rel = os.path.relpath(str(target), str(page_dir)).replace(os.sep, "/")
    return urllib.parse.quote(rel, safe="/.-_~")


def _task_html(task: task_store.Task, ref: str | None, board: dict, page_dir: Path,
               column: str, today: datetime.date) -> str:
    esc = html.escape
    status = task.get("status") or "unknown"
    priority = (task.get("priority") or "").lower()
    due, review = task.day("due"), task.day("next_review")
    late = column != "completed" and ((due and due < today) or (review and review <= today))
    tags = []
    if priority and column != "completed":
        tags.append('<span class="tag">' + esc(priority) + "</span>")
    if status == "cancelled":
        tags.append('<span class="tag">cancelled</span>')
    if due and column != "completed":
        tags.append('<span class="tag' + (" warn" if due < today else "") + '">due ' + due.isoformat() + "</span>")
    if review and column != "completed" and review <= today:
        tags.append('<span class="tag warn">review due</span>')
    # Which project a task belongs to is said only where the board does not already say it.
    if ref and ref != board.get("node"):
        tags.append('<span class="tag">' + esc(ref.rstrip("/").rsplit("/", 1)[-1]) + "</span>")
    wait = ""
    if column in BY_REVIEW:
        parts = []
        if task.get("waiting_on"):
            parts.append("Waiting on: " + esc(task.get("waiting_on")))
        parts.append("review " + (review.isoformat() if review else "not set"))
        wait = '<p class="wait">' + " &middot; ".join(parts) + "</p>"
    cls = "task" + (" pr-" + esc(priority) if priority else "") + (" late" if late else "")
    return ('<article class="' + cls + '" data-task="' + esc(task.tid) + '" data-status="' + esc(status) + '">'
            + ('<div class="tmeta">' + "".join(tags) + "</div>" if tags else "")
            + '<p class="ask"><a href="' + esc(_href(page_dir, task.path)) + '">'
            + esc(task.get("title") or task.tid) + "</a></p>"
            + '<p class="tid">' + esc(task.tid) + "</p>" + wait + "</article>")


def section(board: dict, page_dir: Path, today: datetime.date | None = None) -> str:
    """The task columns for one board, as static HTML."""
    today = today or local_today()
    groups: dict[str, list] = {key: [] for key, _ in COLUMNS}
    lost: list = []
    for task, ref in board.get("tasks") or []:
        column = column_of(task)
        (groups[column] if column in groups else lost).append((task, ref))
    open_count = sum(len(groups[k]) for k in OPEN_STATUSES) + len(lost)
    cols = []
    if lost:
        # Nothing may vanish: a status no column draws is shown first, in the warning colour.
        cols.append('<div class="tcol alarm" data-column="unknown"><h3>Not a task status<span class="n">'
                    + str(len(lost)) + "</span></h3>"
                    + "".join(_task_html(t, r, board, page_dir, "unknown", today) for t, r in lost) + "</div>")
    for key, label in COLUMNS:
        rows = sorted(groups[key], key=lambda pair: sort_key(key, pair[0]))
        body = "".join(_task_html(t, r, board, page_dir, key, today) for t, r in rows)
        cols.append('<div class="tcol" data-column="' + key + '"><h3>' + html.escape(label)
                    + '<span class="n">' + str(len(rows)) + "</span></h3>"
                    + (body or '<div class="tempty">Nothing here.</div>') + "</div>")
    return ('<section class="tasks" id="tasks" data-board="' + html.escape(board["key"]) + '">'
            '<h2>Tasks<span class="n">' + str(open_count) + " open</span></h2>"
            '<p class="tnote">Shown from the task records in /memory/tasks/; a task changes in its record, '
            "not here. Click a title to open it.</p>"
            '<div class="tboard">' + "".join(cols) + "</div></section>")


def counts(board: dict, today: datetime.date | None = None) -> dict[str, int]:
    """Open tasks per status, plus `attention`: past due or review come."""
    today = today or local_today()
    out = {key: 0 for key in OPEN_STATUSES}
    out["open"] = out["attention"] = 0
    for task, _ in board.get("tasks") or []:
        if not is_open(task):
            continue
        column = column_of(task)
        out[column] = out.get(column, 0) + 1
        out["open"] += 1
        due, review = task.day("due"), task.day("next_review")
        if (due and due < today) or (review and review <= today):
            out["attention"] += 1
    return out


def _write_page(config: board_config.Config, board: dict, now: str, today: datetime.date | None) -> Path:
    page = Path(board["page"])
    page.parent.mkdir(parents=True, exist_ok=True)
    index = _href(page.parent, config.directory_folder / "index.html")
    text = (PAGE.replace("__TOKENS__", TOKENS).replace("__CSS__", CSS)
            .replace("__FAVICON__", board_config.favicon_link(config))
            .replace("__TITLE__", html.escape(board["label"]))
            .replace("__GENERATED__", html.escape(now))
            .replace("__INDEX__", html.escape(index))
            .replace("__SECTION__", section(board, page.parent, today)))
    with open(page, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return page


def write_pages(config: board_config.Config, routed: dict[str, dict], now: str,
                today: datetime.date | None = None) -> list[Path]:
    """Write the personal board and every automatic board. Registered boards draw their own."""
    if not enabled(config):
        return []
    written = [_write_page(config, board, now, today) for board in routed.values() if board["kind"] != "registered"]
    # An automatic board whose tasks have all gone keeps its page (it may be bookmarked), drawn
    # empty, rather than going on showing tasks that have moved.
    auto_dir = config.directory_folder / str(config.tasks["auto_folder"])
    for page in sorted(auto_dir.glob("*.html")) if auto_dir.is_dir() else []:
        if page in written:
            continue
        found = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
        empty = {"key": "auto:" + page.stem, "kind": "auto", "label": html.unescape(found.group(1)) if found else page.stem,
                 "node": None, "blurb": "", "page": page, "tasks": []}
        written.append(_write_page(config, empty, now, today))
    return written


# ---------------------------------------------------------------- the headless check


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and "task" in (a.get("class") or "").split() and a.get("data-task"):
            self.found.append((a["data-task"], a.get("data-status") or ""))


def shown_on(page: Path) -> list[tuple[str, str]]:
    collector = _Collector()
    collector.feed(page.read_text(encoding="utf-8"))
    return collector.found


def check(config: board_config.Config, today: datetime.date | None = None) -> list[str]:
    """Read the generated pages back: every open task exactly once, and on the board it routes to."""
    routed = route(config, today=today)
    problems: list[str] = []
    where: dict[str, list[str]] = {}
    for key, board in routed.items():
        page = Path(board["page"])
        if not page.is_file():
            if board["tasks"] or board["kind"] != "auto":
                problems.append(board["label"] + ": page " + str(page) + " has not been generated")
            continue
        for tid, _ in shown_on(page):
            where.setdefault(tid, []).append(key)
    for key, board in routed.items():
        for task, _ in board["tasks"]:
            if not is_open(task):
                continue
            seen = where.get(task.tid, [])
            if seen != [key]:
                problems.append(task.tid + " should be once on " + board["label"] + ", found on: "
                                + (", ".join(seen) or "no board"))
    return problems


# ---------------------------------------------------------------- CLI


def _find(records: list[task_store.Task], which: str) -> task_store.Task:
    for task in records:
        if which in (task.tid, str(task.path), task.path.name) or Path(which).resolve() == task.path.resolve():
            return task
    raise board_config.ConfigError("no task record " + which + " in the task store")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("route", help="which board each open task is on")
    r.add_argument("--json", action="store_true")
    b = sub.add_parser("build", help="regenerate the pages that show tasks")
    b.add_argument("--for", dest="task", help="a task id or file: rebuild only the board it lands on")
    sub.add_parser("check", help="parse the generated pages and compare them with the routing")
    args = p.parse_args(argv)
    config = board_config.load(args)

    import build_boards  # noqa: E402  (imports this module; loaded here to avoid a cycle)
    import build_status  # noqa: E402

    if args.command == "route":
        rows = [{"task": t.tid, "status": t.get("status") or "", "board": b["label"], "kind": b["kind"],
                 "by": ref or "-"} for b in route(config).values() for t, ref in b["tasks"] if is_open(t)]
        rows.sort(key=lambda row: row["task"])
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(row["task"] + "  " + row["status"].ljust(11) + "  " + row["board"] + "  (" + row["by"] + ")")
            print(str(len(rows)) + " open task(s)")
        return 0

    if args.command == "build":
        if args.task:
            known = boards(config)
            task = _find(load(config), args.task)
            board, _ = board_for(config, task, known)
            print(task.tid + " is on " + board["label"] + ": " + str(board["page"]))
            targets = [b for b in config.boards if b["id"] == board["key"]]
        else:
            targets = list(config.boards)
        known_data = {b["id"]: build_status.build(config, b, directory=False) for b in targets}
        build_boards.build(config, known=known_data)
        return 0

    problems = check(config)
    for line in problems:
        print("ERROR: " + line)
    total = sum(1 for b in route(config).values() for t, _ in b["tasks"] if is_open(t))
    print(("FAIL" if problems else "PASS") + ": " + str(total) + " open task(s), " + str(len(problems)) + " problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
