"""brain_secrets.py replace-signin (design synced-secrets-repository.md, section 9, Handing over item 4;
refresh-failure plan part B): an uncertain sign-in is deleted in one administrator commit, its shared
settings kept in a local hand-over file, and the first new authorisation applies them. In-process
stores over bare local repositories and a fake keyring only. Every value is fictional."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_secret_store_broker import AT1, FIELD, RT1, StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401

import brain_secrets  # noqa: E402
from secret_store import SecretStoreError, oauth_ops, replace_ops  # noqa: E402
from secret_store.accept import accept_commit  # noqa: E402
from secret_store.journal import Journal, uncertain_message  # noqa: E402
from secret_store.repo import SecretRepo  # noqa: E402

ENTRY = "xero-demo"
AT2, RT2 = "fictional-access-two", "fictional-refresh-two"


class ReplaceSignin(StoreFixture):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, ENTRY, self.token())
        self.old = self.find(self.a)
        self.journal = Journal(self.a.config["checkpoint_dir"], self.a._identity().x25519)

    def find(self, store):
        store.open()
        return oauth_ops.find(store, ENTRY, FIELD, "personal")

    def make_uncertain(self):
        stack, _record = self.journal.begin(self.old.journal_key, 1)
        stack.close()

    def cli(self, argv, store):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = brain_secrets.main(argv, store_factory=lambda: store)
        text = out.getvalue() + err.getvalue()
        for value in (RT1, AT1, RT2, AT2):
            self.assertNotIn(value, text)
        return code, text

    def handover_files(self):
        return list(self.journal.folder.glob("*" + replace_ops.SUFFIX))

    def test_uncertain_message_names_the_command(self):
        text = uncertain_message(self.old.journal_key, "xero")
        self.assertIn('brain_secrets.py replace-signin "xero-demo"', text)
        self.assertNotIn("stays blocked", text)
        self.assertIn("sign in again in the browser", text)
        self.assertIn("brain_secrets.py delete --entry", text)  # the team step (follow-up plan M2)
        self.assertNotIn("--for", text)

    def test_uncertain_replace_new_authorisation_refresh_and_tenant_survive(self):
        self.make_uncertain()
        with self.assertRaisesRegex(SecretStoreError, "replace-signin"):
            self.ba.begin_refresh(ENTRY, FIELD)
        code, text = self.cli(["replace-signin", ENTRY], self.a)
        self.assertEqual(code, 0, text)
        self.assertIn("sign in again in the browser", text)
        policy = self.a.policy.doc
        for oid in (self.old.oauth_id, self.old.grant_id):
            self.assertIn(oid, policy["retired"])
            self.assertNotIn(oid, policy["assignments"])
        self.assertNotIn(self.old.grant_id, policy["refreshers"])
        self.assertNotIn(f"{ENTRY}#{FIELD}", self.a.list_entries())
        self.assertIsNone(self.journal.read(self.old.journal_key))
        self.assertEqual(len(self.handover_files()), 1)
        self.assertIn(f"Replaced sign-in {ENTRY} {FIELD}", self.a.status())

        self.sign_in(self.ba, ENTRY, {"access_token": AT2, "refresh_token": RT2, "expires_at": 19 * 10**8,
                                      "token_type": "Bearer"})
        new = self.find(self.a)
        self.assertNotIn(new.oauth_id, (self.old.oauth_id, self.old.grant_id))
        self.assertNotIn(new.grant_id, (self.old.oauth_id, self.old.grant_id))
        self.assertEqual(oauth_ops.read_shared(self.a, new)["tenant_id"], "tenant-1")
        self.assertEqual(self.handover_files(), [])
        self.assertNotIn("Replaced sign-in", self.a.status())

        begun = self.ba.begin_refresh(ENTRY, FIELD)  # the new sign-in refreshes normally
        self.ba.set_json(ENTRY, FIELD, {"access_token": "fictional-access-three", "refresh_token": RT2,
                                        "expires_at": 19 * 10**8 + 3600, "token_type": "Bearer"},
                         operation=begun["operation"])
        record = self.ba.get_json(ENTRY, FIELD)
        self.assertEqual((record["access_token"], record["tenant_id"]), ("fictional-access-three", "tenant-1"))
        self.assertEqual(self.bb.get_json(ENTRY, FIELD)["tenant_id"], "tenant-1")

    def test_a_follower_computer_is_refused(self):
        self.make_uncertain()
        before = self.b.open().policy.hash
        code, text = self.cli(["replace-signin", ENTRY], self.b)
        self.assertEqual(code, 1)
        self.assertIn("replace it there", text)
        self.assertEqual(self.b.open().policy.hash, before)
        self.assertEqual(self.handover_files(), [])

    def test_a_non_administrator_refresher_is_given_the_administrator_step(self):
        self.make_uncertain()
        before = self.a.open().policy.hash
        with mock.patch("secret_store.policy.Policy.is_admin_key", return_value=False):
            code, text = self.cli(["replace-signin", ENTRY], self.a)
        self.assertEqual(code, 3, text)  # follow-up plan M2: the step, not a refusal; nothing changed
        self.assertIn("an administrator", text)
        self.assertIn(f'brain_secrets.py delete --entry "{ENTRY}"', text)
        self.assertNotIn("--group", text)  # a personal sign-in
        self.assertEqual(self.a.open().policy.hash, before)
        self.assertEqual(self.journal.read(self.old.journal_key)["state"], "calling")
        self.assertEqual(self.handover_files(), [])

    def test_a_working_signin_needs_even_if_working(self):
        code, text = self.cli(["replace-signin", ENTRY], self.a)
        self.assertEqual(code, 1)
        self.assertIn("--even-if-working", text)
        self.assertIsNotNone(self.find(self.a))
        code, text = self.cli(["replace-signin", ENTRY, "--even-if-working"], self.a)
        self.assertEqual(code, 0, text)
        self.assertIsNone(self.find(self.a))

    def test_a_failed_push_changes_nothing_and_keeps_the_handover_file(self):
        self.make_uncertain()
        before = self.a.open().policy.hash
        with mock.patch.object(SecretRepo, "write", side_effect=SecretStoreError("push refused")), \
                mock.patch.object(SecretRepo, "settle_failed_write", return_value=None):
            code, text = self.cli(["replace-signin", ENTRY], self.a)
        self.assertEqual(code, 1)
        self.assertEqual(self.a.open().policy.hash, before)
        self.assertEqual(self.find(self.a).oauth_id, self.old.oauth_id)
        self.assertEqual(self.journal.read(self.old.journal_key)["state"], "calling")
        self.assertEqual(len(self.handover_files()), 1)
        with self.assertRaisesRegex(SecretStoreError, "uncertain"):
            self.ba.begin_refresh(ENTRY, FIELD)  # still blocked, never retried with the old token
        code, text = self.cli(["replace-signin", ENTRY], self.a)  # the next run completes it
        self.assertEqual(code, 0, text)
        self.assertIsNone(self.find(self.a))

    def test_the_retired_ids_are_refused_when_replayed(self):
        old_files = {f"objects/{oid}.json": self.a._tree_object(oid, self.a.checkpoint)
                     for oid in (self.old.oauth_id, self.old.grant_id)}
        self.make_uncertain()
        self.assertEqual(self.cli(["replace-signin", ENTRY], self.a)[0], 0)
        store = self.a.open()
        with self.assertRaises(SecretStoreError):
            accept_commit(store.policy, store.checkpoint, old_files, store._identity().my_keys(),
                          store._baseline(store.checkpoint, old_files))
        with self.assertRaises(SecretStoreError):
            oauth_ops.publish(store, self.old, {"access_token": AT2, "refresh_token": RT2}, "fictional-operation")


if __name__ == "__main__":
    unittest.main()
