"""The browser code both kinds of board page share, held once (SMART-RULE-0018).

A registered board's `status.html` (`build_status.py`) and the personal and automatic task pages
(`task_board.py`) both need the same things: a pasted screenshot shrunk to at most 1600px and
kept as a JPEG, a text box that accepts pasted screenshots and shows them as thumbnails with a
remove button and a full-size lightbox, a download handed to the browser, and the owner's
actions on task cards. They are written here and inlined into each page, because a page opened
from disk cannot load a sibling script reliably and the owner opens boards by double-clicking.

- `CSS`       the thumbnails, lightbox, bottom bar, buttons and task-card controls
- `SHARED_JS` `window.BoardPage`: `el`, `shrink`, `lightbox`, `download`, `attachShots`
- `TASKS_JS`  `window.BoardTasks`: Do now, Done and a note on every open task card
- `TASK_BAR` and `TASK_SAVE_JS`  the save bar of a page that shows only tasks

Task actions live in the browser's storage under one key, `TASK_KEY`, shared by every page:
a task is the same task on whichever page it is drawn. Each entry is
`{action: "do_now" | "done" | "", note, shots, title}`; an entry with nothing in it is removed.
Saved task actions are applied by `apply_verdicts.py` through the tasks skill's own functions.
"""

from __future__ import annotations

TASK_KEY = "owner-board-task-actions"
TASK_SCHEMA = "owner-board/task-actions/v1"
TASK_PREFIX = "task-actions-"
NOTE_PLACEHOLDER = "Note for the agent – you can paste a screenshot here"

CSS = """
.shots { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 0; }
.shots:empty { display:none; }
.shots span { position:relative; }
.shots img { display:block; height:64px; border:1px solid var(--line); border-radius:4px; cursor:zoom-in; }
.shots button { position:absolute; top:-7px; right:-7px; padding:0 6px; font-size:12px; border-radius:10px; line-height:18px; }
.lb {
  position:fixed; inset:0; background:rgba(8,12,16,.86); z-index:50; cursor:zoom-out;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:28px;
}
.lb img { max-width:100%; max-height:84vh; border-radius:6px; background:#fff; }
.lb p { color:#e7edf2; font-size:13px; margin:0; text-align:center; }
.bar {
  position:fixed; left:0; right:0; bottom:0; background:var(--surface);
  border-top:1px solid var(--line); padding:10px 16px;
  display:flex; flex-wrap:wrap; gap:10px; align-items:center; box-shadow:0 -2px 10px rgba(16,32,42,.10);
}
.bar span { color:var(--muted); font-size:12.5px; flex:1 1 220px; }
#savenote:empty { display:none; }
button {
  font:inherit; font-size:13.5px; border-radius:6px; padding:7px 13px; cursor:pointer;
  border:1px solid var(--line); background:var(--surface-2); color:var(--ink);
}
button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
button:hover { filter:brightness(.97); }
.tact { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0; }
.tact button { font-size:12px; padding:3px 10px; }
.tact button[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
.tact button.done[aria-pressed="true"] { background:var(--ink); border-color:var(--ink); color:var(--surface); }
textarea.tnote-in {
  width:100%; margin-top:6px; min-height:38px; resize:vertical; padding:6px 8px;
  border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink);
  font:inherit; font-size:12.5px;
}
.task .tag.pend { background:var(--accent); color:#fff; }
.task.pending { border-color:var(--accent); }
"""

SHARED_JS = r"""<script>
/* Shared by every board page (page_js.py). */
(function () {
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  /* A pasted screenshot, at most 1600px wide, as a JPEG data URI: small enough that a handful
     fit in the browser's storage. */
  function shrink(file) {
    return new Promise(function (ok) {
      var r = new FileReader();
      r.onload = function () {
        var im = new Image();
        im.onload = function () {
          var scale = Math.min(1, 1600 / im.width);
          var cv = document.createElement('canvas');
          cv.width = Math.round(im.width * scale);
          cv.height = Math.round(im.height * scale);
          cv.getContext('2d').drawImage(im, 0, 0, cv.width, cv.height);
          ok(cv.toDataURL('image/jpeg', 0.88));
        };
        im.src = r.result;
      };
      r.readAsDataURL(file);
    });
  }
  /* Full size, over the page: browsers refuse to navigate to a `data:` URI at the top level. */
  function lightbox(item) {
    var back = el('div', 'lb');
    var im = document.createElement('img');
    im.src = item.image;
    im.alt = item.imageAlt || '';
    back.appendChild(im);
    if (item.imageAlt) back.appendChild(el('p', null, item.imageAlt));
    function shut() { back.remove(); document.removeEventListener('keydown', key); }
    function key(ev) { if (ev.key === 'Escape') shut(); }
    back.addEventListener('click', shut);
    document.addEventListener('keydown', key);
    document.body.appendChild(back);
  }
  /* A page opened from disk cannot write a file, so it hands the browser a download. */
  function download(name, text) {
    var url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    var a = el('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }
  /* Screenshots pasted into `area` are shrunk, kept through `put(list)` and drawn in `holder`
     as thumbnails with a remove button; a click opens one full size. `get()` returns the list
     kept so far. `put` throws when the browser refuses to store it: over quota, the picture is
     taken back and the owner told; refused outright (a preview, a private window), it is kept
     for this visit. Clicks here never reach the card underneath. Returns the redraw. */
  function attachShots(area, holder, get, put) {
    function stop(ev) { ev.stopPropagation(); }
    function draw() {
      holder.innerHTML = '';
      get().forEach(function (src, i) {
        var span = el('span');
        var im = document.createElement('img');
        im.src = src;
        im.alt = 'Screenshot ' + (i + 1);
        im.addEventListener('click', function (ev) { ev.stopPropagation(); ev.preventDefault(); lightbox({ image: src, imageAlt: im.alt }); });
        var x = el('button', null, '×');
        x.type = 'button';
        x.title = 'Remove this screenshot';
        x.addEventListener('click', function (ev) {
          ev.stopPropagation();
          ev.preventDefault();
          var list = get().slice();
          list.splice(i, 1);
          try { put(list); } catch (e) {}
          draw();
        });
        span.appendChild(im);
        span.appendChild(x);
        holder.appendChild(span);
      });
    }
    area.addEventListener('paste', function (ev) {
      var items = (ev.clipboardData && ev.clipboardData.items) || [];
      var files = [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].kind === 'file' && /^image\//.test(items[i].type)) files.push(items[i].getAsFile());
      }
      if (!files.length) return;
      ev.preventDefault();
      files.forEach(function (f) {
        shrink(f).then(function (src) {
          var list = get().concat([src]);
          try { put(list); } catch (e) {
            if (e && e.name === 'QuotaExceededError') {
              try { put(list.slice(0, -1)); } catch (e2) {}
              window.alert('That screenshot does not fit in this browser' + String.fromCharCode(39) + 's storage. Save first, then paste it on its own.');
            }
          }
          draw();
        });
      });
    });
    area.addEventListener('click', stop);
    holder.addEventListener('click', stop);
    draw();
    return draw;
  }
  window.BoardPage = { el: el, shrink: shrink, lightbox: lightbox, download: download, attachShots: attachShots };
})();
</script>"""

TASKS_JS = r"""<script>
/* Do now, Done and a note on every open task card (page_js.py). The actions are kept in the
   browser under one key shared by every board page, because a task is the same task wherever
   it is drawn; storage is read afresh before each change so two open pages do not overwrite
   each other. Nothing here changes a task record: the save hands the actions to the agent. */
(function () {
  var P = window.BoardPage, el = P.el;
  var KEY = '__KEY__';
  var LABEL = { do_now: 'Do now', done: 'Done' };
  var cache = {};
  var listeners = [];
  function read() {
    try { cache = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) {}
    return cache;
  }
  function pending(a) {
    return !!a && (!!a.action || !!String(a.note || '').trim() || !!(a.shots || []).length);
  }
  /* Change one task's entry. `strict` lets a refusal through to the caller (a screenshot). */
  function edit(id, title, fn, strict) {
    var all = read();
    var e = all[id] || { action: '', note: '', shots: [], title: title };
    e.title = title;
    fn(e);
    if (pending(e)) all[id] = e; else delete all[id];
    cache = all;
    try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (err) { if (strict) throw err; }
    listeners.forEach(function (f) { f(); });
  }
  var painters = {};
  read();
  document.querySelectorAll('article.task[data-task]').forEach(function (card) {
    var ctl = card.querySelector('.tact');
    if (!ctl) return;
    var id = card.getAttribute('data-task');
    var link = card.querySelector('.ask');
    var title = link ? link.textContent : id;
    var meta = card.querySelector('.tmeta');
    if (!meta) { meta = el('div', 'tmeta'); card.insertBefore(meta, card.firstChild); }
    var tag = el('span', 'tag pend');
    var buttons = ctl.querySelectorAll('button[data-action]');
    var area = card.querySelector('textarea.tnote-in');
    var holder = card.querySelector('.shots');
    function paint() {
      var e = cache[id] || {};
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].setAttribute('aria-pressed', String(e.action === buttons[i].getAttribute('data-action')));
      }
      if (area && document.activeElement !== area) area.value = e.note || '';
      var words = LABEL[e.action] || (pending(e) ? 'Note' : '');
      tag.textContent = words ? words + ' · not saved' : '';
      if (words && !tag.parentNode) meta.appendChild(tag);
      if (!words && tag.parentNode) tag.remove();
      card.classList.toggle('pending', !!words);
    }
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var act = this.getAttribute('data-action');
        // Pressing the chosen one again clears it.
        edit(id, title, function (e) { e.action = e.action === act ? '' : act; });
        paint();
      });
    }
    ctl.addEventListener('click', function (ev) { ev.stopPropagation(); });
    var redraw = function () {};
    if (area) {
      area.addEventListener('input', function () {
        edit(id, title, function (e) { e.note = area.value; });
        paint();
      });
      if (holder) {
        redraw = P.attachShots(area, holder,
          function () { return ((cache[id] || {}).shots || []).slice(); },
          function (list) { edit(id, title, function (e) { e.shots = list; }, true); paint(); });
      }
    }
    painters[id] = function () { paint(); redraw(); };
    painters[id]();
  });
  function entries() {
    var all = read();
    return Object.keys(all).filter(function (k) { return pending(all[k]); }).sort().map(function (k) {
      var a = all[k];
      return { id: k, action: a.action || '', note: a.note || '', shots: a.shots || [], title: a.title || '' };
    });
  }
  window.BoardTasks = {
    entries: entries,
    /* Plain lines for Copy instead: one per task, the note indented beneath. */
    lines: function () {
      var NL = String.fromCharCode(10);
      return entries().map(function (a) {
        var s = (a.action === 'done' ? 'DONE' : a.action === 'do_now' ? 'DO NOW' : 'NOTE') + ' · ' + a.id + ' ' + a.title;
        if (a.note.trim()) s += NL + '    ' + a.note.split(NL).join(NL + '    ');
        if (a.shots.length) s += NL + '    (' + a.shots.length + ' screenshot(s): use Save to send them)';
        return s;
      });
    },
    /* The saved entries leave storage, and their cards are drawn clean again. */
    forget: function (ids) {
      var all = read();
      ids.forEach(function (k) { delete all[k]; });
      cache = all;
      try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (e) {}
      Object.keys(painters).forEach(function (k) { painters[k](); });
      listeners.forEach(function (f) { f(); });
    },
    onChange: function (fn) { listeners.push(fn); }
  };
})();
</script>""".replace("__KEY__", TASK_KEY)

TASK_BAR = """<div class="bar">
  <span id="tally"></span>
  <span id="savenote" role="status"></span>
  <button id="save" class="primary">Save my verdicts</button>
  <button id="copy">Copy instead</button>
  <button id="reset">Clear</button>
</div>"""

TASK_SAVE_JS = r"""<script>
/* The save bar of a page that shows only tasks (page_js.py): the same bar as a board's, saving a
   task-actions file that apply_verdicts.py reads from the same folders as verdicts. */
(function () {
  var P = window.BoardPage, T = window.BoardTasks;
  var NL = String.fromCharCode(10);
  function note(text) { document.getElementById('savenote').textContent = text; }
  function tally() {
    var n = T.entries().length;
    document.getElementById('tally').textContent = n
      ? n + ' task action' + (n === 1 ? '' : 's') + ' ready. Saving writes them to a file for the agent and clears them here.'
      : 'Mark a task Do now or Done, or leave a note, then save. One message in the thread is enough to make the conductor read it.';
  }
  T.onChange(tally);
  document.getElementById('save').addEventListener('click', function () {
    var list = T.entries();
    if (!list.length) { window.alert('Nothing decided yet.'); return; }
    var out = { schema: '__SCHEMA__', board: 'tasks', savedAt: new Date().toISOString(), tasks: list };
    var name = '__PREFIX__' + out.savedAt.slice(0, 19).replace(/[:T]/g, '-') + '.json';
    P.download(name, JSON.stringify(out, null, 2));
    note('Downloaded ' + name + '. Save it in any folder inside Downloads, then tell the conductor.');
    var btn = this;
    btn.textContent = 'Saved - tell the conductor';
    setTimeout(function () { btn.textContent = 'Save my verdicts'; }, 2600);
    T.forget(list.map(function (a) { return a.id; }));
  });
  document.getElementById('copy').addEventListener('click', function () {
    var list = T.entries();
    if (!list.length) { window.alert('Nothing decided yet.'); return; }
    var text = ['Tasks, ' + new Date().toISOString().slice(0, 10), '', T.lines().join(NL)].join(NL);
    var ids = list.map(function (a) { return a.id; });
    var btn = this;
    function done() {
      btn.textContent = 'Copied';
      setTimeout(function () { btn.textContent = 'Copy instead'; }, 1400);
      T.forget(ids);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        if (window.prompt('Copy this:', text) !== null) T.forget(ids);
      });
    } else if (window.prompt('Copy this:', text) !== null) { T.forget(ids); }
  });
  document.getElementById('reset').addEventListener('click', function () {
    if (!window.confirm('Clear every task action you have not saved?')) return;
    T.forget(T.entries().map(function (a) { return a.id; }));
  });
  tally();
})();
</script>""".replace("__SCHEMA__", TASK_SCHEMA).replace("__PREFIX__", TASK_PREFIX)
