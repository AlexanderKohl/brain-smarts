"""vault_broker_client.broker_request as a real client calls it: the request it puts on the pipe.

Every other test stands in for broker_request with its own function, so the real one's signature
was never met: a refresh passes the journal's operation id as the payload key "operation", which
collided with the function's own first parameter and raised TypeError on a real Vault Agent (found
by the rehearsal with a real agent process). The connection here is an in-memory fake."""

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vault_broker_client  # noqa: E402


class FakeConnection:
    def __init__(self, reply: dict) -> None:
        self.reply, self.sent, self.closed = reply, [], False

    def send(self, request: dict) -> None:
        self.sent.append(request)

    def recv(self) -> dict:
        return self.reply

    def close(self) -> None:
        self.closed = True


class BrokerRequestPayload(unittest.TestCase):
    def _call(self, *args, **payload):
        connection = FakeConnection({"ok": True, "result": {"saved": True}})
        with mock.patch.object(vault_broker_client, "_connect", return_value=(connection, "session-token")):
            result = vault_broker_client.broker_request(*args, **payload)
        self.assertTrue(connection.closed)
        return result, connection.sent[0]

    def test_a_payload_key_named_operation_reaches_the_agent(self) -> None:
        result, request = self._call("set_json", entry="demo", field="oauth_token_json", value={},
                                     operation="journal-operation-1")
        self.assertEqual(result, {"saved": True})
        self.assertEqual(request["op"], "set_json")
        self.assertEqual(request["operation"], "journal-operation-1")
        self.assertEqual(request["token"], "session-token")

    def test_the_refresh_endings_send_their_operation_id(self) -> None:
        for how in ("abort_refresh", "release_refresh"):
            _result, request = self._call(how, entry="demo", field="oauth_token_json", operation="journal-operation-2")
            self.assertEqual((request["op"], request["operation"]), (how, "journal-operation-2"))

    def test_a_payload_cannot_replace_the_request_own_fields(self) -> None:
        for key in ("v", "id", "token", "op"):
            with self.assertRaises(TypeError):
                self._call("status", **{key: "from-the-caller"})


if __name__ == "__main__":
    unittest.main()
