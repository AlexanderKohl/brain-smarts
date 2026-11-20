"""Round-2 review fixes on a personal store with two computers: deleting a rotating sign-in whole, a
grant bound to its oauth id for life, the provider recorded in the policy and bound into a
supersession, and the supersede command refused while no provider profile is verified. Every value
is fictional."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_secret_store_broker import FIELD, StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401

import brain_secrets  # noqa: E402
from secret_store import SecretStoreError, oauth_ops, signing  # noqa: E402
from secret_store.accept_rules import check_supersession  # noqa: E402
from secret_store.keys import key_id  # noqa: E402
from secret_store.policy import Policy  # noqa: E402
from secret_store.store_ops import next_policy  # noqa: E402


class RotatingSignIns(StoreFixture):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())
        self.a.open()
        self.signin = oauth_ops.find(self.a, "xero-demo", FIELD, "personal")

    def policy_write(self, change):
        a = self.a
        a._write(lambda: ({"policy.json": next_policy(a.policy, a._identity().ed25519, change)}, "policy"))

    def assert_deleted(self, name):
        before = len(list(self.a.repo.commits()))
        self.a.delete_entry(name)
        self.assertEqual(len(list(self.a.repo.commits())), before + 1)
        doc = self.a.policy.doc
        for oid in (self.signin.oauth_id, self.signin.grant_id):
            self.assertIn(oid, doc["retired"])
            self.assertNotIn(oid, doc["assignments"])
        self.assertNotIn(self.signin.grant_id, doc["refreshers"])
        self.assertFalse([n for n in self.a._index() if n.startswith("xero-demo")])
        self.assertIsNone(oauth_ops.find(self.b.open(), "xero-demo", FIELD, "personal"))  # B accepts the commit

    def test_delete_by_entry_name_removes_the_whole_signin(self):
        self.assert_deleted("xero-demo")

    def test_delete_by_signin_name_removes_the_pair(self):
        self.assert_deleted(f"xero-demo#{FIELD}")

    def test_grant_may_not_be_rebound_to_another_oauth_id(self):
        self.sign_in(self.ba, "xero-two", self.token())
        self.a.open()
        other = oauth_ops.find(self.a, "xero-two", FIELD, "personal")
        one, two = self.signin.grant_id, other.grant_id

        def swap(doc):
            doc["refreshers"][one]["oauth"], doc["refreshers"][two]["oauth"] = (
                doc["refreshers"][two]["oauth"], doc["refreshers"][one]["oauth"])
        with self.assertRaisesRegex(SecretStoreError, "rebound"):
            self.policy_write(swap)

    def test_recorded_provider_is_immutable(self):
        # A new sign-in records its provider ("xero" for this entry); changing it is refused.
        for oid in (self.signin.oauth_id, self.signin.grant_id):
            self.assertEqual(self.a.policy.doc["assignments"][oid].get("provider"), "xero")

        def record(doc):
            for oid in (self.signin.oauth_id, self.signin.grant_id):
                doc["assignments"][oid]["provider"] = "google"
        with self.assertRaisesRegex(SecretStoreError, "provider"):
            self.policy_write(record)

    def test_policy_accepts_a_recorded_provider_and_binds_the_pair(self):
        doc = dict(self.a.policy.doc)
        doc["assignments"] = {k: dict(v) for k, v in doc["assignments"].items()}
        for oid in (self.signin.oauth_id, self.signin.grant_id):
            doc["assignments"][oid]["provider"] = "xero"
        self.assertEqual(Policy(doc).provider(self.signin.grant_id), "xero")
        doc["assignments"][self.signin.oauth_id]["provider"] = "google"
        with self.assertRaisesRegex(SecretStoreError, "bad oauth id"):
            Policy(doc)

    def test_supersession_provider_must_be_the_recorded_one(self):
        gid, signer = self.signin.grant_id, self.a._identity().ed25519

        def move(doc):
            doc["refreshers"][gid].update(computer="B")
            doc["people"]["alec"]["disabled_refresher"].append("A")
        result = Policy(next_policy(self.a.policy, signer, move))
        body = {"schema": 1, "type": "supersession", "repository": result.repository, "grant": gid,
                "provider": "google", "person": "alec", "computer": "A", "confirmation": "revoked in the console",
                "writer": key_id(signer.public_key())}
        with self.assertRaisesRegex(SecretStoreError, "provider recorded"):
            check_supersession(signing.sign(body, signer), self.a.policy, result)

    def test_supersede_command_is_refused_with_the_plain_message(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = brain_secrets.main(["supersede", "--entry", "xero-demo", "--to", "alec/B",
                                       "--confirmation", "revoked in the console"], store_factory=lambda: self.b)
        self.assertEqual(code, 1)
        self.assertRegex(err.getvalue(), "no (verified )?provider profile")
        self.assertEqual(self.b.open().policy.refresher(self.signin.grant_id), ("alec", "A"))


if __name__ == "__main__":
    unittest.main()
