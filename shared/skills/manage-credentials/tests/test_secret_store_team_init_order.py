"""Team-init after the agent has seen the team repository (plan section H). The agent's backend
opens a team store whenever the configuration names one; for a repository with no commit yet it
serves the personal store, shows the team store as "not created yet", and leaves nothing that
stops init_team in a second instance. Once the team store exists the same backend reads it
without a restart. A team clone holding any commit or ref, or a team checkpoint, still refuses
init_team. Bare local repositories are the remotes and a fake keyring the keychain; every value
is fictional."""
import unittest

from test_secret_store_store import VALUE, StoreCase, git, setUpModule, tearDownModule  # noqa: F401

from secret_store import SecretStoreError  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.repo import SecretRepo  # noqa: E402

NO_GH = None


class TeamInitOrder(StoreCase):
    def setUp(self):
        super().setUp()
        self.team_bare = self.root / "team.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(self.team_bare), cwd=self.root)
        self.personal, _ = self.init()
        self.personal.put_entry("Personal API", {"api_key": VALUE})

    def team(self, name="a", url=None, state="a"):
        return team_ops.TeamStore(use_config_file=False, enabled=True, person="tester", computer="laptop",
                                  team_clone=self.root / name / "team", checkpoint_dir=self.root / state / "state",
                                  recovery_package_dir=self.root / state / "packages",
                                  team_repo_url=str(url or self.team_bare))

    def init_team(self, store):
        return store.init_team("example-org", words_callback=self._words,
                               gh=lambda *args: self.fail("gh must not run when a URL is configured"))

    def populated(self):
        admin = self.team()
        self.init_team(admin)
        return admin

    def assert_refused_unchanged(self, store):
        head = SecretRepo(store.clone, str(self.team_bare)).head() if (store.clone / ".git").is_dir() else None
        before = sorted(p.name for p in store.checkpoint_path.parent.iterdir()) \
            if store.checkpoint_path.parent.is_dir() else []
        with self.assertRaisesRegex(SecretStoreError, "already set up"):
            self.init_team(store)
        if head is not None:
            self.assertEqual(SecretRepo(store.clone, str(self.team_bare)).head(), head)
        after = sorted(p.name for p in store.checkpoint_path.parent.iterdir()) \
            if store.checkpoint_path.parent.is_dir() else []
        self.assertEqual(after, before)

    # -- the agent saw the empty team repository first ---------------------------------------------
    def test_backend_on_an_empty_team_repository_then_init_team_then_a_team_entry_without_restart(self):
        backend = StoreBackend(self.store("a").open(), sync_seconds=3600, team=self.team())
        self.assertEqual(backend.get_fields("Personal API", ["api_key"]), {"api_key": VALUE})
        status = backend.status()
        self.assertIn("not created yet", status.get("team_store", ""))
        self.assertNotIn("store_sync", status)
        self.assertIn("not created yet", status["recovery_packages"]["team"])

        admin = self.team()  # a second instance, as team-init in another process holds it
        self.init_team(admin)
        team_ops.create_groups(admin, ["ops"])
        team_ops.set_groups(admin, "tester", ["ops"])
        admin.put_entry("Ops API", {"api_key": "team-" + VALUE}, group="ops")

        self.assertEqual(backend.get_fields("Ops API", ["api_key"]), {"api_key": "team-" + VALUE})
        self.assertEqual(backend.get_fields("Personal API", ["api_key"]), {"api_key": VALUE})
        status = backend.status()
        self.assertNotIn("team_store", status)
        self.assertNotIn("store_sync", status)

    def test_empty_clone_of_another_remote_is_replaced(self):
        other = self.root / "other.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(other), cwd=self.root)
        seen = self.team(url=other)
        with self.assertRaises(SecretStoreError):
            seen.open()
        self.assertTrue((seen.clone / ".git").is_dir())
        self.init_team(self.team())
        self.assertEqual(SecretRepo(seen.clone, str(self.team_bare))._out("remote", "get-url", "origin"),
                         str(self.team_bare))

    # -- still refused ----------------------------------------------------------------------------
    def test_a_clone_with_a_commit_still_refuses(self):
        self.populated()
        self.assert_refused_unchanged(self.team(name="a", state="fresh"))  # same clone, no checkpoint

    def test_a_team_checkpoint_still_refuses(self):
        self.populated()
        self.assert_refused_unchanged(self.team(name="fresh", state="a"))  # new clone folder, checkpoint kept

    def test_a_clone_holding_only_a_fetched_ref_still_refuses(self):
        self.populated()
        late = self.team(name="late", state="late")
        late.clone.mkdir(parents=True)
        git("init", "--quiet", "--initial-branch=main", str(late.clone), cwd=self.root)
        git("remote", "add", "origin", str(self.team_bare), cwd=late.clone)
        git("fetch", "--quiet", "origin", cwd=late.clone)
        self.assertIsNone(SecretRepo(late.clone, str(self.team_bare)).head())
        self.assert_refused_unchanged(late)


if __name__ == "__main__":
    unittest.main()
