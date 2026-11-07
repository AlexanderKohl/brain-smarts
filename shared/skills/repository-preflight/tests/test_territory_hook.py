"""The mechanics pre-commit hook's territory check: governance and other work stay in separate commits,
except the worker brief, which changes in the same commit as a rule it digests (SMART-RULE-0007).
A merge is judged by its own changes, not by everything the merged-in side brings."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HOOK = ROOT / ".githooks" / "pre-commit"
BRIEF = "shared/skills/delegate-work/templates/worker-brief.template.md"
SH = shutil.which("sh")


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=repo,
                          capture_output=True, text=True)


@unittest.skipIf(SH is None, "no POSIX shell")
class TerritoryHookTest(unittest.TestCase):
    def commit(self, *paths):
        """Stage the given paths in a fresh repository with no brain above it and commit them."""
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "mechanics"
            (repo / ".githooks").mkdir(parents=True)
            shutil.copy(HOOK, repo / ".githooks" / "pre-commit")
            git(repo, "init", "-q")
            git(repo, "config", "core.hooksPath", ".githooks")
            for path in paths:
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_text("x\n", encoding="utf-8")
            git(repo, "add", "--", *paths)
            return git(repo, "commit", "-qm", "change")

    def test_a_rule_and_the_worker_brief_share_one_commit(self):
        result = self.commit("RULES.md", BRIEF)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_rule_and_other_work_are_still_refused(self):
        result = self.commit("RULES.md", "shared/skills/delegate-work/SKILL.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("two territories", result.stdout + result.stderr)

    def test_the_brief_does_not_carry_other_work_past_the_check(self):
        result = self.commit("RULES.md", BRIEF, "shared/skills/delegate-work/templates/packet.template.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("packet.template.md", result.stdout + result.stderr)


@unittest.skipIf(SH is None, "no POSIX shell")
class MergeTerritoryTest(unittest.TestCase):
    """A branch that has left the mainline, which since changed a rule and other work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = self.repo = Path(self.tmp.name) / "mechanics"
        (repo / ".githooks").mkdir(parents=True)
        shutil.copy(HOOK, repo / ".githooks" / "pre-commit")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "core.hooksPath", ".githooks")
        self.write("RULES.md", "rules\n")
        self.write("shared/skills/a/SKILL.md", "skill\n")
        git(repo, "add", "-A")
        git(repo, "commit", "--no-verify", "-qm", "fork point")
        git(repo, "checkout", "-qb", "proposal/x")
        self.write("governance/proposals/x.md", "proposal\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "the proposal")
        git(repo, "checkout", "-q", "main")
        self.write("RULES.md", "rules, accepted on main\n")
        self.write("shared/skills/a/SKILL.md", "skill, changed on main\n")
        git(repo, "commit", "--no-verify", "-qam", "main work across both territories")
        git(repo, "checkout", "-q", "proposal/x")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, text):
        (self.repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / relative).write_text(text, encoding="utf-8")

    def merge_main(self):
        result = git(self.repo, "merge", "--no-commit", "--no-ff", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_merge_of_the_mainline_is_not_a_sweep(self):
        self.merge_main()
        result = git(self.repo, "commit", "-qm", "merge main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_merge_whose_own_changes_span_both_territories_is_refused(self):
        self.merge_main()
        self.write("RULES.md", "rules, changed in the merge\n")
        self.write("shared/skills/b/SKILL.md", "new in the merge\n")
        git(self.repo, "add", "-A")
        result = git(self.repo, "commit", "-qm", "merge main")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("merge's own changes span both", output)
        self.assertIn("shared/skills/b/SKILL.md", output)
        self.assertNotIn("shared/skills/a/SKILL.md", output)

    def test_an_ordinary_commit_on_the_branch_is_still_refused(self):
        self.write("RULES.md", "rules, changed on the branch\n")
        self.write("shared/skills/a/SKILL.md", "skill, changed on the branch\n")
        git(self.repo, "add", "-A")
        result = git(self.repo, "commit", "-qm", "sweep")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("two territories", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
