"""Round-4 review fixes: the Meta provider profile, journal records that need a provider call, a
clean Git index for every write, the recovery package's default place and its automatic refresh,
and the recorded provider on every oauth revision. Every token is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate_to_store  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store import SecretStoreError, accept_rules, oauth_ops, policy, provider_profiles, store_ops  # noqa: E402
from secret_store.repo import SecretRepo  # noqa: E402
from test_secret_store_accept import World, commit  # noqa: E402
from test_secret_store_broker import (FIELD, PASS, SECRET, AgentClients, StoreFixture,  # noqa: E402,F401
                                      agent_request, setUpModule, tearDownModule)
from test_secret_store_repo import RepoCase  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402

META = {"provider": "meta", "user_token": "fictional-user", "user_token_expires_at": 100,
        "pages": [{"id": "page-1", "token": "fictional-page"}], "app": "settings"}


class MetaProfile(unittest.TestCase):
    def setUp(self):
        w = self.w = World()

        def assign(d):
            d["assignments"] = {"o1": {"group": "ops", "kind": "oauth", "provider": "meta"},
                                "g1": {"group": "ops", "kind": "grant", "provider": "meta"}}
            d["refreshers"] = {"g1": {"person": "bob", "computer": "pc", "oauth": "o1"}}
        doc = w.next_policy(assign)
        p = policy.Policy(doc)
        w.apply(commit(w.obj("o1", dict(META), "bob-pc", p, operation="op-0"), w.obj("g1", {}, "bob-pc", p),
                       w.obj("index-ops", w.index(p, "ops"), "bob-pc", p), pol=doc))

    def test_profile_and_signin_marker(self):
        self.assertEqual(provider_profiles.provider_for("meta-graph-oauth"), "meta")
        self.assertFalse(provider_profiles.verified("meta"))
        self.assertTrue({"user_token", "user_token_expires_at", "pages"} <= provider_profiles.token_fields("meta"))
        self.assertTrue(oauth_ops.looks_like_signin({"user_token": "fictional-user"}))

    def test_hostile_member_cannot_replace_meta_tokens(self):
        w, latest = self.w, {"o1": dict(META)}
        for change in ({"user_token": "fictional-hostile"}, {"user_token_expires_at": 999},
                       {"pages": [{"id": "page-1", "token": "fictional-hostile"}]}):
            with self.assertRaisesRegex(SecretStoreError, "access-token fields changed"):
                w.accept(commit(w.obj("o1", dict(META, **change), "carol-pc")), latest=latest)
        w.accept(commit(w.obj("o1", dict(META, app="other settings"), "carol-pc")), latest=latest)


class MetaMigration(StoreFixture):
    def test_meta_record_migrates_as_oauth_and_grant(self):
        vault = PortableVault(self.root / "vault" / "credentials.vault")
        vault.initialize(PASS)
        record = {k: v for k, v in META.items() if k != "provider"}
        vault.set_fields("meta-graph-oauth", {FIELD: (record, "json")}, PASS)
        agent = VaultAgent(vault.path)
        agent.unlock(PASS)
        self.assertEqual(migrate_to_store.migrate(agent_request(agent), lambda: self.a, out=lambda _l: None), 0)
        signin = oauth_ops.find(self.a, "meta-graph-oauth", FIELD)
        self.assertIsNotNone(signin)
        self.assertEqual(signin.provider, "meta")
        self.assertTrue(set(oauth_ops.signin_names("meta-graph-oauth", FIELD)) <= set(self.a._index()))


class JournalNeedsACall(AgentClients):
    def key(self):
        return oauth_ops.find(self.ba.store, "xero-demo", FIELD).journal_key

    def test_tokenless_signin_is_no_signin_yet(self):
        self.ba.set_text("xero-demo", "client_secret", SECRET)  # a grant without a token
        a = self.client(self.ba, "A")
        with self.assertRaises(RuntimeError), a.rotation_lock(refresh=True):
            raise RuntimeError("no refresh token yet")
        self.assertEqual((self.ba._journal.read(self.key()), self.ba._pending), (None, {}))
        with self.assertRaises(CredentialError), a.rotation_lock(new_authorisation=True):
            pass  # a code exchange that ended without a save
        self.assertEqual((self.ba._journal.read(self.key()), self.ba._pending), (None, {}))
        with a.rotation_lock(new_authorisation=True):
            a.save(self.token())
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], self.token()["refresh_token"])
        self.assertIsNone(self.ba._journal.read(self.key()))

    def test_new_authorisation_without_a_save_leaves_no_record(self):
        self.sign_in(self.ba, "xero-demo", self.token())
        a = self.client(self.ba, "A")
        with self.assertRaises(ValueError), a.rotation_lock(new_authorisation=True):
            raise ValueError("the code was refused")
        self.assertEqual((self.ba._journal.read(self.key()), self.ba._pending), (None, {}))
        with a.rotation_lock(refresh=True):  # still refreshable: nothing is uncertain
            a.save({**a.load(), "access_token": "fictional-access-9"})

    def test_provider_not_called_is_exported_from_portable_vault(self):
        import portable_vault
        from secret_store.journal import ProviderNotCalled
        self.assertIs(portable_vault.ProviderNotCalled, ProviderNotCalled)
        self.sign_in(self.ba, "xero-demo", self.token())
        a = self.client(self.ba, "A")
        with self.assertRaises(ProviderNotCalled), a.rotation_lock(refresh=True):
            self.assertEqual(self.ba._journal.read(self.key())["state"], "calling")
            raise portable_vault.ProviderNotCalled("no client secret here")
        self.assertEqual((self.ba._journal.read(self.key()), self.ba._pending), (None, {}))


class CleanIndex(RepoCase):
    def status(self, repo):
        return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo.path,
                              capture_output=True, check=True).stdout

    def test_failure_after_each_staged_file_restores_a_clean_state(self):
        repo = self.clone("a")
        base = repo.write({"base.json": {"v": 0}}, "update")
        change = {"one.json": {"v": 1}, "two.json": {"v": 2}, "base.json": None}
        for failing_after in (1, 2, 3):
            original, seen = repo._git, []

            def git(*args, **kw):
                result = original(*args, **kw)
                if args[0] in ("add", "rm"):
                    seen.append(args[0])
                    if len(seen) == failing_after:
                        raise OSError("injected")
                return result
            with mock.patch.object(repo, "_git", side_effect=git), self.assertRaises(OSError):
                repo.write(change, "update")
            self.assertEqual((self.status(repo), repo.head()), (b"", base))
        repo.write({"three.json": {"v": 3}}, "update")
        self.assertEqual(set(repo._changed_files(repo.head())), {"three.json"})

    def test_pre_staged_stray_file_never_enters_a_commit(self):
        repo = self.clone("a")
        repo.write({"base.json": {"v": 0}}, "update")
        (repo.path / "stray.json").write_text("{}", "utf-8")
        subprocess.run(["git", "add", "stray.json"], cwd=repo.path, check=True)
        (repo.path / "loose.json").write_text("{}", "utf-8")
        repo.write({"mine.json": {"v": 1}}, "update")
        self.assertEqual(set(repo._changed_files(repo.head())), {"mine.json"})
        self.assertEqual(self.status(repo), b"")


class RecoveryPlace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def place(self, platform, env, home=None):
        with mock.patch.object(store_ops.sys, "platform", platform), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(store_ops.Path, "home", return_value=home or self.root / "home"):
            return store_ops.recovery_package_place()

    def test_onedrive_icloud_or_local_with_a_warning(self):
        (self.root / "od").mkdir()
        (self.root / "odc").mkdir()
        self.assertEqual(self.place("win32", {"OneDrive": str(self.root / "od"), "LOCALAPPDATA": str(self.root)}),
                         (self.root / "od" / "brain-secrets-recovery", True))
        self.assertEqual(self.place("win32", {"OneDriveConsumer": str(self.root / "odc"),
                                              "LOCALAPPDATA": str(self.root)}),
                         (self.root / "odc" / "brain-secrets-recovery", True))
        self.assertEqual(self.place("win32", {"OneDrive": str(self.root / "missing"), "LOCALAPPDATA": str(self.root)}),
                         (self.root / "brain-secrets" / "recovery-packages", False))
        icloud = self.root / "mac" / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        icloud.mkdir(parents=True)
        self.assertEqual(self.place("darwin", {}, home=self.root / "mac"), (icloud / "brain-secrets-recovery", True))
        place, cloud = self.place("darwin", {}, home=self.root / "bare-mac")
        self.assertFalse(cloud)
        with mock.patch.object(store_ops, "recovery_package_place", return_value=(self.root / "od2", True)):
            self.assertEqual(store_ops.load_config(use_config_file=False, person="p")["recovery_package_dir"],
                             self.root / "od2")

    def test_status_warns_when_the_package_stays_on_this_computer(self):
        (self.root / "clone" / ".git").mkdir(parents=True)
        fake = types.SimpleNamespace(config={"enabled": True, "person": "p", "recovery_package_cloud": False},
                                     clone=self.root / "clone", repo=types.SimpleNamespace(status=lambda: "Up to date."),
                                     _package_path=lambda: self.root / "none.package", package_error=None)
        self.assertIn("only on this computer", store_ops.store_status(fake))


class PackageRefreshOnOpen(StoreFixture):
    def test_open_refreshes_a_package_older_than_seven_days(self):
        path = self.a._package_path()
        old = time.time() - 8 * 86400
        os.utime(path, (old, old))
        self.a.open()
        self.assertGreater(path.stat().st_mtime, old + 86400)
        os.utime(path, (old, old))
        with mock.patch("secret_store.recovery_package.build", side_effect=OSError("drive offline")):
            self.a.open()  # opening still works; status says the package needs attention
        self.assertIn("recovery-package", self.a.status())


class RecordedProviderEverywhere(unittest.TestCase):
    def test_first_revision_and_admin_rekey_carry_the_recorded_provider(self):
        for revision, admin in ((1, False), (4, True)):
            with self.assertRaisesRegex(SecretStoreError, "provider"):
                accept_rules.check_oauth_payload({"provider": "gohighlevel", "access_token": "fictional"}, None,
                                                 {"id": "o1", "revision": revision}, False, admin,
                                                 recorded_provider="xero")
        self.assertTrue(accept_rules.check_oauth_payload({"provider": "xero"}, None, {"id": "o1", "revision": 1},
                                                         False, True, recorded_provider="xero"))


if __name__ == "__main__":
    unittest.main()
