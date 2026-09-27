"""One working copy per session (SMART-RULE-0038): what session.py does, and what it prevents.

Every brain here is invented, in a temporary folder: a mechanics, a library and a memory, each with
a local bare `origin`, checked out nested as the brain is. The two-session tests are the proposal's
trial: the control shows an edit silently lost in one shared folder; with a copy per session the
same overlap becomes a conflict and nothing is lost.
Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import session  # noqa: E402
import sync  # noqa: E402

HAS_GIT = shutil.which("git") is not None
FICTIONAL = {"GIT_AUTHOR_NAME": "Example Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
             "GIT_COMMITTER_NAME": "Example Tester", "GIT_COMMITTER_EMAIL": "tester@example.com"}

# A stand-in for the owner-board generator: rebuilds boards/index.html from the memory's notes.
FAKE_BUILDER = """import pathlib
memory = pathlib.Path("memory")
notes = sorted(p.name for p in memory.glob("*.md"))
(memory / "boards").mkdir(exist_ok=True)
(memory / "boards" / "index.html").write_text("built from " + ", ".join(notes) + "\\n", encoding="utf-8")
"""


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = session.main(list(argv))
    return code, out.getvalue()


@unittest.skipUnless(HAS_GIT, "git is not installed")
class SessionTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, FICTIONAL)
        self.env.start()
        self.base = Path(tempfile.mkdtemp(prefix="session-"))
        self.shared = self.base / "brain"
        self.sessions = self.base / "sessions"
        seeds = {
            "mechanics": {"CONTRACT.md": "# contract\n", ".gitignore": "library/\nmemory/\n__pycache__/\n",
                          ".gitattributes": "LOG.md merge=union\n",
                          "shared/skills/owner-board/scripts/build_boards.py": FAKE_BUILDER},
            "library": {"README.md": "# library\n"},
            "memory": {"notes.md": "a line everyone edits\n", "LOG.md": "# Log\n",
                       ".gitattributes": "LOG.md merge=union\n", "boards/index.html": "built from LOG.md, notes.md\n"},
        }
        for name, files in seeds.items():
            origin = self.base / f"{name}.git"
            git(self.base, "init", "-q", "--bare", "-b", "main", str(origin))
            seed = self.base / f"seed-{name}"
            git(self.base, "clone", "-q", str(origin), str(seed))
            for path, text in files.items():
                write(seed / path, text)
            commit_all(seed, "start")
            git(seed, "push", "-q", "origin", "main")
        git(self.base, "clone", "-q", str(self.base / "mechanics.git"), str(self.shared))
        for name in ("library", "memory"):
            git(self.base, "clone", "-q", str(self.base / f"{name}.git"), str(self.shared / name))

    def tearDown(self):
        self.env.stop()
        for repo in (self.shared, self.shared / "library", self.shared / "memory"):
            subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
        shutil.rmtree(self.base, ignore_errors=True)

    # ------------------------------------------------------------ helpers

    def start(self, name: str) -> Path:
        code, out = cli("--root", str(self.shared), "start", name, "--sessions", str(self.sessions))
        self.assertEqual(code, 0, out)
        return self.sessions / name

    def finish(self, name: str, *extra: str) -> tuple[int, str]:
        return cli("--root", str(self.shared), "finish", name, "--sessions", str(self.sessions),
                   "--no-preflight", *extra)

    def on_origin(self, repo: str, path: str) -> str:
        return git(self.base / f"{repo}.git", "show", f"main:{path}")

    # ------------------------------------------------------------ start

    def test_start_makes_a_nested_copy_on_its_own_branch(self):
        copy = self.start("alpha")
        self.assertTrue((copy / "CONTRACT.md").is_file())
        self.assertTrue((copy / "memory" / "notes.md").is_file())
        self.assertTrue((copy / "library" / "README.md").is_file())
        for path in (copy, copy / "library", copy / "memory"):
            self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD"), "session/alpha")
        # Inside the copy, the brain root and /memory/ resolve to the copy, not the shared checkout.
        self.assertEqual(sync.brain_root(copy / "memory").resolve(), copy.resolve())
        # From anywhere inside it, the shared checkout is still found.
        self.assertEqual(session.shared_root(copy / "memory").resolve(), self.shared.resolve())
        self.assertEqual(git(self.shared, "status", "--porcelain"), "")

    def test_start_refuses_a_name_in_use(self):
        self.start("alpha")
        code, out = cli("--root", str(self.shared), "start", "alpha", "--sessions", str(self.sessions))
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)

    def test_start_refuses_a_bad_name(self):
        code, out = cli("--root", str(self.shared), "start", "Alpha Session", "--sessions", str(self.sessions))
        self.assertEqual(code, 1)

    # ------------------------------------------------------------ finish

    def test_finish_merges_pushes_fast_forwards_and_removes(self):
        copy = self.start("alpha")
        write(copy / "memory" / "notes.md", "alpha's edit\n")
        commit_all(copy / "memory", "alpha edits the notes")
        write(copy / "shared" / "skills" / "__pycache__" / "x.pyc", "ignored build output")
        code, out = self.finish("alpha")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.on_origin("memory", "notes.md"), "alpha's edit")
        self.assertEqual((self.shared / "memory" / "notes.md").read_text(encoding="utf-8"), "alpha's edit\n")
        self.assertFalse(copy.exists())
        self.assertEqual(git(self.shared / "memory", "branch", "--list", "session/alpha"), "")

    def test_finish_refuses_uncommitted_changes_and_keeps_the_copy(self):
        copy = self.start("alpha")
        write(copy / "memory" / "notes.md", "not committed\n")
        code, out = self.finish("alpha")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", out)
        self.assertTrue(copy.exists())

    def test_finish_keep_merges_but_keeps_the_copy(self):
        copy = self.start("alpha")
        write(copy / "memory" / "extra.md", "more\n")
        commit_all(copy / "memory", "alpha adds a note")
        code, out = self.finish("alpha", "--keep")
        self.assertEqual(code, 0, out)
        self.assertTrue(copy.exists())
        self.assertEqual(self.on_origin("memory", "extra.md"), "more")

    # ------------------------------------------------------------ the trial

    def test_control_one_shared_folder_loses_an_edit_silently(self):
        """The problem the rule removes: two sessions, one folder, read then write."""
        notes = self.shared / "memory" / "notes.md"
        first = notes.read_text(encoding="utf-8")            # session A reads
        second = notes.read_text(encoding="utf-8")           # session B reads
        notes.write_text(first + "A's addition\n", encoding="utf-8")
        notes.write_text(second + "B's addition\n", encoding="utf-8")
        text = notes.read_text(encoding="utf-8")
        self.assertNotIn("A's addition", text)               # lost, and nothing said so
        self.assertEqual(git(self.shared / "memory", "diff", "--name-only", "--diff-filter=U"), "")

    def test_two_copies_turn_the_same_overlap_into_a_conflict(self):
        a, b = self.start("alpha"), self.start("beta")
        write(a / "memory" / "notes.md", "alpha's version\n")
        commit_all(a / "memory", "alpha")
        write(b / "memory" / "notes.md", "beta's version\n")
        commit_all(b / "memory", "beta")
        self.assertEqual(self.finish("alpha")[0], 0)
        code, out = self.finish("beta")
        self.assertEqual(code, 1)
        self.assertIn("conflict left for the session to resolve", out)
        self.assertIn("notes.md", out)
        self.assertEqual(self.on_origin("memory", "notes.md"), "alpha's version")
        waiting = (b / "memory" / "notes.md").read_text(encoding="utf-8")
        self.assertIn("alpha's version", waiting)
        self.assertIn("beta's version", waiting)             # both survive, for the session to reconcile

    def test_two_log_entries_both_survive(self):
        a, b = self.start("alpha"), self.start("beta")
        for copy, name in ((a, "alpha"), (b, "beta")):
            write(copy / "memory" / "LOG.md", f"# Log\n\n## entry from {name}\n")
            commit_all(copy / "memory", name)
        self.assertEqual(self.finish("alpha")[0], 0)
        code, out = self.finish("beta")
        self.assertEqual(code, 0, out)
        log = self.on_origin("memory", "LOG.md")
        self.assertIn("entry from alpha", log)
        self.assertIn("entry from beta", log)

    def test_log_entries_conflict_without_the_union_merge(self):
        """Control for the test above: the survival depends on `merge=union`."""
        seed = self.base / "seed-memory"
        git(seed, "pull", "-q")
        (seed / ".gitattributes").unlink()
        commit_all(seed, "no union merge")
        git(seed, "push", "-q", "origin", "main")
        a, b = self.start("alpha"), self.start("beta")
        for copy, name in ((a, "alpha"), (b, "beta")):
            write(copy / "memory" / "LOG.md", f"# Log\n\n## entry from {name}\n")
            commit_all(copy / "memory", name)
        self.assertEqual(self.finish("alpha")[0], 0)
        code, out = self.finish("beta")
        self.assertEqual(code, 1)
        self.assertIn("LOG.md", out)

    def test_a_conflicting_generated_file_is_rebuilt(self):
        a, b = self.start("alpha"), self.start("beta")
        write(a / "memory" / "boards" / "index.html", "alpha's hand edit\n")
        write(a / "memory" / "alpha.md", "a\n")
        commit_all(a / "memory", "alpha")
        write(b / "memory" / "boards" / "index.html", "beta's hand edit\n")
        write(b / "memory" / "beta.md", "b\n")
        commit_all(b / "memory", "beta")
        self.assertEqual(self.finish("alpha")[0], 0)
        code, out = self.finish("beta")
        self.assertEqual(code, 0, out)
        self.assertIn("rebuilt boards/index.html", out)
        self.assertEqual(self.on_origin("memory", "boards/index.html"),
                         "built from LOG.md, alpha.md, beta.md, notes.md")

    def test_a_generated_file_conflict_stops_without_its_generator(self):
        """Control for the test above: take the generator away and the conflict is left."""
        with mock.patch.dict(session.GENERATED, {"memory": []}):
            a, b = self.start("alpha"), self.start("beta")
            for copy, name in ((a, "alpha"), (b, "beta")):
                write(copy / "memory" / "boards" / "index.html", f"{name}'s hand edit\n")
                commit_all(copy / "memory", name)
            self.assertEqual(self.finish("alpha")[0], 0)
            code, out = self.finish("beta")
        self.assertEqual(code, 1)
        self.assertIn("boards/index.html", out)

    # ------------------------------------------------------------ list

    def test_list_shows_copies_and_their_unmerged_commits(self):
        copy = self.start("alpha")
        write(copy / "memory" / "extra.md", "more\n")
        commit_all(copy / "memory", "alpha adds a note")
        code, out = cli("--root", str(self.shared), "list")
        self.assertEqual(code, 0, out)
        self.assertIn("| alpha | memory | 1 | 0 |", out)
        self.assertIn("| alpha | mechanics | 0 | 0 |", out)


if __name__ == "__main__":
    unittest.main()
