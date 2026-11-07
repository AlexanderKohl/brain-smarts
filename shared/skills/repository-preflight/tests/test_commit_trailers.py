"""SMART-RULE-0009: a commit names its tool and model in trailers; the hook refuses one that does not,
and lets a merge through."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hooks  # noqa: E402

BOTH = "Fix the widget's empty input\n\nTool: Claude Code desktop\nCo-Authored-By: Claude Opus 5.5 <noreply@example.com>\n"


class CommitTrailersTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        brain = Path(self.folder.name) / "brain"
        (brain / "shared").mkdir(parents=True)
        (brain / "CONTRACT.md").write_text("x\n", encoding="utf-8")
        # The memory layer: the trailer check runs there, the personal-data scan does not.
        self.repo = brain / "memory"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

    def check(self, message: str) -> int:
        path = Path(self.folder.name) / "message.txt"
        path.write_text(message, encoding="utf-8")
        return hooks.commit_msg(self.repo, path)

    def test_both_trailers_pass(self):
        self.assertEqual(self.check(BOTH), 0)

    def test_a_missing_tool_trailer_is_refused(self):
        self.assertEqual(self.check(BOTH.replace("Tool: Claude Code desktop\n", "")), 1)

    def test_a_missing_model_trailer_is_refused(self):
        self.assertEqual(self.check(BOTH.replace("Co-Authored-By: Claude Opus 5.5 <noreply@example.com>\n", "")), 1)

    def test_the_tool_in_the_subject_does_not_count(self):
        self.assertEqual(self.check("Claude Code desktop Opus 5.5: fix the widget\n"), 1)

    def test_a_merge_needs_no_trailers(self):
        git_dir = Path(subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=self.repo, capture_output=True,
                                      text=True).stdout.strip())
        (git_dir / "MERGE_HEAD").write_text("0" * 40 + "\n", encoding="utf-8")
        self.assertEqual(self.check("Merge branch 'main'\n"), 0)


if __name__ == "__main__":
    unittest.main()
