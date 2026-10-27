"""The team pages: what has been released, per environment, newest release first.

One page per configured team page and per environment: `<id>.testing.html` shows what has
reached testing, `<id>.production.html` only what has reached production; `<id>.html` is the
production view, the one a team link points at. The pages are derived from the `released/`
folders; nothing on them is edited by hand. The owner's choosing happens on the project's
board (`/shared/skills/owner-board/`, the release-notes section), not here.
"""

from __future__ import annotations

import datetime as dt
import html
import os
import re

CSS = """
:root { --bg:#f6f7f8; --card:#fff; --ink:#15191c; --ink-2:#5a646c; --line:#dde2e6;
  --accent:#1f7a5a; --warn:#b06a00; --sunk:#eef1f3; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#14181b; --card:#1b2024; --ink:#eef2f4; --ink-2:#9aa6ae; --line:#2b3238;
  --accent:#4cc39a; --warn:#e0a24b; --sunk:#20262b; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:860px; margin:0 auto; padding:34px 16px 60px; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
.sub { color:var(--ink-2); font-size:13px; margin-bottom:26px; }
.foot { color:var(--ink-2); font-size:12px; margin-top:26px; }
.none { color:var(--ink-2); font-size:13px; }
.look { font-size:13.5px; background:var(--sunk); border-radius:7px; padding:8px 11px; margin-bottom:11px; }
.look b { color:var(--warn); }
.rel { background:var(--card); border:1px solid var(--line); border-radius:11px; padding:16px 19px; margin-bottom:14px; }
.rel.new { border-left:4px solid var(--accent); }
.rel h2 { font-size:17px; margin:0 0 10px; }
.rel h2 span, details.rel summary span { font-weight:400; color:var(--ink-2); font-size:13px; margin-left:8px; }
details.rel summary { cursor:pointer; font-weight:600; }
details.rel[open] summary { margin-bottom:10px; }
.it { margin:0 0 12px; }
.it h4 { font-size:15px; margin:0 0 3px; }
.it p { margin:0 0 5px; white-space:pre-wrap; }
.tag { font-size:11px; color:var(--ink-2); background:var(--sunk); border:1px solid var(--line);
  border-radius:5px; padding:1px 7px; margin-right:6px; vertical-align:2px; }
.search { width:100%; font:inherit; padding:8px 12px; border:1px solid var(--line); border-radius:8px;
  background:var(--card); color:var(--ink); margin-bottom:18px; }
"""

TEAM_JS = r"""
document.getElementById('q').addEventListener('input', function(){
  var q = this.value.toLowerCase();
  document.querySelectorAll('.rel').forEach(function(r){
    var any = false;
    r.querySelectorAll('.it').forEach(function(it){
      var hit = !q || it.textContent.toLowerCase().indexOf(q) >= 0; it.style.display = hit ? '' : 'none'; any = any || hit;
    });
    r.style.display = any ? '' : 'none'; if (q && any && r.tagName === 'DETAILS') r.open = true;
  });
});
"""


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def prose(v) -> str:
    """Escaped text with **bold** kept – the one piece of Markdown notes use."""
    return re.sub(r"\*\*(.+?)\*\*", lambda m: "<b>" + m.group(1) + "</b>", esc(v))


def page(title: str, body: str, script: str = "") -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>" + esc(title) + "</title><style>" + CSS + "</style></head><body>"
            "<div class=\"wrap\">" + body + "</div>" + (("<script>" + script + "</script>") if script else "")
            + "</body></html>\n")


def day(iso: str) -> str:
    try:
        when = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return when.strftime("%#d %B %Y") if os.name == "nt" else when.strftime("%-d %B %Y")


def build_team(page_cfg: dict, env: str, releases: list) -> str:
    """One team page for one environment. `releases` carry `label`, `version`, `environments`
    and announced `notes`; they are drawn newest first by the date they reached `env`."""
    rels = sorted(releases, key=lambda r: (r["environments"].get(env, ""), r.get("label", "")), reverse=True)
    parts = ['<h1>%s</h1><div class="sub">For %s · released to %s · newest first</div>' % (
        esc(page_cfg["title"]), esc(page_cfg.get("readers", "the team")), esc(env)),
        '<input class="search" id="q" placeholder="Search every release">']
    if not rels:
        parts.append('<p class="none">Nothing released to %s yet.</p>' % esc(env))
    for i, r in enumerate(rels):
        head = '%s %s<span>Released %s · %d change%s</span>' % (
            esc(r["label"]), esc(r["version"]), day(r["environments"][env]), len(r["notes"]), "" if len(r["notes"]) == 1 else "s")
        items = "".join('<div class="it"><h4><span class="tag">%s</span>%s</h4><p>%s</p>%s</div>' % (
            esc(n["front"].get("kind", "")), esc(n["front"].get("title")), prose(n["body"]),
            ('<div class="look"><b>Look out for:</b> %s</div>' % esc(n["front"]["look_out_for"]))
            if n["front"].get("look_out_for") else "") for n in r["notes"])
        if i == 0:
            parts.append('<div class="rel new"><h2>%s</h2>%s</div>' % (head, items))
        else:
            parts.append('<details class="rel"><summary>%s</summary>%s</details>' % (head, items))
    parts.append('<div class="foot">Held and internal changes are never shown here.</div>')
    return page(page_cfg["title"], "".join(parts), TEAM_JS)
