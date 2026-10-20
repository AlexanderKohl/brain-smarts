"""`session.py finish` refreshes the release notes and the boards before it merges, and never
refuses the finish for anything the refresh finds.

Every brain and project here is invented, in a temporary folder. The generators are stand-ins
that record how they were called and write what the real ones would; the project repository is
a real git repository, so a note the refresh repairs shows as a change there. Run from the brain
root:
    python -m unittest discover -s shared/skills/repository-preflight/scripts/tests -v
"""

from __future__ import annotations

import io
import json
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
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "tests"))

import session  # noqa: E402
import test_session  # noqa: E402  (its fixture, borrowed below; its tests run from their own folder)
from test_session import commit_all, git, write  # noqa: E402

HAS_GIT = shutil.which("git") is not None
FICTIONAL = {"GIT_AUTHOR_NAME": "Example Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
             "GIT_COMMITTER_NAME": "Example Tester", "GIT_COMMITTER_EMAIL": "tester@example.com"}

# A stand-in for release_notes.py: `fix` repairs the one note, `build` writes the page.
FAKE_RELEASE_NOTES = """import json, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(args[args.index("--root") + 1])
cmd = [a for a in args if not a.startswith("--") and a != str(root)][0]
cfg = json.loads((root / "memory/skills/release-notes/config/release-notes.json").read_text())
repo = pathlib.Path(cfg["project_repos_root"]) / "app"
if cmd == "fix":
    note = repo / "release-notes" / "unreleased" / "colon.md"
    note.write_text(note.read_text().replace("look_out_for: Check: it", "look_out_for: >-\\n  Check: it"))
    print("fixed app/colon")
elif cmd == "link":
    print("0 note(s) changed")
elif cmd == "build":
    page = root / "memory" / "boards" / "release-notes.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("<p>built</p>")
    print("wrote " + str(page))
"""

FAKE_BUILD_STATUS = """import pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--root") + 1])
(root / "memory" / "boards").mkdir(parents=True, exist_ok=True)
(root / "memory" / "boards" / "index.html").write_text("every board, rebuilt\\n")
print("wrote index.html")
"""

FAKE_RECONCILE = """print("  - origin/fix/orphan is pushed and not merged - no card on the board is building it")
"""

FAILING = """import sys
print("something broke")
sys.exit(2)
"""


@unittest.skipUnless(HAS_GIT, "git is not installed")
class RefreshTests(unittest.TestCase):
    """`refresh` on a plain folder laid out like a session copy."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, FICTIONAL)
        self.env.start()
        self.base = Path(tempfile.mkdtemp(prefix="refresh-"))
        self.copy = self.base / "copy"
        write(self.copy / "CONTRACT.md", "# contract\n")
        write(self.copy / session.RELEASE_NOTES, FAKE_RELEASE_NOTES)
        write(self.copy / session.BUILD_STATUS, FAKE_BUILD_STATUS)
        write(self.copy / session.RECONCILE, FAKE_RECONCILE)
        write(self.copy / session.BOARDS_CONFIG, json.dumps({"boards": [{"id": "garden", "label": "Garden"}]}))
        repos = self.base / "repos"
        write(self.copy / session.RELEASE_CONFIG, json.dumps({
            "project_repos_root": str(repos),
            "projects": [{"id": "app", "kind": "git", "repo": "app", "production": "main", "development": "dev"},
                         {"id": "crm", "kind": "folder", "folder": "/memory/projects/x/release-notes"}]}))
        self.repo = repos / "app"
        write(self.repo / "release-notes" / "unreleased" / "colon.md",
              "---\ntitle: Colon\nlook_out_for: Check: it\n---\n\nWhat they see.\n")
        git(self.base, "init", "-q", "-b", "dev", str(self.repo))
        commit_all(self.repo, "start")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.base, ignore_errors=True)

    def run_refresh(self) -> tuple[dict, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            found = session.refresh(self.copy)
        return found, out.getvalue()

    def test_notes_and_boards_are_rebuilt_and_the_project_change_is_named_under_its_heading(self):
        found, out = self.run_refresh()
        self.assertTrue((self.copy / "memory" / "boards" / "release-notes.html").is_file())
        self.assertTrue((self.copy / "memory" / "boards" / "index.html").is_file())
        self.assertIn("release-notes/unreleased/colon.md",
                      git(self.repo, "status", "--porcelain"))          # repaired, left for the project's own commit
        self.assertEqual(found["project_changes"], {str(self.repo): ["release-notes/unreleased/colon.md"]})
        self.assertEqual(found["drift"], {"garden": [
            "origin/fix/orphan is pushed and not merged - no card on the board is building it"]})
        heading = out.index("project repositories with release notes to commit and push")
        self.assertIn("colon.md", out[heading:])
        drift = out.index("board drift (printed, never a stop):")
        self.assertIn("garden:", out[drift:])
        self.assertIn("  fixed app/colon", out)

    def test_a_failing_generator_is_reported_and_the_refresh_still_returns(self):
        write(self.copy / session.BUILD_STATUS, FAILING)
        found, out = self.run_refresh()
        self.assertIn("something broke", out)
        self.assertIn("build_status.py --all --no-fetch exited 2", out)
        self.assertIn("garden:", out)                                   # the drift step still ran
        self.assertIn("colon.md", out)                                  # and so did the notes step

    def test_without_configuration_each_part_says_it_was_skipped(self):
        (self.copy / session.RELEASE_CONFIG).unlink()
        (self.copy / session.BOARDS_CONFIG).unlink()
        found, out = self.run_refresh()
        self.assertIn("no release-notes configuration in the copy; skipped", out)
        self.assertIn("no boards configuration in the copy; skipped", out)
        self.assertEqual(found, {"project_changes": {}, "drift": {}})
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_a_missing_script_is_said_not_raised(self):
        (self.copy / session.RECONCILE).unlink()
        found, out = self.run_refresh()
        self.assertEqual(found["drift"], {})
        self.assertTrue((self.copy / "memory" / "boards" / "index.html").is_file())


@unittest.skipUnless(HAS_GIT, "git is not installed")
class FinishRefreshTests(unittest.TestCase):
    """`finish` runs the refresh and carries the regenerated files to main.

    The invented three-repository brain is test_session's own fixture, borrowed by calling its
    setUp and helpers on this case rather than inheriting them, so its tests do not run twice.
    """

    def setUp(self):
        test_session.SessionTests.setUp(self)

    def tearDown(self):
        test_session.SessionTests.tearDown(self)

    def start(self, name: str) -> Path:
        return test_session.SessionTests.start(self, name)

    def finish(self, name: str) -> tuple[int, str]:
        return test_session.SessionTests.finish(self, name)

    def on_origin(self, repo: str, path: str) -> str:
        return test_session.SessionTests.on_origin(self, repo, path)

    def seed(self, repo: str, files: dict) -> None:
        checkout = self.shared if repo == "mechanics" else self.shared / repo
        for path, text in files.items():
            write(checkout / path.removeprefix(repo + "/"), text)   # a copy-relative path, inside its repository
        commit_all(checkout, "seed " + repo)
        git(checkout, "push", "-q", "origin", "main")

    def test_finish_rebuilds_the_boards_and_pushes_them(self):
        self.seed("mechanics", {session.BUILD_STATUS: FAKE_BUILD_STATUS, session.RECONCILE: FAKE_RECONCILE})
        self.seed("memory", {session.BOARDS_CONFIG: json.dumps({"boards": [{"id": "garden", "label": "Garden"}]})})
        copy = self.start("alpha")
        write(copy / "memory" / "notes.md", "alpha's edit\n")
        commit_all(copy / "memory", "alpha edits the notes")
        code, out = self.finish("alpha")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.on_origin("memory", "boards/index.html"), "every board, rebuilt")
        self.assertIn("Finish: release notes and boards rebuilt", git(self.base / "memory.git", "log", "--format=%s", "main"))
        self.assertIn("memory: regenerated files committed", out)
        self.assertIn("origin/fix/orphan is pushed and not merged", out)
        self.assertFalse(copy.exists())                                 # drift never stopped the finish


if __name__ == "__main__":
    unittest.main()
