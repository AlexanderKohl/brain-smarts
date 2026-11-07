"""No board page is written into the shared checkout's memory (SMART-RULE-0038, TASK-alec-2026-0312).

A temporary folder holds an invented brain laid out as on the owner's machine: a shared checkout
(the mechanics and the memory, each a git repository of its own, with a copy of the owner-board
and tasks skills), a session copy of it made of linked worktrees, and a project repository whose
`brain/status` holds a repository board. One board lives in memory, one in the repository.

The fault this guards against: a command run against the shared checkout (`card.py --root
<shared>`, `build_status.py`, `apply_events.py`, `build_boards.py`, the board refresh of
`tasks.py`) rebuilt the directory, the personal board and the owner's pages of the repository
boards there, so tracked memory files differed from HEAD by their time only and the next
`session.py finish` could not fast-forward the checkout. Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
SKILLS = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILLS / "repository-preflight" / "scripts"))

import board_config  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import task_board  # noqa: E402
from board_fixtures import Brain, quiet  # noqa: E402

HAS_GIT = shutil.which("git") is not None
FICTIONAL = {"GIT_AUTHOR_NAME": "Example Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
             "GIT_COMMITTER_NAME": "Example Tester", "GIT_COMMITTER_EMAIL": "tester@example.com"}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(" ".join(args) + ": " + done.stderr)
    return done.stdout


def snapshot(folder: Path) -> dict:
    """Every file under `folder` outside `.git`: its modification time and its content's hash.
    A page rewritten with the same words still changes its time, so either difference shows."""
    found = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(folder).parts:
            found[path.relative_to(folder).as_posix()] = (path.stat().st_mtime_ns,
                                                          hashlib.sha256(path.read_bytes()).hexdigest())
    return found


@unittest.skipUnless(HAS_GIT, "git is not installed")
class SharedCheckoutTests(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, FICTIONAL)
        self.env.start()
        os.environ.pop(board_config.SHARED_CHECKOUT_ENV, None)
        self.brain = Brain(shared=True, second_board=True)
        self.shared = self.brain.root
        for skill in ("owner-board", "tasks"):
            shutil.copytree(SKILLS / skill, self.shared / "shared" / "skills" / skill,
                            ignore=shutil.ignore_patterns("__pycache__", "tests"))
        # The pages as the last finish left them, built before memory became a repository.
        quiet(build_status.main, ["--root", str(self.shared), "--all", "--no-fetch"])
        (self.shared / ".gitignore").write_text("memory/\n", encoding="utf-8")
        # git keeps no empty folder, and without the owner store the copy draws no task pages
        (self.shared / "memory" / "tasks" / "open" / "README.txt").write_text("the owner store\n", encoding="utf-8")
        for repo in (self.shared, self.shared / "memory"):
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "start")
        self.copy = self.shared.parent / (self.shared.name + "-sessions") / "copy"
        git(self.shared, "worktree", "add", "-q", "-b", "session/copy", str(self.copy))
        git(self.shared / "memory", "worktree", "add", "-q", "-b", "session/copy", str(self.copy / "memory"))
        self.before = snapshot(self.shared / "memory")
        self.copy_before = snapshot(self.copy / "memory")
        self.assertIn("boards/index.html", self.before)
        self.assertIn("projects/example-pond/status/status.html", self.before)
        time.sleep(0.05)   # so a rewrite cannot keep the same modification time

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.copy.parent, ignore_errors=True)
        self.brain.close()

    def rewritten_in_copy(self) -> set:
        after = snapshot(self.copy / "memory")
        return {path for path, seen in after.items() if self.copy_before.get(path) != seen}

    def assert_shared_unchanged(self):
        self.assertEqual(snapshot(self.shared / "memory"), self.before)
        self.assertEqual(git(self.shared / "memory", "status", "--porcelain"), "")

    def test_the_finish_refresh_writes_in_the_copy_and_never_in_the_shared_checkout(self):
        import session
        out = io.StringIO()
        with redirect_stdout(out):
            session.refresh(self.copy)
        self.assertNotIn("exited", out.getvalue())
        self.assert_shared_unchanged()
        rewritten = self.rewritten_in_copy()                               # rebuilt where the session works:
        self.assertIn("boards/index.html", rewritten)                      # the directory,
        self.assertIn("boards/personal.html", rewritten)                   # the personal board,
        self.assertIn("boards/projects/garden.html", rewritten)            # the owner's page of the repository board
        self.assertIn("projects/example-pond/status/status.html", rewritten)   # and the board in memory

    def test_a_board_command_aimed_at_the_shared_checkout_writes_nothing_in_its_memory(self):
        import card as card_cli
        commands = [
            (build_status.main, ["--root", str(self.shared), "--board", "garden", "--no-fetch"]),
            (build_status.main, ["--root", str(self.shared), "--board", "pond", "--no-fetch"]),
            (build_status.main, ["--root", str(self.shared), "--all", "--no-fetch"]),
            (build_boards.main, ["--root", str(self.shared), "--no-fetch"]),
            (task_board.main, ["--root", str(self.shared), "--no-fetch", "build", "--for", "TASK-2026-0901"]),
            (card_cli.main, ["--root", str(self.shared), "--board", "garden", "--no-fetch",
                             "new", "--track", "beds", "--title", "Edge the beds"]),
        ]
        for main, argv in commands:
            with self.subTest(argv=argv[2:]):
                _, said = quiet(main, argv)
                self.assertEqual(sorted(p for p, seen in snapshot(self.shared / "memory").items()
                                        if self.before.get(p) != seen), [])
                self.assert_shared_unchanged()
                self.assertIn("shared checkout", said)                  # and it says why
                self.assertIn("SMART-RULE-0038", said)
        # The repository board's own page is the repository's business, and is still drawn.
        page = self.brain.checkout / "brain" / "status" / "status.html"
        self.assertIn("Edge the beds", page.read_text(encoding="utf-8"))

    def test_the_owner_can_still_write_there_on_purpose(self):
        with mock.patch.dict(os.environ, {board_config.SHARED_CHECKOUT_ENV: "1"}):
            _, said = quiet(build_boards.main, ["--root", str(self.shared), "--no-fetch"])
        self.assertNotIn("shared checkout", said)
        self.assertNotEqual(snapshot(self.shared / "memory")["boards/index.html"], self.before["boards/index.html"])

    def test_the_same_commands_in_the_session_copy_write_there(self):
        _, said = quiet(build_status.main, ["--root", str(self.copy), "--all", "--no-fetch"])
        self.assertNotIn("shared checkout", said)
        self.assert_shared_unchanged()
        self.assertIn("boards/personal.html", self.rewritten_in_copy())


if __name__ == "__main__":
    unittest.main()
