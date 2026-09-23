"""Tests for ghl_oauth.client._request: a status the caller named is an answer, not a failure.

urllib raises on every 4xx and 5xx, so before this was fixed a caller that passed
`expected=(200, 404)` still met an exception on a 404 and could never take its own
"not found" branch. A project index reader fetches records that way, and one deleted record
in a staging sub-account crashed its `check`, `list` and `import` alike.

Nothing here reaches HighLevel: every request is answered by a fake opener.
Every name and id is invented (RULE-2026-0016).
"""

import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghl_oauth import client as c  # noqa: E402


def http_error(code, body=b'{"message":"nope"}'):
    """An HTTPError exactly as urllib.request.urlopen raises one."""
    return urllib.error.HTTPError(
        url="https://services.leadconnectorhq.com/objects/example/records/r1",
        code=code,
        msg="Not Found",
        hdrs={"Content-Type": "application/json"},
        fp=io.BytesIO(body),
    )


def raising(exc):
    return mock.patch.object(c.urllib.request, "urlopen", side_effect=exc)


class NamedErrorStatusIsReturned(unittest.TestCase):
    def test_a_404_the_caller_named_comes_back_as_a_status(self):
        with raising(http_error(404)):
            status, body, _ = c._request("GET", "https://example.invalid/r1", expected=(200, 404))
        self.assertEqual(status, 404)
        self.assertEqual(body, b'{"message":"nope"}')

    def test_the_whole_body_survives_not_the_truncated_message(self):
        long_body = b'{"message":"' + b"x" * 4000 + b'"}'
        with raising(http_error(404, long_body)):
            _, body, _ = c._request("GET", "https://example.invalid/r1", expected=(200, 404))
        self.assertEqual(body, long_body)

    def test_a_404_the_caller_did_not_name_still_raises(self):
        with raising(http_error(404)):
            with self.assertRaises(c.HighLevelOAuthError) as caught:
                c._request("GET", "https://example.invalid/r1")
        self.assertIn("404", str(caught.exception))

    def test_an_unnamed_500_still_raises_even_when_404_was_named(self):
        with raising(http_error(500, b'{"message":"boom"}')):
            with self.assertRaises(c.HighLevelOAuthError):
                c._request("GET", "https://example.invalid/r1", expected=(200, 404))

    def test_a_network_failure_still_raises(self):
        with raising(urllib.error.URLError("no route")):
            with self.assertRaises(c.HighLevelOAuthError):
                c._request("GET", "https://example.invalid/r1", expected=(200, 404))


class RateLimitRetryIsUnchanged(unittest.TestCase):
    def test_a_429_is_retried_first_and_only_then_read_as_a_named_status(self):
        """The retry the client already does must happen before `expected` is consulted,
        so naming 429 does not turn a rate limit into an instant answer."""
        error = http_error(429)
        error.headers = {"Retry-After": "0"}
        with mock.patch.dict("os.environ", {"GHL_RATE_LIMIT_RETRIES": "1"}):
            with raising(error), mock.patch.object(c.time, "sleep") as slept:
                status, _, _ = c._request("GET", "https://example.invalid/r1", expected=(200, 429))
        slept.assert_called_once()
        self.assertEqual(status, 429)

    def test_an_unnamed_429_still_raises_once_the_retries_are_spent(self):
        error = http_error(429)
        error.headers = {"Retry-After": "0"}
        with mock.patch.dict("os.environ", {"GHL_RATE_LIMIT_RETRIES": "1"}):
            with raising(error), mock.patch.object(c.time, "sleep") as slept:
                with self.assertRaises(c.HighLevelOAuthError):
                    c._request("GET", "https://example.invalid/r1")
        slept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
