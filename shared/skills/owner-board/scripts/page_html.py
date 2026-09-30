"""The status page's HTML and CSS template, filled in by build_status.build.

Moved unchanged from build_status.py. build_status.py imports these names back, so everything that
uses build_status sees the same names.
"""

from __future__ import annotations


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
.sentshots img { display:block; width:100%; height:auto; margin:6px 0 0; border:1px solid var(--line); border-radius:6px; cursor:zoom-in; }
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
  <span id="savenote" role="status"></span>
  <button id="save" class="primary">Save my verdicts</button>
  <button id="copy">Copy instead</button>
  <button id="reset">Clear</button>
</div>
<script id="config" type="application/json">__CONFIG__</script>
<script id="data" type="application/json">__DATA__</script>
__SHAREDJS__
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

  // Shared with the task pages (page_js.py): one copy of each.
  var P = window.BoardPage, TASKS = window.BoardTasks;
  var el = P.el, lightbox = P.lightbox;
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
      if (item.sent_back_images && item.sent_back_images.length) {
        var shown = el('div', 'sentshots');
        item.sent_back_images.forEach(function (src, i) {
          var im = document.createElement('img');
          im.src = src;
          im.alt = L.sentBack + ', screenshot ' + (i + 1);
          im.addEventListener('click', function (ev) { ev.stopPropagation(); lightbox({ image: src, imageAlt: im.alt }); });
          shown.appendChild(im);
        });
        body.appendChild(shown);
      }
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
        ? 'What happened, or what is in the way (optional) \u2013 you can paste a screenshot here'
        : 'Anything to add, either way (optional) \u2013 you can paste a screenshot here';
      why.value = mine.why || '';
      why.addEventListener('click', function (ev) { ev.stopPropagation(); });
      why.addEventListener('input', function () {
        saved[item.id] = saved[item.id] || {};
        saved[item.id].why = why.value;
        saved[item.id].title = item.title;
        store(KEY, saved);
      });
      c.appendChild(why);

      /* A screenshot pasted into the reason box travels with the verdict: shrunk to at most
         1600px wide so a handful fit in the browser's storage, shown as a thumbnail with a
         remove button, and saved beside the card when the verdict is applied. */
      var shots = el('div', 'shots');
      P.attachShots(why, shots,
        function () { return ((saved[item.id] || {}).shots || []).slice(); },
        function (list) {
          saved[item.id] = saved[item.id] || {};
          saved[item.id].title = item.title;
          saved[item.id].shots = list;
          localStorage.setItem(KEY, JSON.stringify(saved));
        });
      c.appendChild(shots);
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
    if (ctl) {
      c.insertBefore(ctl, body);
      var w2 = c.querySelector('.why'); if (w2) c.insertBefore(w2, body);
      var s2 = c.querySelector('.shots'); if (s2) c.insertBefore(s2, body);
    }

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

  function lines() {
    return Object.keys(saved).filter(function (k) { return saved[k].verdict; }).map(function (k) {
      var v = saved[k];
      var s = (v.verdict === 'accepted' ? 'ACCEPTED' : 'REWORK') + ' \\u00b7 ' + k;
      if (v.verdict === 'rework' && v.why) s += NL + '    ' + v.why.split(NL).join(NL + '    ');
      if (v.shots && v.shots.length) s += NL + '    (' + v.shots.length + ' screenshot(s): use Save my verdicts to send them)';
      return s;
    });
  }

  /* Task actions (Do now, Done, a note) travel with the verdicts: they are the owner's word too.
     They are kept under one key for every page, so whatever is pending is saved from here. */
  function tally() {
    var n = lines().length, t = TASKS.entries().length;
    var parts = [];
    if (n) parts.push(n + ' decision' + (n === 1 ? '' : 's'));
    if (t) parts.push(t + ' task action' + (t === 1 ? '' : 's'));
    document.getElementById('tally').textContent =
      parts.length ? parts.join(' and ') + ' ready. Saving writes them to a file for the conductor and clears them here.'
        : 'Decide on a card or a task, then save. One message in the thread is enough to make the conductor read it.';
  }
  TASKS.onChange(tally);

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

  /* Where the verdicts go. A page opened from disk cannot write a file, so it hands the browser
     a download. A folder remembered through the File System Access API was tried on
     26 September 2026 and failed twice on the owner's Chrome, in ways that could not be
     reproduced, so it was removed: the download is the one path. `apply_verdicts.py` reads
     Downloads and every folder directly inside it, so whichever folder the save dialog offers
     is fine. The file names its board in its name and its body; the signature rides along so
     a verdict on a card that has since changed is refused rather than applied. */
  function note(text) {
    document.getElementById('savenote').textContent = text;
  }
  function taskIds(list) { return list.map(function (a) { return a.id; }); }

  document.getElementById('save').addEventListener('click', function () {
    var decided = Object.keys(saved).filter(function (k) { return saved[k].verdict; });
    var tasks = TASKS.entries();
    if (!decided.length && !tasks.length) { window.alert('Nothing decided yet.'); return; }
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
          version: (byId[id] || {}).version || '',
          shots: saved[id].shots || []
        };
      }),
      // Every pending task action, whichever page it was given on: {id, action, note, shots, title}.
      tasks: tasks
    };
    var name = CONFIG.prefix + (out.board ? out.board + '-' : '')
      + out.savedAt.slice(0, 19).replace(/[:T]/g, '-') + '.json';
    var text = JSON.stringify(out, null, 2);
    var btn = this;
    P.download(name, text);
    note('Downloaded ' + name + '. Save it in any folder inside Downloads, then tell the conductor.');
    btn.textContent = 'Saved - tell the conductor';
    setTimeout(function () { btn.textContent = 'Save my verdicts'; }, 2600);
    TASKS.forget(taskIds(tasks));
    handOver(decided);
  });

  document.getElementById('copy').addEventListener('click', function () {
    var decided = Object.keys(saved).filter(function (k) { return saved[k].verdict; });
    var tasks = TASKS.entries();
    var l = lines().concat(TASKS.lines());
    if (!l.length) { window.alert('Nothing decided yet.'); return; }
    var text = [CONFIG.label + ' review, ' + new Date().toISOString().slice(0, 10), '', l.join(NL)].join(NL);
    var btn = this;
    function over() { TASKS.forget(taskIds(tasks)); handOver(decided); }
    function done() {
      btn.textContent = 'Copied';
      setTimeout(function () { btn.textContent = 'Copy instead'; }, 1400);
      over();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        // null means the prompt was cancelled, and a cancelled copy has handed nothing over.
        if (window.prompt('Copy this:', text) !== null) over();
      });
    } else if (window.prompt('Copy this:', text) !== null) { over(); }
  });

  document.getElementById('reset').addEventListener('click', function () {
    if (!window.confirm('Clear every verdict, including the ones you have handed over, and every unsaved task action?')) return;
    saved = {};
    handed = {};
    TASKS.forget(taskIds(TASKS.entries()));
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
