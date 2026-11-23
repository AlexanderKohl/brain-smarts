"""brain_secrets.py restore (personal and --team) and recovery-package --team (plan rows M6 and M7):
the recovery words come only through the injected masked-window reader, the package is chosen by path,
the target must be new or empty, freshness is reported, and a refusal writes nothing. Bare local
repositories and a fake keyring only. Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_secret_store_cli import CliCase  # noqa: E402
from test_secret_store_store import VALUE, setUpModule, tearDownModule  # noqa: E402,F401

from secret_store import recovery  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402
from secret_store.team import TeamStore  # noqa: E402


class RestoreCommand(CliCase):
    def words_reader(self, words=None):
        seen = []

        def ask(title, fields):
            seen.append(fields)
            return ({fields[0]: words if words is not None else " ".join(self.words)}, None)
        return ask, seen

    def personal_package(self):
        factory = self.personal_factory()
        self.run_cli(["init"], store_factory=factory)
        factory().open().put_entry("Example API", {"api_key": VALUE})
        text = self.run_cli(["recovery-package"], store_factory=factory)
        return Path(text.split("Recovery package written: ", 1)[1].strip())

    def test_personal_restore_reports_freshness_and_reads_the_entry(self):
        package, target = self.personal_package(), self.root / "restored"
        ask, seen = self.words_reader()
        text = self.run_cli(["restore", "--package", str(package), "--target", str(target)], ask=ask)
        self.assertEqual(seen, [["Recovery words"]])
        self.assertIn("Freshness: the package was made 0 day(s) ago", text)
        self.assertTrue((target / "brain-secrets" / ".git").is_dir())
        again = SecretStore.restore_from_package(" ".join(self.words), package, self.root / "check")
        self.assertEqual(again.get_record("Example API"), {"api_key": VALUE})

    def test_wrong_words_write_nothing(self):
        package, target = self.personal_package(), self.root / "restored"
        ask, _seen = self.words_reader(recovery.generate_mnemonic())
        self.assertIn("nothing was written", self.run_cli(
            ["restore", "--package", str(package), "--target", str(target)], expect=1, ask=ask))
        self.assertFalse(target.exists())
        target.mkdir()
        ask, _seen = self.words_reader("not a recovery phrase")
        self.run_cli(["restore", "--package", str(package), "--target", str(target)], expect=1, ask=ask)
        self.assertEqual(list(target.iterdir()), [])

    def test_a_damaged_package_writes_nothing(self):
        package, target = self.personal_package(), self.root / "restored"
        data = bytearray(package.read_bytes())
        data[-20] ^= 1
        damaged = self.root / "damaged.package"
        damaged.write_bytes(bytes(data))
        ask, _seen = self.words_reader()
        self.run_cli(["restore", "--package", str(damaged), "--target", str(target)], expect=1, ask=ask)
        self.assertFalse(target.exists())

    def test_a_non_empty_target_is_refused_before_the_words_are_asked(self):
        package, target = self.personal_package(), self.root / "busy"
        target.mkdir()
        (target / "keep.txt").write_text("kept")
        ask, seen = self.words_reader()
        self.assertIn("new or empty folder", self.run_cli(
            ["restore", "--package", str(package), "--target", str(target)], expect=1, ask=ask))
        self.assertEqual(seen, [])
        self.assertEqual([p.name for p in target.iterdir()], ["keep.txt"])

    def test_cancelled_window_restores_nothing(self):
        package, target = self.personal_package(), self.root / "restored"
        self.run_cli(["restore", "--package", str(package), "--target", str(target)], expect=1,
                     ask=lambda _t, _f: None)
        self.assertFalse(target.exists())


class TeamPackageAndRestore(CliCase):
    def test_team_package_then_team_restore(self):
        admin, _pinned = self.team_setup()
        text = self.run_cli(["recovery-package", "--team"], team_factory=lambda: admin)
        package = Path(text.split("Recovery package written: ", 1)[1].strip())
        self.assertIn("brain-team-secrets", package.name)
        target = self.root / "team-restored"
        ask = lambda _t, fields: ({fields[0]: " ".join(self.words)}, None)  # noqa: E731
        text = self.run_cli(["restore", "--team", "--package", str(package), "--target", str(target)], ask=ask)
        self.assertIn("Restored the team store", text)
        self.assertIn("day(s) ago", text)
        self.assertTrue((target / "brain-team-secrets" / ".git").is_dir())
        check = TeamStore.restore_from_package(" ".join(self.words), package, self.root / "check")
        self.assertEqual(check.get_record("Ops API", group="ops"), {"api_key": VALUE})

    def test_unwritable_team_folder_warns_and_writes_the_upkeep_error(self):
        admin, _pinned = self.team_setup()
        blocker = self.root / "blocked-cloud"
        blocker.write_text("not a folder")
        admin.config["recovery_package_dir"] = blocker / "brain-secrets-recovery"
        text = self.run_cli(["recovery-package", "--team"], expect=1, team_factory=lambda: admin)
        self.assertIn("Warning: the recovery package could not be written", text)
        self.assertIn("recovery-package --team", text)
        upkeep = Path(admin.config["checkpoint_dir"]) / (admin._package_path().name + ".upkeep-error")
        self.assertTrue(upkeep.is_file())


if __name__ == "__main__":
    unittest.main()
