"""Integration after the two fix rounds and the cooperative handover (design synced-secrets-repository.md,
section 9, Handing over item 1): one provider key, grant fields kept out of oauth revisions and static
objects, a superseded grant read as empty, the broker fixture enrolling for real, and a full handover in
a personal and a team repository. Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_secret_store_broker import FIELD, KEY, RT1, SECRET, StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401
from test_secret_store_team import TeamCase  # noqa: E402

import brain_secrets  # noqa: E402
from secret_store import SecretStoreError, handover, oauth_ops, provider_profiles  # noqa: E402
from secret_store.broker_backend import put_grant_fields  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.accept_rules import check_oauth_payload  # noqa: E402
from secret_store.journal import Journal  # noqa: E402
from secret_store.store_ops import next_policy, seal_object  # noqa: E402


class Fields(unittest.TestCase):
    def test_one_provider_key(self):
        self.assertEqual(oauth_ops.PROVIDER_KEY, "provider")

    def test_default_token_fields_include_the_camel_case_spellings(self):
        self.assertLessEqual({"accessToken", "expiresAt"}, provider_profiles.DEFAULT_TOKEN_FIELDS)

    def test_oauth_revision_may_not_change_a_grant_field(self):
        obj = {"id": "o1", "revision": 2}
        for name in ("refresh_token", "client_secret", "refreshToken"):
            with self.assertRaises(SecretStoreError):
                check_oauth_payload({"a": 1, name: "fictional"}, {"a": 1}, obj, False, False)

    def test_superseded_grant_reads_empty_until_the_new_revision(self):
        class Ident:
            @staticmethod
            def my_keys():
                return {"new-key": object()}

        class Stub:
            config = {"person": "alec", "computer": "B"}
            checkpoint = None

            class policy:  # noqa: N801
                @staticmethod
                def refresher(_oid):
                    return ("alec", "B")

            @staticmethod
            def _identity():
                return Ident()

            @staticmethod
            def _tree_object(oid, _cp):
                return {"id": oid, "readers": [{"key": "old-key"}]}

            @staticmethod
            def _open_object(obj):
                raise SecretStoreError(f"this computer is not a reader of object {obj['id']}")

        signin = oauth_ops.SignIn("e", FIELD, "o1", "g1", ("alec", "B"), True, None)
        self.assertEqual(oauth_ops.read_grant(Stub, signin), {})
        Stub.policy.refresher = staticmethod(lambda _oid: ("alec", "A"))
        with self.assertRaises(SecretStoreError):
            oauth_ops.read_grant(Stub, signin)


class PersonalHandover(StoreFixture):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())

    def signin(self, store):
        store.open()
        return oauth_ops.find(store, "xero-demo", FIELD, "personal")

    def test_new_signin_binds_its_provider_in_the_policy(self):
        signin = self.signin(self.a)
        for oid in (signin.oauth_id, signin.grant_id):
            self.assertEqual(self.a.policy.doc["assignments"][oid].get("provider"), "xero")

    def test_fixture_enrols_through_the_enrolment_exchange(self):
        self.a.put_entry("plain", {"api_key": KEY})
        c = self.enrol("C")
        self.assertEqual(c.open().get_record("plain")["api_key"], KEY)

    def test_put_sends_grant_fields_to_the_grant(self):
        answer = ({"client_secret": SECRET, "api_key": KEY}, None)
        self.assertEqual(brain_secrets.main(["put", "--entry", "acme-app", "--secret", "client_secret",
                                             "--secret", "api_key"], store_factory=lambda: self.a,
                                            ask=lambda _t, _f: answer), 0)
        self.assertEqual(self.a.get_record("acme-app"), {"api_key": KEY})
        signin = oauth_ops.find(self.a, "acme-app", FIELD, "personal")
        self.assertEqual(oauth_ops.read_grant(self.a, signin)["fields"], {"client_secret": SECRET})

    def cli(self, argv, store):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = brain_secrets.main(argv, store_factory=lambda: store, ask=lambda _t, _f: (
                {"client_secret": SECRET, "api_key": KEY}, None))
        return code, out.getvalue()

    def test_get_check_and_list_show_signins_by_entry_name_without_values(self):
        self.cli(["put", "--entry", "acme-app", "--secret", "client_secret", "--secret", "api_key"], self.a)
        code, text = self.cli(["get-check", "--entry", "acme-app"], self.a)
        self.assertEqual(code, 0)
        self.assertIn("acme-app has fields: api_key", text)
        self.assertIn("grant fields: client_secret", text)
        code, signin = self.cli(["get-check", "--entry", "xero-demo"], self.a)
        self.assertEqual(code, 0)
        self.assertIn("refresh_token", signin)
        self.assertIn("provider", signin)
        code, listed = self.cli(["list"], self.a)
        self.assertIn("acme-app", listed)
        self.assertIn("xero-demo", listed)
        for shown in (text, signin, listed):
            self.assertNotIn("#", shown)
            for value in (SECRET, KEY, RT1):
                self.assertNotIn(value, shown)

    def test_replace_keeps_the_grant_fields(self):
        put_grant_fields(self.a, "personal", "xero-demo", {"client_secret": SECRET})
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, self.token(), replace=True)
        fields = oauth_ops.read_grant(self.a, self.signin(self.a))["fields"]
        self.assertEqual(fields.get("client_secret"), SECRET)
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, self.token(), {"client_id": "fictional-id"}, replace=True)
        fields = oauth_ops.read_grant(self.a, self.signin(self.a))["fields"]
        self.assertEqual((fields.get("client_secret"), fields.get("client_id")), (SECRET, "fictional-id"))

    def test_release_refused_on_an_uncertain_record_leaves_the_refresher_enabled(self):
        journal = Journal(self.a.config["checkpoint_dir"], self.a._identity().x25519)
        key = self.signin(self.a).journal_key
        stack, _record = journal.begin(key, 1)
        stack.close()
        with self.assertRaises(SecretStoreError):
            handover.release(self.a, "xero-demo", "alec/B", journal=journal)
        self.assertFalse(journal.disabled(key))

    def test_supersede_moves_every_grant_of_the_lost_computer(self):
        self.sign_in(self.ba, "xero-two", self.token())
        with self.assertRaisesRegex(SecretStoreError, "no verified provider profile"):
            handover.supersede(self.b, None, "alec/B", "revoked at the provider", all_from="alec/A")
        code, _text = self.cli(["supersede", "--all-from", "alec/A", "--to", "alec/B", "--confirmation", "revoked"],
                               self.b)
        self.assertEqual(code, 1)  # refused with the plain message today: no profile is verified
        with mock.patch.object(provider_profiles, "recovery_refusal", return_value=None):
            handover.supersede(self.b, "xero-demo", "alec/B", "revoked at the provider")
        self.b.open()
        for entry in ("xero-demo", "xero-two"):
            self.assertTrue(oauth_ops.find(self.b, entry, FIELD, "personal").mine)

    def test_full_handover_between_two_computers(self):
        self.assertIn(oauth_ops.PROVIDER_KEY, oauth_ops.read_shared(self.a, self.signin(self.a)))
        handover.release(self.a, "xero-demo", "alec/B")
        journal = Journal(self.a.config["checkpoint_dir"], self.a._identity().x25519)
        with self.assertRaisesRegex(SecretStoreError, "switched off"):
            journal.check(self.signin(self.a).journal_key)
        handover.accept(self.b, "xero-demo")
        mine = self.signin(self.b)
        self.assertTrue(mine.mine)
        self.assertEqual(oauth_ops.read(self.b, mine)["refresh_token"], RT1)
        old = self.signin(self.a)
        self.assertFalse(old.mine)
        with self.assertRaisesRegex(SecretStoreError, "refreshes on B"):
            oauth_ops.read_grant(self.a, old)
        self.assertNotIn("refresh_token", self.ba.get_json("xero-demo", FIELD))
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["refresh_token"], RT1)

    def test_release_not_bound_to_the_revision_is_refused(self):
        handover.release(self.a, "xero-demo", "alec/B")
        gid = self.signin(self.a).grant_id
        path = handover.request_path(gid)
        req = self.a.repo.read(path)
        readers = sorted(r["key"] for r in req["revision"]["readers"])
        policy = self.a.policy
        req["revision"] = seal_object(policy, gid, "grant", {"token": {}, "fields": {}}, self.a._identity().ed25519,
                                      self.a.checkpoint.objects[gid], epoch=policy.epoch + 1, readers=readers)
        self.a._write(lambda: ({path: req}, "update"))
        with self.assertRaisesRegex(SecretStoreError, "not bound"):
            handover.accept(self.b, "xero-demo")

    def test_handover_without_a_release_is_refused(self):
        with self.assertRaisesRegex(SecretStoreError, "no release"):
            handover.accept(self.b, "xero-demo")
        gid = self.signin(self.b).grant_id
        b = self.b

        def move(doc):
            doc["refreshers"][gid]["computer"] = "B"
        with self.assertRaisesRegex(SecretStoreError, "release or supersession"):
            b._write(lambda: ({"policy.json": next_policy(b.policy, b._identity().ed25519, move)}, "policy"))

    def test_cli_handover(self):
        self.assertEqual(brain_secrets.main(["handover-release", "--entry", "xero-demo", "--to", "alec/B"],
                                            store_factory=lambda: self.a), 0)
        self.assertEqual(brain_secrets.main(["handover-accept", "--entry", "xero-demo"],
                                            store_factory=lambda: self.b), 0)
        self.assertTrue(self.signin(self.b).mine)


class TeamHandover(TeamCase):
    def test_handover_in_a_team_repository(self):
        admin, pinned = self.team_setup()
        bob = self.enrol_member(admin, pinned, "tb", "bob", "pc")
        team_ops.admit(admin, "bob", ["ops"])
        token = {"access_token": "fictional-access", "refresh_token": RT1, "token_type": "Bearer"}
        oauth_ops.put_signin(admin, "Ops sign-in", FIELD, token, group="ops")
        handover.release(admin, "Ops sign-in", "bob/pc", group="ops")
        handover.accept(admin, "Ops sign-in", group="ops")
        bob.open()
        mine = oauth_ops.find(bob, "Ops sign-in", FIELD, "ops")
        self.assertTrue(mine.mine)
        self.assertEqual(oauth_ops.read(bob, mine)["refresh_token"], RT1)
        theirs = oauth_ops.find(admin, "Ops sign-in", FIELD, "ops")
        self.assertFalse(theirs.mine)
        self.assertNotIn("refresh_token", oauth_ops.read(admin, theirs))

    def test_static_object_carries_its_group(self):
        admin, _pinned = self.team_setup()
        oid = admin._index("ops")["Ops API"]
        self.assertEqual(admin.repo.read(f"objects/{oid}.json")["group"], "ops")


if __name__ == "__main__":
    unittest.main()
