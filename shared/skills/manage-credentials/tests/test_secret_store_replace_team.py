"""Follow-up plan F3.2: replace-signin in a team repository, run by a real team member who is not an
administrator and became the sign-in's refresher through a handover. It is refused and nothing
changes: the policy, the sign-in's ids, the journal record and the hand-over files stay as they were.
Bare local repositories, a fake keyring and in-process stores only. Every value is fictional."""
import contextlib
import io
import unittest

from test_secret_store_store import setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase

import brain_secrets  # noqa: E402
from secret_store import handover, oauth_ops, replace_ops  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.journal import Journal  # noqa: E402
from secret_store.keys import key_id  # noqa: E402

ENTRY, FIELD, GROUP = "Ops sign-in", oauth_ops.DEFAULT_FIELD, "ops"
ACCESS, REFRESH = "fictional-team-access", "fictional-team-refresh"


class NonAdministratorRefresher(TeamCase):
    def setUp(self):
        super().setUp()
        self.admin, pinned = self.team_setup()
        self.bob = self.enrol_member(self.admin, pinned, "tb", "bob", "pc")
        team_ops.admit(self.admin, "bob", [GROUP])
        oauth_ops.put_signin(self.admin, ENTRY, FIELD, {"access_token": ACCESS, "refresh_token": REFRESH,
                                                        "token_type": "Bearer"}, group=GROUP)
        handover.release(self.admin, ENTRY, "bob/pc", group=GROUP)
        handover.accept(self.admin, ENTRY, group=GROUP)
        self.bob.open()
        self.signin = oauth_ops.find(self.bob, ENTRY, FIELD, GROUP)
        self.journal = Journal(self.bob.config["checkpoint_dir"], self.bob._identity().x25519)

    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = brain_secrets.main(argv, team_factory=lambda: self.bob)
        text = out.getvalue() + err.getvalue()
        for value in (ACCESS, REFRESH):
            self.assertNotIn(value, text)
        return code, text

    def state(self):
        self.bob.open()
        found = oauth_ops.find(self.bob, ENTRY, FIELD, GROUP)
        return (self.bob.policy.hash, found.oauth_id, found.grant_id, found.mine,
                sorted(p.name for p in self.journal.folder.glob("*" + replace_ops.SUFFIX))
                if self.journal.folder.is_dir() else [])

    def test_the_member_is_the_refresher_and_not_an_administrator(self):
        self.assertTrue(self.signin.mine)
        self.assertFalse(self.bob.policy.is_admin_key(key_id(self.bob._identity().ed25519.public_key())))
        self.assertTrue(self.admin.open().policy.is_admin_key(key_id(self.admin._identity().ed25519.public_key())))

    def test_an_uncertain_signin_is_not_replaced_by_the_member(self):
        stack, _record = self.journal.begin(self.signin.journal_key, 1)  # a lost answer: calling
        stack.close()
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP])
        self.assertEqual(code, 1, text)
        self.assertIn("only an administrator", text)
        self.assertEqual(self.state(), before)
        self.assertEqual(before[4], [])
        self.assertEqual(self.journal.read(self.signin.journal_key)["state"], "calling")
        self.assertEqual(oauth_ops.read(self.bob, self.signin)["refresh_token"], REFRESH)

    def test_even_if_working_does_not_let_the_member_replace_it(self):
        before = self.state()
        code, text = self.cli(["replace-signin", ENTRY, "--group", GROUP, "--even-if-working"])
        self.assertEqual(code, 1, text)
        self.assertIn("only an administrator", text)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.journal.read(self.signin.journal_key))
        self.assertEqual(oauth_ops.find(self.admin.open(), ENTRY, FIELD, GROUP).oauth_id, self.signin.oauth_id)


if __name__ == "__main__":
    unittest.main()
