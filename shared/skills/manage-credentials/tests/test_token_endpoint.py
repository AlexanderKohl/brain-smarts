"""token_endpoint.post_token sorts a failed token-endpoint call into not sent (ProviderNotCalled),
refused (ProviderRefused) and uncertain (any other error), one test per row of the refresh-failure
plan's table; then the journal and the broker treat ProviderRefused like ProviderNotCalled and a
time-out after the request was written as uncertain. The socket is a fake behind the real
connection class: no network, no TLS. A bare local repository is the remote and a fake keyring the
keychain. Every value is fictional."""
import http.client
import io
import json
import socket
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portable_vault  # noqa: E402
import token_endpoint  # noqa: E402
from portable_vault import CredentialError  # noqa: E402
from secret_store.journal import Journal, ProviderNotCalled, ProviderRefused  # noqa: E402
from test_secret_store_broker import FIELD, AgentClients, setUpModule, tearDownModule  # noqa: E402,F401

URL = "https://token.example.com/oauth/token"
BODY = {"grant_type": "refresh_token", "refresh_token": "fictional-refresh-1"}
TOKEN = {"access_token": "fictional-access-2", "refresh_token": "fictional-refresh-2", "expires_in": 1800}


def answer(status, body, content_type="application/json"):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    return (f"HTTP/1.1 {status} X\r\nContent-Type: {content_type}\r\nContent-Length: {len(data)}\r\n"
            "Connection: close\r\n\r\n").encode() + data


class TimedOut(io.BytesIO):
    def readline(self, *args):
        raise socket.timeout("timed out")


class FakeSocket:
    def __init__(self, reply=None, send_error=None):
        self.reply, self.send_error, self.sent = reply, send_error, b""

    def sendall(self, data):
        if self.send_error:
            raise self.send_error
        self.sent += data

    def makefile(self, mode):
        return TimedOut() if self.reply is None else io.BytesIO(self.reply)

    def close(self):
        pass


class FakeNetwork:
    """Replaces http.client.HTTPSConnection.connect (socket, tunnel and TLS handshake) only: the
    helper's own connection class, its flag and http.client's request code all run for real."""

    def __init__(self, reply=None, connect_error=None, send_error=None):
        self.reply, self.connect_error, self.send_error = reply, connect_error, send_error
        self.connections, self.sockets = [], []

    def connect(self, conn):
        self.connections.append(conn)
        if self.connect_error:
            raise self.connect_error
        conn.sock = FakeSocket(self.reply, self.send_error)
        self.sockets.append(conn.sock)

    def __enter__(self):
        fake = self

        def connect(conn):
            fake.connect(conn)
        self._patches = [mock.patch.object(http.client.HTTPSConnection, "connect", connect),
                         mock.patch.object(token_endpoint.urllib.request, "getproxies", return_value={})]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


def post(**kw):
    return token_endpoint.post_token(URL, {"Accept": "application/json"}, BODY, **kw)


class NotSent(unittest.TestCase):
    def test_failure_inside_connect_is_provider_not_called(self):
        for error in (socket.gaierror("no such host"), ConnectionRefusedError("refused"),
                      OSError("network unreachable"), ssl.SSLError("handshake failed"),
                      socket.timeout("connect timed out")):
            with self.subTest(error=type(error).__name__), FakeNetwork(connect_error=error) as net:
                with self.assertRaises(ProviderNotCalled):
                    post()
                self.assertEqual(net.sockets, [])
                self.assertFalse(net.connections[0].handshake_done)

    def test_proxy_tunnel_failure_is_provider_not_called(self):
        with FakeNetwork(connect_error=OSError("Tunnel connection failed: 403")) as net, \
                mock.patch.object(token_endpoint.urllib.request, "getproxies",
                                  return_value={"https": "http://proxy.example.com:8080"}), \
                mock.patch.object(token_endpoint.urllib.request, "proxy_bypass", return_value=False):
            with self.assertRaises(ProviderNotCalled):
                post()
        conn = net.connections[0]
        self.assertEqual((conn.host, conn.port, conn._tunnel_host), ("proxy.example.com", 8080, "token.example.com"))

    def test_a_plain_http_address_is_refused_before_connecting(self):
        with FakeNetwork(reply=answer(200, TOKEN)) as net, self.assertRaises(ProviderNotCalled):
            token_endpoint.post_token("http://token.example.com/token", {}, BODY)
        self.assertEqual(net.connections, [])


class Refused(unittest.TestCase):
    def test_oauth_error_answer_is_provider_refused(self):
        for status, code in ((400, "invalid_request"), (400, "invalid_grant"), (401, "invalid_client")):
            with self.subTest(status=status, code=code), \
                    FakeNetwork(reply=answer(status, {"error": code, "error_description": "x" * 2000})):
                with self.assertRaises(ProviderRefused) as caught:
                    post()
                self.assertEqual((caught.exception.status, caught.exception.error), (status, code))
                self.assertEqual(len(caught.exception.body), 1000)
                self.assertNotIn("x" * 20, str(caught.exception))

    def test_refused_is_not_logged(self):
        with FakeNetwork(reply=answer(400, {"error": "invalid_grant"})), self.assertNoLogs(level="DEBUG"):
            with self.assertRaises(ProviderRefused):
                post()


class Uncertain(unittest.TestCase):
    def assert_uncertain(self, net, error=token_endpoint.TokenEndpointError):
        with net, self.assertRaises(error) as caught:
            post()
        self.assertNotIsInstance(caught.exception, (ProviderNotCalled, ProviderRefused))
        self.assertEqual(len(net.connections), 1)  # never retried
        self.assertTrue(net.connections[0].handshake_done)
        return caught.exception

    def test_failure_just_after_connect_is_uncertain(self):
        self.assert_uncertain(FakeNetwork(reply=answer(200, TOKEN), send_error=ConnectionResetError("reset")),
                              ConnectionResetError)

    def test_time_out_after_the_request_is_written_is_uncertain(self):
        net = FakeNetwork(reply=None)
        self.assert_uncertain(net, socket.timeout)
        self.assertIn(b"refresh_token=fictional-refresh-1", net.sockets[0].sent)

    def test_other_answers_are_uncertain(self):
        cases = ((500, {"error": "server_error"}, "application/json"), (503, b"<html>busy</html>", "text/html"),
                 (429, {"error": "rate_limited"}, "application/json"), (403, {"error": "access_denied"},
                                                                         "application/json"),
                 (400, b"<html>gateway</html>", "text/html"), (400, {"message": "no error field"},
                                                               "application/json"),
                 (401, {"error": 7}, "application/json"))
        for status, body, kind in cases:
            with self.subTest(status=status, body=body):
                error = self.assert_uncertain(FakeNetwork(reply=answer(status, body, kind)))
                self.assertEqual(error.status, status)


class Answered(unittest.TestCase):
    def test_a_token_is_returned_and_an_unreadable_200_is_left_to_the_connector(self):
        for body in (TOKEN, b"<html>not json</html>"):
            with self.subTest(body=body), FakeNetwork(reply=answer(200, body)) as net:
                status, data = post()
            self.assertEqual((status, data), (200, json.dumps(body).encode() if isinstance(body, dict) else body))
            sent = net.sockets[0].sent
            self.assertTrue(sent.startswith(b"POST /oauth/token HTTP/1.1"))
            self.assertIn(b"Content-Type: application/x-www-form-urlencoded", sent)

    def test_one_new_connection_per_call(self):
        with FakeNetwork(reply=answer(200, TOKEN)) as net:
            post()
            post()
        self.assertEqual(len(net.connections), 2)
        self.assertIsNot(net.connections[0], net.connections[1])
        self.assertIsNot(net.sockets[0], net.sockets[1])


class JournalOutcomes(unittest.TestCase):
    ENTRY = "xero-demo#oauth_token_json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.journal = Journal(self._tmp.name, X25519PrivateKey.generate())

    def refresh(self, net):
        def call():
            with net:
                return json.loads(post()[1])
        return self.journal.refresh(self.ENTRY, 1, call, lambda op, a: None, lambda op, a: False, provider="xero")

    def test_refused_leaves_no_record_and_the_next_refresh_calls_the_provider(self):
        with self.assertRaises(ProviderRefused):
            self.refresh(FakeNetwork(reply=answer(400, {"error": "invalid_grant"})))
        self.assertIsNone(self.journal.read(self.ENTRY))
        net = FakeNetwork(reply=answer(200, TOKEN))
        self.assertEqual(self.refresh(net)["access_token"], TOKEN["access_token"])
        self.assertEqual(len(net.connections), 1)

    def test_time_out_after_writing_leaves_calling(self):
        with self.assertRaises(socket.timeout):
            self.refresh(FakeNetwork(reply=None))
        self.assertEqual(self.journal.read(self.ENTRY)["state"], "calling")


class BrokerOutcomes(AgentClients):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())
        self.journal = self.ba._journal
        self.a = self.client(self.ba, "A")

    def refresh(self, net):
        with self.a.rotation_lock(refresh=True), net:
            fresh = json.loads(post()[1])
            self.a.save({**self.a.load(), "access_token": fresh["access_token"],
                         "refresh_token": fresh["refresh_token"]})

    def test_provider_refused_is_exported_from_portable_vault(self):
        self.assertIs(portable_vault.ProviderRefused, ProviderRefused)

    def test_refused_removes_the_record_releases_the_lock_and_allows_the_next_refresh(self):
        with self.assertRaises(ProviderRefused):
            self.refresh(FakeNetwork(reply=answer(400, {"error": "invalid_grant"})))
        self.assertEqual((self.journal.read(self.SIGNIN), self.ba._pending), (None, {}))
        net = FakeNetwork(reply=answer(200, TOKEN))
        self.refresh(net)
        self.assertEqual(len(net.connections), 1)
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], TOKEN["access_token"])

    def test_time_out_after_writing_stays_uncertain_and_blocks(self):
        with self.assertRaises(socket.timeout):
            self.refresh(FakeNetwork(reply=None))
        self.assertEqual((self.journal.read(self.SIGNIN)["state"], self.ba._pending), ("calling", {}))
        net = FakeNetwork(reply=answer(200, TOKEN))
        with self.assertRaisesRegex(CredentialError, "uncertain"):
            self.refresh(net)
        self.assertEqual(net.connections, [])


if __name__ == "__main__":
    unittest.main()
