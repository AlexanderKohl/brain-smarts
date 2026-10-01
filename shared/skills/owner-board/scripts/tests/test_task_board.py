"""Behavioural tests for the owner board's task views, on a fictional brain in a temporary folder.

Moved unchanged from test_owner_board.py.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BRAIN = SCRIPTS.parents[3]  # the brain root: owner-board is a core skill beside tasks
sys.path.insert(0, str(SCRIPTS))

import apply_verdicts  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import task_board  # noqa: E402
import verdicts  # noqa: E402
from board_fixtures import Brain, quiet  # noqa: E402


TASK = """---
id: {id}
title: {title}
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: {status}
owner: Sam
priority: {priority}
created: 2026-01-02T09:00:00+10:00
updated: {updated}
due: {due}
next_review: {review}
waiting_on: {waiting}
project_refs:{refs}
---

# {title}
"""

TEMPLATE = """---
id: TASK-YYYY-NNNN
title: Clear action or outcome
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: inbox
owner: OWNER_SHORT_NAME
priority: normal
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
due: null
next_review: null
waiting_on: null
project_refs: []
skill_refs: []
depends_on: []
---

# Clear action or outcome

## Outcome

## Next action

## History
"""

STATE = """# Current State

| Task | Status | Priority | Review / waiting on | Title |
|---|---|---|---|---|
| `TASK-2026-0901` | **ready** | normal | - | Beds |
"""

TODAY = __import__("datetime").date(2026, 1, 10)


class TaskBoardTests(unittest.TestCase):
    """Tasks shown on boards: routing, fallback, no duplication, order, the new-task path."""

    def setUp(self):
        self.brain = Brain(second_board=True)
        today = mock.patch.object(task_board, "local_today", return_value=TODAY)
        today.start()
        self.addCleanup(today.stop)
        store = self.brain.memory / "tasks"
        for folder in ("inbox", "completed", "templates"):
            (store / folder).mkdir(parents=True, exist_ok=True)
        (store / "templates" / "TASK_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
        (store / "STATE.md").write_text(STATE, encoding="utf-8")
        self.add("TASK-2026-0910", "open", "ready", ["/memory/projects/example-garden"], priority="low")
        self.add("TASK-2026-0911", "open", "ready", ["/memory/projects/example-garden"], priority="high",
                 due="2026-02-01")
        self.add("TASK-2026-0912", "open", "ready", ["/memory/projects/example-garden"], priority="high",
                 due="2026-01-15")
        # The first reference has no board, the second has: the second decides.
        self.add("TASK-2026-0913", "open", "waiting", ["/memory/projects/example-shed", "/memory/projects/example-pond"],
                 review="2026-01-20", waiting="Example Pumps Pty Ltd")
        # A folder beneath a board's node belongs to that board.
        self.add("TASK-2026-0914", "open", "waiting", ["/memory/projects/example-pond/filters"],
                 review="2026-01-08", waiting="a delivery")
        self.add("TASK-2026-0915", "open", "in_progress", ["/memory/projects/example-shed"])
        self.add("TASK-2026-0916", "inbox", "inbox", [])
        self.add("TASK-2026-0917", "completed", "completed", ["/memory/projects/example-garden"], updated="2026-01-09T10:00:00+10:00")
        self.add("TASK-2026-0918", "completed", "completed", ["/memory/projects/example-garden"], updated="2025-11-01T10:00:00+10:00")

    def tearDown(self):
        self.brain.close()

    def add(self, tid, folder, status, refs, priority="normal", due="null", review="null", waiting="null",
            updated="2026-01-02T09:00:00+10:00"):
        text = TASK.format(id=tid, title="Fictional task " + tid[-4:], status=status, priority=priority,
                           updated=updated, due=due, review=review, waiting=waiting,
                           refs="".join("\n  - " + r for r in refs) if refs else " []")
        (self.brain.memory / "tasks" / folder / (tid + "-fictional.md")).write_text(text, encoding="utf-8")

    def test_the_memory_skeleton_config_draws_the_personal_board_from_the_first_task(self):
        skeleton = (BRAIN / "shared" / "templates" / "memory-skeleton" / "skills" / "owner-board"
                    / "config" / "boards.json")
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        shutil.copyfile(skeleton, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["boards"], [])
        _, out = quiet(task_board.main, ["--root", str(self.brain.root), "--no-fetch", "build",
                                         "--for", "TASK-2026-0910"])
        self.assertIn("is on Personal tasks", out)
        self.assertTrue((self.brain.memory / "boards" / "personal.html").is_file())
        self.assertTrue((self.brain.memory / "boards" / "index.html").is_file())

    def set_tasks(self, **values):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("tasks", {}).update(values)
        path.write_text(json.dumps(data), encoding="utf-8")

    def placed(self, config=None):
        routed = task_board.route(config or self.brain.config(), today=TODAY)
        return {key: sorted(t.tid for t, _ in b["tasks"]) for key, b in routed.items()}

    def build_all(self):
        config = self.brain.config()
        for board in config.boards:
            quiet(build_status.build, config, board, False)
        quiet(build_boards.build, config, None, "2026-01-10 09:00")
        return config

    def test_routing_takes_the_first_reference_that_has_a_board(self):
        placed = self.placed()
        self.assertEqual(placed["garden"], ["TASK-2026-0910", "TASK-2026-0911", "TASK-2026-0912", "TASK-2026-0917"])
        self.assertEqual(placed["pond"], ["TASK-2026-0913", "TASK-2026-0914"])

    def test_tasks_without_a_board_fall_back_to_the_personal_board(self):
        placed = self.placed()
        # No references (0901, 0916) or only a project without a board (0915).
        self.assertEqual(placed["personal"], ["TASK-2026-0901", "TASK-2026-0915", "TASK-2026-0916"])

    def test_auto_boards_give_a_project_without_a_board_its_own_page(self):
        self.set_tasks(auto_boards=True)
        placed = self.placed()
        # The first reference of 0913 now has a board of its own, so it decides.
        self.assertEqual(placed["auto:example-shed"], ["TASK-2026-0913", "TASK-2026-0915"])
        self.assertEqual(placed["pond"], ["TASK-2026-0914"])
        config = self.build_all()
        self.assertTrue((self.brain.memory / "boards" / "projects" / "example-shed.html").is_file())
        self.assertEqual(task_board.check(config, TODAY), [])

    def test_a_project_that_outgrows_the_personal_board_is_suggested_once_until_declined(self):
        # example-shed has 0915 on the personal board; 0913 names it too but is on Pond Pump.
        self.assertEqual(task_board.outgrown(self.brain.config(), task_board.route(self.brain.config(), today=TODAY)), [])
        for n in range(3):
            self.add("TASK-2026-092" + str(n), "open", "ready", ["/memory/projects/example-shed"])
        routed = task_board.route(self.brain.config(), today=TODAY)
        self.assertEqual(task_board.outgrown(self.brain.config(), routed), [])      # four: not yet
        self.add("TASK-2026-0923", "open", "ready", ["/memory/projects/example-shed/roof"])
        self.add("TASK-2026-0924", "completed", "completed", ["/memory/projects/example-shed"],
                 updated="2026-01-09T10:00:00+10:00")                               # not open: not counted
        config = self.brain.config()
        found = task_board.outgrown(config, task_board.route(config, today=TODAY))
        self.assertEqual(found, [])     # shed four, shed/roof one: each project counts on its own
        self.add("TASK-2026-0925", "open", "waiting", ["/memory/projects/example-shed"], review="2026-01-20")
        config = self.brain.config()
        found = task_board.outgrown(config, task_board.route(config, today=TODAY))
        self.assertEqual([(node, n) for node, _, n in found], [("/memory/projects/example-shed", 5)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            build_boards.build(config, None, "2026-01-10 09:00")
        self.assertIn("suggest a board: example-shed (/memory/projects/example-shed) has 5 open tasks", out.getvalue())
        self.set_tasks(board_declined=["/memory/projects/example-shed"])
        config = self.brain.config()
        self.assertEqual(task_board.outgrown(config, task_board.route(config, today=TODAY)), [])

    def test_every_open_task_appears_exactly_once_on_its_board(self):
        config = self.build_all()
        self.assertEqual(task_board.check(config, TODAY), [])
        pages = {"garden": self.brain.memory / "projects/example-garden/status/status.html",
                 "pond": self.brain.memory / "projects/example-pond/status/status.html",
                 "personal": self.brain.memory / "boards" / "personal.html"}
        seen = [tid for page in pages.values() for tid, _ in task_board.shown_on(page)]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertIn("TASK-2026-0917", seen)       # completed nine days ago: recent
        self.assertNotIn("TASK-2026-0918", seen)    # completed in November: not recent
        # A duplicated task is caught by the check.
        page = pages["pond"]
        page.write_text(page.read_text(encoding="utf-8").replace(
            "</section>", '<article class="task" data-task="TASK-2026-0910"></article></section>'), encoding="utf-8")
        self.assertTrue(any("TASK-2026-0910" in p for p in task_board.check(config, TODAY)))

    def test_task_cards_link_to_the_record_and_carry_no_form(self):
        self.build_all()
        text = (self.brain.memory / "projects/example-pond/status/status.html").read_text(encoding="utf-8")
        section = text[text.index('<section class="tasks"'):text.index("</section>")]
        self.assertIn('href="../../../tasks/open/TASK-2026-0913-fictional.md"', section)
        self.assertIn("Waiting on: Example Pumps Pty Ltd", section)
        # Buttons and a note box, never a form or an input that could submit anything.
        self.assertNotIn("<input", section)
        self.assertNotIn("<form", section)
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="personal.html">Personal tasks</a>', index)
        self.assertIn("<b>3</b>Open tasks", index)   # garden: 0910, 0911, 0912

    # ------------------------------------------------ Do now, Done and a note

    def test_both_page_kinds_carry_the_task_controls_and_the_save_bar(self):
        self.build_all()
        pages = {"status": self.brain.memory / "projects/example-garden/status/status.html",
                 "personal": self.brain.memory / "boards" / "personal.html"}
        for kind, page in pages.items():
            text = page.read_text(encoding="utf-8")
            with self.subTest(kind):
                articles = re.findall(r'<article class="task[^"]*" data-task="([^"]+)" data-status="([^"]+)">(.*?)</article>',
                                      text, re.S)
                self.assertTrue(articles)
                for tid, status, inner in articles:
                    has = 'data-action="do_now"' in inner and 'data-action="done"' in inner
                    # Every open task card has the controls; a completed one has none.
                    self.assertEqual(has, status != "completed", tid)
                    if has:
                        self.assertIn('placeholder="Note for the agent – you can paste a screenshot here"', inner)
                        self.assertIn('<a href="', inner)          # the link to the record is kept
                for needle in ('id="save"', ">Save my verdicts<", ">Copy instead<", ">Clear<", 'id="tally"',
                               "window.BoardTasks", "attachShots", "a.download = name", "stopPropagation",
                               "'" + task_board.page_js.TASK_KEY + "'"):
                    self.assertIn(needle, text)
                # The shared code is inlined once, never a second copy.
                self.assertEqual(text.count("function shrink("), 1)
                self.assertEqual(text.count("function lightbox("), 1)
        personal = pages["personal"].read_text(encoding="utf-8")
        self.assertIn("owner-board/task-actions/v1", personal)
        self.assertIn("task-actions-", personal)
        status = pages["status"].read_text(encoding="utf-8")
        self.assertIn("tasks: tasks", status)                 # the verdicts file carries the task actions
        self.assertIn("TASKS.entries().length", status)       # and the tally counts them
        source = (SCRIPTS / "build_status.py").read_text(encoding="utf-8")
        for copy in ("function shrink", "function lightbox", "createObjectURL", "clipboardData"):
            self.assertNotIn(copy, source)

    @unittest.skipUnless(shutil.which("node"), "needs node to run the page's own script")
    def test_a_note_without_an_action_is_neither_sent_nor_cleared(self):
        # The owner's rule: a note alone means they are still deciding, so it stays on its card.
        script = re.search(r"<script>(.*)</script>", task_board.page_js.TASKS_JS, re.S).group(1)
        key = task_board.page_js.TASK_KEY
        stored = {"TASK-2099-0001": {"action": "", "note": "still thinking", "shots": [], "title": "a"},
                  "TASK-2099-0002": {"action": "done", "note": "finished", "shots": [], "title": "b"},
                  "TASK-2099-0003": {"action": "do_now", "note": "", "shots": [], "title": "c"}}
        harness = (
            "var store = {}; store[" + json.dumps(key) + "] = " + json.dumps(json.dumps(stored)) + ";"
            "var localStorage = { getItem: function (k) { return store[k] || null; },"
            " setItem: function (k, v) { store[k] = v; } };"
            "var document = { querySelectorAll: function () { return []; } };"
            "var window = { BoardPage: { el: function () { return {}; } } };"
            + script +
            "; var T = window.BoardTasks; var sent = T.entries().map(function (a) { return a.id; });"
            " var lines = T.lines(); T.forget(sent);"
            " console.log(JSON.stringify({ sent: sent, lines: lines.length,"
            " left: Object.keys(JSON.parse(store[" + json.dumps(key) + "])) }));")
        out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(result["sent"], ["TASK-2099-0002", "TASK-2099-0003"])
        self.assertEqual(result["lines"], 2)
        self.assertEqual(result["left"], ["TASK-2099-0001"])

    def downloads(self) -> Path:
        folder = self.brain.root / "fake-downloads" / "Board saves"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def apply_all(self):
        with mock.patch.object(verdicts, "downloads", return_value=str(self.downloads().parent)):
            return quiet(apply_verdicts.route, self.brain.config(), False)

    def test_task_actions_saved_from_a_task_page_are_applied_through_the_tasks_skill(self):
        store = self.brain.memory / "tasks"
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG fictional").decode("ascii")
        body = {"schema": "owner-board/task-actions/v1", "board": "tasks", "savedAt": "2026-01-10T08:30:00.000Z",
                "tasks": [{"id": "TASK-2026-0910", "action": "done", "note": "Finished early.", "shots": [png], "title": "x"},
                          {"id": "TASK-2026-0913", "action": "do_now", "note": "The pump first.", "shots": [], "title": "y"},
                          {"id": "TASK-2026-0915", "action": "", "note": "Ask about the hinges.", "shots": [], "title": "z"},
                          {"id": "TASK-2026-0999", "action": "done", "note": "", "shots": [], "title": "gone"}]}
        saved = self.downloads() / "task-actions-2026-01-10-08-30-00.json"
        saved.write_text(json.dumps(body), encoding="utf-8")
        changed, out = self.apply_all()
        # done: completed, moved, its STATE.md row out
        record = store / "completed" / "TASK-2026-0910-fictional.md"
        self.assertTrue(record.is_file())
        self.assertFalse((store / "open" / "TASK-2026-0910-fictional.md").exists())
        text = record.read_text(encoding="utf-8")
        self.assertIn("status: completed", text)
        self.assertIn("The owner's note: Finished early.", text)
        self.assertIn("![Screenshot 1](../img/TASK-2026-0910-20260110083000-1.png)", text)
        self.assertTrue((store / "img" / "TASK-2026-0910-20260110083000-1.png").is_file())
        # do now: waiting -> ready, high, and listed for the conductor
        meta = task_board.task_store.parse_front_matter((store / "open" / "TASK-2026-0913-fictional.md").read_text(encoding="utf-8"))
        self.assertEqual((meta["status"], meta["priority"]), ("ready", "high"))
        self.assertIn("Do now (asked for by the owner):\n  TASK-2026-0913  Fictional task 0913 – The pump first.", out)
        # a note alone changes nothing but History
        in_progress = (store / "open" / "TASK-2026-0915-fictional.md").read_text(encoding="utf-8")
        self.assertIn("status: in_progress", in_progress)
        self.assertIn("Note from the owner.\n  The owner's note: Ask about the hinges.", in_progress)
        # an unknown id is reported and skipped; the file is filed with the task store
        self.assertIn("SKIPPED TASK-2026-0999: no task with that id", out)
        self.assertFalse(saved.exists())
        self.assertTrue((store / "actions-applied" / saved.name).is_file())
        self.assertEqual(sorted(changed), ["garden", "pond"])      # every board is redrawn

    def test_task_actions_ride_in_a_verdicts_file(self):
        garden = self.brain.config().board("garden")
        state_path = self.brain.memory / "tasks" / "STATE.md"
        state_path.write_text(state_path.read_text(encoding="utf-8").replace(
            "# Current State\n", "# Current State\n\n## Open tasks (2, ordered by task number ascending)\n")
            + "| `TASK-2026-0911` | **ready** | high | - | Fictional task 0911 |\n", encoding="utf-8")
        body = {"schema": garden["verdict_schema"], "board": "garden", "savedAt": "2026-01-10T08:30:00.000Z",
                "verdicts": [], "tasks": [{"id": "TASK-2026-0911", "action": "done", "note": "", "shots": [], "title": "x"}]}
        (self.downloads() / (garden["verdict_prefix"] + "t.json")).write_text(json.dumps(body), encoding="utf-8")
        _, out = self.apply_all()
        store = self.brain.memory / "tasks"
        self.assertTrue((store / "completed" / "TASK-2026-0911-fictional.md").is_file())
        state = (store / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("TASK-2026-0901", state)
        self.assertNotIn("TASK-2026-0911", state)
        self.assertIn("## Open tasks (1, ordered", state)
        self.assertIn("done     TASK-2026-0911", out)

    def test_a_dry_run_changes_no_task(self):
        body = {"schema": "owner-board/task-actions/v1", "board": "tasks", "savedAt": "",
                "tasks": [{"id": "TASK-2026-0912", "action": "done", "note": "", "shots": [], "title": "x"}]}
        saved = self.downloads() / "task-actions-dry.json"
        saved.write_text(json.dumps(body), encoding="utf-8")
        with mock.patch.object(verdicts, "downloads", return_value=str(self.downloads().parent)):
            changed, out = quiet(apply_verdicts.route, self.brain.config(), True)
        self.assertEqual(changed, [])
        self.assertTrue(saved.exists())
        self.assertTrue((self.brain.memory / "tasks" / "open" / "TASK-2026-0912-fictional.md").is_file())
        self.assertIn("(dry run)", out)

    def test_column_order_is_deliberate(self):
        routed = task_board.route(self.brain.config(), today=TODAY)
        garden = task_board.section(routed["garden"], self.brain.memory, TODAY)
        ready = garden[garden.index('data-column="ready"'):garden.index('data-column="in_progress"')]
        # Priority first, then the nearer deadline: 0912 (high, 15 Jan), 0911 (high, 1 Feb), 0910 (low).
        order = re.findall(r'data-task="(TASK-\d{4}-\d{4})"', ready)
        self.assertEqual(order, ["TASK-2026-0912", "TASK-2026-0911", "TASK-2026-0910"])
        pond = task_board.section(routed["pond"], self.brain.memory, TODAY)
        waiting = re.findall(r'data-task="(TASK-\d{4}-\d{4})"', pond)
        self.assertEqual(waiting, ["TASK-2026-0914", "TASK-2026-0913"])   # nearest review first
        self.assertIn("review due", pond)                                  # 0914's review has come
        columns = re.findall(r'data-column="([a-z_]+)"', garden)
        self.assertEqual(columns, ["inbox", "ready", "in_progress", "waiting", "scheduled", "blocked", "completed"])

    def test_a_new_task_appears_on_its_board_at_once(self):
        sys.path.insert(0, str(SCRIPTS.parents[1] / "tasks" / "scripts"))
        import tasks as task_cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = task_cli.main(["--tasks", str(self.brain.memory / "tasks"), "new", "--title", "Mulch the pond edge",
                                  "--status", "ready", "--priority", "high", "--project", "/memory/projects/example-pond",
                                  "--now", "2026-01-10T09:00:00+10:00"], cwd=self.brain.root)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("TASK-2026-0919 is on Pond Pump", out.getvalue())
        record = self.brain.memory / "tasks" / "open" / "TASK-2026-0919-mulch-the-pond-edge.md"
        self.assertTrue(record.is_file())
        self.assertIn("| `TASK-2026-0919` | **ready** | high | - | Mulch the pond edge |",
                      (self.brain.memory / "tasks" / "STATE.md").read_text(encoding="utf-8"))
        page = self.brain.memory / "projects/example-pond/status/status.html"
        self.assertIn(("TASK-2026-0919", "ready"), task_board.shown_on(page))
