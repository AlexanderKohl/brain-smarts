"""setup_store.py, the one-command setup of a person's computer: the order of the steps, what each
skips when it is already done, and where it stops. The outside world (sync, pip, gh, the Vault
Agent, the migration, the stores and the team enrolment) is replaced by fakes that record what was
asked of them; the configuration file is real, in a throwaway brain. Every name is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import setup_store  # noqa: E402
from secret_store import invite  # noqa: E402

URL = "https://github.com/example-owner/brain-team-secrets.git"


class FakeGitHub:
    GitHubError = setup_store.team_github.GitHubError
    repository_of = staticmethod(setup_store.team_github.repository_of)

    def __init__(self, name="alex-example", writable=True, pending=True, personal="missing"):
        self.name, self.writable, self.pending, self.accepted, self.personal = name, writable, pending, 0, personal

    def state(self, repository):
        assert repository == f"{self.name}/brain-secrets"
        return self.personal

    def login(self):
        return self.name

    def can_write(self, _repository):
        return self.writable

    def accept(self, _repository):
        if self.pending:
            self.accepted += 1
            self.writable = True
        return self.pending


class FakeStore:
    def __init__(self, root, name, entries=()):
        self.checkpoint_path = root / name / "checkpoint.json"
        self.clone = root / name / "clone"
        self.pin_path = root / name / "pin.json"
        self.entries, self.inits = list(entries), 0
        self.config = {"person": "alex-example", "computer": "desk"}
        self.policy = mock.Mock(computers=set())

    def init_personal(self):
        self.inits += 1
        self.enrol()
        return "f" * 64

    def enrol(self):
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text("{}", "utf-8")
        self.policy.computers.add(("alex-example", "desk"))

    def open(self):
        return self

    def list_entries(self, _group=None):
        return self.entries


class FakeSetup(setup_store.Setup):
    """Agent states are played from a list: each status read takes the next, the last one stays."""

    def __init__(self, root, statuses=(None,), old_vault=False, migrated=False, migrate_codes=(0, 0), **kw):
        self.log, self.statuses, self.codes = [], list(statuses), list(migrate_codes)
        self.old_vault, self.done_migration = old_vault, migrated
        self.personal = FakeStore(root, "personal")
        self.team = FakeStore(root, "team", ["Ops API#oauth_token_json", "Ops API"])
        self.lines, self.now = [], 0.0
        super().__init__(root, say=self.lines.append, ask=lambda _prompt: "ab" * 32, clock=self.clock_now,
                         sleep=self.advance, **kw)

    def clock_now(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    missing = ["keyring>=25,<26"]

    def missing_requirements(self):
        return list(self.missing)

    def run(self, command):
        self.log.append(("run", Path(command[1]).name if command[1].endswith(".py") else command[2]))
        if command[1:4] == ["-m", "pip", "install"]:
            self.pip = command[6:]
        return 0

    def agent_status(self):
        status = self.statuses[0]
        if len(self.statuses) > 1:
            self.statuses.pop(0)
        return status

    def start_agent(self):
        self.log.append(("start_agent", self.config().get("enabled")))

    def migrate(self, argv):
        self.log.append(("migrate", tuple(argv)))
        return self.codes.pop(0)

    def stores(self, force_on=False):
        return self.personal, self.team

    def vault(self):
        return self.root / ("credentials.vault" if self.old_vault else "missing.vault")

    def migrated(self):
        return self.done_migration


STORE = {"backend": "store", "recovery_packages": {"personal": {}}}
TEAM = {"backend": "store", "recovery_packages": {"personal": {}, "team": {}}}


class SetupCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "credentials.vault").write_bytes(b"fictional")
        self.err = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stderr(self.err))
        self.addCleanup(stack.close)

    def config(self, setup):
        return json.loads(setup.config_path.read_text("utf-8"))

    def joined(self, groups=("ops",)):
        patcher = mock.patch.object(invite, "join_team", return_value=list(groups))
        found = patcher.start()
        self.addCleanup(patcher.stop)
        return found


class NewPersonTests(SetupCase):
    def test_a_person_without_an_old_vault_joins_a_team(self):
        join = self.joined()
        setup = FakeSetup(self.root, statuses=[None, None, None, TEAM], github=FakeGitHub(writable=False))
        self.assertEqual(setup_store.main(["--join", URL], setup), 0, self.err.getvalue())
        self.assertEqual(self.config(setup), {"enabled": True, "person": "alex-example", "team_repo_url": URL})
        self.assertFalse(setup.config_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(setup.personal.inits, 1)
        self.assertEqual(setup.github.accepted, 1)
        self.assertEqual(join.call_args.args[1], "ab" * 32)  # the pasted fingerprint
        self.assertEqual([e for e in setup.log if e[0] != "run"], [("start_agent", True)])
        self.assertEqual([e[1] for e in setup.log if e[0] == "run"], ["sync.py", "pip"])
        self.assertEqual(setup.pip, ["keyring>=25,<26"])  # only what is missing, never the whole file
        self.assertIn("Team group ops: Ops API", setup.lines)
        self.assertFalse(any(e[0] == "migrate" for e in setup.log))

    def test_the_invitation_is_waited_for(self):
        self.joined()
        github = FakeGitHub(writable=False, pending=False)
        setup = FakeSetup(self.root, statuses=[None, None, TEAM], github=github)
        original = setup.advance

        def later(seconds):
            original(seconds)
            github.pending = True  # the administrator has now invited
        setup.sleep = later
        self.assertEqual(setup_store.main(["--join", URL, "--no-sync"], setup), 0, self.err.getvalue())
        self.assertTrue(any("Waiting for the GitHub invitation" in line for line in setup.lines))


class CutOverTests(SetupCase):
    def test_the_old_vault_is_unlocked_moved_and_the_agent_restarted(self):
        vault = {"backend": "vault", "unlocked": True}
        setup = FakeSetup(self.root, statuses=[None, None, vault, vault, vault, None, STORE], old_vault=True,
                          github=FakeGitHub())
        setup.set_config(enabled=True, person="alex-example")  # an earlier run stopped after switching on
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        steps = [e for e in setup.log if e[0] != "run"]
        self.assertEqual(steps, [("start_agent", False), ("migrate", ("--dry-run",)), ("migrate", ()),
                                 ("start_agent", True)])
        self.assertTrue(any("choose Quit" in line for line in setup.lines))
        self.assertEqual(self.config(setup), {"enabled": True, "person": "alex-example"})

    def test_a_failed_migration_stops_before_the_restart(self):
        unlocked = {"backend": "vault", "unlocked": True}
        setup = FakeSetup(self.root, statuses=[unlocked], old_vault=True, migrate_codes=(0, 4), github=FakeGitHub())
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn("migration stopped (code 4", self.err.getvalue())
        self.assertNotIn(("start_agent", True), setup.log)

    def test_an_agent_already_on_the_store_with_an_unmigrated_vault_stops(self):
        setup = FakeSetup(self.root, statuses=[STORE], old_vault=True, github=FakeGitHub())
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn("never migrated", self.err.getvalue())
        self.assertFalse(any(e[0] == "migrate" for e in setup.log))


class RunAgainTests(SetupCase):
    def test_everything_done_is_skipped(self):
        join = self.joined()
        setup = FakeSetup(self.root, statuses=[TEAM], old_vault=True, migrated=True, github=FakeGitHub())
        setup.missing = []
        setup.set_config(enabled=True, person="alex-example", team_repo_url=URL)
        setup.personal.init_personal()
        setup.personal.inits = 0
        setup.team.pin_path.parent.mkdir(parents=True)
        setup.team.pin_path.write_text("{}", "utf-8")
        self.assertEqual(setup_store.main(["--join", URL, "--no-sync"], setup), 0, self.err.getvalue())
        self.assertEqual(setup.personal.inits, 0)
        self.assertIsNone(join.call_args.args[1])  # pinned already: no fingerprint asked for
        self.assertEqual(setup.log, [])  # not even pip
        self.assertEqual(sum("already done" in line for line in setup.lines), 5)

    def test_an_installed_requirement_keeps_its_version(self):
        setup = setup_store.Setup(self.root)
        from importlib import metadata
        real = metadata.version

        def version(name):
            if name.lower() == "keyring":
                raise metadata.PackageNotFoundError(name)
            return "99.0" if name.lower() == "pillow" else real(name)  # installed, outside the range
        with mock.patch.object(metadata, "version", version):
            self.assertEqual(setup.missing_requirements(), ["keyring>=25,<26"])

    def test_another_github_login_stops(self):
        setup = FakeSetup(self.root, github=FakeGitHub(name="someone-else"))
        setup.set_config(enabled=True, person="alex-example")
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn("gh is signed in as someone-else", self.err.getvalue())

    def test_a_second_team_store_is_refused(self):
        setup = FakeSetup(self.root, statuses=[STORE], migrated=True, github=FakeGitHub())
        setup.set_config(enabled=True, person="alex-example",
                         team_repo_url="https://github.com/example-owner/other-team.git")
        self.assertEqual(setup_store.main(["--join", URL, "--no-sync"], setup), 1)
        self.assertIn("one team store per brain", self.err.getvalue())

    def test_repository_addresses(self):
        repository_of = setup_store.team_github.repository_of
        self.assertEqual(repository_of(URL), "example-owner/brain-team-secrets")
        self.assertEqual(repository_of("https://github.com/example-owner/x"), "example-owner/x")
        with self.assertRaises(setup_store.team_github.GitHubError):
            repository_of("ssh://github.example/example-owner/x.git")


class RecoveryTests(SetupCase):
    """The review's cases: a run that stopped half-way, and a second computer of the same person."""

    def record(self, setup, name, unverified, age):
        folder = setup.root / "migration-backups"
        folder.mkdir(exist_ok=True)
        path = folder / f"{name}.migration.json"
        path.write_text(json.dumps({"entries": ["Example API"], "unverified_signins": unverified}), "utf-8")
        import os
        os.utime(path, (1755501000 + age, 1755501000 + age))

    def test_only_a_clean_newest_record_of_this_vault_counts_as_migrated(self):
        import os
        setup = FakeSetup(self.root, old_vault=True)
        os.utime(setup.vault(), (1755501000, 1755501000))
        migrated = lambda: setup_store.Setup.migrated(setup)  # noqa: E731 - the real check, not the fake's
        self.assertFalse(migrated())
        self.record(setup, "other-20260101-000000", [], 1)  # another vault's record
        self.assertFalse(migrated())
        self.record(setup, "credentials-20260101-000000", ["Example API#oauth_token_json"], 2)  # exit 4
        self.assertFalse(migrated())
        self.record(setup, "credentials-20260102-000000", [], 3)
        self.assertTrue(migrated())
        os.utime(setup.vault(), (1755501000 + 9, 1755501000 + 9))  # a rollback restored into the vault
        self.assertFalse(migrated())

    def test_copies_left_by_an_earlier_run_are_replaced(self):
        unlocked = {"backend": "vault", "unlocked": True}
        setup = FakeSetup(self.root, statuses=[unlocked, unlocked, None, None, STORE], old_vault=True, github=FakeGitHub())
        setup.personal.entries = ["Example API"]  # an earlier run copied one entry, then stopped
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        self.assertIn(("migrate", ("--replace",)), setup.log)

    def test_a_locked_agent_with_the_store_switched_on_is_unlocked_with_the_store_off(self):
        locked, unlocked = {"backend": "vault", "unlocked": False}, {"backend": "vault", "unlocked": True}
        setup = FakeSetup(self.root, statuses=[locked, locked, unlocked, unlocked, None, STORE], old_vault=True,
                          github=FakeGitHub())
        setup.set_config(enabled=True, person="alex-example")
        seen = []
        original = setup.agent_status

        def status():
            seen.append(setup.config().get("enabled"))
            return original()
        setup.agent_status = status
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        self.assertFalse(seen[1])  # switched off before the person was asked to unlock
        self.assertTrue(self.config(setup)["enabled"])

    def test_a_second_computer_joins_its_store_and_leaves_its_old_vault(self):
        join = self.joined(groups=("personal",))
        setup = FakeSetup(self.root, statuses=[None, None, STORE], old_vault=True,
                          github=FakeGitHub(personal="used"))
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        self.assertIs(join.call_args.args[0], setup.personal)
        self.assertEqual(join.call_args.args[1], "ab" * 32)
        self.assertEqual(self.config(setup)["personal_repo_url"], "https://github.com/alex-example/brain-secrets.git")
        self.assertFalse(any(e[0] == "migrate" for e in setup.log))
        self.assertEqual(setup.personal.inits, 0)
        self.assertTrue(setup_store.Setup.migrated(setup))  # a later run does not move the old vault either
        self.assertTrue(any("add-computer" in line for line in setup.lines))

    def test_copies_in_a_store_another_computer_uses_are_never_replaced(self):
        unlocked = {"backend": "vault", "unlocked": True}
        setup = FakeSetup(self.root, statuses=[unlocked], old_vault=True, github=FakeGitHub())
        setup.personal.enrol()
        setup.personal.policy.computers.add(("alex-example", "laptop"))
        setup.personal.entries = ["Example API"]
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn("another computer is in it", self.err.getvalue())
        self.assertFalse(any(e[0] == "migrate" for e in setup.log))

    def test_a_join_stopped_half_way_never_moves_the_old_vault_later(self):
        from secret_store import SecretStoreError
        patcher = mock.patch.object(invite, "join_team", side_effect=SecretStoreError("stopped"))
        patcher.start()
        self.addCleanup(patcher.stop)
        setup = FakeSetup(self.root, old_vault=True, github=FakeGitHub(personal="used"))
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertTrue(setup_store.Setup.migrated(setup))  # decided before enrolment could finish
        setup.personal.enrol()  # the approval had gone through after all
        again = FakeSetup(self.root, statuses=[STORE], old_vault=True, github=FakeGitHub(personal="used"))
        again.personal = setup.personal
        again.migrated = lambda: setup_store.Setup.migrated(again)
        self.assertEqual(setup_store.main(["--no-sync"], again), 0, self.err.getvalue())
        self.assertFalse(any(e[0] == "migrate" for e in again.log))

    def test_enrolment_is_judged_with_the_store_switched_off_too(self):
        setup = setup_store.Setup(self.root)
        with mock.patch("secret_store.store.SecretStore") as personal, mock.patch("secret_store.team.TeamStore"):
            personal.return_value.checkpoint_path.exists.return_value = False
            setup.own_store_ready()
        self.assertEqual(personal.call_args.kwargs.get("enabled"), True)

    def test_an_empty_clone_left_by_an_earlier_run_is_removed_before_init(self):
        setup = FakeSetup(self.root, statuses=[None, None, STORE], github=FakeGitHub())
        (setup.personal.clone / ".git").mkdir(parents=True)
        with mock.patch("secret_store.team.clone_has_history", return_value=False):
            self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        self.assertFalse(setup.personal.clone.exists())
        self.assertEqual(setup.personal.inits, 1)


if __name__ == "__main__":
    unittest.main()
