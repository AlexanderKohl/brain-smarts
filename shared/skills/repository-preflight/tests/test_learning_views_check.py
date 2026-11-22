"""The preflight check that the learning index and board are current (SMART-RULE-0028)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import checks_b  # noqa: E402

BRAIN = HERE.parents[4]
GENERATOR = BRAIN / "shared" / "skills" / "learning-maintenance" / "scripts" / "learning_views.py"
RECORD = """---
id: LEARN-1
title: A fictional learning
type: learning
category: working-methods
created: 2026-01-01T00:00:00+10:00
evidence_status: unverified
review_status: pending
next_action: Look at it.
---

Body.
"""


def make_brain(root, with_records=True):
    target = root / "shared" / "skills" / "learning-maintenance" / "scripts"
    target.mkdir(parents=True)
    shutil.copy(GENERATOR, target / "learning_views.py")
    (root / "memory").mkdir()
    if with_records:
        learnings = root / "memory/projects/brain-development/data/learnings"
        learnings.mkdir(parents=True)
        (learnings / "learn-1.md").write_text(RECORD, encoding="utf-8")


def build(root):
    sys.path.insert(0, str(GENERATOR.parent))
    import learning_views
    learning_views.cmd_build(root, None)


class LearningViewsCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_check(self):
        errors = []
        checks_b.validate_learning_views(self.root, errors)
        return errors

    def test_current_views_pass(self):
        make_brain(self.root)
        build(self.root)
        self.assertEqual(self.run_check(), [])

    def test_stale_board_fails_with_rebuild_command(self):
        make_brain(self.root)
        build(self.root)
        board = self.root / "memory/projects/brain-development/data/learning/board.md"
        board.write_text(board.read_text(encoding="utf-8").replace("Look at it.", "Changed by hand."), encoding="utf-8")
        errors = self.run_check()
        self.assertEqual(len(errors), 1)
        self.assertIn("board.md", errors[0])
        self.assertIn("learning_views.py build", errors[0])

    def test_no_learning_folder_passes(self):
        make_brain(self.root, with_records=False)
        self.assertEqual(self.run_check(), [])

    def test_no_memory_skips(self):
        self.assertEqual(self.run_check(), [])

    def test_generator_that_raises_gives_one_error(self):
        make_brain(self.root)
        (self.root / "shared/skills/learning-maintenance/scripts/learning_views.py").write_text(
            "raise RuntimeError('boom')\n", encoding="utf-8")
        errors = self.run_check()
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])
        self.assertNotIn("Traceback", errors[0])


if __name__ == "__main__":
    unittest.main()
