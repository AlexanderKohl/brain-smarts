"""Fetch-before-write and conflict refusals for task stores (task_git.py), through real Git.

All names and content below are fictional.
"""

from __future__ import annotations

import unittest

from brainfix import NOW, Brain, git, record
from test_tasks import run

import task_git  # noqa: E402
import task_stores  # noqa: E402

POINTER = "/memory/projects/example-app"


class GitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.root = self.brain.root
        self.brain.node(POINTER, "Example app", node_type="project_pointer",
                        repo_url="https://example.com/sam/example-app.git", default_branch="main")
        self.clone = self.brain.checkout("example-app")
        self.path = self.brain.add("open", "TASK-sam-2026-0001-fix", record(
            "TASK-sam-2026-0001", "Fix the form", "ready", refs=["example-app:brain"]), store=self.clone / "brain/tasks")
        git(self.clone, "add", ".")
        git(self.clone, "commit", "-q", "-m", "a task")
        git(self.clone, "push", "-q")

    def tearDown(self) -> None:
        self.brain.close()

    def store(self):
        return task_stores.store_for(self.root, POINTER)

    def note(self, *extra: str) -> tuple[int, str]:
        return run(*extra, "note", "TASK-sam-2026-0001", "--note", "Checked.", "--now", NOW, "--no-board", cwd=self.root)

    def test_an_up_to_date_checkout_on_its_branch_is_written(self) -> None:
        self.assertEqual(task_git.ready_to_write(self.store()), [])
        code, out = self.note()
        self.assertEqual(code, 0, out)
        self.assertIn("sam: note", self.path.read_text(encoding="utf-8"))

    def test_the_wrong_branch_is_refused(self) -> None:
        git(self.clone, "checkout", "-q", "-b", "elsewhere")
        code, out = self.note()
        self.assertEqual(code, 1)
        self.assertIn("on elsewhere, not the store branch main", out)
        self.assertNotIn("Checked.", self.path.read_text(encoding="utf-8"))

    def test_a_checkout_behind_origin_is_refused(self) -> None:
        other = self.brain.tmp / "other"
        git(self.brain.tmp, "clone", "-q", str(self.brain.tmp / "origins/example-app.git"), "other")
        (other / "brain" / "extra.md").write_text("---\nid: extra\n---\n", encoding="utf-8")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "bob's change")
        git(other, "push", "-q")
        code, out = self.note()
        self.assertEqual(code, 1)
        self.assertIn("1 commit(s) behind origin/main", out)
        self.assertIn("pull --ff-only", out)

    def test_a_failed_fetch_is_refused_unless_offline(self) -> None:
        git(self.clone, "remote", "set-url", "origin", str(self.brain.tmp / "nowhere.git"))
        code, out = self.note()
        self.assertEqual(code, 1)
        self.assertIn("fetch origin main` failed", out)
        code, out = self.note("--offline")
        self.assertEqual(code, 0, out)
        self.assertIn("offline, not fetched", out)

    def test_a_conflict_marker_is_refused_in_every_store(self) -> None:
        self.path.write_text(self.path.read_text(encoding="utf-8") + "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> x\n",
                             encoding="utf-8")
        code, out = self.note()
        self.assertEqual(code, 1)
        self.assertIn("has a Git conflict marker", out)
        memory = self.brain.add("open", "TASK-sam-2026-0002-mem", record("TASK-sam-2026-0002", "Memory task", "ready")
                                + ">>>>>>> theirs\n")
        code, out = run("done", "TASK-sam-2026-0002", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertTrue(memory.is_file())
        self.assertTrue(task_git.conflicted(memory.read_text(encoding="utf-8")))

    def test_an_unmerged_path_is_refused(self) -> None:
        other = self.brain.tmp / "other"
        git(self.brain.tmp, "clone", "-q", str(self.brain.tmp / "origins/example-app.git"), "other")
        for clone, words in ((other, "Bob's words."), (self.clone, "Sam's words.")):
            target = clone / "brain/tasks/open/TASK-sam-2026-0001-fix.md"
            target.write_text(target.read_text(encoding="utf-8") + words + "\n", encoding="utf-8")
            git(clone, "commit", "-q", "-am", words)
        git(other, "push", "-q")
        git(self.clone, "fetch", "-q")
        try:
            git(self.clone, "merge", "-q", "origin/main")
        except RuntimeError:
            pass
        self.path.write_text(record("TASK-sam-2026-0001", "Fix the form", "ready", refs=["example-app:brain"]),
                             encoding="utf-8")       # markers removed, but Git still says unmerged
        self.assertEqual(task_git.unmerged_paths(self.clone, self.clone / "brain/tasks"), [self.path])
        with self.assertRaises(task_git.WriteRefused) as refused:
            task_git.ready_to_write(self.store(), offline=True)
        self.assertIn("unmerged in Git", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
