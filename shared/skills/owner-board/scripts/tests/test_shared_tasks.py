"""Tasks from every store on the boards: a shared board's two pages, card links, actions in a repository.

Fictional brains `sam` (this brain) and `bob` (a peer that works on the same repository), in
temporary folders (SMART-RULE-0008). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v
"""

from __future__ import annotations

import datetime
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import apply_events  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import reconcile  # noqa: E402
import task_board  # noqa: E402
from board_fixtures import HAS_GIT, Brain, git, quiet  # noqa: E402

TODAY = datetime.date(2026, 1, 10)

TASK = """---
id: {id}
title: {title}
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: {status}
owner: Sam
author: sam
priority: normal
created: 2026-01-02T09:00:00+10:00
updated: 2026-01-02T09:00:00+10:00
due: null
next_review: null
waiting_on: null
project_refs:{refs}
---

# {title}

## History

- 2026-01-02T09:00:00+10:00 – sam: created
"""


def write_task(store: Path, tid: str, title: str, refs: list[str], status: str = "ready", folder: str = "open") -> Path:
    path = store / folder / (tid + "-fictional.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TASK.format(id=tid, title=title, status=status,
                                refs="".join("\n  - " + r for r in refs) if refs else " []"), encoding="utf-8")
    return path


class SharedBoardTasks(unittest.TestCase):
    """A board shared through the repository `example-garden`, a second board in memory, and the
    owner store: every open task once, each on the page its store belongs to."""

    def setUp(self):
        self.brain = Brain(shared=True, second_board=True)
        today = mock.patch.object(task_board, "local_today", return_value=TODAY)
        today.start()
        self.addCleanup(today.stop)
        self.repo_store = self.brain.checkout / "brain" / "tasks"
        self.private_store = self.brain.memory / "projects" / "example-garden" / "tasks"
        write_task(self.repo_store, "TASK-sam-2026-0003", "Edge the paths", ["example-garden:brain"])
        write_task(self.private_store, "TASK-sam-2026-0004", "Ask the supplier about mulch",
                   ["/memory/projects/example-garden"])
        # A memory node beneath the pointer: private too, so on the owner's page.
        self.brain.make_node("projects/example-garden/greenhouse", "Greenhouse")
        write_task(self.brain.memory / "projects" / "example-garden" / "greenhouse" / "tasks", "TASK-sam-2026-0005",
                   "Price a heater", ["/memory/projects/example-garden/greenhouse"])
        write_task(self.brain.memory / "projects" / "example-pond" / "tasks", "TASK-sam-2026-0006", "Clean the pump",
                   ["/memory/projects/example-pond"])
        write_task(self.brain.memory / "tasks", "TASK-sam-2026-0007", "Renew the library card", [])

    def tearDown(self):
        self.brain.close()

    def build_all(self):
        config = self.brain.config()
        for board in config.boards:
            quiet(build_status.build, config, board, False)
        quiet(build_boards.build, config, None, "2026-01-10 09:00")
        return config

    def placed(self) -> dict:
        routed = task_board.route(self.brain.config(), today=TODAY)
        return {key: sorted(t.tid for t, _ in b["tasks"]) for key, b in routed.items()}

    def test_each_open_task_is_drawn_once_on_the_page_of_its_store(self):
        placed = self.placed()
        self.assertEqual(placed["garden"], ["TASK-2026-0901", "TASK-sam-2026-0003"])
        self.assertEqual(placed[task_board.OWN + "garden"], ["TASK-sam-2026-0004", "TASK-sam-2026-0005"])
        self.assertEqual(placed["pond"], ["TASK-sam-2026-0006"])
        self.assertEqual(placed["personal"], ["TASK-sam-2026-0007"])
        config = self.build_all()
        self.assertEqual(task_board.check(config, TODAY), [])
        shared = [tid for tid, _ in task_board.shown_on(self.brain.checkout / "brain" / "status" / "status.html")]
        own = [tid for tid, _ in task_board.shown_on(self.brain.memory / "boards" / "projects" / "garden.html")]
        self.assertEqual(sorted(shared), ["TASK-2026-0901", "TASK-sam-2026-0003"])
        self.assertEqual(sorted(own), ["TASK-sam-2026-0004", "TASK-sam-2026-0005"])

    def test_the_shared_page_links_inside_the_repository_and_names_no_memory_path(self):
        self.build_all()
        page = (self.brain.checkout / "brain" / "status" / "status.html").read_text(encoding="utf-8")
        self.assertNotIn("/memory/", page)
        self.assertIn('href="../tasks/open/TASK-sam-2026-0003-fictional.md"', page)
        self.assertIn(task_board.SHARED_NOTE, page)
        # A note on a repository task goes into History, which the repository's readers see.
        self.assertIn(task_board.html.escape(task_board.REPOSITORY_NOTE), page)
        own = (self.brain.memory / "boards" / "projects" / "garden.html").read_text(encoding="utf-8")
        self.assertNotIn(task_board.html.escape(task_board.REPOSITORY_NOTE), own)
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="projects/garden.html">your own page</a> &middot; 2 open', index)

    def test_a_shared_page_whose_repository_task_names_memory_is_refused(self):
        write_task(self.repo_store, "TASK-sam-2026-0008", "See /memory/projects/example-garden/STATE.md", [])
        config = self.brain.config()
        with self.assertRaises(build_status.Refused):
            quiet(build_status.build, config, config.board("garden"), False)
        self.assertFalse((self.brain.checkout / "brain" / "status" / "status.html").exists())

    def test_a_pointer_that_names_another_checkout_draws_no_repository_task_on_the_shared_page(self):
        readme = self.brain.memory / "projects" / "example-garden" / "README.md"
        other = self.brain.repos / "example-garden-copy"
        (other / "brain" / "tasks" / "open").mkdir(parents=True)
        readme.write_text(readme.read_text(encoding="utf-8").replace(self.brain.checkout.as_posix(), other.as_posix()),
                          encoding="utf-8")
        config = self.brain.config()
        data, _ = quiet(build_status.build, config, config.board("garden"), False)
        self.assertTrue(any("make them the same folder" in s for s in data["adrift"]), data["adrift"])

    def test_check_10_reads_the_repository_store_of_a_shared_board(self):
        board = self.brain.config().board("garden")
        said = reconcile.check(board)
        self.assertIn("TASK-2026-0901 still says ready, but the beds track has landed work or has a card in flight.", said)
        self.assertIn("TASK-2026-0902 is the task for the seeds track and has no open record in "
                      "example-garden:brain/tasks.", said)
        self.assertFalse(any("/memory/" in s for s in said), said)

    def test_a_store_that_cannot_be_read_is_named_on_the_directory(self):
        self.brain.make_node("projects/example-orchard", "Example Orchard",
                             repo_url="https://example.com/fictional/example-orchard.git", default_branch="main")
        self.build_all()
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Task stores not read: example-orchard:brain/tasks (not checked out here)", index)


@unittest.skipUnless(HAS_GIT, "git is not installed")
class ActionsInARepositoryStore(unittest.TestCase):
    """bob's brain completes sam's task in the shared repository: the change names bob."""

    def setUp(self):
        self.sam = Brain(shared=True)
        checkout = self.sam.checkout
        write_task(checkout / "brain" / "tasks", "TASK-sam-2026-0003", "Edge the paths", ["example-garden:brain"])
        remote = self.sam.repos / "example-garden-origin.git"
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare", "-b", "main")
        git(checkout, "init", "-q", "-b", "main")
        git(checkout, "config", "user.email", "tester@example.com")
        git(checkout, "config", "user.name", "Tester")
        git(checkout, "add", "-A")
        git(checkout, "commit", "-q", "-m", "start")
        git(checkout, "remote", "add", "origin", str(remote))
        git(checkout, "push", "-q", "-u", "origin", "main")
        # bob's own brain, with a pointer node to the same checkout.
        self.bob = Brain(owner="Bob")
        self.bob.make_node("projects/example-garden-shared", "Example Garden",
                           repo_url="https://example.com/fictional/example-garden.git",
                           local_path=checkout.as_posix(), default_branch="main")

    def tearDown(self):
        self.sam.close()
        self.bob.close()

    def test_done_on_a_repository_task_is_attributed_to_the_acting_brain(self):
        downloads = self.bob.root / "fake-downloads" / "Board saves"
        downloads.mkdir(parents=True)
        (downloads / "task-actions-2026-01-10-08-30-00.json").write_text(json.dumps({
            "schema": "owner-board/task-actions/v1", "board": "tasks", "savedAt": "2026-01-10T08:30:00.000Z",
            "tasks": [{"id": "TASK-sam-2026-0003", "action": "done", "note": "Edged on Saturday.", "shots": [],
                       "title": "x"}]}), encoding="utf-8")
        with mock.patch.object(apply_events, "downloads", return_value=str(downloads.parent)):
            _, out = quiet(apply_events.route, self.bob.config(), False)
        self.assertIn("done     TASK-sam-2026-0003", out)
        record = self.sam.checkout / "brain" / "tasks" / "completed" / "TASK-sam-2026-0003-fictional.md"
        text = record.read_text(encoding="utf-8")
        self.assertIn("author: sam", text)                    # the author never changes
        self.assertRegex(text, r" – bob: done \(completed\)\n  Note: Edged on Saturday\.\n")
        state = (self.sam.checkout / "brain" / "tasks" / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("`TASK-sam-2026-0003`", state.split("## Recently completed")[1])
        self.assertNotIn("/memory/", text + state)

    def test_a_repository_on_another_branch_is_refused_and_nothing_is_written(self):
        git(self.sam.checkout, "checkout", "-q", "-b", "feature/elsewhere")
        downloads = self.bob.root / "fake-downloads" / "Board saves"
        downloads.mkdir(parents=True)
        (downloads / "task-actions-x.json").write_text(json.dumps({
            "schema": "owner-board/task-actions/v1", "board": "tasks", "savedAt": "",
            "tasks": [{"id": "TASK-sam-2026-0003", "action": "done", "note": "", "shots": [], "title": "x"}]}),
            encoding="utf-8")
        with mock.patch.object(apply_events, "downloads", return_value=str(downloads.parent)):
            _, out = quiet(apply_events.route, self.bob.config(), False)
        self.assertIn("SKIPPED TASK-sam-2026-0003: example-garden:brain/tasks: the checkout is on feature/elsewhere", out)
        self.assertTrue((self.sam.checkout / "brain" / "tasks" / "open" / "TASK-sam-2026-0003-fictional.md").is_file())


if __name__ == "__main__":
    unittest.main()
