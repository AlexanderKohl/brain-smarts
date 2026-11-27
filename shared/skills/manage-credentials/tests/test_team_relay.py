"""The brain's side of the team credential relay (design team-credential-relay.md, 7.1, 8.1, 8.2,
10.1 to 10.3): relay enrolments, the relay document, the transport, the revocation sorting, the
relay key's recovery file and Railway variable, and the administrator commands with the relay
replaced by a stand-in. Every person, key and value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import base64
import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402

from secret_store import SecretStoreError, canonical  # noqa: E402
from secret_store.journal import ProviderNotCalled, ProviderRefused  # noqa: E402
from secret_store.policy import Policy, create_trust_root, public_entry  # noqa: E402
from team_relay import client, commands, document, envelope, keygen, keys, revoke  # noqa: E402

VALUE = "fictional-relay-value-55501-not-a-secret"


class Member:
    def __init__(self, person, computer):
        self.person, self.computer = person, computer
        self.x25519, self.ed25519 = X25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.relay = Ed25519PrivateKey.generate()

    def entry(self):
        return public_entry(self.x25519.public_key(), self.ed25519.public_key())


def team():
    alice, bob = Member("alice", "laptop"), Member("bob", "desktop")
    recovery_x, recovery_e = X25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    people = {m.person: {"computers": {m.computer: m.entry()}, "disabled_refresher": []} for m in (alice, bob)}
    root = create_trust_root(people, public_entry(recovery_x.public_key(), recovery_e.public_key()),
                             {"ads": ["bob"]}, ["alice"], alice.ed25519)
    return Policy(root), alice, bob


RELAY_PUBLIC = base64.b64encode(X25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")


class Enrolments(unittest.TestCase):
    def test_an_enrolment_is_checked_against_the_computer_key(self):
        policy, _alice, bob = team()
        doc = keys.enrolment(policy.repository, "bob", "desktop", bob.relay, bob.ed25519)
        self.assertEqual(keys.verify_enrolment(doc, policy), ("bob", "desktop", keys.public_text(bob.relay)))
        forged = keys.enrolment(policy.repository, "bob", "desktop", bob.relay, Ed25519PrivateKey.generate())
        with self.assertRaises(SecretStoreError):
            keys.verify_enrolment(forged, policy)
        swapped = dict(doc, relay_key=keys.public_text(Ed25519PrivateKey.generate()))
        with self.assertRaises(SecretStoreError):
            keys.verify_enrolment(swapped, policy)  # the signature covers the key
        with self.assertRaises(SecretStoreError):
            keys.verify_enrolment(dict(doc, repository="another"), policy)


class RelayDocument(unittest.TestCase):
    def test_first_and_next_versions_verify(self):
        policy, alice, bob = team()
        first = document.first(policy, alice.ed25519, "https://relay.example.com/", RELAY_PUBLIC, "alice")
        view = document.verify(first, policy)
        self.assertEqual(view.url, "https://relay.example.com")
        second = document.next_version(first, policy, alice.ed25519,
                                       lambda d: d["computers"].setdefault("bob", {}).update(desktop="k"))
        self.assertEqual((second["epoch"], document.verify(second, policy).relay_key_of("bob", "desktop")), (2, "k"))

    def test_a_member_or_a_tampered_document_is_refused(self):
        policy, alice, bob = team()
        first = document.first(policy, alice.ed25519, "https://relay.example.com", RELAY_PUBLIC, "alice")
        with self.assertRaises(SecretStoreError):
            document.next_version(first, policy, bob.ed25519, lambda d: None)  # Bob administers nothing
        tampered = dict(first, relay={"url": "https://evil.example.net", "x25519": RELAY_PUBLIC})
        with self.assertRaises(SecretStoreError):
            document.verify(tampered, policy)

    def test_the_relayed_mark_is_read_beside_the_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "brain"
            root.mkdir()
            (root / "CONTRACT.md").write_text("contract", "utf-8")
            clone = Path(tmp) / "brain-team-relay"
            clone.mkdir()
            self.assertFalse(document.relayed("google-ads", root))
            (clone / "relay.json").write_bytes(canonical.dumps({"credentials": {"google-ads": {"relayed": True}}}))
            self.assertTrue(document.relayed("google-ads", root))
            self.assertFalse(document.relayed("meta", root))


class Transport(unittest.TestCase):
    def make(self, answers):
        sent = []

        def opener(request, timeout):
            sent.append(request)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        _policy, _alice, bob = team()
        return client.RelayClient("https://relay.example.com", "bob", "desktop", relay_key=bob.relay,
                                  opener=opener), sent, bob

    def test_a_call_is_signed_over_the_whole_body(self):
        body = json.dumps({"status": 200, "headers": [["Content-Type", "application/json"]],
                           "body": base64.b64encode(b'{"ok": true}').decode()}).encode()
        relay, sent, bob = self.make([(200, body)])
        answer = relay.call("google-ads", "post", "https://googleads.googleapis.com/v26/x", {"a": "b"}, b"{}")
        self.assertEqual((answer.status, answer.json()), (200, {"ok": True}))
        raw = sent[0].data
        bob.relay.public_key().verify(base64.b64decode(sent[0].get_header("Relay-signature")), raw)
        doc = canonical.loads(raw)
        self.assertEqual((doc["method"], doc["computer"], doc["token"]), ("POST", "bob/desktop", "default"))
        self.assertEqual(raw, canonical.dumps(doc))

    def test_refusals_and_failures_are_named(self):
        relay, _sent, _bob = self.make([(403, b'{"refused": "not-granted", "message": "no"}'),
                                        urllib.error.URLError("down"), (502, b"<html>")])
        with self.assertRaises(client.RelayRefused) as caught:
            relay.call("google-ads", "GET", "https://x.example.com/")
        self.assertEqual(caught.exception.code, "not-granted")
        for _ in range(2):
            with self.assertRaises(client.RelayUnreachable) as caught:
                relay.call("google-ads", "GET", "https://x.example.com/")
            self.assertIn("relay.example.com", str(caught.exception))

    def test_only_https(self):
        with self.assertRaises(SecretStoreError):
            client.RelayClient("http://relay.example.com", "bob", "desktop")


class Revocation(unittest.TestCase):
    def outcome(self, effect):
        def post(*_args, **_kwargs):
            if isinstance(effect, Exception):
                raise effect
            return 200, b""
        return revoke.google_revoke("1//old-refresh-55501", post).state

    def test_a_revocation_is_sorted_like_a_refresh(self):
        self.assertEqual(self.outcome(None), "dead")
        self.assertEqual(self.outcome(ProviderNotCalled("no network")), "alive")
        self.assertEqual(self.outcome(ProviderRefused(400, "invalid_token")), "dead")
        self.assertEqual(self.outcome(ProviderRefused(400, "unsupported")), "uncertain")
        self.assertEqual(self.outcome(TimeoutError("lost")), "uncertain")

    def test_the_probe_decides_an_uncertain_revocation(self):
        self.assertEqual(revoke.google_probe("ya29.old", lambda _url: 400).state, "dead")
        self.assertEqual(revoke.google_probe("ya29.old", lambda _url: 200).state, "alive")
        self.assertEqual(revoke.google_probe("ya29.old", lambda _url: 0).state, "uncertain")
        self.assertEqual(revoke.google_probe(None, lambda _url: 400).state, "uncertain")

    def test_tokens_are_found_inside_a_nested_record(self):
        record = {"oauth_token_json": json.dumps({"refresh_token": "1//r", "access_token": "a"})}
        self.assertEqual(revoke.find_token(record, "refresh_token"), "1//r")
        self.assertIsNone(revoke.find_token({"x": 1}, "refresh_token"))


class FakePolicy:
    def __init__(self):
        self.recovery_x = X25519PrivateKey.generate()
        from secret_store.keys import key_id
        self.rid = key_id(self.recovery_x.public_key())
        self.recovery = (self.rid, "sign")
        self.enc_keys = {self.rid: self.recovery_x.public_key()}
        self.repository = "0123456789abcdef0123456789abcdef"


class RelayKey(unittest.TestCase):
    def test_the_recovery_file_opens_only_with_the_recovery_key(self):
        policy, key = FakePolicy(), X25519PrivateKey.generate()
        sealed = keygen.seal_recovery(key, policy)
        self.assertEqual(keygen.open_recovery(sealed, policy.recovery_x).private_bytes_raw(), key.private_bytes_raw())
        with self.assertRaises(SecretStoreError):
            keygen.open_recovery(sealed, X25519PrivateKey.generate())

    def test_the_railway_variable_is_set_without_showing_the_key(self):
        key, posts = X25519PrivateKey.generate(), []
        with mock.patch.dict("os.environ", {"RAILWAY_API_TOKEN": ""}):
            with self.assertRaises(SecretStoreError):
                keygen.set_railway_variable(key, "p", "e", "s", lambda *a: {})
        out = io.StringIO()
        with mock.patch.dict("os.environ", {"RAILWAY_API_TOKEN": "railway-token-55501-fictional"}), \
                contextlib.redirect_stdout(out):
            keygen.set_railway_variable(key, "p", "e", "s",
                                        lambda token, body: posts.append(body) or {"data": {"variableUpsert": True}})
            with self.assertRaises(SecretStoreError):
                keygen.set_railway_variable(key, "p", "e", "s", lambda token, body: {"errors": [{"message": "x"}]})
        given = posts[0]["variables"]["input"]
        self.assertEqual((given["name"], given["serviceId"]), ("RELAY_PRIVATE_KEY", "s"))
        self.assertEqual(base64.b64decode(given["value"]), key.private_bytes_raw())
        self.assertNotIn(given["value"], out.getvalue())


class Envelope(unittest.TestCase):
    def test_bound_to_credential_and_revision(self):
        key = X25519PrivateKey.generate()
        sealed = envelope.seal(key.public_key(), "meta", 2, {"access_token": VALUE})
        self.assertEqual(envelope.open_(key, "meta", 2, sealed), {"access_token": VALUE})
        with self.assertRaises(SecretStoreError):
            envelope.open_(key, "meta", 3, sealed)


class FakeAdmin:
    """The relay's administrator endpoint, in memory."""

    def __init__(self, rows):
        self.rows, self.requests = rows, []

    def admin(self, action, args=None):
        self.requests.append((action, args or {}))
        if action == "status":
            return {"credentials": self.rows, "records": [], "switches": [], "policy_epoch": 1, "relay_epoch": 1}
        if action == "put":
            return {"test": "passed", "state": "pending-revoke"}
        if action == "advance":
            self.rows[0]["state"] = args["to"]
            return {"state": args["to"]}
        return {}


class Commands(unittest.TestCase):
    def setUp(self):
        out = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(out))
        self.addCleanup(stack.close)
        self.out = out

    def tearDown(self):
        self.assertNotIn(VALUE, self.out.getvalue())

    def test_put_seals_to_the_relay_key_at_the_next_revision(self):
        relay_key = X25519PrivateKey.generate()
        admin = FakeAdmin([{"name": "meta", "revision": 4, "state": "serving"}])
        view = mock.Mock(records={"meta": {}}, relay_public=relay_key.public_key())
        with mock.patch.object(client, "for_this_computer", return_value=(admin, (None, view, None))):
            self.assertEqual(commands.relay_put("meta", ["access_token"], ask=lambda t, f: ({"access_token": VALUE}, None)), 0)
        action, args = admin.requests[-1]
        self.assertEqual((action, args["revision"]), ("put", 5))
        self.assertEqual(envelope.open_(relay_key, "meta", 5, args["envelope"]), {"access_token": VALUE})

    def test_revoke_moves_on_only_when_the_old_secret_is_dead(self):
        admin = FakeAdmin([{"name": "google-ads", "revision": 2, "state": "pending-revoke"}])
        record = {"oauth_token_json": json.dumps({"refresh_token": "1//old-55501", "access_token": "a"})}
        with mock.patch.object(commands, "_admin_client", return_value=admin), \
                mock.patch.object(commands, "_old_signin", return_value=record), \
                mock.patch.object(revoke, "google_revoke", return_value=revoke.Outcome("uncertain", "lost")), \
                mock.patch.object(revoke, "google_probe", return_value=revoke.Outcome("uncertain", "no probe")):
            self.assertEqual(commands.relay_revoke("google-ads", "Google Ads", "oauth_token_json", None, False,
                                                   confirm=lambda _p: "google-ads"), 1)
        self.assertEqual(admin.rows[0]["state"], "pending-revoke")
        with mock.patch.object(commands, "_admin_client", return_value=admin), \
                mock.patch.object(commands, "_old_signin", return_value=record), \
                mock.patch.object(revoke, "google_revoke", return_value=revoke.Outcome("dead", "confirmed")):
            self.assertEqual(commands.relay_revoke("google-ads", "Google Ads", "oauth_token_json", None, False,
                                                   confirm=lambda _p: "google-ads"), 0)
        self.assertEqual(admin.rows[0]["state"], "pending-delete")
        self.assertIn("brain_secrets.py delete --entry Google Ads", self.out.getvalue())

    def test_revoke_needs_the_name_typed(self):
        admin = FakeAdmin([{"name": "google-ads", "revision": 2, "state": "pending-revoke"}])
        record = {"refresh_token": "1//old-55501"}
        with mock.patch.object(commands, "_admin_client", return_value=admin), \
                mock.patch.object(commands, "_old_signin", return_value=record), \
                mock.patch.object(revoke, "google_revoke") as called:
            self.assertEqual(commands.relay_revoke("google-ads", "E", "f", None, False, confirm=lambda _p: "no"), 1)
        called.assert_not_called()

    def test_serve_only_after_the_store_copy_is_gone(self):
        admin = FakeAdmin([{"name": "google-ads", "revision": 2, "state": "pending-revoke"}])
        with mock.patch.object(commands, "_admin_client", return_value=admin):
            self.assertEqual(commands.main(["relay-serve", "--credential", "google-ads"]), 1)
            admin.rows[0]["state"] = "pending-delete"
            self.assertEqual(commands.main(["relay-serve", "--credential", "google-ads"]), 0)
        self.assertEqual(admin.rows[0]["state"], "serving")


if __name__ == "__main__":
    unittest.main()
