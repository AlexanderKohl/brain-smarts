"""Replacing a team sign-in whose refresher is a team member who is not an administrator (Sol round 9,
medium; follow-up plan K.1, the conductor's option 2). The member's replace-signin changes nothing and
names the administrator's step (exit code 3). On an administrator's computer that is not the
refresher, replace-signin --for PERSON/COMPUTER keeps the shared settings in that computer's own
hand-over file and makes the one deletion commit; the administrator's next authorisation creates the
new pair with the kept settings, and the existing handover moves it to the member. The member's next
operation discards its journal record of the retired grant. Two real key sets, bare local
repositories, a fake keyring and in-process stores only. Every value is fictional."""
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
from secret_store.repo import SecretRepo  # noqa: E402

ENTRY, FIELD, GROUP = "Ops sign-in", oauth_ops.DEFAULT_FIELD, "ops"
ACCESS, REFRESH = "fictional-team-access", "fictional-team-refresh"
AT2, RT2, AT3 = "fictional-team-access-2", "fictional-team-refresh-2", "fictional-team-access-3"
TENANT = "tenant-ops"


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
            code = brain_secrets.main(argv, team_factory=lambda: store)
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
                self.files(self.journal, "*" + replace_ops.SUFFIX),
                self.files(self.admin_journal, "*" + replace_ops.SUFFIX))

    def make_uncertain(self):
        stack, _record = self.journal.begin(self.signin.journal_key, 1)  # a lost answer: calling
        stack.close()

    def test_the_member_is_the_refresher_and_not_an_administrator(self):
        self.assertTrue(self.signin.mine)
        self.assertFalse(self.bob.policy.is_admin_key(key_id(self.bob._identity().ed25519.public_key())))
        self.assertTrue(self.admin.open().policy.is_admin_key(key_id(self.admin._identity().ed25519.public_key())))

    def test_the_whole_sequence_ends_with_a_working_signin_on_the_member(self):
        self.make_uncertain()
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP], self.bob)
        self.assertEqual(code, 3, text)  # the administrator's step, not a refusal
        self.assertIn(f'replace-signin "{ENTRY}" --group {GROUP} --for bob/pc', text)
        self.assertIn("hand the sign-in back", text)
        self.assertEqual(self.state(), before)  # nothing deleted, nothing written
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")

        admin_journals = self.files(self.admin_journal, "*.journal")
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--for", "bob/pc"], self.admin)
        self.assertEqual(code, 0, text)
        self.assertIn("kept on this computer", text)
        self.assertIn("handover-release", text)
        policy = self.admin.policy.doc
        for oid in (self.signin.oauth_id, self.signin.grant_id):
            self.assertIn(oid, policy["retired"])
        self.assertEqual(len(self.files(self.admin_journal, "*" + replace_ops.SUFFIX)), 1)
        self.assertEqual(self.files(self.admin_journal, "*.journal"), admin_journals)  # no journal touched

        backend = StoreBackend(self.bob, sync_seconds=0)  # the member's agent: its next operation
        self.assertIn("api_key", backend.get_fields("Ops API", ["api_key"]))
        self.assertIsNone(self.journal.read(self.signin.journal_key))  # discarded with the retired grant

        oauth_ops.put_signin(self.admin.open(), ENTRY, FIELD, {"access_token": AT2, "refresh_token": RT2,
                                                               "token_type": "Bearer"}, group=GROUP)
        new = oauth_ops.find(self.admin, ENTRY, FIELD, GROUP)
        self.assertTrue(new.mine)
        self.assertNotIn(new.grant_id, (self.signin.oauth_id, self.signin.grant_id))
        self.assertEqual(oauth_ops.read_shared(self.admin, new)["tenant_id"], TENANT)
        self.assertEqual(self.files(self.admin_journal, "*" + replace_ops.SUFFIX), [])
        handover.release(self.admin, ENTRY, "bob/pc", group=GROUP)
        handover.accept(self.admin, ENTRY, group=GROUP)

        begun = backend.begin_refresh(ENTRY, FIELD)  # the member refreshes normally
        self.assertTrue(begun["refresher"])
        self.assertEqual(begun["record"]["refresh_token"], RT2)
        backend.set_json(ENTRY, FIELD, {"access_token": AT3, "refresh_token": RT2, "token_type": "Bearer"},
                         operation=begun["operation"])
        record = backend.get_json(ENTRY, FIELD)
        self.assertEqual((record["access_token"], record["tenant_id"]), (AT3, TENANT))
        self.assertEqual(self.files(self.journal, "*.journal"), [])
        self.assertEqual(oauth_ops.read_shared(self.admin.open(), new)["access_token"], AT3)

    def test_even_if_working_on_the_member_names_the_administrator_step(self):
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--even-if-working"], self.bob)
        self.assertEqual(code, 3, text)
        self.assertIn("--for bob/pc", text)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.journal.read(self.signin.journal_key))

    def test_for_naming_another_computer_is_refused(self):
        self.make_uncertain()
        before = self.state()
        for who in ("alice/laptop", "bob/other"):
            code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--for", who], self.admin)
            self.assertEqual(code, 1, text)
            self.assertIn("refreshes on bob/pc", text)
            self.assertEqual(self.state(), before)

    def test_for_run_by_a_non_administrator_is_refused(self):
        self.make_uncertain()
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--for", "bob/pc"], self.bob)
        self.assertEqual(code, 1, text)
        self.assertIn("only an administrator", text)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")

    def test_a_failed_push_in_the_administrator_step_changes_nothing(self):
        self.make_uncertain()
        before = self.state()
        with mock.patch.object(SecretRepo, "write", side_effect=SecretStoreError("push refused")), \
                mock.patch.object(SecretRepo, "settle_failed_write", return_value=None):
            code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--for", "bob/pc"], self.admin)
        self.assertEqual(code, 1, text)
        self.assertEqual(self.state(), before)  # no hand-over file left on the administrator's computer
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--for", "bob/pc"], self.admin)
        self.assertEqual(code, 0, text)  # the next run completes it


if __name__ == "__main__":
    unittest.main()
