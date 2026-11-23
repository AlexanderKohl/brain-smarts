"""Ending a team sign-in whose refresher is a team member who is not an administrator (Sol round 10,
high 2; follow-up plan M2). There is no replace-signin --for: the member's uncertain sign-in stays
blocked by its own calling journal record, which refuses every refresh and survives restarts, and
an administrator deletes exactly that sign-in (brain_secrets.py delete --field, design section 7,
plan R11 rule 3), signs in again and hands the new sign-in back. The member's agent discards the journal
record of the exact retired grant. Two real key sets, bare local repositories, a fake keyring and
in-process stores only. Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import unittest
from unittest import mock

from test_secret_store_store import setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase

import brain_secrets  # noqa: E402
from secret_store import SecretStoreError, handover, oauth_ops, replace_ops  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.journal import Journal  # noqa: E402
from secret_store.keys import key_id  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402

ENTRY, FIELD, GROUP = "Ops sign-in", oauth_ops.DEFAULT_FIELD, "ops"
ACCESS, REFRESH = "fictional-team-access", "fictional-team-refresh"
AT2, RT2, AT3 = "fictional-team-access-2", "fictional-team-refresh-2", "fictional-team-access-3"
TENANT = "tenant-ops"
DELETE = f'brain_secrets.py delete --entry "{ENTRY}" --field "{FIELD}" --group {GROUP}'


class NonAdministratorRefresher(TeamCase):
    def setUp(self):
        super().setUp()
        self.admin, pinned = self.team_setup()
        self.bob = self.enrol_member(self.admin, pinned, "tb", "bob", "pc")
        team_ops.admit(self.admin, "bob", [GROUP])
        oauth_ops.put_signin(self.admin, ENTRY, FIELD, {"access_token": ACCESS, "refresh_token": REFRESH,
                                                        "token_type": "Bearer", "tenant_id": TENANT}, group=GROUP)
        handover.release(self.admin, ENTRY, "bob/pc", group=GROUP)
        handover.accept(self.admin, ENTRY, group=GROUP)
        self.bob.open()
        self.signin = oauth_ops.find(self.bob, ENTRY, FIELD, GROUP)
        self.journal = Journal(self.bob.config["checkpoint_dir"], self.bob._identity().x25519)
        self.admin_journal = Journal(self.admin.config["checkpoint_dir"], self.admin._identity().x25519)

    def cli(self, argv, store):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = brain_secrets.main(argv, team_factory=lambda: store, confirm=lambda _prompt: ENTRY)
        text = out.getvalue() + err.getvalue()
        for value in (ACCESS, REFRESH, AT2, RT2, AT3):
            self.assertNotIn(value, text)
        return code, text

    @staticmethod
    def files(journal, pattern):
        return sorted(p.name for p in journal.folder.glob(pattern)) if journal.folder.is_dir() else []

    def state(self):
        self.bob.open()
        found = oauth_ops.find(self.bob, ENTRY, FIELD, GROUP)
        return (self.bob.policy.hash, found.oauth_id, found.grant_id, found.mine,
                self.files(self.journal, "*" + replace_ops.SUFFIX), self.files(self.journal, "*.disabled"),
                self.files(self.admin_journal, "*" + replace_ops.SUFFIX))

    def make_uncertain(self):
        stack, _record = self.journal.begin(self.signin.journal_key, 1)  # a lost answer: calling
        stack.close()

    def delete(self):
        code, text = self.cli(["delete", "--entry", ENTRY, "--field", FIELD, "--group", GROUP], self.admin)
        self.assertEqual(code, 0, text)
        policy = self.admin.policy.doc
        for oid in (self.signin.oauth_id, self.signin.grant_id):  # both ids in the one deletion commit
            self.assertIn(oid, policy["retired"])

    def assert_no_refresh_begins(self, backend):
        """After the deletion: nothing to refresh. With no personal store beside the team store the
        agent cannot route a deleted entry and says so ("name a group"); either way nothing begins."""
        try:
            self.assertEqual(backend.begin_refresh(ENTRY, FIELD), {"signin": False})
        except SecretStoreError as error:
            self.assertIn("name a group", str(error))
        self.assertEqual(backend._pending, {})
        self.assertEqual(self.files(self.journal, "*.journal"), [])

    def test_the_member_is_the_refresher_and_not_an_administrator(self):
        self.assertTrue(self.signin.mine)
        self.assertFalse(self.bob.policy.is_admin_key(key_id(self.bob._identity().ed25519.public_key())))
        self.assertTrue(self.admin.open().policy.is_admin_key(key_id(self.admin._identity().ed25519.public_key())))

    def test_for_is_gone(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            brain_secrets.main(["replace-signin", ENTRY, "--group", GROUP, "--for", "bob/pc"],
                               team_factory=lambda: self.admin)
        self.assertNotIn("for_computer", replace_ops.replace.__code__.co_varnames)

    def test_the_whole_sequence_ends_with_a_working_signin_on_the_member(self):
        self.make_uncertain()
        backend = StoreBackend(self.bob, sync_seconds=3600)  # the member's agent, already running
        self.assertIn("api_key", backend.get_fields("Ops API", ["api_key"]))
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP], self.bob)
        self.assertEqual(code, 3, text)  # the administrator's step, not a refusal
        self.assertIn(DELETE, text)
        self.assertIn("stays blocked", text)
        self.assertIn("handover-release", text)
        self.assertEqual(self.state(), before)  # nothing deleted, nothing written
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")

        self.delete()
        with self.assertRaisesRegex(SecretStoreError, "uncertain"):
            backend.begin_refresh(ENTRY, FIELD)  # the deletion is not pulled yet: the calling record refuses
        backend.sync()  # pulled: the record of the exact retired grant is discarded
        self.assertIsNone(self.journal.read(self.signin.journal_key))
        self.assert_no_refresh_begins(backend)

        oauth_ops.put_signin(self.admin.open(), ENTRY, FIELD, {"access_token": AT2, "refresh_token": RT2,
                                                               "token_type": "Bearer"}, group=GROUP)
        new = oauth_ops.find(self.admin, ENTRY, FIELD, GROUP)
        self.assertNotIn(new.grant_id, (self.signin.oauth_id, self.signin.grant_id))
        self.assertEqual(self.files(self.admin_journal, "*" + replace_ops.SUFFIX), [])  # no hand-over file
        handover.release(self.admin, ENTRY, "bob/pc", group=GROUP)
        handover.accept(self.admin, ENTRY, group=GROUP)

        backend.sync()
        begun = backend.begin_refresh(ENTRY, FIELD)  # the member refreshes the new sign-in normally
        self.assertTrue(begun["refresher"])
        self.assertEqual(begun["record"]["refresh_token"], RT2)
        backend.set_json(ENTRY, FIELD, {"access_token": AT3, "refresh_token": RT2, "token_type": "Bearer"},
                         operation=begun["operation"])
        self.assertEqual(backend.get_json(ENTRY, FIELD)["access_token"], AT3)
        self.assertEqual(self.files(self.journal, "*.journal"), [])  # no record of the retired grant
        self.assertEqual(oauth_ops.read_shared(self.admin.open(), new)["access_token"], AT3)

    def test_even_if_working_on_the_member_is_refused(self):
        for uncertain in (False, True):
            if uncertain:
                self.make_uncertain()
            before = self.state()
            code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--even-if-working"], self.bob)
            self.assertEqual(code, 1, text)
            self.assertIn("handover-release", text)
            self.assertIn("handover-accept", text)
            self.assertEqual(self.state(), before)
            record = self.journal.read(self.signin.journal_key)
            self.assertEqual(record and record["state"], "calling" if uncertain else None)

    def test_an_administrator_who_is_not_the_refresher_is_refused(self):
        self.make_uncertain()
        before = self.state()
        for extra in ([], ["--even-if-working"]):
            code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, *extra], self.admin)
            self.assertEqual(code, 1, text)
            self.assertIn(DELETE, text)
            self.assertEqual(self.state(), before)  # no hand-over file on either computer
            self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")

    def test_a_calling_record_refuses_offline_stale_and_after_a_restart(self):
        self.make_uncertain()
        backend = StoreBackend(self.bob, sync_seconds=0)
        with mock.patch.object(SecretStore, "_sync", side_effect=SecretStoreError("offline")):
            with self.assertRaisesRegex(SecretStoreError, "uncertain"):
                backend.begin_refresh(ENTRY, FIELD)  # offline: the pull fails, reads go on, no refresh
            self.assertIn("offline", backend.sync_error)
        stale = StoreBackend(self.bob, sync_seconds=3600)
        stale.get_fields("Ops API", ["api_key"])
        self.delete()
        with self.assertRaisesRegex(SecretStoreError, "uncertain"):
            stale.begin_refresh(ENTRY, FIELD)  # a stale copy, the deletion not yet pulled
        with mock.patch.object(SecretStore, "_sync", side_effect=SecretStoreError("offline")):
            with self.assertRaisesRegex(SecretStoreError, "uncertain"):
                stale.begin_refresh(ENTRY, FIELD, new_authorisation=True)
        restarted = StoreBackend(self.member("tb", "bob", "pc"), sync_seconds=3600)
        with mock.patch.object(SecretStore, "open", side_effect=SecretStoreError("offline")):
            with self.assertRaises(SecretStoreError):
                restarted.begin_refresh(ENTRY, FIELD)  # a restart offline: nothing verified, nothing refreshed
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")
        member = self.member("tb", "bob", "pc")  # a restart from this computer's own verified copy
        member._remote_url = lambda: str(self.root / "unreachable.git")
        with self.assertRaises(SecretStoreError):
            StoreBackend(member, sync_seconds=3600).begin_refresh(ENTRY, FIELD)
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")

    def test_the_deletion_arriving_during_the_original_request_brings_no_retry_and_no_publication(self):
        backend = StoreBackend(self.bob, sync_seconds=3600)
        begun = backend.begin_refresh(ENTRY, FIELD)  # the provider request is now in flight
        self.assertTrue(begun["refresher"])
        self.delete()
        ids = (self.signin.oauth_id, self.signin.grant_id)
        tombstones = {oid: dict(self.admin.checkpoint.objects[oid]) for oid in ids}
        with mock.patch.object(Journal, "lock_timeout", 0.5):
            backend.sync()  # the deletion arrives; the in-flight record holds its lock and is left alone
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")
        with self.assertRaises(SecretStoreError):  # the late answer is never published
            backend.set_json(ENTRY, FIELD, {"access_token": AT2, "refresh_token": RT2, "token_type": "Bearer"},
                             operation=begun["operation"])
        self.assert_no_refresh_begins(backend)  # no retry; the retired grant's record is gone
        self.admin.open()
        self.assertIsNone(oauth_ops.find(self.admin, ENTRY, FIELD, GROUP))
        for oid in (self.signin.oauth_id, self.signin.grant_id):  # nothing after the deletion's tombstones
            self.assertIn(oid, self.admin.policy.doc["retired"])
            self.assertEqual(self.admin.checkpoint.objects[oid], tombstones[oid])

    def test_the_discard_matches_the_exact_retired_grant(self):
        self.make_uncertain()
        other = self.signin.journal_key.rpartition("/")[0] + "/another-grant-id"
        stack, _record = self.journal.begin(other, 1)  # a record of a grant that is not retired
        stack.close()
        self.delete()
        self.bob.open()
        removed = replace_ops.discard_retired(self.bob, self.journal)
        self.assertEqual(removed, [self.signin.journal_key.split(" @ ")[0]])
        self.assertIsNone(self.journal.read(self.signin.journal_key))
        self.assertEqual(self.journal.read(other)["state"], "calling")


if __name__ == "__main__":
    unittest.main()
