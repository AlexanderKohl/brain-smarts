"""The mechanics pre-commit hook's territory check: governance and other work stay in separate commits,
except the worker brief, which changes in the same commit as a rule it digests (SMART-RULE-0007)."""
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


if __name__ == "__main__":
    unittest.main()
