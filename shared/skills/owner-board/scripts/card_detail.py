"""What a card's detail shows beyond what landed and what to check: its facts, its task and its history.

Since 1.0.0 a card is a file and the page inlines only a slim copy of it (`build_status.page_data`):
the event log is left out and no card carries a link to its task. This module puts the detail back
on the page's copy of each card, never in the card file or `state.json`:

- `facts`: asked, started, branch, version, release note and author, in that order (the order a
  card lives through them), each only when the card has it.
- `taskLinks`: every task id the card names (its `task` or `tasks` field, then its title, what
  landed and what to check, in that order, each id once). On a memory board each links to its
  task record, relative to the page. A repository board carries no `/memory/` path (CONTRACT
  16.1), so there the id stands alone with a note that the record is in the owner's own brain.
- `history`: the card's events, oldest first, as kind, by, when and why.

`JS` draws them inside a card's detail and `CSS` styles them; both are inlined into the page.
"""

from __future__ import annotations

import re
from pathlib import Path

import task_board

TASK_ID = re.compile(r"\bTASK-\d{4}-\d{4}\b")
REPO_NOTE = "the task record is kept in the owner's own brain, not in this repository"
MISSING_NOTE = "no task record with this id was found"
FACTS = (("asked", "Asked"), ("startedAt", "Started"), ("branch", "Branch"), ("version", "Version"),
         ("release_note", "Release note"), ("author", "Author"))


def task_ids(item: dict) -> list:
    found: list = []
    named = item.get("tasks") or []
    sources = [item.get("task") or ""] + (named if isinstance(named, list) else [named])
    sources += [item.get("title") or "", item.get("landed") or "", item.get("review") or ""]
    for text in sources:
        for tid in TASK_ID.findall(str(text)):
            if tid not in found:
                found.append(tid)
    return found


def _facts(item: dict) -> list:
    out = []
    for key, label in FACTS:
        value = item.get(key)
        if value in (None, "", []):
            continue
        out.append([label, str(value)[:16].replace("T", " ") if key == "startedAt" else str(value)])
    return out


def _history(item: dict) -> list:
    rows = []
    for event in item.get("events") or []:
        row = {k: event.get(k) for k in ("kind", "by", "saved_at", "why", "outcome", "version")
               if event.get(k) not in (None, "")}
        rows.append(row)
    return rows


def attach(config, board: dict, shown: dict, derived: dict, records=None) -> None:
    """Add facts, task links and history to each card of the page data `shown`.

    `derived` is the full state the page data was cut from, in the same order; it still holds
    each card's events. `records` replaces the task store in tests.
    """
    shared = bool(board.get("shared"))
    by_id = {}
    if not shared:
        loaded = records if records is not None else task_board.load(config)
        by_id = {t.tid: t for t in loaded}
    page_dir = Path(board["folder"])
    full = {item["id"]: item for item in derived.get("items", [])}
    for item in shown.get("items", []):
        whole = full.get(item["id"], item)
        links = []
        for tid in task_ids(whole):
            if shared:
                links.append({"id": tid, "note": REPO_NOTE})
                continue
            record = by_id.get(tid)
            if record is None:
                links.append({"id": tid, "note": MISSING_NOTE})
            else:
                links.append({"id": tid, "href": task_board._href(page_dir, record.path),
                              "title": record.get("title") or ""})
        item["facts"] = _facts(whole)
        item["taskLinks"] = links
        item["history"] = _history(whole)


CSS = """
.facts { font-size:12px; color:var(--muted); margin:6px 0; }
.facts span { margin-right:12px; white-space:nowrap; }
.facts b, .tlinks b, .hist b { color:var(--ink, inherit); font-weight:600; }
.tlinks { font-size:12.5px; margin:6px 0; }
.tlinks a { margin-right:8px; }
.tlinks i { color:var(--muted); font-size:11.5px; }
.hist { font-size:11.5px; color:var(--muted); margin:6px 0 0; padding-left:16px; }
.hist li { margin:2px 0; }
"""

# Carries its own script tags, as page_js.TASKS_JS does: it is inlined after that block.
JS = r"""<script>
/* A card's facts, task links and history (card_detail.py), drawn inside its detail. */
window.BoardDetail = (function () {
  function node(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function draw(item, body) {
    var facts = item.facts || [];
    if (facts.length) {
      var f = node('p', 'facts');
      facts.forEach(function (pair) {
        var s = node('span');
        s.appendChild(node('b', null, pair[0] + ': '));
        s.appendChild(document.createTextNode(pair[1]));
        f.appendChild(s);
      });
      body.appendChild(f);
    }
    var links = item.taskLinks || [];
    if (links.length) {
      var t = node('p', 'tlinks');
      t.appendChild(node('b', null, (links.length === 1 ? 'Task' : 'Tasks') + ': '));
      links.forEach(function (link) {
        if (link.href) {
          var a = node('a', null, link.id + (link.title ? ' – ' + link.title : ''));
          a.href = link.href;
          a.target = '_blank';
          a.rel = 'noreferrer';
          a.addEventListener('click', function (ev) { ev.stopPropagation(); });
          t.appendChild(a);
        } else {
          t.appendChild(node('span', 'tid', link.id + ' '));
          if (link.note) t.appendChild(node('i', null, '(' + link.note + ') '));
        }
      });
      body.appendChild(t);
    }
    var hist = item.history || [];
    if (hist.length) {
      var h = node('p', 'facts');
      h.appendChild(node('b', null, 'History'));
      body.appendChild(h);
      var ul = node('ul', 'hist');
      hist.forEach(function (e) {
        var line = (e.saved_at || '').slice(0, 16).replace('T', ' ') + ' · ' + (e.by || '?') + ' · ' + (e.kind || '?');
        if (e.version) line += ' ' + e.version;
        if (e.outcome) line += ' (' + e.outcome + ')';
        if (e.why) line += ': ' + e.why;
        ul.appendChild(node('li', null, line));
      });
      body.appendChild(ul);
    }
  }
  return { draw: draw };
})();
</script>
"""
