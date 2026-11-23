"""The administrator's step deletes the sign-in, never the entry (follow-up plan R11, rule 3; Sol round
11, high 2). An entry holds a plain field, a sign-in F refreshed by a member who is not an
administrator and a second sign-in G. The member's replace-signin names brain_secrets.py delete
--entry E --field F; the administrator runs it: one commit retires exactly the two ids of F, chosen by
the store's own lookup, and the static object and G are untouched. delete --entry E without --field
still removes the whole entry. Two real key sets, bare local repositories, a fake keyring and
in-process stores only. Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import subprocess
import unittest
from unittest import mock

from test_secret_store_store import setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase

import brain_secrets  # noqa: E402
import token_endpoint  # noqa: E402
from secret_store import SecretStoreError, delete_ops, handover, oauth_ops  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.journal import Journal  # noqa: E402

ENTRY, GROUP, F, G = "Ops portal", "ops", "member_token_json", "admin_token_json"
PLAIN = {"region": "fictional-region"}
TOKENS = {F: ("fictional-f-access", "fictional-f-refresh"), G: ("fictional-g-access", "fictional-g-refresh")}
VALUES = ["fictional-region", *TOKENS[F], *TOKENS[G]]
DELETE_F = f'brain_secrets.py delete --entry "{ENTRY}" --field "{F}" --group {GROUP}'


class DeleteOneSignIn(TeamCase):
    def setUp(self):
        super().setUp()
        self.admin, pinned = self.team_setup()
        self.bob = self.enrol_member(self.admin, pinned, "tb", "bob", "pc")
        team_ops.admit(self.admin, "bob", [GROUP])
        self.admin.put_entry(ENTRY, dict(PLAIN), group=GROUP)
        for field, (access, refresh) in TOKENS.items():
            oauth_ops.put_signin(self.admin, ENTRY, field, {"access_token": access, "refresh_token": refresh,
                                                             "token_type": "Bearer"}, group=GROUP)
        handover.release(self.admin, ENTRY, "bob/pc", group=GROUP, field=F)
        handover.accept(self.admin, ENTRY, group=GROUP, field=F)
        self.bob.open()
        self.admin.open()
        self.f = oauth_ops.find(self.bob, ENTRY, F, GROUP)
        self.g = oauth_ops.find(self.admin, ENTRY, G, GROUP)
        self.static_id = self.admin._index(GROUP)[ENTRY]
        self.journal = Journal(self.bob.config["checkpoint_dir"], self.bob._identity().x25519)

    def cli(self, argv, store, confirm=ENTRY):
        out, err = io.StringIO(), io.StringIO()
        prompts = []

        def answer(prompt):
            prompts.append(prompt)
            return confirm
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = brain_secrets.main(argv, team_factory=lambda: store, confirm=answer)
        text = out.getvalue() + err.getvalue()
        for value in VALUES:
            self.assertNotIn(value, text + "".join(prompts))
        return code, text, prompts

    def remote_head(self):
        return subprocess.run(["git", "--git-dir", str(self.team_bare), "rev-parse", "main"], capture_output=True,
                              check=True).stdout.strip()

    def commits_since(self, head):
        out = subprocess.run(["git", "--git-dir", str(self.team_bare), "rev-list", head.decode() + "..main"],
                             capture_output=True, check=True).stdout.split()
        return len(out)

    def make_uncertain(self):
        stack, _record = self.journal.begin(self.f.journal_key, 1)  # a lost answer: calling
        stack.close()

    def test_the_printed_step_deletes_exactly_the_one_signin(self):
        self.make_uncertain()
        code, text, _ = self.cli(["replace-signin", ENTRY, "--field", F, "--group", GROUP], self.bob)
        self.assertEqual(code, 3, text)
        self.assertIn(DELETE_F, text)  # the administrator's step names the field

        static_before = dict(self.admin.checkpoint.objects[self.static_id])
        retired_before = set(self.admin.policy.doc["retired"])
        head = self.remote_head()
        code, text, prompts = self.cli(["delete", "--entry", ENTRY, "--field", F, "--group", GROUP], self.admin)
        self.assertEqual(code, 0, text)
        self.assertIn("other fields stay", prompts[0])
        self.assertEqual(self.commits_since(head), 1)  # one commit
        self.admin.open()
        self.assertEqual(set(self.admin.policy.doc["retired"]) - retired_before, {self.f.oauth_id, self.f.grant_id})
        self.assertEqual(self.admin._index(GROUP)[ENTRY], self.static_id)  # the static object keeps its id,
        self.assertEqual(self.admin.checkpoint.objects[self.static_id], static_before)  # hash and revision,
        self.assertEqual(self.admin.get_record(ENTRY, GROUP), PLAIN)  # and its values
        g = oauth_ops.find(self.admin, ENTRY, G, GROUP)
        self.assertEqual((g.oauth_id, g.grant_id), (self.g.oauth_id, self.g.grant_id))  # G keeps its ids
        self.assertIsNone(oauth_ops.find(self.admin, ENTRY, F, GROUP))

        backend = StoreBackend(self.bob, sync_seconds=3600)  # the old refresher's next operation
        with mock.patch.object(token_endpoint, "post_token", side_effect=AssertionError("provider called")):
            backend.sync()
            self.assertIsNone(self.journal.read(self.f.journal_key))  # its record of the retired grant is gone
            self.assertEqual(backend.begin_refresh(ENTRY, F), {"signin": False})
        self.assertEqual(backend._pending, {})

    def test_the_shared_builder_takes_the_two_looked_up_ids(self):
        with mock.patch.object(delete_ops, "targets", side_effect=AssertionError("name scan")):
            self.cli(["delete", "--entry", ENTRY, "--field", G, "--group", GROUP], self.admin)
        self.admin.open()
        self.assertIsNone(oauth_ops.find(self.admin, ENTRY, G, GROUP))
        self.assertEqual(self.admin.get_record(ENTRY, GROUP), PLAIN)

    def test_a_field_naming_no_signin_and_a_member_are_refused_with_the_remote_head_unmoved(self):
        head = self.remote_head()
        for field in ("region", "no_such_field"):
            code, text, _ = self.cli(["delete", "--entry", ENTRY, "--field", field, "--group", GROUP], self.admin)
            self.assertEqual(code, 1, text)
            self.assertIn("nothing was deleted", text)
            self.assertEqual(self.remote_head(), head)
        code, text, _ = self.cli(["delete", "--entry", ENTRY, "--field", F, "--group", GROUP], self.bob)
        self.assertEqual(code, 1, text)
        self.assertIn("administrator", text)
        self.assertEqual(self.remote_head(), head)
        code, text, _ = self.cli(["delete", "--entry", ENTRY, "--field", F, "--group", GROUP], self.admin,
                                 confirm="wrong")
        self.assertEqual(code, 1, text)
        self.assertEqual(self.remote_head(), head)
        self.admin.open()
        self.assertIsNotNone(oauth_ops.find(self.admin, ENTRY, F, GROUP))

    def test_delete_without_field_still_removes_the_whole_entry(self):
        code, text, prompts = self.cli(["delete", "--entry", ENTRY, "--group", GROUP], self.admin)
        self.assertEqual(code, 0, text)
        self.assertIn("every sign-in", prompts[0])
        self.admin.open()
        retired = self.admin.policy.doc["retired"]
        for oid in (self.static_id, self.f.oauth_id, self.f.grant_id, self.g.oauth_id, self.g.grant_id):
            self.assertIn(oid, retired)
        self.assertEqual([n for n in self.admin.list_entries(GROUP) if n.startswith(ENTRY)], [])

    def test_an_administrator_who_is_not_the_refresher_is_shown_the_field_form(self):
        self.make_uncertain()
        code, text, _ = self.cli(["replace-signin", ENTRY, "--field", F, "--group", GROUP], self.admin)
        self.assertEqual(code, 1, text)
        self.assertIn(DELETE_F, text)
        with self.assertRaisesRegex(SecretStoreError, "administrator"):  # the store's own refusal
            self.bob.open().delete_entry(ENTRY, GROUP, field=F)


if __name__ == "__main__":
    unittest.main()
