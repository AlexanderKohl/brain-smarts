"""The command lines brain_secrets.py and migrate_to_store.py: every subcommand called through main()
with injected fakes (bare local repositories as remotes, a fake keyring, fake recovery-word and
enrolment-word windows). Each call must give the expected exit code, the output must name entries,
fields, groups, people and computers only, and no value, recovery word or private key may appear in
stdout or stderr. Every value here is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import importlib.util
import re
import sys
import unittest
import tempfile
from pathlib import Path
from unittest import mock

from test_secret_store_store import OTHER, VALUE, git, setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from secret_store import store as store_module  # noqa: E402
from secret_store import team as team_module  # noqa: E402
import keyring  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def match(_title, _words):
    return True


class CliCase(TeamCase):
    def setUp(self):
        super().setUp()
        self.cli = _load("brain_secrets")
        for module in (store_module, team_module):
            patcher = mock.patch.object(module, "_default_words_window", self._words)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, argv, expect=0, **fakes):
        """Run main(); check the exit code and that nothing secret was printed; return stdout."""
        before_out, before_err = len(self.out.getvalue()), len(self.err.getvalue())
        code = self.cli.main(argv, **fakes)
        out, err = self.out.getvalue()[before_out:], self.err.getvalue()[before_err:]
        self.assertEqual(code, expect, f"{argv}: {out}{err}")
        text = out + err
        secrets_seen = [VALUE, OTHER, " ".join(self.words)]
        secrets_seen += [v for v in keyring.get_keyring().items.values()]
        for secret in secrets_seen:
            if secret:
                self.assertNotIn(secret, text, f"{argv} printed a secret")
        # No run of three recovery words in order either, whatever stands between them (spaces, line
        # breaks, numbering). A single word is not checked: the words are drawn at random from a list of
        # common English words, and one of them ("another") also stands in a fixed message, which failed
        # this check at random.
        for first, second, third in zip(self.words, self.words[1:], self.words[2:]):
            run = "[^A-Za-z]+".join(re.escape(word) for word in (first, second, third))
            self.assertNotRegex(text, rf"(?i)(?<![A-Za-z]){run}(?![A-Za-z])", f"{argv} printed recovery words")
        return text

    def personal_factory(self, name="a", computer="laptop"):
        store = self.personal(name, computer)
        return lambda: store

    def member_factory(self, name, person, computer):
        store = self.member(name, person, computer)
        return lambda: store


class PersonalCommandTests(CliCase):
    def test_status_and_list_before_and_after_init(self):
        factory = self.personal_factory()
        self.assertIn("not set up", self.run_cli(["status"], store_factory=factory))
        self.run_cli(["list"], expect=1, store_factory=factory)
        self.assertIn("Secrets store:", self.err.getvalue())
        text = self.run_cli(["init"], store_factory=factory)
        self.assertEqual(len(self.words), 24)
        self.assertIn("Trust root fingerprint", text)
        self.assertIn("No entries.", self.run_cli(["list"], store_factory=factory))
        self.assertIn("Recovery package", self.run_cli(["status"], store_factory=factory))
        self.run_cli(["init"], expect=1, store_factory=factory)  # already set up

    def test_status_off_when_not_configured(self):
        from secret_store.store import SecretStore
        text = self.run_cli(["status"], store_factory=lambda: SecretStore(use_config_file=False))
        self.assertIn("off", text)

    def test_put_get_check_list_delete_and_recovery_package(self):
        factory = self.personal_factory()
        self.run_cli(["init"], store_factory=factory)
        ask = lambda title, fields: ({"password": VALUE, "token": OTHER}, None)  # noqa: E731
        text = self.run_cli(["put", "--entry", "CLI Entry", "--secret", "password", "--secret", "token",
                             "--empty-json", "settings"], store_factory=factory, ask=ask)
        self.assertIn("Stored CLI Entry: password, settings, token", text)
        self.run_cli(["put", "--entry", "CLI Entry"], expect=2, store_factory=factory)
        self.run_cli(["put", "--entry", "Never", "--secret", "password"], expect=1, store_factory=factory,
                     ask=lambda title, fields: None)
        self.assertIn("CLI Entry has fields: password, settings, token",
                      self.run_cli(["get-check", "--entry", "CLI Entry"], store_factory=factory))
        self.assertEqual(self.run_cli(["list"], store_factory=factory).strip(), "CLI Entry")
        self.assertIn("Recovery package written", self.run_cli(["recovery-package"], store_factory=factory))
        self.assertIn("nothing was deleted", self.run_cli(
            ["delete", "--entry", "CLI Entry"], expect=1, store_factory=factory, confirm=lambda prompt: "wrong"))
        self.assertIn("Deleted CLI Entry.", self.run_cli(
            ["delete", "--entry", "CLI Entry"], store_factory=factory, confirm=lambda prompt: "CLI Entry"))
        self.run_cli(["get-check", "--entry", "CLI Entry"], expect=1, store_factory=factory)

    def test_enrol_request_and_approve_for_a_second_computer(self):
        first = self.personal_factory("a", "laptop")
        fingerprint = self.run_cli(["init"], store_factory=first).strip().splitlines()[-1]
        new = self.personal_factory("b", "desktop")
        text = self.run_cli(["enrol-request", "--fingerprint", fingerprint], store_factory=new)
        rid = re.search(r"request ([0-9a-f]{16}) written", text).group(1)
        self.assertIn("Request answered", self.run_cli(
            ["enrol-approve", "--request", rid], store_factory=first, display=match))
        self.assertIn("Challenge answered", self.run_cli(
            ["enrol-request", "--request", rid], store_factory=new, display=match))
        self.assertIn("The computer is enrolled.", self.run_cli(
            ["enrol-approve", "--request", rid], store_factory=first, display=match))
        self.run_cli(["enrol-request", "--fingerprint", fingerprint], expect=1, store_factory=new)  # enrolled


class TeamCommandTests(CliCase):
    def setUp(self):
        super().setUp()
        self.team_bare = self.root / "team.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(self.team_bare), cwd=self.root)

    def test_team_commands_end_to_end(self):
        admin = self.member_factory("ta", "alice", "laptop")
        text = self.run_cli(["team-init", "--owner", "example-org"], team_factory=admin)
        self.assertIn("The team secrets store is set up.", text)
        fingerprint = text.strip().splitlines()[-1]
        self.assertIn("Created ops, finance.", self.run_cli(
            ["team-groups", "--create", "ops", "--create", "finance"], team_factory=admin))
        self.run_cli(["team-groups"], expect=2, team_factory=admin)
        ask = lambda title, fields: ({"api_key": VALUE}, None)  # noqa: E731
        self.run_cli(["put", "--entry", "Ops API", "--secret", "api_key", "--group", "ops"],
                     team_factory=admin, ask=ask)
        self.assertEqual(self.run_cli(["list", "--group", "ops"], team_factory=admin).strip(), "Ops API")
        self.assertIn("Ops API has fields: api_key", self.run_cli(
            ["get-check", "--entry", "Ops API", "--group", "ops"], team_factory=admin))
        self.run_cli(["team-admit", "--login", "bob", "--group", "ops"], expect=1, team_factory=admin)

        bob = self.member_factory("tb", "bob", "desktop")
        text = self.run_cli(["enrol-request", "--team", "--fingerprint", fingerprint], team_factory=bob)
        rid = re.search(r"request ([0-9a-f]{16}) written", text).group(1)
        self.assertIn("--team", text)
        self.run_cli(["enrol-approve", "--team", "--request", rid], team_factory=admin, display=match)
        self.run_cli(["enrol-request", "--team", "--request", rid], team_factory=bob, display=match)
        self.assertIn("The computer is enrolled.", self.run_cli(
            ["enrol-approve", "--team", "--request", rid], team_factory=admin, display=match))

        self.assertIn("Admitted bob to ops.", self.run_cli(
            ["team-admit", "--login", "bob", "--group", "ops"], team_factory=admin))
        self.assertIn("bob is now in: ops, finance.", self.run_cli(
            ["team-groups", "--login", "bob", "--group", "ops", "--group", "finance"], team_factory=admin))
        self.run_cli(["delete", "--entry", "Ops API", "--group", "ops"], team_factory=admin,
                     confirm=lambda prompt: "Ops API")
        self.assertIn("Removed and re-keyed.", self.run_cli(["team-remove", "--login", "bob"], team_factory=admin))
        self.run_cli(["team-remove", "--login", "nobody"], expect=1, team_factory=admin)


class MigrationDryRunTests(CliCase):
    def run_migrate(self, answers, expect):
        module = _load("migrate_to_store")

        def broker(operation, **payload):
            self.assertIn(operation, ("status", "vault_list_entries"), "a dry run reads names only")
            return answers[operation]

        with mock.patch("vault_broker_client.broker_request", broker):
            before = len(self.out.getvalue())
            code = module.main(["--dry-run"])
        self.assertEqual(code, expect)
        return self.out.getvalue()[before:]

    def test_dry_run_lists_entries_and_fields_only(self):
        listing = {"Example API": {"api_key": "text", "oauth_token_json": "json"}, "Other": {"password": "text"}}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        vault_path = str(Path(folder.name) / "credentials.vault")  # the migration lock goes beside it
        text = self.run_migrate({"status": {"vault_unlocked": True, "vault_path": vault_path},
                                 "vault_list_entries": listing}, 0)
        self.assertIn("Dry run: 2 entries would be copied", text)
        self.assertIn("Example API: api_key (text), oauth_token_json (json)", text)
        self.assertIn("Other: password (text)", text)
        self.assertNotIn(VALUE, text)

    def test_dry_run_refuses_a_locked_vault(self):
        text = self.run_migrate({"status": {"vault_unlocked": False}}, 2)
        self.assertIn("not unlocked", text)


if __name__ == "__main__":
    unittest.main()
