"""The refresh commit `session.py finish` makes carries both trailers SMART-RULE-0009 asks for,
and passes the brain's real commit-msg hook.

A temporary folder is laid out as a brain (a CONTRACT.md and a copy of these scripts) holding one
git repository whose hooks are the brain's own `/.githooks/commit-msg`. Every name and address is
invented. Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/scripts/tests -v
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
BRAIN = SCRIPTS.parents[3]
sys.path.insert(0, str(SCRIPTS))

import session  # noqa: E402

HAS_GIT = shutil.which("git") is not None
FICTIONAL = {"GIT_AUTHOR_NAME": "Example Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
             "GIT_COMMITTER_NAME": "Example Tester", "GIT_COMMITTER_EMAIL": "tester@example.com"}
AGENT = "Example Agent 1.0 <agent@example.com>"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, text=True)


@unittest.skipUnless(HAS_GIT and (BRAIN / ".githooks" / "commit-msg").is_file(), "git or the hook is missing")
class RefreshTrailerTests(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, FICTIONAL)
        self.env.start()
        os.environ.pop(session.CO_AUTHOR_ENV, None)
        self.base = Path(tempfile.mkdtemp(prefix="refresh-trailers-"))
        (self.base / "CONTRACT.md").write_text("an invented brain\n", encoding="utf-8")
        shutil.copytree(SCRIPTS, self.base / "shared/skills/repository-preflight/scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))
        hooks = self.base / "hooks"
        hooks.mkdir()
        shutil.copy2(BRAIN / ".githooks" / "commit-msg", hooks / "commit-msg")
        self.repo = self.base / "memory"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q", "-b", "main")
        run_git(self.repo, "config", "core.hooksPath", str(hooks).replace("\\", "/"))

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.base, ignore_errors=True)

    def seed(self, message: str, verify: bool = True) -> subprocess.CompletedProcess:
        (self.repo / "notes.md").write_text(message, encoding="utf-8")
        run_git(self.repo, "add", "-A")
        return run_git(self.repo, "commit", "-q", "-m", message, *([] if verify else ["--no-verify"]))

    def regenerate(self) -> str:
        (self.repo / "boards.html").write_text("<p>rebuilt</p>\n", encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            session.commit_regenerated([("memory", self.repo, self.repo)])
        return out.getvalue()

    def last_message(self) -> str:
        return run_git(self.repo, "log", "-n", "1", "--format=%B").stdout

    def test_the_hook_refuses_the_old_message_with_only_a_tool_trailer(self):
        self.seed("seed\n\nTool: invented\nCo-Authored-By: " + AGENT)
        (self.repo / "boards.html").write_text("x\n", encoding="utf-8")
        run_git(self.repo, "add", "-A")
        self.assertNotEqual(run_git(self.repo, "commit", "-q", "-m", session.REFRESH_MESSAGE).returncode, 0)

    def test_co_author_from_the_environment_passes_the_hook(self):
        self.seed("seed without trailers", verify=False)
        with mock.patch.dict(os.environ, {session.CO_AUTHOR_ENV: "Co-Authored-By: Other Agent <other@example.com>"}):
            out = self.regenerate()
        self.assertIn("memory: regenerated files committed", out)
        message = self.last_message()
        self.assertIn("Tool: session.py finish", message)
        self.assertIn("Co-Authored-By: Other Agent <other@example.com>", message)

    def test_co_author_from_the_newest_commit_that_carries_one_passes_the_hook(self):
        self.assertEqual(self.seed("seed\n\nTool: invented\nCo-Authored-By: " + AGENT).returncode, 0)
        self.seed("later, no trailers", verify=False)
        out = self.regenerate()
        self.assertIn("memory: regenerated files committed", out)
        message = self.last_message()
        self.assertIn("Tool: session.py finish", message)
        self.assertIn("Co-Authored-By: " + AGENT, message)
        self.assertEqual(run_git(self.repo, "status", "--porcelain").stdout.strip(), "")

    def test_no_co_author_anywhere_is_said_and_nothing_is_committed(self):
        self.seed("seed without trailers", verify=False)
        out = self.regenerate()
        self.assertIn("could not commit the regenerated files", out)
        self.assertIn(session.CO_AUTHOR_ENV, out)
        self.assertEqual(self.last_message().strip(), "seed without trailers")


if __name__ == "__main__":
    unittest.main()
