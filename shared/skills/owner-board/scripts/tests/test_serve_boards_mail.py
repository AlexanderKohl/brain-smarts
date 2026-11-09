"""The board server's full-text endpoint (design 04, increment 4): `POST /_mail/text` passes the same
checks as every post, answers only when the mail-review skill's `inbox_serve.py` is loaded
(`"mail": true` in `/_board-server.json`, else 404 and `"mail": false`), writes nothing and never
echoes the reason for a refused post. The fetching itself, read-only and with a fake Gmail service,
is tested in the mail-review skill (`test_inbox_serve.py`); here a stand-in fetcher is loaded.
Every name is invented (SMART-RULE-0008). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_serve_boards_mail.py" -v
"""
from __future__ import annotations

import json

from test_serve_boards_post import PlumbingBase  # noqa: E402

REQUEST = {"account": "example-gmail", "threadId": "t-1", "messageId": "m-1"}


class StandIn:
    """What `inbox_serve.Fetcher` is to the server: a `text(body)` that answers (status, data)."""

    def __init__(self):
        self.seen: list[dict] = []

    def text(self, body: dict) -> tuple:
        self.seen.append(body)
        if body.get("messageId") == "m-none":
            return 404, {"refused": "not in the snapshot"}
        return 200, {"text": "The whole message.", "chars": 18, "cut": False, "fetched": "2026-01-10T10:00:00+10:00"}


class MailTextTests(PlumbingBase):
    def setUp(self):
        super().setUp()
        self.fetcher = StandIn()
        self.run_.handler.inbox.fetcher = self.fetcher

    def post(self, body=REQUEST, **overrides):
        status, _, text = self.run_.post("/_mail/text", body, **overrides)
        return status, json.loads(text)

    def test_a_loaded_fetcher_turns_mail_true_in_the_servers_answer(self):
        status, _, body = self.run_.request("GET", "/_board-server.json")
        self.assertIs(json.loads(body)["mail"], True)

    def test_without_the_skill_mail_is_false_and_the_endpoint_is_a_404(self):
        self.run_.handler.inbox.fetcher = None
        status, _, body = self.run_.request("GET", "/_board-server.json")
        self.assertIs(json.loads(body)["mail"], False)
        self.assertEqual(self.post()[0], 404)

    def test_a_post_with_everything_right_is_answered_with_the_fetchers_answer(self):
        status, data = self.post()
        self.assertEqual((status, data["text"], data["cut"]), (200, "The whole message.", False))
        self.assertEqual(self.fetcher.seen, [REQUEST])

    def test_the_fetchers_refusal_status_and_reason_pass_through(self):
        self.assertEqual(self.post(dict(REQUEST, messageId="m-none")), (404, {"refused": "not in the snapshot"}))

    def test_every_post_check_applies_and_the_fetcher_is_never_asked(self):
        for name, over in {"no token": {"token": None}, "wrong token": {"token": "nope"}, "foreign origin": {"origin": "https://attacker.example"},
                           "no origin": {"origin": None}, "form content type": {"content_type": "text/plain"}, "foreign host": {"host": "attacker.example"}}.items():
            with self.subTest(name):
                status, data = self.post(**over)
                self.assertEqual((status, data), (403, {"refused": "not allowed"}))
        self.assertEqual(self.fetcher.seen, [])

    def test_a_body_that_is_not_a_json_object_is_refused_before_the_fetcher(self):
        status, _, text = self.run_.post("/_mail/text", b"[1, 2]")
        self.assertEqual(status, 400)
        self.assertEqual(self.fetcher.seen, [])

    def test_the_answer_carries_no_cors_header_and_nothing_is_written(self):
        status, headers, _ = self.run_.post("/_mail/text", REQUEST)
        self.assertFalse([h for h in headers if h.lower().startswith("access-control-")])
        self.assertEqual(self.written(), [])

    def test_a_get_of_the_mail_address_is_not_an_endpoint(self):
        status, _, _ = self.run_.request("GET", "/_mail/text")
        self.assertEqual(status, 404)
