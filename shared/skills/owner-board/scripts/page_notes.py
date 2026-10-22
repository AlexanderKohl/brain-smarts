"""The release-notes section of a board page, for the projects the board names.

A board whose entry carries `release_notes: ["<project id>", ...]` draws, below its cards, what
the combined selection page used to draw for those projects only: every unreleased note with
its visibility and in-place editing, the commits no note claims (New note, Add to an existing
note, Not user-visible), and a Released lane per environment. Choices are kept in the
browser under one key until **Save my verdicts** puts them into the verdicts file as
`releaseNotes: {notes, commits}`; `apply_events.py` hands them to the release-notes skill,
which records each as an append-only choice event (`release_choices.py`).

The release-notes skill is a library skill; it is imported from the brain root only when a
board names projects, so owner-board stays a core skill with an optional dependency. A shared
board also draws the projects its repository defines in `brain/status/release-notes.json`, so a
brain without the owner's release-notes configuration still shows the section; the owner's
memory configuration overrides a repository entry with the same id. Every problem is said on
the page as a visible line as well as in the build's report.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

VISIBILITY = ["undecided", "announce", "hold", "internal"]
ENVIRONMENTS = ("testing", "production")

CSS = """
.notes { margin-top:28px; }
.notes h2 { font-size:16px; margin:0 0 4px; }
.notes .sub { margin-bottom:12px; }
.notes .notes-problem { margin:0 0 8px; font-size:12.5px; color:var(--warn); }
.notes .proj { display:flex; flex-wrap:wrap; gap:10px; align-items:baseline; justify-content:space-between;
  border-bottom:2px solid var(--line); padding-bottom:6px; margin:18px 0 10px; }
.notes .proj h3 { font-size:14.5px; margin:0; }
.notes .proj a { color:var(--accent); font-size:12.5px; }
.note { background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--line);
  border-radius:9px; padding:11px 14px; margin-bottom:9px; }
.note[data-v=announce] { border-left-color:var(--accent); }
.note[data-v=hold] { border-left-color:var(--warn); }
.note[data-v=internal] { border-left-style:dashed; }
.note h4 { font-size:14px; margin:0 0 5px; }
.note .nbody { margin:0 0 7px; white-space:pre-wrap; font-size:13px; }
.note .look { font-size:12.5px; background:var(--surface-2); border-radius:6px; padding:6px 9px; margin-bottom:8px; }
.note .look b { color:var(--warn); }
.note .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; }
.note .refs { font-size:11.5px; color:var(--muted); }
.note .who { font-size:11.5px; color:var(--warn); }
.notes [contenteditable] { outline:none; border-radius:4px; }
.notes [contenteditable]:hover { box-shadow:0 0 0 1px var(--line); }
.notes [contenteditable]:focus { box-shadow:0 0 0 2px var(--accent); }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:7px; overflow:hidden; }
.seg button { font:inherit; font-size:12px; padding:3px 9px; border:0; border-right:1px solid var(--line);
  background:var(--surface); color:var(--muted); cursor:pointer; border-radius:0; }
.seg button:last-child { border-right:0; }
.seg button.on { background:var(--ink); color:var(--surface); }
.seg button.on[data-v=announce] { background:var(--accent); color:#fff; }
.seg button.on[data-v=hold] { background:var(--warn); color:#fff; }
details.loose { background:var(--surface); border:1px dashed var(--line); border-radius:9px; padding:9px 14px; margin-bottom:10px; }
details.loose summary { cursor:pointer; font-size:13px; }
details.loose ul { padding-left:18px; margin:6px 0 0; }
details.loose li { font-size:12.5px; margin:6px 0; }
details.loose li button, details.loose li select { font-size:11.5px; padding:2px 7px; margin-left:5px; }
details.loose li.done { opacity:.55; }
.lanes { display:flex; flex-wrap:wrap; gap:10px; }
.lane { flex:1 1 260px; background:var(--col); border:1px solid var(--line); border-radius:9px; padding:9px 11px; }
.lane h4 { margin:0 0 6px; font-size:11.5px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); }
.lane p { margin:0 0 4px; font-size:12.5px; }
.lane p b { font-weight:600; }
"""

JS = r"""<script>
/* Release-note choices on a board page (page_notes.py). Kept in the browser under one key per
   board until saved; nothing here changes a note file. */
(function () {
  var KEY = '__KEY__';
  var saved = { notes: {}, commits: {} };
  var listeners = [];
  try { saved = JSON.parse(localStorage.getItem(KEY) || 'null') || saved; } catch (e) {}
  function store() { try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {} listeners.forEach(function (f) { f(); }); }
  function key(n) { return n.dataset.project + '/' + n.dataset.slug; }
  function entry(n) { return saved.notes[key(n)] = saved.notes[key(n)] || { project: n.dataset.project, slug: n.dataset.slug }; }
  function stop(ev) { ev.stopPropagation(); }
  document.querySelectorAll('.notes .note').forEach(function (n) {
    var mine = saved.notes[key(n)] || {};
    if (mine.visibility) {
      n.dataset.v = mine.visibility;
      n.querySelectorAll('.seg button').forEach(function (b) { b.classList.toggle('on', b.dataset.v === mine.visibility); });
    }
    n.addEventListener('click', stop);
  });
  document.querySelectorAll('.notes .seg').forEach(function (seg) { seg.addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    seg.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
    var n = seg.closest('.note'); n.dataset.v = b.dataset.v; entry(n).visibility = b.dataset.v; store();
  }); });
  document.querySelectorAll('.notes [contenteditable]').forEach(function (f) { f.addEventListener('input', function () {
    entry(f.closest('.note'))[f.dataset.f] = f.innerText.trim(); store();
  }); });
  function fill(s) {
    if (!s || s.dataset.filled) return;
    var t = document.querySelector('template.note-opts[data-project="' + s.dataset.opts + '"]');
    if (t) s.appendChild(t.content.cloneNode(true));
    s.dataset.filled = '1';
  }
  document.querySelectorAll('.notes li[data-hash]').forEach(function (li) {
    if (saved.commits[li.dataset.hash]) li.classList.add('done');
    var sel = li.querySelector('select');
    ['pointerdown', 'mousedown', 'focus', 'keydown'].forEach(function (ev) { sel.addEventListener(ev, function () { fill(sel); }); });
    li.addEventListener('click', function (e) {
      stop(e);
      var b = e.target.closest('button'); if (!b) return;
      var a = { project: li.dataset.project, hash: li.dataset.hash, subject: li.dataset.subject, action: b.dataset.a };
      if (a.action === 'add') { var s = li.querySelector('select'); if (!s.value) { fill(s); s.focus(); return; } a.slug = s.value; }
      saved.commits[a.hash] = a;
      li.classList.add('done');
      store();
    });
  });
  function count() { return Object.keys(saved.notes).filter(function (k) { return Object.keys(saved.notes[k]).length > 2; }).length + Object.keys(saved.commits).length; }
  window.BoardNotes = {
    entries: function () {
      return { notes: Object.keys(saved.notes).map(function (k) { return saved.notes[k]; }).filter(function (e) { return Object.keys(e).length > 2; }),
        commits: Object.keys(saved.commits).map(function (k) { return saved.commits[k]; }) };
    },
    count: count,
    lines: function () {
      var out = [];
      Object.keys(saved.notes).forEach(function (k) { var e = saved.notes[k]; if (Object.keys(e).length > 2) out.push('NOTE ' + k + ' ' + JSON.stringify(e)); });
      Object.keys(saved.commits).forEach(function (k) { out.push('COMMIT ' + k + ' ' + saved.commits[k].action); });
      return out;
    },
    forget: function () { saved = { notes: {}, commits: {} }; store(); },
    onChange: function (fn) { listeners.push(fn); }
  };
})();
</script>"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def skill_module(brain: Path):
    """The library skill's choices module, or None when the library is not checked out."""
    scripts = brain / "library" / "skills" / "release-notes" / "scripts"
    if not (scripts / "release_choices.py").is_file():
        return None
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import release_choices  # noqa: E402
    return release_choices


def note_html(project: dict, note: dict) -> str:
    f = note["front"]
    v = f.get("visibility") if f.get("visibility") in VISIBILITY else "undecided"
    tags = [f.get("kind"), f.get("area")]
    commits = [str(c) for c in (f.get("commits") or [])]
    refs = (str(len(commits)) + " commit" + ("" if len(commits) == 1 else "s")) if commits else ""
    seg = "".join('<button type="button" data-v="%s"%s>%s</button>' % (x, ' class="on"' if x == v else "", x.capitalize())
                  for x in VISIBILITY)
    who = "".join('<span class="who">%s chose %s %s; %s chose %s later</span>' % (
        esc(c["first"]["by"]), esc(c["field"]), esc(c["first"]["value"]), esc(c["later"]["by"]), esc(c["later"]["value"]))
        for c in note.get("conflicts") or [])
    return ('<div class="note" data-v="%s" data-project="%s" data-slug="%s">'
            '<h4 contenteditable data-f="title">%s</h4><div class="meta">%s</div>'
            '<p class="nbody" contenteditable data-f="body">%s</p>'
            '<div class="look"><b>Look out for:</b> <span contenteditable data-f="look_out_for">%s</span></div>'
            '<div class="row"><div class="seg">%s</div><span class="refs">%s</span>%s</div></div>') % (
        v, esc(project["id"]), esc(note["slug"]), esc(f.get("title")),
        "".join('<span class="tag">%s</span>' % esc(t) for t in tags if t),
        esc(note["body"]), esc(f.get("look_out_for")), seg, esc(refs), who)


def loose_html(project: dict, notes: list, loose: list) -> str:
    if not loose:
        return ""
    # One option list per project in a <template>; each select is filled from it when first used,
    # so the page carries the list once rather than once per loose commit.
    options = "".join(
        '<option value="%s">%s</option>' % (esc(n["slug"]), esc(n["front"].get("title"))) for n in notes)
    blank = '<option value="">choose a note…</option>'
    items = "".join(
        '<li data-project="%s" data-hash="%s" data-subject="%s"><code>%s</code> %s – %s '
        '<button type="button" data-a="new">New note</button>'
        '<select data-opts="%s">%s</select><button type="button" data-a="add">Add to an existing note</button>'
        '<button type="button" data-a="skip">Not user-visible</button></li>' % (
            esc(project["id"]), esc(c["hash"]), esc(c["subject"]), esc(c["hash"]), esc(c["author"]),
            esc(c["subject"]), esc(project["id"]), blank) for c in loose)
    return ('<template class="note-opts" data-project="%s">%s</template>' % (esc(project["id"]), options)
            + '<details class="loose"><summary><b>%d commit%s in no note</b> – would a user notice %s?'
            '</summary><ul>%s</ul></details>' % (len(loose), "" if len(loose) == 1 else "s",
                                                 "it" if len(loose) == 1 else "them", items))


def lanes_html(released: dict) -> str:
    lanes = []
    for env in ENVIRONMENTS:
        rows = released.get(env) or []
        body = "".join('<p><b>%s</b> · %s · %d note%s</p>' % (esc(r["version"]), esc(r["date"]), len(r["notes"]),
                                                              "" if len(r["notes"]) == 1 else "s") for r in rows[:8])
        lanes.append('<div class="lane"><h4>Released to %s</h4>%s</div>' % (env, body or '<p>Nothing yet.</p>'))
    return '<div class="lanes">' + "".join(lanes) + "</div>"


MISSING_SKILL = ("The board names release-notes projects but the release-notes skill is not checked out "
                 "under /library/ (pull the skill library: git -C library pull, from the brain root).")


def repository_root(board: dict) -> Path | None:
    """The project repository of a shared board: the status folder's ancestor named after it."""
    if not board.get("shared") or not board.get("repo_name") or not board.get("folder"):
        return None
    for folder in [Path(board["folder"])] + list(Path(board["folder"]).parents):
        if folder.name == board["repo_name"]:
            return folder
    return None


def skill_config(module, config, board: dict):
    """The release-notes configuration for this board: the owner's, plus its repository's own
    projects when the board is shared. Shared with apply_events.py (one implementation)."""
    repository = repository_root(board)
    if repository is None or not hasattr(module, "repo_definition"):
        return module.load_config(config.brain)
    return module.load_config(config.brain, repo_definition=module.repo_definition(repository))


def problem_html(problems: list) -> str:
    return "".join('<p class="notes-problem">%s</p>' % esc(p) for p in problems)


def section(config, board: dict) -> tuple:
    """(HTML for the section, problems). An empty string when the board names no project.

    Every problem is also drawn in the section as a short visible line."""
    if not board.get("release_notes"):
        return "", []
    head = ('<section class="notes" id="notes"><h2>Release notes</h2>'
            '<div class="sub">One note per change a user would notice · choose what the team is told, hold the rest · '
            'testing shows what reached testing, production only what reached production</div>')
    module = skill_module(config.brain)
    if module is None:
        return head + problem_html([MISSING_SKILL]) + "</section>", [MISSING_SKILL]
    try:
        cfg = skill_config(module, config, board)
    except Exception as err:
        problem = "The release-notes configuration could not be read: " + str(err)
        return head + problem_html([problem]) + "</section>", [problem]
    problems: list = list(getattr(cfg, "problems", None) or [])
    parts: list = []
    for pid in board["release_notes"]:
        project = cfg.projects.get(pid)
        if not project:
            problems.append("release_notes names " + pid + ", which is not a project in the release-notes "
                            "configuration or the repository's brain/status/release-notes.json")
            continue
        try:
            notes, broken, conflicts = module.collect_unreleased(cfg, project)
            loose = module.collect_loose(cfg, project, notes)
            released = module.collect_released(cfg, project)
        except Exception as err:   # a repository that cannot be read is said on the page, not hidden
            problems.append("release notes of " + pid + " could not be read: " + str(err))
            continue
        link = project.get("artifact_url") or ""
        parts.append('<div class="proj"><h3>%s</h3>%s</div>' % (
            esc(project["label"]), ('<a href="%s">Team page ↗</a>' % esc(link)) if link else ""))
        for b in broken:
            problems.append("release note " + pid + "/" + b["slug"] + " does not parse: " + str(b["error"]))
        parts += [note_html(project, n) for n in notes] or ['<p class="empty">No notes waiting.</p>']
        parts.append(loose_html(project, notes, loose))
        parts.append(lanes_html(released))
    html_out = head + problem_html(problems) + "".join(parts) + "</section>"
    html_out += JS.replace("__KEY__", board["storage_prefix"] + "-notes")
    return html_out, problems


def to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
