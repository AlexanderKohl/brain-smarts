"""The scheduled review writes only the ignored /temp/due.md and changes nothing Git tracks."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]


class ScheduledReviewTest(unittest.TestCase):
    def test_writes_due_file_and_leaves_git_clean(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        run = subprocess.run([sys.executable, str(ROOT / "shared/skills/tasks/scripts/scheduled_review.py")],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        due = (ROOT / "temp" / "due.md").read_text(encoding="utf-8")
        self.assertIn("## Tasks due, blocked or waiting", due)
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
