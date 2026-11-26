"""SMART-RULE-0026 for this skill: the version in SKILL.md moves with every change to the skill's files.
The first test is the check itself: it fails when a file changed and VERSION-LEDGER.json was not
recorded under a raised version. The others show the check catching a change on a copy of the skill,
--record refusing an unraised version, line endings not counting, and the commands printing the
version. Nothing here touches a credential."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skill_version  # noqa: E402


class TheSkillsVersionTest(unittest.TestCase):
    def test_the_ledger_records_this_version_and_these_files(self):
        ledger = skill_version.recorded()
        self.assertEqual(ledger.get("version"), skill_version.version(),
                         "SKILL.md's version is not the recorded one: run python scripts/skill_version.py --record")
        self.assertEqual(ledger.get("fingerprint"), skill_version.fingerprint(),
                         "the skill's files changed since the version was recorded: raise metadata.version in "
                         "SKILL.md (SMART-RULE-0026), then run python scripts/skill_version.py --record")


class OnACopy(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.skill = root / "skill"
        shutil.copytree(skill_version.SKILL, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        for name, value in (("SKILL", self.skill), ("LEDGER", self.skill / "VERSION-LEDGER.json")):
            patcher = mock.patch.object(skill_version, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.committed = dict(skill_version.recorded())
        patcher = mock.patch.object(skill_version, "committed", lambda: self.committed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def bump(self, new):
        text = (self.skill / "SKILL.md").read_text("utf-8")
        (self.skill / "SKILL.md").write_text(text.replace(f"version: {skill_version.version()}", f"version: {new}", 1),
                                             "utf-8")

    def test_a_changed_file_changes_the_fingerprint(self):
        before = skill_version.fingerprint()
        with (self.skill / "scripts" / "setup_store.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# a change\n")
        self.assertNotEqual(skill_version.fingerprint(), before)

    def test_line_endings_do_not_count(self):
        before = skill_version.fingerprint()
        path = self.skill / "scripts" / "team_github.py"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(skill_version.fingerprint(), before)

    def test_record_refuses_a_change_under_the_committed_version(self):
        (self.skill / "scripts" / "team_github.py").write_text("# changed\n", "utf-8")
        with self.assertRaisesRegex(SystemExit, "raise metadata.version"):
            skill_version.record()
        self.bump("9.8.7")
        self.assertEqual(skill_version.record(), "9.8.7: recorded")
        self.assertEqual(skill_version.recorded(), {"version": "9.8.7", "fingerprint": skill_version.fingerprint()})
        (self.skill / "scripts" / "team_github.py").write_text("# changed again\n", "utf-8")
        self.assertEqual(skill_version.record(), "9.8.7: recorded")  # still uncommitted: recorded again

    def test_the_ledger_itself_is_not_part_of_the_fingerprint(self):
        before = skill_version.fingerprint()
        skill_version.LEDGER.write_text("{}", "utf-8")
        self.assertEqual(skill_version.fingerprint(), before)


class CommandsTest(unittest.TestCase):
    def output(self, main, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(argv), 0)
        return out.getvalue().strip()

    def test_both_commands_print_the_version(self):
        import brain_secrets
        import setup_store
        expected = f"manage-credentials {skill_version.version()}"
        self.assertEqual(self.output(brain_secrets.main, ["--version"]), expected)
        self.assertEqual(self.output(setup_store.main, ["--version"]), expected)
        self.assertEqual(self.output(skill_version.main, []), expected)


if __name__ == "__main__":
    unittest.main()
