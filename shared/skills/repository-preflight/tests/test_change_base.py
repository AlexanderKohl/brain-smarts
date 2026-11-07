"""Where a repository's changes are measured from, while a merge of the mainline is in progress.

A merge of `origin/main` stages everything the mainline changed since the branch left it. Those
changes are already on the branch where a change becomes active (CONTRACT §13.2), so they are not
this commit's changes: during the merge they are measured from the merged-in mainline commit, as
they are once the merge is committed. A merge of anything else is measured as before.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from preflight_base import change_base, repository_changes  # noqa: E402

HAS_GIT = shutil.which("git") is not None


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "core.hooksPath=", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, relative: str, text: str) -> None:
    (repo / relative).parent.mkdir(parents=True, exist_ok=True)
    (repo / relative).write_text(text, encoding="utf-8")


@unittest.skipIf(not HAS_GIT, "git not available")
class ChangeBaseDuringMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        repo = self.repo
        git(repo, "init", "-q", "-b", "main")
        write(repo, "RULES.md", "rules\n")
        write(repo, "notes.md", "notes\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "fork point")
        self.fork = git(repo, "rev-parse", "HEAD")
        # The branch's own change.
        git(repo, "checkout", "-qb", "proposal/x")
        write(repo, "branch.md", "branch\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "branch work")
        # The mainline's accepted change since the fork, published as origin/main.
        git(repo, "checkout", "-q", "main")
        write(repo, "RULES.md", "rules, accepted on main\n")
        git(repo, "commit", "-qam", "main work")
        self.main = git(repo, "rev-parse", "HEAD")
        git(repo, "update-ref", "refs/remotes/origin/main", self.main)
        git(repo, "checkout", "-q", "proposal/x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_ordinary_branch_is_measured_from_where_it_left_the_mainline(self):
        self.assertEqual(change_base(self.repo), self.fork)

    def test_during_a_merge_of_the_mainline_its_changes_are_not_counted(self):
        git(self.repo, "merge", "--no-commit", "--no-ff", "origin/main")
        base, paths = repository_changes(self.repo)
        self.assertEqual(base, self.main)
        self.assertNotIn("RULES.md", paths)
        self.assertIn("branch.md", paths)

    def test_a_merge_of_an_older_mainline_commit_is_measured_from_it(self):
        git(self.repo, "checkout", "-q", "main")
        write(self.repo, "later.md", "later\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "more main work")
        git(self.repo, "update-ref", "refs/remotes/origin/main", git(self.repo, "rev-parse", "HEAD"))
        git(self.repo, "checkout", "-q", "proposal/x")
        git(self.repo, "merge", "--no-commit", "--no-ff", self.main)
        base, paths = repository_changes(self.repo)
        self.assertEqual(base, self.main)
        self.assertNotIn("RULES.md", paths)

    def test_after_the_merge_is_committed_it_is_measured_from_the_mainline(self):
        git(self.repo, "merge", "--no-ff", "-qm", "merge main", "origin/main")
        base, paths = repository_changes(self.repo)
        self.assertEqual(base, self.main)
        self.assertNotIn("RULES.md", paths)

    def test_a_merge_of_a_branch_not_on_the_mainline_is_measured_as_before(self):
        git(self.repo, "checkout", "-qb", "other", self.fork)
        write(self.repo, "RULES.md", "rules, unreviewed elsewhere\n")
        git(self.repo, "commit", "-qam", "other work")
        git(self.repo, "checkout", "-q", "proposal/x")
        git(self.repo, "merge", "--no-commit", "--no-ff", "other")
        base, paths = repository_changes(self.repo)
        self.assertEqual(base, self.fork)
        self.assertIn("RULES.md", paths)


if __name__ == "__main__":
    unittest.main()
