"""The board pages as clients of the board server (design 04, increment 6): the shared page code
(`page_js.py`: `BoardPage.server`, `post`, `save`, `say`, `show`) and the two save bars built on it,
the task pages' (`TASK_SAVE_JS`) and a registered board's status page (`page_html.py`, verdicts).

Two layers, both with a fake `fetch` so nothing reaches a server or a network:
- the shared code alone, run in node against a stub window: the token is asked once, an answer
  without a token or a kind the server does not offer falls back to the download, a 403 asks for a
  new token once, a refusal carries the server's own reason, a failed call falls back;
- the built pages in headless Chrome (Edge as the fallback, `CHROME` overrides the binary), opened
  from disk with `BoardPage.served` replaced: Save posts the same JSON the download would have
  held, shows the line to say with Copy, and clears the task actions only when the file was saved
  or downloaded, never on a refusal.

Every name is invented (SMART-RULE-0008). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_board_clients.py" -v
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from board_fixtures import Brain, quiet  # noqa: E402  (puts the scripts folder on sys.path)
from test_task_board import TaskBoardTests  # noqa: E402

import build_boards  # noqa: E402
import build_status  # noqa: E402
import page_js  # noqa: E402

NODE = shutil.which("node")
TASK = "TASK-2026-0915"       # in the shed's store: drawn on the personal page, not on the garden board's own


def find_browser() -> str | None:
    env = os.environ.get("CHROME")
    if env and Path(env).is_file():
        return env
    for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("LOCALAPPDATA", "")):
        for tail in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
            if root and Path(root, tail).is_file():
                return str(Path(root, tail))
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


BROWSER = find_browser()

INFO = {"server": 1, "token": "tok-one", "started": "x", "saves": ["verdicts", "task-actions", "inbox-decisions", "social-decisions"], "mail": False}

# ---- the shared code alone, in node ------------------------------------------------------------

NODE_HARNESS = r"""
var calls = [], logged = [], SERVER = null;
function Node(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.listeners = {}; }
Node.prototype.appendChild = function (c) { this.children.push(c); return c; };
Node.prototype.addEventListener = function (n, f) { this.listeners[n] = f; };
var document = { createElement: function (t) { return new Node(t); }, body: new Node('body'), addEventListener: function () {} };
var window = { location: { protocol: 'http:' }, document: document, fetch: function (url, opts) {
  opts = opts || {};
  calls.push({ url: url, method: opts.method || 'GET', token: (opts.headers || {})['X-Board-Token'] || null, type: (opts.headers || {})['Content-Type'] || null, body: opts.body || null });
  var a = SERVER(url, opts.method || 'GET', calls.filter(function (c) { return c.url === url; }).length);
  if (a === 'fail') return Promise.reject(new Error('offline'));
  return Promise.resolve({ ok: a[0] < 300, status: a[0], json: function () { return Promise.resolve(a[1]); } });
} };
var navigator = {};
var setTimeout = global.setTimeout;
"""

NODE_STEPS = r"""
var P = window.BoardPage;
P.download = function (name, text) { logged.push([name, JSON.parse(text).tasks.length]); };
var BODY = JSON.stringify({ schema: 'owner-board/task-actions/v1', savedAt: '2026-01-10T10:00:00.000Z', tasks: [{ id: 'T' }] });
var NAME = 'task-actions-2026-01-10-10-00-00.json';
var INFO = %(info)s;
var out = {};
function scenario(name, server, kind) {
  return function () {
    calls.length = 0; logged.length = 0; SERVER = server; P.forget();
    return P.save(kind || 'task-actions', NAME, BODY).then(function (res) {
      out[name] = { res: res, calls: calls.map(function (c) { return [c.method, c.url, c.token, c.type]; }), logged: logged.slice(), body: (calls.filter(function (c) { return c.method === 'POST'; })[0] || {}).body === BODY };
    });
  };
}
var steps = [
  scenario('saved', function (u) { return u === '/_board-server.json' ? [200, INFO] : [200, { saved: NAME, folder: '/memory/inbox/', say: 'Apply ' + NAME + ' (1 task action)' }]; }),
  scenario('refused', function (u) { return u === '/_board-server.json' ? [200, INFO] : [400, { refused: 'not a task-actions file' }]; }),
  scenario('no endpoint', function () { return [404, {}]; }),
  scenario('no token', function () { return [200, { server: 1 }]; }),
  scenario('kind not offered', function (u) { return u === '/_board-server.json' ? [200, Object.assign({}, INFO, { saves: ['verdicts'] })] : [500, {}]; }),
  scenario('new token', function (u, m, n) { return u === '/_board-server.json' ? [200, Object.assign({}, INFO, { token: n === 1 ? 'old' : 'new' })] : (calls.filter(function (c) { return c.method === 'POST'; }).length === 1 ? [403, { refused: 'not allowed' }] : [200, { saved: NAME, folder: '/memory/inbox/', say: 's' }]); }),
  scenario('token refused twice', function (u) { return u === '/_board-server.json' ? [200, INFO] : [403, { refused: 'not allowed' }]; }),
  scenario('call fails', function (u) { return u === '/_board-server.json' ? [200, INFO] : 'fail'; }),
  scenario('too large', function (u) { return u === '/_board-server.json' ? [200, INFO] : [413, { refused: 'the post is larger than 25 MB' }]; }),
  scenario('server answer fails', function () { return 'fail'; })
];
steps.reduce(function (chain, s) { return chain.then(s); }, Promise.resolve()).then(function () {
  // once: the token is asked for one time over several saves
  calls.length = 0; SERVER = function (u) { return u === '/_board-server.json' ? [200, INFO] : [200, { saved: NAME, folder: 'f', say: 's' }]; }; P.forget();
  return P.save('task-actions', NAME, BODY).then(function () { return P.save('task-actions', NAME, BODY); }).then(function () {
    out.askedOnce = calls.filter(function (c) { return c.url === '/_board-server.json'; }).length;
    // from disk
    window.location.protocol = 'file:'; calls.length = 0; logged.length = 0; P.forget();
    return P.save('task-actions', NAME, BODY).then(function (res) { out.disk = { res: res, calls: calls.length, logged: logged.length }; });
  });
}).then(function () {
  // show and say
  var node = new Node('span');
  var states = [P.show(node, { state: 'saved', name: 'n', folder: '/memory/inbox/', say: 'Apply n (1 task action)' }), node.textContent, node.children.length];
  var node2 = new Node('span'); states.push(P.show(node2, { state: 'refused', reason: 'a reason' }), node2.textContent, node2.children.length);
  var node3 = new Node('span'); states.push(P.show(node3, { state: 'downloaded', name: 'n.json' }), node3.textContent);
  out.shown = states;
  console.log(JSON.stringify(out));
}).catch(function (e) { console.log(JSON.stringify({ error: String(e && e.stack || e) })); });
"""


def node_run() -> dict:
    code = page_js.SHARED_JS
    script = re.search(r"<script>(.*)</script>", code, re.S).group(1)
    program = NODE_HARNESS + script + (NODE_STEPS % {"info": json.dumps(INFO)})
    run = subprocess.run([NODE, "-e", program], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


@unittest.skipUnless(NODE, "needs node to run the shared page code")
class SharedClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = node_run()

    def test_a_server_with_a_token_and_the_kind_gets_the_exact_body_with_the_token(self):
        got = self.out["saved"]
        self.assertEqual(got["calls"], [["GET", "/_board-server.json", None, None],
                                        ["POST", "/_save/task-actions", "tok-one", "application/json"]])
        self.assertTrue(got["body"], "the body posted is the exact text the download would have held")
        self.assertEqual(got["res"], {"state": "saved", "name": "task-actions-2026-01-10-10-00-00.json", "folder": "/memory/inbox/",
                                      "say": "Apply task-actions-2026-01-10-10-00-00.json (1 task action)"})
        self.assertEqual(got["logged"], [], "a saved file is not also downloaded")

    def test_the_servers_own_reason_for_a_refusal_is_carried_and_nothing_is_downloaded(self):
        for name, reason in (("refused", "not a task-actions file"), ("too large", "the post is larger than 25 MB")):
            self.assertEqual(self.out[name]["res"], {"state": "refused", "reason": reason}, name)
            self.assertEqual(self.out[name]["logged"], [], name)

    def test_no_endpoint_no_token_an_unoffered_kind_and_a_dead_server_all_download_as_before(self):
        for name in ("no endpoint", "no token", "kind not offered", "server answer fails", "call fails", "token refused twice"):
            self.assertEqual(self.out[name]["res"]["state"], "downloaded", name)
            self.assertEqual(self.out[name]["logged"], [["task-actions-2026-01-10-10-00-00.json", 1]], name)
        self.assertEqual([c[0] for c in self.out["kind not offered"]["calls"]], ["GET"], "no post for a kind the server does not offer")

    def test_a_403_asks_for_a_new_token_once_then_posts_again_and_a_second_403_falls_back(self):
        self.assertEqual([(c[0], c[2]) for c in self.out["new token"]["calls"]], [("GET", None), ("POST", "old"), ("GET", None), ("POST", "new")])
        self.assertEqual(self.out["new token"]["res"]["state"], "saved")
        self.assertEqual([c[0] for c in self.out["token refused twice"]["calls"]], ["GET", "POST", "GET", "POST"])

    def test_the_token_is_asked_for_once_and_a_page_from_disk_asks_nothing(self):
        self.assertEqual(self.out["askedOnce"], 1)
        self.assertEqual((self.out["disk"]["res"]["state"], self.out["disk"]["calls"], self.out["disk"]["logged"]), ("downloaded", 0, 1))

    def test_show_gives_the_line_to_say_with_copy_the_reason_or_the_download_note(self):
        saved, text, children, refused, reason, kids, downloaded, note = self.out["shown"]
        self.assertEqual((saved, children), ("saved", 2), "the line and a Copy button")
        self.assertEqual(text, "")           # the line is in the child node, with its button
        self.assertEqual((refused, reason, kids), ("refused", "Not saved: a reason", 0))
        self.assertEqual((downloaded, note), ("downloaded", "Downloaded n.json. Save it in any folder inside Downloads, then tell the conductor."))


# ---- the built pages, in a browser --------------------------------------------------------------

PRELUDE = r"""
<script>
window.OUT = {}; window.CALLS = []; window.LOGGED = []; window.SERVER = {};
(function () {
  var P = window.BoardPage;
  P.download = function (name, text) { window.LOGGED.push([name, JSON.parse(text).schema]); };
  P.served = function () { return true; };
  window.fetch = function (url, opts) {
    opts = opts || {};
    var body = opts.body ? JSON.parse(opts.body) : null;
    window.CALLS.push({url: url, method: opts.method || 'GET', token: (opts.headers || {})['X-Board-Token'] || null, body: body});
    var a = window.SERVER.answer(url, opts.method || 'GET');
    return Promise.resolve({ok: a[0] < 300, status: a[0], json: function () { return Promise.resolve(a[1]); }});
  };
})();
const INFO = %(info)s;
function wait(ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); }
function click(sel) { document.querySelector(sel).dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true})); }
function scenario(name, server, kind) {
  return function () {
    window.CALLS.length = 0; window.LOGGED.length = 0; window.SERVER = server;
    BoardPage.forget();
    try { localStorage.clear(); } catch (e) {}
    BoardTasks.forget(BoardTasks.entries().map(function (a) { return a.id; }));
    click('[data-task="%(task)s"] button[data-action="done"]');
    var before = BoardTasks.entries().length;
    document.getElementById('savenote').textContent = '';
    click('#save');
    return wait(60).then(function () {
      var post = window.CALLS.filter(function (c) { return c.method === 'POST'; })[0] || null;
      var note = document.getElementById('savenote');
      window.OUT[name] = {before: before, after: BoardTasks.entries().length, calls: window.CALLS.map(function (c) { return [c.method, c.url, c.token]; }),
        schema: post && post.body.schema, tasks: post && post.body.tasks.length, board: post && post.body.board, logged: window.LOGGED.slice(),
        note: note.textContent, copy: !!note.querySelector('button')};
    });
  };
}
const SAVED = {saved: 'x-2026-01-10-10-00-00.json', folder: '/memory/inbox/', say: 'Apply x-2026-01-10-10-00-00.json (1 task action)'};
var steps = [
  scenario('saved', {answer: function (u) { return u === '/_board-server.json' ? [200, INFO] : [200, SAVED]; }}),
  scenario('refused', {answer: function (u) { return u === '/_board-server.json' ? [200, INFO] : [400, {refused: 'not a task-actions file'}]; }}),
  scenario('no server', {answer: function () { return [404, {}]; }}),
  scenario('old server without the kind', {answer: function (u) { return u === '/_board-server.json' ? [200, {server: 1, token: 't', saves: [], mail: false}] : [500, {}]; }})
];
steps.reduce(function (chain, s) { return chain.then(s); }, Promise.resolve()).then(function () {
  document.getElementById('result').textContent = JSON.stringify(window.OUT);
}, function (e) { document.getElementById('result').textContent = JSON.stringify({error: String(e && e.stack || e)}); });
</script>
<pre id="result"></pre>
"""


def run_browser(page: str) -> dict:
    base = Path(tempfile.mkdtemp(prefix="board-client-"))
    try:
        path = base / "page.html"
        path.write_text(page, encoding="utf-8")
        cmd = [BROWSER, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
               f"--user-data-dir={base / 'profile'}", "--virtual-time-budget=8000", "--dump-dom", path.resolve().as_uri()]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    found = re.search(r'<pre id="result">(.*?)</pre>', run.stdout, re.S)
    if not found or not found.group(1).strip():
        raise AssertionError("the harness wrote no result: " + run.stderr[-800:])
    out = json.loads(html.unescape(found.group(1)))
    if "error" in out:
        raise AssertionError("the harness threw: " + out["error"])
    return out


@unittest.skipUnless(BROWSER, "no headless Chromium found: set CHROME to chrome.exe or msedge.exe, or install Google Chrome")
class PageClientTests(unittest.TestCase):
    """The task page's bar and a board's status page save through the shared code."""

    @classmethod
    def setUpClass(cls):
        base = TaskBoardTests("test_routing_follows_the_node_of_the_store_that_holds_the_task")
        base.setUp()
        try:
            base.build_all()
            memory = base.brain.memory
            prelude = PRELUDE % {"info": json.dumps(INFO), "task": TASK}
            cls.task_page = run_browser((memory / "boards" / "personal.html").read_text(encoding="utf-8").replace("</body>", prelude + "</body>"))
            garden = (memory / "projects/example-garden/status/status.html").read_text(encoding="utf-8")
            cls.board_page = run_browser(garden.replace("</body>", (PRELUDE % {"info": json.dumps(INFO), "task": "TASK-2026-0910"}) + "</body>"))
        finally:
            base.tearDown()

    def test_the_task_page_posts_task_actions_and_shows_the_line_to_say_with_copy(self):
        got = self.task_page["saved"]
        self.assertEqual(got["calls"], [["GET", "/_board-server.json", None], ["POST", "/_save/task-actions", "tok-one"]])
        self.assertEqual((got["schema"], got["board"], got["tasks"]), ("owner-board/task-actions/v1", "tasks", 1))
        self.assertIn("Apply x-2026-01-10-10-00-00.json (1 task action)", got["note"])
        self.assertTrue(got["copy"])
        self.assertEqual((got["before"], got["after"]), (1, 0), "a saved file clears the action from its card")
        self.assertEqual(got["logged"], [])

    def test_a_refused_task_save_shows_the_reason_and_keeps_the_action(self):
        got = self.task_page["refused"]
        self.assertIn("Not saved: not a task-actions file", got["note"])
        self.assertEqual((got["before"], got["after"], got["logged"]), (1, 1, []))

    def test_the_task_page_downloads_as_before_with_no_server_or_an_old_one(self):
        for name in ("no server", "old server without the kind"):
            got = self.task_page[name]
            self.assertEqual(got["logged"], [["task-actions-" + got["logged"][0][0][len("task-actions-"):], "owner-board/task-actions/v1"]], name)
            self.assertIn("Downloaded task-actions-", got["note"], name)
            self.assertEqual((got["before"], got["after"]), (1, 0), name + ": the download hands the action over, as it always did")
            self.assertEqual([c[0] for c in got["calls"] if c[0] == "POST"], [], name)

    def test_a_boards_status_page_posts_its_verdicts_file_as_the_verdicts_kind(self):
        got = self.board_page["saved"]
        self.assertEqual(got["calls"], [["GET", "/_board-server.json", None], ["POST", "/_save/verdicts", "tok-one"]])
        self.assertTrue(got["schema"].endswith("/verdicts/v1"), got["schema"])
        self.assertEqual(got["tasks"], 1, "a task action given on a board page travels in the verdicts file")
        self.assertIn("Apply x-2026-01-10-10-00-00.json", got["note"])
        self.assertTrue(got["copy"])
        self.assertEqual((got["before"], got["after"]), (1, 0))

    def test_a_boards_status_page_keeps_everything_on_a_refusal_and_downloads_without_a_server(self):
        refused = self.board_page["refused"]
        self.assertIn("Not saved: not a task-actions file", refused["note"])
        self.assertEqual((refused["before"], refused["after"], refused["logged"]), (1, 1, []))
        for name in ("no server", "old server without the kind"):
            got = self.board_page[name]
            self.assertEqual(len(got["logged"]), 1, name)
            self.assertRegex(got["logged"][0][0], r"-garden-\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d\.json$", name)
            self.assertIn("Downloaded ", got["note"], name)
            self.assertEqual((got["before"], got["after"]), (1, 0), name)


if __name__ == "__main__":
    unittest.main()
