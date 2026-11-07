"""Team lanes on the task boards: a colour per team, who holds a card, and a WIP count per team.

A task record may name a `team` (the conductor thread that works it), and while it is in
progress, `claimed_by` and `claimed_at` (see /shared/schemas/task-schema.md). `task_board.py`
draws these through this module:

- every card shows its team as a small coloured tag; the colour is chosen deterministically
  from the label, from a palette of six that reads on the light and the dark theme;
- an in-progress card says who holds it and how long ago it was claimed;
- above the columns, one line per team present: `team · in progress n / limit`, in the warning
  colour when n exceeds the limit (`tasks.wip_limit` in boards.json, default 2).
"""

from __future__ import annotations

import datetime
import html
import zlib

PALETTE = 6

# The six lane colours, one token each, redefined for the dark theme like the board's own tokens.
TOKENS = """:root {
  --team-0:#1d5fd1; --team-1:#b4420a; --team-2:#0b7a6f; --team-3:#6d28d9; --team-4:#946a00; --team-5:#b4176a;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --team-0:#8ab4ff; --team-1:#ffab80; --team-2:#5eead4; --team-3:#c4b5fd; --team-4:#f6d46a; --team-5:#f9a8d4;
  }
}
:root[data-theme="dark"] {
  --team-0:#8ab4ff; --team-1:#ffab80; --team-2:#5eead4; --team-3:#c4b5fd; --team-4:#f6d46a; --team-5:#f9a8d4;
}"""

CSS = """
.task .tag.team, .lane .tag.team { background:transparent; border:1px solid var(--team); color:var(--team);
  text-transform:none; letter-spacing:0; font-size:10.5px; }
.team-0 { --team:var(--team-0); } .team-1 { --team:var(--team-1); } .team-2 { --team:var(--team-2); }
.team-3 { --team:var(--team-3); } .team-4 { --team:var(--team-4); } .team-5 { --team:var(--team-5); }
.task .held { color:var(--muted); font-size:12px; margin:5px 0 0; }
.lanes { display:flex; flex-wrap:wrap; gap:6px 18px; margin:0 0 12px; font-size:12.5px; color:var(--muted); }
.lane { margin:0; display:flex; gap:6px; align-items:center; }
.lane.over { color:var(--warn); font-weight:600; }
"""


def local_now() -> datetime.datetime:
    """The clock, the one place a page asks for it (tests replace this)."""
    return datetime.datetime.now().astimezone()


def team_of(task) -> str | None:
    """A task's team label, lowercased, or None."""
    label = str(task.get("team") or "").strip().lower()
    return label or None


def team_index(label: str) -> int:
    """Which of the six colours a team gets: the same label always gets the same one."""
    return zlib.crc32(label.encode("utf-8")) % PALETTE


def team_tag(label: str) -> str:
    return '<span class="tag team team-' + str(team_index(label)) + '">' + html.escape(label) + "</span>"


def parse_stamp(value: str | None) -> datetime.datetime | None:
    """An ISO 8601 timestamp as an aware datetime; a naive one is taken as the machine's zone."""
    if not value:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.astimezone()


def ago(stamp: datetime.datetime, now: datetime.datetime | None = None) -> str:
    """How long ago, in the coarsest unit that is not zero: `just now`, `12 min ago`, `3 h ago`, `2 d ago`."""
    seconds = int(((now or local_now()) - stamp).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return str(minutes) + " min ago"
    hours = minutes // 60
    if hours < 48:
        return str(hours) + " h ago"
    return str(hours // 24) + " d ago"


def held_html(task, now: datetime.datetime | None = None) -> str:
    """Who holds a card and since when, for an in-progress card; nothing when nobody does."""
    holder = task.get("claimed_by")
    if not holder:
        return ""
    stamp = parse_stamp(task.get("claimed_at"))
    when = "claimed " + ago(stamp, now) if stamp else "claimed at an unknown time"
    return ('<p class="held" data-claimed-by="' + html.escape(holder) + '"'
            + (' data-claimed-at="' + html.escape(str(task.get("claimed_at"))) + '"' if stamp else "")
            + ">Held by " + html.escape(holder) + " &middot; " + when + "</p>")


def wip_lines(entries: list[tuple[str | None, str]], limit: int) -> str:
    """One line per team present among `entries` (team, column) of a board's open tasks.

    `team · in progress n / limit`, with `over` on a line whose count exceeds the limit.
    """
    teams = sorted({team for team, _ in entries if team})
    if not teams:
        return ""
    lines = []
    for team in teams:
        n = sum(1 for t, column in entries if t == team and column == "in_progress")
        over = n > limit
        lines.append('<p class="lane' + (" over" if over else "") + '" data-team="' + html.escape(team)
                     + '" data-in-progress="' + str(n) + '" data-limit="' + str(limit) + '">' + team_tag(team)
                     + " &middot; in progress " + str(n) + " / " + str(limit) + "</p>")
    return '<div class="lanes">' + "".join(lines) + "</div>"
