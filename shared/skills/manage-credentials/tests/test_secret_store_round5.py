"""Round-5 review fixes: an oauth revision 1 only from the sign-in's refresher (its first
authorisation, with an operation id) or an administrator; recovery-package upkeep after a commit
is a warning, never a failure; a missing package is rebuilt and the age check runs daily while the
store stays open; put with plain and grant fields is one commit; incoming commit subjects outside
the allowed set are refused. Every token is fictional."""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_store import SecretStoreError, oauth_ops, policy, store_ops  # noqa: E402
from secret_store import repo as repo_module  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from test_secret_store_accept import TOK_A, World, commit  # noqa: E402
from test_secret_store_broker import SECRET, StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401
from test_secret_store_team import TeamCase  # noqa: E402

HOSTILE = dict(TOK_A, access_token="fictional-attacker")


def cli():
    spec = importlib.util.spec_from_file_location("brain_secrets_r5", SCRIPTS / "brain_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FirstRevisionAuthority(unittest.TestCase):
    """bob-pc refreshes o1/g1 under an administrator-signed assignment; carol is a hostile member."""

    def setUp(self):
        w = self.w = World()

        def assign(d):
            d["assignments"] = {"o1": {"group": "ops", "kind": "oauth", "provider": "xero"},
                                "g1": {"group": "ops", "kind": "grant", "provider": "xero"}}
            d["refreshers"] = {"g1": {"person": "bob", "computer": "pc", "oauth": "o1"}}
        self.doc = w.next_policy(assign)
        self.p = policy.Policy(self.doc)

    def files(self, oauth_writer, payload, operation=None):
        w, p = self.w, self.p
        return commit(w.obj("o1", payload, oauth_writer, p, operation=operation),
                      w.obj("g1", {"refresh_token": "fictional-r"}, "bob-pc", p, operation="op-1"),
                      w.obj("index-ops", w.index(p, "ops"), "bob-pc", p), pol=self.doc)

    def test_hostile_member_revision_one_is_refused(self):
        for me in ("bob-pc", "carol-pc"):
            for operation in (None, "op-9"):
                with self.assertRaises(SecretStoreError):
                    self.w.accept(self.files("carol-pc", HOSTILE, operation), me=me)

    def test_forked_history_with_a_substituted_oauth_object_is_refused(self):
        honest = self.files("bob-pc", dict(TOK_A), "op-1")
        self.w.accept(honest, me="carol-pc")  # the refresher's first authorisation
        fork = dict(honest)
        fork["objects/o1.json"] = self.w.obj("o1", HOSTILE, "carol-pc", self.p)
        with self.assertRaises(SecretStoreError):
            self.w.accept(fork, me="carol-pc")  # a computer still at the parent checkpoint

    def test_refresher_revision_one_needs_its_operation(self):
        with self.assertRaisesRegex(SecretStoreError, "baseline"):
            self.w.accept(self.files("bob-pc", dict(TOK_A)), me="carol-pc")
        self.w.accept(self.files("bob-pc", dict(TOK_A), "op-1"), me="carol-pc")


class PackageWarnings(TeamCase):
    def test_team_remove_returns_the_list_when_the_cloud_folder_cannot_be_written(self):
        admin, pinned = self.team_setup()
        self.enrol_member(admin, pinned, "tb", "bob", "desk")
        team_ops.admit(admin, "bob", ["ops"])
        blocker = self.root / "blocked-cloud"
        blocker.write_text("not a folder")
        admin.config["recovery_package_dir"] = blocker / "brain-secrets-recovery"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli().main(["team-remove", "--login", "bob"], team_factory=lambda: admin)
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertIn("Change these provider secrets: Ops API.", out.getvalue())
        self.assertIn("recovery package", err.getvalue())
        self.assertNotIn("bob", admin.policy.doc["people"])
        self.assertTrue(admin.package_error)


class PackageUpkeep(StoreFixture):
    def test_missing_package_is_rebuilt_on_open(self):
        path = self.a._package_path()
        path.unlink()
        self.a.open()
        self.assertTrue(path.exists())

    def test_age_check_runs_daily_while_the_store_stays_open(self):
        path = self.a._package_path()
        old = time.time() - 8 * 86400
        os.utime(path, (old, old))
        self.a._package_checked = time.time() - 25 * 3600
        self.a.list_entries()
        self.assertGreater(path.stat().st_mtime, old + 86400)
        os.utime(path, (old, old))
        self.a.list_entries()  # checked less than a day ago: nothing rebuilt
        self.assertLess(path.stat().st_mtime, old + 86400)


class PutOneCommit(StoreFixture):
    def commits(self):
        return int(subprocess.run(["git", "-C", str(self.a.clone), "rev-list", "--count", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout)

    def put(self, answer):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli().main(["put", "--entry", "xero-demo", *sum((["--secret", k] for k in answer), [])],
                              store_factory=lambda: self.a, ask=lambda _t, _f: (answer, None))

    def test_plain_and_grant_fields_make_one_commit(self):
        for answer in ({"client_secret": SECRET, "password": "fictional-pw"},
                       {"client_secret": SECRET + "-2", "username": "fictional-user"}):
            before = self.commits()
            self.assertEqual(self.put(answer), 0)
            self.assertEqual(self.commits(), before + 1)
        record = self.a.get_record("xero-demo")
        self.assertEqual(record, {"password": "fictional-pw", "username": "fictional-user"})
        signin = oauth_ops.find(self.a, "xero-demo", oauth_ops.DEFAULT_FIELD)
        self.assertEqual(oauth_ops.read_grant(self.a, signin)["fields"], {"client_secret": SECRET + "-2"})
        oauth_obj = self.a._tree_object(signin.oauth_id, self.a.checkpoint)
        self.assertEqual(oauth_obj["revision"], 1)
        self.assertIsNotNone(oauth_obj["operation"])  # the refresher's first authorisation
        self.b.open()  # another computer accepts it


class IncomingSubjects(StoreFixture):
    def test_commit_with_a_subject_outside_the_allowed_set_is_refused(self):
        b = self.b
        files, _message = store_ops.build_put(b.policy, b.checkpoint.objects, b._index(None), "Hidden",
                                              {"k": "fictional"}, "static", b._identity().ed25519, b._group(None))
        with mock.patch.object(repo_module, "ALLOWED_MESSAGES", repo_module.ALLOWED_MESSAGES | {"Hidden entry"}):
            b._write(lambda: (files, "Hidden entry"))
        with self.assertRaises(SecretStoreError):
            self.a.open()


if __name__ == "__main__":
    unittest.main()
