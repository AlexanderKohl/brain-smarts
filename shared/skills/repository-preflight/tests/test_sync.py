"""Start from the latest (SMART-RULE-0034): what sync.py does to a repository in each state.

Every repository is invented, in a temporary folder; `origin` is a local bare repository.
Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sync  # noqa: E402

HAS_GIT = shutil.which("git") is not None


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=Example Tester", "-c", "user.email=tester@example.com",
                           "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", "change " + name)


@unittest.skipUnless(HAS_GIT, "git is not installed")
class SyncTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="sync-"))
        self.origin = self.base / "origin.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.other = self.base / "other"      # the other computer
        self.here = self.base / "here"        # this computer
        git(self.base, "clone", "-q", str(self.origin), str(self.other))
        commit(self.other, "notes.md", "first\n")
        git(self.other, "push", "-q", "origin", "main")
        git(self.base, "clone", "-q", str(self.origin), str(self.here))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def push_from_other(self, name: str = "other.md") -> None:
        commit(self.other, name, "from the other computer\n")
        git(self.other, "push", "-q", "origin", "main")

    def test_up_to_date_says_so(self):
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["ok"]), ("up to date", True))

    def test_behind_and_clean_is_fast_forwarded(self):
        self.push_from_other()
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["ok"]), ("updated", True))
        self.assertTrue((self.here / "other.md").exists())

    def test_behind_with_changes_is_left_alone(self):
        self.push_from_other()
        (self.here / "notes.md").write_text("edited here\n", encoding="utf-8")
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["ok"]), ("behind, with changes", False))
        self.assertFalse((self.here / "other.md").exists())
        self.assertEqual((self.here / "notes.md").read_text(encoding="utf-8"), "edited here\n")

    def test_diverged_is_left_alone(self):
        self.push_from_other()
        commit(self.here, "mine.md", "made here\n")
        before = git(self.here, "rev-parse", "HEAD")
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["ok"]), ("diverged", False))
        self.assertEqual(git(self.here, "rev-parse", "HEAD"), before)

    def test_ahead_is_reported_not_pushed(self):
        commit(self.here, "mine.md", "made here\n")
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["detail"]), ("ahead", "1 commit(s) not pushed yet"))
        self.assertNotIn("mine.md", git(self.other, "ls-remote", "origin"))

    def test_an_unreachable_origin_is_reported(self):
        git(self.here, "remote", "set-url", "origin", str(self.base / "missing.git"))
        r = sync.sync_one("memory", self.here)
        self.assertEqual((r["state"], r["ok"]), ("unreachable", False))

    def test_untracked_files_do_not_block_a_fast_forward(self):
        self.push_from_other()
        (self.here / "scratch.txt").write_text("not tracked\n", encoding="utf-8")
        self.assertEqual(sync.sync_one("memory", self.here)["state"], "updated")

    def test_the_brain_repositories_are_found_from_the_root(self):
        root = self.base / "brain"
        root.mkdir()
        (root / "CONTRACT.md").write_text("contract\n", encoding="utf-8")
        git(self.base, "clone", "-q", str(self.origin), str(root / "memory"))
        names = [name for name, _ in sync.repositories(root, [self.here])]
        self.assertEqual(names, ["mechanics", "memory", "here"])


if __name__ == "__main__":
    unittest.main()
