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
import reconcile  # noqa: E402
import task_board  # noqa: E402
import verdicts  # noqa: E402

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
__FAVICON__
<style>
__TOKENS__
* { box-sizing:border-box; }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { padding:20px 16px 96px; max-width:1800px; margin:0 auto; }
header { display:flex; flex-wrap:wrap; gap:10px 16px; align-items:baseline; margin-bottom:14px; }
h1 { font-size:20px; margin:0; letter-spacing:-.01em; }
.sub { color:var(--muted); font-size:12.5px; }
.tracks { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:18px; }
.track {
  background:var(--surface); border:1px solid var(--line); border-radius:7px;
  padding:5px 9px; font-size:12px;
}
.track b { font-weight:600; }
.track i { font-style:normal; color:var(--muted); }

.board { display:flex; gap:12px; align-items:flex-start; overflow-x:auto; padding-bottom:8px; }
.col {
  background:var(--col); border-radius:10px; padding:10px; flex:1 1 0;
  min-width:250px; border:1px solid var(--line);
}
.colh {
  display:flex; align-items:baseline; gap:7px; margin:2px 4px 10px;
  font-size:11.5px; text-transform:uppercase; letter-spacing:.07em; font-weight:700; color:var(--muted);
}
.colh .n {
  background:var(--surface); border:1px solid var(--line); border-radius:20px;
  padding:0 7px; font-size:11px; letter-spacing:0; color:var(--ink);
}
.colh.act { color:var(--accent); }

.card {
  background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:8px; padding:9px 11px; margin-bottom:8px; box-shadow:var(--shadow); cursor:pointer;
}
.card:hover { border-color:var(--muted); }
.card.needs_review { border-left-color:var(--accent); }
.grp { display:flex; align-items:baseline; gap:8px; margin:16px 2px 7px;
  font-size:11.5px; font-weight:700; letter-spacing:0.07em; text-transform:uppercase;
  color:var(--ink-2); }
.grp:first-of-type { margin-top:4px; }
.grp .n { font-weight:600; letter-spacing:0; text-transform:none; opacity:0.75; }
.grp::after { content:''; flex:1; height:1px; background:var(--line); }
.card.rework, .card.waiting_on_you, .card.yours { border-left-color:var(--warn); }
.rev.owner { border-left:3px solid var(--warn); padding-left:9px; }
.card.open { cursor:default; }
.meta { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:6px; align-items:center; }
.tag {
  font-size:10px; letter-spacing:.04em; text-transform:uppercase; font-weight:700;
  background:var(--surface-2); color:var(--muted); border-radius:4px; padding:2px 6px;
}
.tag.hot { background:var(--accent); color:#fff; }
.tag.v { color:var(--ink); }
.tag.yes { background:var(--accent); color:#fff; }
.tag.no { background:var(--warn); color:#fff; }
.ask { font-weight:600; font-size:13.5px; margin:0; }
.card:not(.open) .ask {
  display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden;
}
.more { color:var(--muted); font-size:11.5px; margin:6px 0 0; }
.body { margin-top:9px; padding-top:9px; border-top:1px solid var(--line); }
.did { color:var(--muted); margin:0 0 8px; font-size:13px; }
.rev { margin:0; font-size:13px; }
.rev b { font-weight:600; }
.verdict { display:flex; flex-wrap:wrap; gap:14px; margin-top:9px; padding-top:8px; border-top:1px dashed var(--line); }
label.opt { display:flex; gap:6px; align-items:center; font-size:13px; cursor:pointer; }
label.opt input { width:15px; height:15px; accent-color:var(--accent); cursor:pointer; }
textarea.why {
  width:100%; margin-top:8px; min-height:50px; resize:vertical; padding:7px 9px;
  border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink);
  font:inherit; font-size:13px;
}
.empty { color:var(--muted); font-size:12.5px; padding:2px 4px 6px; }
.adrift {
  border:1px solid var(--warn); border-left:3px solid var(--warn); border-radius:9px;
  background:var(--surface); padding:11px 14px; margin:0 0 16px;
}
.adrift h3 { margin:0 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--warn); }
.adrift ul { margin:0; padding-left:18px; font-size:13px; }
.adrift li { margin:2px 0; }
.shot { display:block; margin:0 0 6px; border:1px solid var(--line); border-radius:6px; overflow:hidden; cursor:zoom-in; }
.lb {
  position:fixed; inset:0; background:rgba(8,12,16,.86); z-index:50; cursor:zoom-out;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:28px;
}
.lb img { max-width:100%; max-height:84vh; border-radius:6px; background:#fff; }
.lb p { color:#e7edf2; font-size:13px; margin:0; text-align:center; }
.shot img { display:block; width:100%; height:auto; }
.cap { color:var(--muted); font-size:11.5px; margin:0 0 8px; }
.where { font-size:13px; margin:0 0 8px; }
.where a { color:var(--accent); font-weight:600; }
.wcopy {
  font:inherit; font-size:13px; font-weight:600; color:var(--accent); background:none;
  border:0; border-bottom:1px dashed var(--accent); border-radius:0; padding:0 0 1px;
  cursor:copy;
}
.wcopy:hover { filter:none; border-bottom-style:solid; }
.blocked { color:var(--muted); font-size:11.5px; margin:5px 0 0; }
.free { color:var(--accent); font-size:11.5px; font-weight:600; margin:5px 0 0; }
.alarm { border-left-color:var(--warn); }

.bar {
  position:fixed; left:0; right:0; bottom:0; background:var(--surface);
  border-top:1px solid var(--line); padding:10px 16px;
  display:flex; flex-wrap:wrap; gap:10px; align-items:center; box-shadow:0 -2px 10px rgba(16,32,42,.10);
}
.bar span { color:var(--muted); font-size:12.5px; flex:1 1 220px; }
button {
  font:inherit; font-size:13.5px; border-radius:6px; padding:7px 13px; cursor:pointer;
  border:1px solid var(--line); background:var(--surface-2); color:var(--ink);
}
button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
button:hover { filter:brightness(.97); }

__TASKCSS__
@media (max-width:900px) {
  .board { display:block; overflow-x:visible; }
  .col { min-width:0; margin-bottom:12px; }
  .wrap { padding:18px 16px 110px; }
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <div class="sub">__MAIN__ __VERSION__ &middot; updated __GENERATED__ &middot; click a card for the detail</div>
  </header>
  <div class="tracks" id="tracks"></div>
  <div class="board" id="board"></div>
  __TASKS__
</div>
<div class="bar">
  <span id="tally"></span>
  <button id="save" class="primary">Save my verdicts</button>
  <button id="folder" hidden>Change folder</button>
  <button id="copy">Copy instead</button>
  <button id="reset">Clear</button>
</div>
<script id="config" type="application/json">__CONFIG__</script>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  // One source for a line break: a backslash escape here has to survive Python's parsing of
  // this file as well as the browser's.
  var NL = String.fromCharCode(10);
  var CONFIG = JSON.parse(document.getElementById('config').textContent);
  var DATA = JSON.parse(document.getElementById('data').textContent);
  var L = CONFIG.labels;
  var KEY = CONFIG.storage + '-verdicts';
  var OPENKEY = CONFIG.storage + '-open';
  var HANDKEY = CONFIG.storage + '-handed';
  var saved = {};
  var opened = {};
  var handed = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { saved = {}; }
  try { opened = JSON.parse(localStorage.getItem(OPENKEY) || '{}'); } catch (e) { opened = {}; }
  try { handed = JSON.parse(localStorage.getItem(HANDKEY) || '{}'); } catch (e) { handed = {}; }

  // Left to right is the way work travels. A card only ever moves right, except `rework`,
  // the one loop back, which has its own column so the loop is visible.
  var COLUMNS = [
    { key: 'queued', label: 'Queued' },
    { key: 'building', label: 'Being built' },
    { key: 'rework', label: 'Sent back' },
    { key: 'needs_review', label: L.needsReview, act: true, also: ['waiting_on_you'] },
    { key: 'yours', label: L.yours },
    { key: 'handed', label: 'Back with the conductor', quiet: true }
  ];
  var DECIDABLE = { needs_review: true, waiting_on_you: true, yours: true };

  /* Why a queued card has not started: another card in flight holds the same `area`.
     A card with no `area` declares nothing and can always start. */
  function blockers(item) {
    var mine = item.area || [];
    if (!mine.length) return [];
    var busy = DATA.items.filter(function (o) {
      return o.id !== item.id && (o.state === 'building' || o.state === 'rework');
    });
    return busy.filter(function (o) {
      return (o.area || []).some(function (a) { return mine.indexOf(a) >= 0; });
    }).map(function (o) { return o.id; });
  }

  /* A handed-over verdict moves its card only while the card still carries the signature it
     was decided against. Once the conductor records the verdict and regenerates, the
     signature changes and the board tells the truth from the files again. */
  function handedTo(item) {
    var h = handed[item.id];
    if (!h) return null;
    if (h.atSig ? h.atSig !== item.sig : h.atState !== item.state) return null;
    return h.verdict === 'rework' ? 'rework' : 'handed';
  }
  function placeOf(item) { return handedTo(item) || item.state; }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function store(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  var tracks = document.getElementById('tracks');
  Object.keys(DATA.tracks || {}).forEach(function (k) {
    var t = DATA.tracks[k];
    var n = el('div', 'track');
    n.appendChild(el('b', null, t.label));
    n.appendChild(el('i', null, (t.of ? ' ' + t.done + ' of ' + t.of : ' ongoing') + ' \\u00b7 ' + t.task));
    tracks.appendChild(n);
  });

  /* What git says that the board does not, drawn first and in the warning colour. */
  if ((DATA.adrift || []).length) {
    var warn = el('div', 'adrift');
    warn.appendChild(el('h3', null, DATA.adrift.length === 1 ? 'One thing is adrift' : DATA.adrift.length + ' things are adrift'));
    var ul = document.createElement('ul');
    DATA.adrift.forEach(function (s) { ul.appendChild(el('li', null, s)); });
    warn.appendChild(ul);
    document.querySelector('.tracks').insertAdjacentElement('afterend', warn);
  }

  var board = document.getElementById('board');

  // Nothing may vanish from this page: a state with no column is named loudly instead.
  var held = {};
  COLUMNS.forEach(function (c) {
    held[c.key] = true;
    (c.also || []).forEach(function (a) { held[a] = true; });
  });
  var lost = DATA.items.filter(function (i) { return !held[i.state]; });

  function draw() {
    board.textContent = '';
    COLUMNS.forEach(function (c) {
      var states = [c.key].concat(c.also || []);
      var rows = DATA.items.filter(function (i) { return states.indexOf(placeOf(i)) >= 0; });
      // The resting place only earns a column once something is in it.
      if (c.quiet && !rows.length) return;
      var col = el('div', 'col');
      var h = el('div', 'colh' + (c.act && rows.length ? ' act' : ''));
      h.appendChild(el('span', null, c.label));
      h.appendChild(el('span', 'n', String(rows.length)));
      col.appendChild(h);
      if (!rows.length) col.appendChild(el('div', 'empty', 'Nothing here.'));

      /* Cards are grouped by track inside a column. The column says what the owner has to DO
         with a card; the track says what it is ABOUT. Tracks appear in the order of
         `DATA.tracks`, so a new track appears at the end rather than reshuffling the rest.
         A column holding a single track draws its cards without a heading. */
      var order = Object.keys(DATA.tracks || {});
      var seen = [];
      rows.forEach(function (i) {
        var k = i.track || '';
        if (seen.indexOf(k) < 0) seen.push(k);
      });
      seen.sort(function (a, b) {
        var ia = order.indexOf(a), ib = order.indexOf(b);
        return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
      });
      if (seen.length < 2) {
        rows.forEach(function (item) { col.appendChild(card(item)); });
      } else {
        seen.forEach(function (k) {
          var mine = rows.filter(function (i) { return (i.track || '') === k; });
          if (!mine.length) return;
          var tr = (DATA.tracks || {})[k];
          var g = el('div', 'grp');
          g.appendChild(el('span', null, tr ? tr.label : (k || 'Everything else')));
          g.appendChild(el('span', 'n', String(mine.length)));
          col.appendChild(g);
          mine.forEach(function (item) { col.appendChild(card(item)); });
        });
      }
      board.appendChild(col);
    });

    if (lost.length) {
      var w = el('div', 'col');
      w.appendChild(el('div', 'colh act', 'Not on the board'));
      var c2 = el('div', 'card open alarm');
      c2.appendChild(el('p', 'ask', lost.length + ' item(s) have a state no column draws: ' +
        lost.map(function (i) { return i.id + ' (' + i.state + ')'; }).join(', ')));
      c2.appendChild(el('p', 'did', 'Add the state to COLUMNS in build_status.py.'));
      w.appendChild(c2);
      board.insertBefore(w, board.firstChild);
    }
    tally();
  }

  function card(item) {
    var moved = handedTo(item);
    var open = !!opened[item.id];
    var c = el('div', 'card ' + placeOf(item) + (open ? ' open' : ''));

    var meta = el('div', 'meta');
    var tr = (DATA.tracks || {})[item.track];
    meta.appendChild(el('span', 'tag hot', tr ? tr.label : item.track));
    // A version on a card means a build the owner can load; unmerged work carries no number.
    if (item.version) meta.appendChild(el('span', 'tag v', item.version));
    else if (item.state === 'waiting_on_you' || item.state === 'yours') {
      meta.appendChild(el('span', 'tag', 'not built yet'));
    }
    if (item.increment != null) {
      meta.appendChild(el('span', 'tag', 'inc ' + item.increment + (tr && tr.of ? '/' + tr.of : '')));
    }
    var mine = saved[item.id] || {};
    if (mine.verdict) {
      meta.appendChild(el('span', 'tag ' + (mine.verdict === 'accepted' ? 'yes' : 'no'),
        mine.verdict === 'accepted' ? 'accepted' : 'sent back'));
    }
    c.appendChild(meta);
    c.appendChild(el('p', 'ask', '\\u201c' + item.title + '\\u201d'));

    var body = el('div', 'body');
    body.appendChild(el('p', 'did', item.landed));
    if (item.image) {
      var fig = el('div', 'shot');
      fig.addEventListener('click', function (ev) { ev.stopPropagation(); lightbox(item); });
      var im = document.createElement('img');
      im.src = item.image;
      im.alt = item.imageAlt || 'What landed';
      im.loading = 'lazy';
      fig.appendChild(im);
      body.appendChild(fig);
      if (item.imageAlt) body.appendChild(el('p', 'cap', item.imageAlt));
    }
    /* Where to go to review it: a real link where the browser will follow one, and plain
       words where there is no address. An address a page may not open by itself (a browser
       extension page, for example) is copied instead: pasting it into the address bar is a
       navigation the person started, which the browser allows. Whether it copies is decided
       by the address itself, never by which field produced it. */
    if (item.where) {
      var w = el('p', 'where');
      w.appendChild(el('b', null, 'Where: '));
      var href = typeof item.where.href === 'string' ? item.where.href : '';
      var copyOnly = !!href && CONFIG.copyOnly.some(function (p) { return href.indexOf(p) === 0; });
      if (href && copyOnly) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'wcopy';
        btn.textContent = item.where.text;
        btn.title = 'Copy the address, then paste it into the address bar - the browser will not let this page open it for you';
        btn.addEventListener('click', function (ev) {
          ev.stopPropagation();
          var back = item.where.text;
          function done() {
            btn.textContent = 'Copied \\u2013 paste into the address bar';
            setTimeout(function () { btn.textContent = back; }, 2200);
          }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(href).then(done, function () { window.prompt('Copy this:', href); });
          } else { window.prompt('Copy this:', href); }
        });
        w.appendChild(btn);
      } else if (href) {
        var a = document.createElement('a');
        a.href = href;
        a.target = '_blank';
        a.rel = 'noreferrer';
        a.textContent = item.where.text;
        a.addEventListener('click', function (ev) { ev.stopPropagation(); });
        w.appendChild(a);
      } else {
        w.appendChild(document.createTextNode(item.where.text));
      }
      body.appendChild(w);
    }

    // The owner's words when they sent it back, above the conductor's line.
    if (item.sent_back) {
      var said = el('p', 'rev owner');
      said.appendChild(el('b', null, L.sentBack + ': '));
      said.appendChild(document.createTextNode(item.sent_back));
      body.appendChild(said);
    }

    var rev = el('p', 'rev');
    rev.appendChild(el('b', null, item.state === 'yours' || item.state === 'waiting_on_you' ? L.ownerTurn + ': ' : 'To check: '));
    rev.appendChild(document.createTextNode(item.review));
    body.appendChild(rev);

    // A card already handed over is not decided again; the verdict rides on it as a tag.
    if (DECIDABLE[item.state] && !moved) {
      var box = el('div', 'verdict');
      var why = el('textarea', 'why');
      [['accepted', item.state === 'yours' ? 'Done' : 'Accepted'], ['rework', 'Send back']].forEach(function (o) {
        var lab = el('label', 'opt');
        var cb = document.createElement('input');
        cb.type = 'radio';
        cb.name = 'v-' + item.id;
        cb.checked = mine.verdict === o[0];
        cb.addEventListener('change', function (ev) {
          ev.stopPropagation();
          saved[item.id] = saved[item.id] || {};
          saved[item.id].verdict = o[0];
          saved[item.id].title = item.title;
          store(KEY, saved);
          tally();
          var tg = c.querySelector('.tag.yes, .tag.no');
          if (!tg) { tg = el('span', ''); c.querySelector('.meta').appendChild(tg); }
          tg.className = 'tag ' + (o[0] === 'accepted' ? 'yes' : 'no');
          tg.textContent = o[0] === 'accepted' ? 'accepted' : 'sent back';
        });
        lab.addEventListener('click', function (ev) { ev.stopPropagation(); });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(o[1]));
        box.appendChild(lab);
      });
      c.appendChild(box);
      why.placeholder = item.state === 'yours'
        ? 'What happened, or what is in the way (optional)'
        : 'Anything to add, either way (optional)';
      why.value = mine.why || '';
      why.addEventListener('click', function (ev) { ev.stopPropagation(); });
      why.addEventListener('input', function () {
        saved[item.id] = saved[item.id] || {};
        saved[item.id].why = why.value;
        saved[item.id].title = item.title;
        store(KEY, saved);
      });
      c.appendChild(why);
    }

    if (moved) {
      var h2 = handed[item.id];
      var tagged = el('span', 'tag ' + (h2.verdict === 'accepted' ? 'yes' : 'no'),
        h2.verdict === 'accepted' ? L.accepted : L.sentBack);
      c.querySelector('.meta').appendChild(tagged);
      if (h2.verdict === 'rework' && h2.why) body.appendChild(el('p', 'did', '\\u201c' + h2.why + '\\u201d'));
    }
    var hint = el('p', 'more', 'Click for the detail');
    body.style.display = open ? 'block' : 'none';
    hint.style.display = open ? 'none' : 'block';
    c.appendChild(body);
    c.appendChild(hint);
    // Ask, decide, then the detail for anyone who wants it.
    var ctl = c.querySelector('.verdict');
    if (ctl) { c.insertBefore(ctl, body); var w2 = c.querySelector('.why'); if (w2) c.insertBefore(w2, body); }

    c.addEventListener('click', function () {
      var now = body.style.display === 'none';
      body.style.display = now ? 'block' : 'none';
      hint.style.display = now ? 'none' : 'block';
      c.classList.toggle('open', now);
      opened[item.id] = now;
      store(OPENKEY, opened);
    });
    return c;
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

  function lines() {
    return Object.keys(saved).filter(function (k) { return saved[k].verdict; }).map(function (k) {
      var v = saved[k];
      var s = (v.verdict === 'accepted' ? 'ACCEPTED' : 'REWORK') + ' \\u00b7 ' + k;
      if (v.verdict === 'rework' && v.why) s += NL + '    ' + v.why.split(NL).join(NL + '    ');
      return s;
    });
  }

  function tally() {
    var n = lines().length;
    document.getElementById('tally').textContent =
      n ? n + ' decision' + (n === 1 ? '' : 's') + ' ready. Saving writes them to a file for the conductor and clears this column.'
        : 'Decide on a card, then save. One message in the thread is enough to make the conductor read it.';
  }

  /* Handing over moves only what was actually saved or copied: a card that left the review
     column without the verdict reaching the conductor is a decision silently lost. */
  function handOver(decided) {
    var byId = {};
    DATA.items.forEach(function (i) { byId[i.id] = i; });
    decided.forEach(function (id) {
      var item = byId[id];
      if (!item || !saved[id]) return;
      handed[id] = { verdict: saved[id].verdict, why: saved[id].why || '', atSig: item.sig };
      delete saved[id];
    });
    store(HANDKEY, handed);
    store(KEY, saved);
    draw();
  }

  /* Where the verdicts go. Chrome lets a `file://` page write into a folder the owner chose
     once: the folder's handle is kept in IndexedDB, so every later save writes straight into
     it with no dialog. The first save asks for the board's own `verdicts-in` folder by name.
     Where that is not available, or the write fails, the page hands the browser a download as
     before, and `apply_verdicts.py` still reads Downloads. The file names its board in its
     name and its body, so any folder works; the signature rides along so a verdict on a card
     that has since changed is refused rather than applied. */
  var FOLDERDB = 'owner-board', FOLDERSTORE = 'folders';
  function folderDb() {
    return new Promise(function (ok, fail) {
      var req = indexedDB.open(FOLDERDB, 1);
      req.onupgradeneeded = function () { req.result.createObjectStore(FOLDERSTORE); };
      req.onsuccess = function () { ok(req.result); };
      req.onerror = function () { fail(req.error); };
    });
  }
  function folderGet() {
    return folderDb().then(function (db) {
      return new Promise(function (ok) {
        var req = db.transaction(FOLDERSTORE).objectStore(FOLDERSTORE).get(CONFIG.board);
        req.onsuccess = function () { ok(req.result || null); };
        req.onerror = function () { ok(null); };
      });
    }).catch(function () { return null; });
  }
  function folderPut(handle) {
    return folderDb().then(function (db) {
      return new Promise(function (ok) {
        var tx = db.transaction(FOLDERSTORE, 'readwrite');
        if (handle) tx.objectStore(FOLDERSTORE).put(handle, CONFIG.board);
        else tx.objectStore(FOLDERSTORE).delete(CONFIG.board);
        tx.oncomplete = tx.onerror = function () { ok(); };
      });
    }).catch(function () {});
  }
  function chooseFolder() {
    window.alert('Choose where verdicts are saved. This is asked once.' + NL + NL
      + 'Pick this folder:' + NL + CONFIG.inbox);
    return window.showDirectoryPicker({ id: 'verdicts-' + CONFIG.board, mode: 'readwrite' })
      .then(function (handle) {
        var want = CONFIG.inboxName;
        if (handle.name !== want && !window.confirm('That folder is "' + handle.name + '", not "'
            + want + '". Save there anyway?')) return chooseFolder();
        return folderPut(handle).then(function () { showFolder(handle); return handle; });
      });
  }
  function showFolder(handle) {
    var b = document.getElementById('folder');
    b.hidden = !handle;
    b.title = handle ? 'Verdicts are saved into "' + handle.name + '". Press to choose another folder.' : '';
  }
  function writeInto(handle, name, text) {
    return handle.queryPermission({ mode: 'readwrite' }).then(function (p) {
      return p === 'granted' ? p : handle.requestPermission({ mode: 'readwrite' });
    }).then(function (p) {
      if (p !== 'granted') throw new Error('permission ' + p);
      return handle.getFileHandle(name, { create: true });
    }).then(function (file) { return file.createWritable(); })
      .then(function (w) { return w.write(text).then(function () { return w.close(); }); });
  }
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
  var canPick = !!(window.showDirectoryPicker && window.indexedDB && CONFIG.inbox);
  if (canPick) folderGet().then(showFolder);
  document.getElementById('folder').addEventListener('click', function () {
    chooseFolder().catch(function () {});
  });

  document.getElementById('save').addEventListener('click', function () {
    var decided = Object.keys(saved).filter(function (k) { return saved[k].verdict; });
    if (!decided.length) { window.alert('Nothing decided yet.'); return; }
    var byId = {};
    DATA.items.forEach(function (i) { byId[i.id] = i; });
    var out = {
      schema: CONFIG.schema,
      board: DATA.id || CONFIG.board,
      savedAt: new Date().toISOString(),
      mainVersion: DATA.mainVersion || '',
      verdicts: decided.map(function (id) {
        return {
          id: id,
          verdict: saved[id].verdict,
          why: saved[id].why || '',
          sig: (byId[id] || {}).sig || '',
          version: (byId[id] || {}).version || ''
        };
      })
    };
    var name = CONFIG.prefix + (out.board ? out.board + '-' : '')
      + out.savedAt.slice(0, 19).replace(/[:T]/g, '-') + '.json';
    var text = JSON.stringify(out, null, 2);
    var btn = this;
    function done(where) {
      btn.textContent = 'Saved' + where + ' - tell the conductor';
      setTimeout(function () { btn.textContent = 'Save my verdicts'; }, 2600);
      handOver(decided);
    }
    if (!canPick) { download(name, text); done(''); return; }
    folderGet().then(function (handle) { return handle || chooseFolder(); })
      .then(function (handle) {
        return writeInto(handle, name, text).then(function () { done(' to ' + handle.name); });
      })
      .catch(function (err) {
        // Cancelling the folder choice saves nothing, so nothing is handed over.
        if (err && err.name === 'AbortError') return;
        download(name, text);
        done('');
      });
  });

  document.getElementById('copy').addEventListener('click', function () {
    var decided = Object.keys(saved).filter(function (k) { return saved[k].verdict; });
    var l = lines();
    if (!l.length) { window.alert('Nothing decided yet.'); return; }
    var text = [CONFIG.label + ' review, ' + new Date().toISOString().slice(0, 10), '', l.join(NL)].join(NL);
    var btn = this;
    function done() {
      btn.textContent = 'Copied';
      setTimeout(function () { btn.textContent = 'Copy my verdicts'; }, 1400);
      handOver(decided);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        // null means the prompt was cancelled, and a cancelled copy has handed nothing over.
        if (window.prompt('Copy this:', text) !== null) handOver(decided);
      });
    } else if (window.prompt('Copy this:', text) !== null) { handOver(decided); }
  });

  document.getElementById('reset').addEventListener('click', function () {
    if (!window.confirm('Clear every verdict, including the ones you have handed over?')) return;
    saved = {};
    handed = {};
    try { localStorage.removeItem(KEY); localStorage.removeItem(HANDKEY); } catch (e) {}
    location.reload();
  });

  /* The board is regenerated whenever the conductor records something, so a page left open
     reloads itself from disk – except while a reason is being typed or a picture is open.
     Scroll position is carried across so the reload is not felt. */
  var SCROLLKEY = CONFIG.storage + '-scroll';
  try {
    var back = sessionStorage.getItem(SCROLLKEY);
    if (back) { window.scrollTo(0, parseInt(back, 10) || 0); sessionStorage.removeItem(SCROLLKEY); }
  } catch (e) {}

  setInterval(function () {
    var el2 = document.activeElement;
    var typing = el2 && (el2.tagName === 'TEXTAREA' || el2.tagName === 'INPUT');
    if (typing || document.querySelector('.lb')) return;
    try { sessionStorage.setItem(SCROLLKEY, String(window.scrollY)); } catch (e) {}
    location.reload();
  }, 20000);

  draw();
})();
</script>
</body>
</html>
"""


def page_config(board: dict) -> dict:
    """Everything the page needs that is not card data, from the board's configuration."""
    owner = board.get("owner") or ""
    return {
        "board": board["id"],
        "copyOnly": list(board.get("copy_only_prefixes") or []),
        "inbox": verdicts.inbox(board) if board.get("folder") else "",
        "inboxName": os.path.basename(verdicts.inbox(board)) if board.get("folder") else "",
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
        .replace("__TASKCSS__", task_board.CSS)
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
