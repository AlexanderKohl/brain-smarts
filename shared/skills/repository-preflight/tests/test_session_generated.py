"""Every file a finish regenerates counts as generated when two sessions' merges meet on it
(TASK-alec-2026-0312): taken from main and rebuilt, never left as a conflict.

On 7 Nov 2026 a finish stopped five times with "conflict left for the session to resolve" on
`boards/projects/<board>.html` (the owner's pages of the repository boards, one folder below
`boards/`, which `Path.match("boards/*.html")` does not match) and on a memory board's
`status/state.json` (not listed at all). The repository and its generators here are invented;
the fixture is `test_session.SessionTests`'. Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import test_session
from test_session import HAS_GIT, commit_all, git, session, write

# Stand-ins for the owner-board generators, as they lay out their files: the directory and the
# owner's page of a repository board (build_boards.py); a memory board's page and state.json,
# then the directory again (build_status.py --all).
BOARDS = """import pathlib
memory = pathlib.Path("memory")
notes = ", ".join(sorted(p.name for p in memory.glob("*.md")))
for rel in ("boards/index.html", "boards/projects/garden.html"):
    (memory / rel).parent.mkdir(parents=True, exist_ok=True)
    (memory / rel).write_text("built from " + notes + "\\n", encoding="utf-8")
"""
STATUS = """import pathlib, runpy
memory = pathlib.Path("memory")
notes = ", ".join(sorted(p.name for p in memory.glob("*.md")))
folder = memory / "projects" / "pond" / "status"
folder.mkdir(parents=True, exist_ok=True)
(folder / "status.html").write_text("built from " + notes + "\\n", encoding="utf-8")
(folder / "state.json").write_text('{"built from": "' + notes + '"}\\n', encoding="utf-8")
runpy.run_path("shared/skills/owner-board/scripts/build_boards.py")
"""
NESTED = ("boards/projects/garden.html", "projects/pond/status/state.json", "projects/pond/status/status.html")


@unittest.skipUnless(HAS_GIT, "git is not installed")
class GeneratedFilesTests(unittest.TestCase):
    setUp = test_session.SessionTests.setUp
    tearDown = test_session.SessionTests.tearDown
    start = test_session.SessionTests.start
    finish = test_session.SessionTests.finish
    on_origin = test_session.SessionTests.on_origin

    def install_generators(self) -> None:
        """Put both generators on origin's mechanics and in the shared checkout, as a merge left them."""
        seed = self.base / "seed-mechanics"
        write(seed / "shared/skills/owner-board/scripts/build_boards.py", BOARDS)
        write(seed / "shared/skills/owner-board/scripts/build_status.py", STATUS)
        commit_all(seed, "generators")
        git(seed, "push", "-q", "origin", "main")
        git(self.shared, "pull", "-q", "--ff-only")

    def both_rebuild(self) -> None:
        """Two sessions each add a note and rebuild every generated page, as each finish does."""
        self.install_generators()
        a, b = self.start("alpha"), self.start("beta")
        for copy, name in ((a, "alpha"), (b, "beta")):
            write(copy / "memory" / f"{name}.md", name + "\n")
            write(copy / "memory" / "boards" / "index.html", f"{name}'s build\n")
            for rel in NESTED:
                write(copy / "memory" / rel, f"{name}'s build\n")
            commit_all(copy / "memory", name)
        self.assertEqual(self.finish("alpha")[0], 0)

    def test_a_finish_whose_copy_and_main_both_rebuilt_every_page_completes(self):
        self.both_rebuild()
        code, out = self.finish("beta")
        self.assertEqual(code, 0, out)
        self.assertNotIn("conflict left", out)
        for rel in NESTED:
            self.assertIn(rel, out)                                         # named as rebuilt
        notes = "LOG.md, alpha.md, beta.md, notes.md"
        self.assertEqual(self.on_origin("memory", "boards/projects/garden.html"), "built from " + notes)
        self.assertEqual(self.on_origin("memory", "projects/pond/status/state.json"), '{"built from": "' + notes + '"}')
        self.assertEqual(git(self.base / "memory.git", "show", "main:boards/index.html"), "built from " + notes)

    def test_control_the_table_before_the_fix_leaves_the_conflict(self):
        """The table as it was on 7 Nov 2026: the same finish stops on the nested pages."""
        before = {"memory": [
            ("boards/*.html", ["python", "shared/skills/owner-board/scripts/build_boards.py", "--no-fetch"]),
            ("projects/*/status/status.html", ["python", "shared/skills/owner-board/scripts/build_status.py", "--no-fetch"]),
        ]}
        with mock.patch.dict(session.GENERATED, before):
            self.both_rebuild()
            code, out = self.finish("beta")
        self.assertEqual(code, 1)
        self.assertIn("conflict left for the session to resolve", out)
        self.assertIn("boards/projects/garden.html", out)
        self.assertIn("projects/pond/status/state.json", out)

    def test_every_page_the_refresh_writes_is_in_the_table(self):
        patterns = [pattern for pattern, _ in session.GENERATED["memory"]]
        for rel in ("boards/index.html", "boards/personal.html", "boards/projects/orchard.html",
                    "projects/example-pond/status/state.json", "projects/example-pond/status/status.html",
                    "projects/a/b/status/status.html", "skills/release-notes/pages/example-app.testing.html"):
            with self.subTest(rel=rel):
                self.assertTrue(any(Path(rel).match(p) for p in patterns), rel)
        self.assertFalse(any(Path("notes.md").match(p) for p in patterns))


if __name__ == "__main__":
    unittest.main()
