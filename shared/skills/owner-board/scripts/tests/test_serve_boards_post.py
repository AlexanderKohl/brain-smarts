"""The board server's post plumbing (design 04, increment 1): the per-start token at
`GET /_board-server.json`, and the checks every `POST` passes before anything is saved – the
token, the page's own Origin, this machine's Host, a JSON content type and a bounded body. A
refused post writes nothing and says nothing about why; no answer carries a CORS header.
Every name is invented (SMART-RULE-0008): the owner is Sam (author `sam`). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_serve_boards_post.py" -v
"""
from __future__ import annotations

import datetime
import http.client
import json
import threading
import unittest
from pathlib import Path

from board_fixtures import Brain  # noqa: E402  (puts the scripts folder on sys.path)

import page_js  # noqa: E402
import serve_boards  # noqa: E402

TASKS_BODY = {"schema": page_js.TASK_SCHEMA, "board": "tasks", "savedAt": "2026-01-10T10:00:00.000Z",
              "tasks": [{"id": "TASK-2026-0901", "action": "", "note": "the beds want mulch", "title": "Beds"}]}


class Running:
    """The server of a fictional brain on a free port of this machine, as `main` starts it."""

    def __init__(self, brain: Brain):
        handler = serve_boards.make_handler(brain.config())
        handler.log_message = lambda *a: None
        self.handler = handler
        self.server = serve_boards.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
                host: str | None = None, length: int | None = None):
        """(status, headers, body text). `length` sends that Content-Length and no body at all."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or "localhost:%d" % self.port)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        if length is not None:
            conn.putheader("Content-Length", str(length))
        elif body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders()
        if body is not None and length is None:
            conn.send(body)
        try:
            res = conn.getresponse()
            text = res.read().decode("utf-8", errors="replace")
            return res.status, {k.lower(): v for k, v in res.getheaders()}, text
        finally:
            conn.close()

    def token(self) -> str:
        return json.loads(self.request("GET", "/_board-server.json")[2])["token"]

    def post(self, path: str, body: dict | bytes, **overrides):
        """A post as the page makes it; an override of None leaves that header out."""
        raw = body if isinstance(body, bytes) else json.dumps(body, indent=2).encode("utf-8")
        headers = {"Content-Type": "application/json", "Origin": "http://localhost:%d" % self.port,
                   "X-Board-Token": self.token()}
        host = overrides.pop("host", None)
        length = overrides.pop("length", None)
        for name, value in overrides.items():
            name = {"content_type": "Content-Type", "origin": "Origin", "token": "X-Board-Token"}[name]
            if value is None:
                headers.pop(name)
            else:
                headers[name] = value
        return self.request("POST", path, raw, headers, host=host, length=length)


class PlumbingBase(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.addCleanup(self.brain.close)
        self.run_ = Running(self.brain)
        self.addCleanup(self.run_.close)
        self.inbox = self.brain.memory / "inbox"

    def written(self) -> list[str]:
        return sorted(p.name for p in self.inbox.iterdir()) if self.inbox.is_dir() else []


class ServerAnswerTests(PlumbingBase):
    """GET /_board-server.json: how a page finds the server and its token."""

    def test_the_answer_names_the_server_its_token_its_start_and_what_it_saves(self):
        status, headers, body = self.run_.request("GET", "/_board-server.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["content-type"])
        self.assertEqual(headers.get("cache-control"), "no-store")
        data = json.loads(body)
        self.assertEqual(sorted(data), ["mail", "saves", "server", "started", "token"])
        self.assertEqual(data["server"], 1)
        self.assertGreaterEqual(len(data["token"]), 40)
        self.assertIsNotNone(datetime.datetime.fromisoformat(data["started"]).tzinfo)
        self.assertIn("verdicts", data["saves"])
        self.assertIn("task-actions", data["saves"])
        self.assertIs(data["mail"], False)

    def test_the_token_is_the_same_for_one_start_and_differs_between_two(self):
        first = self.run_.token()
        self.assertEqual(self.run_.token(), first)
        second = Running(self.brain)
        self.addCleanup(second.close)
        self.assertNotEqual(second.token(), first)

    def test_the_token_is_refused_to_another_host(self):
        status, _, body = self.run_.request("GET", "/_board-server.json", host="attacker.example")
        self.assertEqual(status, 403)
        self.assertNotIn(self.run_.handler.token, body)

    def test_the_token_is_never_written_to_a_file(self):
        token = self.run_.token()
        for path in self.brain.root.rglob("*"):
            if path.is_file():
                with self.subTest(path=path.name):
                    self.assertNotIn(token, path.read_text(encoding="utf-8", errors="replace"))


class PostCheckTests(PlumbingBase):
    """Every miss is 403 with the same few words, and nothing is written."""

    def assert_refused(self, answer, status: int = 403):
        self.assertEqual(answer[0], status, answer[2])
        self.assertEqual(self.written(), [])

    def test_a_post_with_everything_right_is_answered(self):
        status, headers, body = self.run_.post("/_save/task-actions", TASKS_BODY)
        self.assertEqual(status, 200, body)
        self.assertIn("application/json", headers["content-type"])

    def test_a_post_without_the_token_or_with_a_wrong_one_is_refused(self):
        self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, token=None))
        self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, token="not-the-token"))
        self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, token=""))

    def test_a_token_from_an_earlier_start_is_refused(self):
        old = Running(self.brain)
        stale = old.token()
        old.close()
        self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, token=stale))

    def test_a_post_from_a_foreign_origin_or_with_none_is_refused(self):
        port = self.run_.port
        for origin in ("http://attacker.example", "http://localhost:%d" % (port + 1), "https://localhost:%d" % port,
                       "http://localhost", "null", None):
            with self.subTest(origin=origin):
                self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, origin=origin))

    def test_both_names_of_this_machine_are_its_own_origin(self):
        answer = self.run_.post("/_save/task-actions", TASKS_BODY, origin="http://127.0.0.1:%d" % self.run_.port)
        self.assertEqual(answer[0], 200, answer[2])

    def test_a_post_for_a_foreign_host_is_refused(self):
        self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, host="attacker.example:%d" % self.run_.port))

    def test_a_post_that_is_not_json_is_refused(self):
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", None):
            with self.subTest(content_type=ctype):
                self.assert_refused(self.run_.post("/_save/task-actions", TASKS_BODY, content_type=ctype))

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        status, _, _ = self.run_.post("/_save/task-actions", b"", length=25 * 1024 * 1024 + 1)
        self.assertEqual(status, 413)
        self.assertEqual(self.written(), [])

    def test_a_body_that_is_not_a_json_object_is_refused(self):
        for raw in (b"not json", b"[1, 2]", b"", "\"text\"".encode("utf-8")):
            with self.subTest(raw=raw):
                self.assert_refused(self.run_.post("/_save/task-actions", raw), 400)

    def test_a_post_anywhere_but_a_known_save_is_refused(self):
        for path in ("/_save/unknown", "/_save/", "/_save/task-actions/x", "/index.html", "/_board-server.json"):
            with self.subTest(path=path):
                self.assert_refused(self.run_.post(path, TASKS_BODY), 404)

    def test_every_refusal_says_the_same_few_words(self):
        bodies = {self.run_.post("/_save/task-actions", TASKS_BODY, token="x")[2],
                  self.run_.post("/_save/task-actions", TASKS_BODY, origin="http://attacker.example")[2],
                  self.run_.post("/_save/task-actions", TASKS_BODY, content_type="text/plain")[2]}
        self.assertEqual(len(bodies), 1)
        self.assertEqual(json.loads(bodies.pop()), {"refused": "not allowed"})

    def test_no_answer_carries_a_cors_header(self):
        answers = [self.run_.request("GET", "/_board-server.json"),
                   self.run_.request("GET", "/_boards-status.json"),
                   self.run_.request("GET", "/"),
                   self.run_.request("OPTIONS", "/_save/task-actions",
                                     headers={"Origin": "http://attacker.example", "Access-Control-Request-Method": "POST"}),
                   self.run_.post("/_save/task-actions", TASKS_BODY),
                   self.run_.post("/_save/task-actions", TASKS_BODY, token="x")]
        for status, headers, _ in answers:
            with self.subTest(status=status):
                self.assertFalse([h for h in headers if h.startswith("access-control-")])


class WithoutAToken(unittest.TestCase):
    """A handler made without `make_handler` (no token) refuses every post: fail closed."""

    def test_a_handler_without_a_token_refuses_posts_and_offers_none(self):
        self.assertIsNone(serve_boards.Handler.token)


if __name__ == "__main__":
    unittest.main()
