"""Reminders and repeating tasks: remind, done (re-armed), done --final, review, reminders, check.

Run from the brain root:
    python -m unittest discover -s shared/skills/tasks/scripts/tests -v

All task content below is fictional (the brain of `sam`).
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from brainfix import NOW, Brain, record

import tasks  # noqa: E402

TODAY = "2026-03-10"
DONE = "python shared/skills/tasks/scripts/tasks.py done"


def run(*argv: str, cwd: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = tasks.main(list(argv), cwd=cwd)
    return code, out.getvalue()


class RemindersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.root, self.store = self.brain.root, self.brain.store
        self.brain.add("open", "TASK-2026-0001-quote", record("TASK-2026-0001", "Send a quote to Example Plumbing",
                                                              "waiting", next_review="2026-03-09",
                                                              waiting_on="Example Plumbing Pty Ltd"))
        self.state_now()

    def tearDown(self) -> None:
        self.brain.close()

    def state_now(self) -> None:
        import task_state
        import task_stores
        task_state.write(task_stores.owner_store(self.root))

    def remind(self, *extra: str) -> tuple[str, Path]:
        code, out = run("remind", *extra, "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        tid = out.splitlines()[0]
        path, = self.store.rglob(f"{tid}-*.md")
        return tid, path

    def meta(self, path: Path) -> dict:
        return tasks.parse_front_matter(path.read_text(encoding="utf-8"))

    # ------------------------------------------------ remind

    def test_remind_creates_a_scheduled_reminder_in_open_and_prints_its_id_alone(self) -> None:
        tid, path = self.remind("--title", "Check the garden hose order", "--on", "2026-03-12",
                                "--next-action", "Look in the order mailbox")
        self.assertEqual(tid, "TASK-sam-2026-0002")
        self.assertEqual(path.parent.name, "open")
        meta = self.meta(path)
        self.assertEqual((meta["status"], meta["reminder"], meta["next_review"]), ("scheduled", "true", "2026-03-12"))
        self.assertNotIn("repeat_days", meta)
        text = path.read_text(encoding="utf-8")
        self.assertIn("\nnext_review: 2026-03-12\nreminder: true\n", text)
        self.assertIn("## Next action\n\nLook in the order mailbox", text)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_remind_with_repeat_days_goes_to_recurring(self) -> None:
        tid, path = self.remind("--title", "Weekly review of the example ledger", "--on", "2026-03-10",
                                "--repeat-days", "7")
        self.assertEqual(path.parent.name, "recurring")
        meta = self.meta(path)
        self.assertEqual((meta["reminder"], meta["repeat_days"], meta["status"]), ("true", "7", "scheduled"))
        self.assertIn("\nreminder: true\nrepeat_days: 7\n", path.read_text(encoding="utf-8"))
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0, out)

    def test_remind_refuses_a_bad_day_or_repeat_and_writes_nothing(self) -> None:
        for extra, said in ((["--on", "12 March"], "is not a date"),
                            (["--on", "2026-03-12", "--repeat-days", "0"], "not a positive whole number"),
                            (["--on", "2026-03-12", "--repeat-days", "-3"], "not a positive whole number")):
            code, out = run("remind", "--title", "Feed the fish", *extra, "--no-board", cwd=self.root)
            self.assertEqual(code, 1, extra)
            self.assertIn(said, out)
        self.assertEqual(list(self.store.rglob("TASK-sam-*")), [])

    # ------------------------------------------------ done

    def test_done_re_arms_a_repeating_task_and_keeps_its_folder(self) -> None:
        tid, path = self.remind("--title", "Weekly review of the example ledger", "--on", "2026-03-10",
                                "--repeat-days", "7")
        text = path.read_text(encoding="utf-8").replace("claimed_by: null", "claimed_by: Example Session")
        path.write_text(text, encoding="utf-8")
        code, out = run("done", tid, "--note", "Ledger reviewed.", "--now", "2026-03-10T16:00:00+10:00",
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn(f"done {tid}; next on 2026-03-17", out)
        self.assertTrue(path.is_file(), "the record stays in recurring/")
        meta = self.meta(path)
        self.assertEqual((meta["status"], meta["next_review"], meta["claimed_by"], meta["updated"]),
                         ("scheduled", "2026-03-17", None, "2026-03-10T16:00:00+10:00"))
        self.assertIn("- 2026-03-10T16:00:00+10:00 – sam: done; next on 2026-03-17\n  Note: Ledger reviewed.",
                      path.read_text(encoding="utf-8"))
        self.assertFalse(list((self.store / "completed").glob(f"{tid}-*")))
        self.assertIn(tid, (self.store / "STATE.md").read_text(encoding="utf-8"))
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_done_final_completes_a_repeating_task(self) -> None:
        tid, path = self.remind("--title", "Weekly review of the example ledger", "--on", "2026-03-10",
                                "--repeat-days", "7")
        code, out = run("done", tid, "--final", "--now", "2026-03-10T16:00:00+10:00", "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertFalse(path.exists())
        done, = (self.store / "completed").glob(f"{tid}-*.md")
        self.assertEqual(self.meta(done)["status"], "completed")
        self.assertEqual(run("check", cwd=self.root)[0], 0, "repeat_days kept on a completed record is history")

    def test_done_refuses_a_repeat_days_that_is_not_a_positive_whole_number(self) -> None:
        path = self.brain.add("recurring", "TASK-2026-0005-odd", record(
            "TASK-2026-0005", "Odd repeat", "scheduled", next_review="2026-03-09", repeat_days="weekly"))
        before = path.read_text(encoding="utf-8")
        code, out = run("done", "TASK-2026-0005", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("repeat_days weekly is not a positive whole number", out)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    # ------------------------------------------------ review and reminders

    def add_reminders(self) -> None:
        self.brain.add("open", "TASK-2026-0002-hose", record("TASK-2026-0002", "Check the hose order", "scheduled",
                                                             next_review="2026-03-08", reminder="true"))
        self.brain.add("recurring", "TASK-2026-0003-ledger", record(
            "TASK-2026-0003", "Weekly ledger review", "scheduled", next_review="2026-03-10", reminder="true",
            repeat_days="7"))
        self.brain.add("open", "TASK-2026-0004-later", record("TASK-2026-0004", "Ring the example council", "scheduled",
                                                              next_review="2026-03-20", reminder="true"))
        self.state_now()

    def test_review_prints_the_due_reminders_first_and_counts_them_apart(self) -> None:
        self.add_reminders()
        code, out = run("review", "--today", TODAY, cwd=self.root)
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Reminders for the owner (2)")
        self.assertEqual(lines[2], f"- Check the hose order – TASK-2026-0002, due 2026-03-08, /memory/tasks; "
                                   f"when done: {DONE} TASK-2026-0002")
        self.assertTrue(lines[3].startswith("- Weekly ledger review – TASK-2026-0003, due 2026-03-10"))
        table = out[out.index("| Task |"):]
        self.assertNotIn("TASK-2026-0002", table)
        self.assertNotIn("TASK-2026-0003", table)
        self.assertNotIn("TASK-2026-0004", out, "a reminder not yet due is not shown")
        self.assertIn("| TASK-2026-0001 |", table)
        self.assertIn("\n1 task(s) need attention\n2 reminder(s) due\n", out)
        rows = json.loads(run("--json", "review", "--today", TODAY, cwd=self.root)[1])
        self.assertEqual({r["id"]: r["reminder"] for r in rows},
                         {"TASK-2026-0001": False, "TASK-2026-0002": True, "TASK-2026-0003": True})

    def test_review_without_reminders_says_none_due(self) -> None:
        out = run("review", "--today", TODAY, cwd=self.root)[1]
        self.assertTrue(out.startswith("Reminders for the owner (0)\n\n- none due\n"))
        self.assertIn("1 task(s) need attention\n0 reminder(s) due", out)

    def test_reminders_prints_one_line_per_due_reminder_and_nothing_when_none(self) -> None:
        self.assertEqual(run("reminders", "--today", TODAY, cwd=self.root), (0, ""))
        self.add_reminders()
        code, out = run("reminders", "--today", TODAY, cwd=self.root)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            f"reminder: Check the hose order – TASK-2026-0002, due 2026-03-08; when done: {DONE} TASK-2026-0002",
            f"reminder: Weekly ledger review – TASK-2026-0003, due 2026-03-10; when done: {DONE} TASK-2026-0003"])
        found = json.loads(run("reminders", "--json", "--today", TODAY, cwd=self.root)[1])
        self.assertEqual([r["id"] for r in found["reminders"]], ["TASK-2026-0002", "TASK-2026-0003"])
        self.assertEqual(found["lines"], out.splitlines())
        self.assertEqual(found["not_read"], [])

    def test_reminders_always_exits_0_and_names_what_it_could_not_read(self) -> None:
        code, out = run("--tasks", "/memory/nowhere", "reminders", cwd=self.root)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("reminder: could not be read (task store not found:"), out)
        self.brain.profile(None)        # no author name: the review cannot tell whose tasks are whose
        code, out = run("reminders", cwd=self.root)
        self.assertEqual(code, 0)
        self.assertIn("reminder: could not be read (", out)

    def test_reminders_from_a_store_still_print_beside_one_not_read(self) -> None:
        self.add_reminders()
        self.brain.node("/memory/projects/example-app", "Example App", repo_url="https://example.com/sam/example-app",
                        local_path="example-app-missing")
        code, out = run("reminders", "--today", TODAY, cwd=self.root)
        self.assertEqual(code, 0)
        self.assertIn("reminder: Check the hose order – TASK-2026-0002", out)
        self.assertIn("reminder: could not be read (example-app", out)

    # ------------------------------------------------ check

    def test_check_reports_each_reminder_and_repeat_error(self) -> None:
        add = self.brain.add
        add("open", "TASK-2026-0010-a", record("TASK-2026-0010", "Reminder without a day", "ready", reminder="true"))
        add("recurring", "TASK-2026-0011-b", record("TASK-2026-0011", "Bad repeat", "scheduled",
                                                    next_review="2026-03-12", repeat_days="0"))
        add("open", "TASK-2026-0012-c", record("TASK-2026-0012", "Repeat in open", "scheduled",
                                               next_review="2026-03-12", repeat_days="7"))
        add("recurring", "TASK-2026-0013-d", record("TASK-2026-0013", "Old recurring", "scheduled",
                                                    next_review="2026-03-12"))
        self.state_now()
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 1)
        for line in ("ERROR: /memory/tasks/open/TASK-2026-0010-a.md: reminder: true without next_review",
                     "ERROR: /memory/tasks/recurring/TASK-2026-0011-b.md: repeat_days 0 is not a positive whole number",
                     "ERROR: /memory/tasks/open/TASK-2026-0012-c.md: repeat_days on a record in open/",
                     "WARN: /memory/tasks/recurring/TASK-2026-0013-d.md: in recurring/ without repeat_days"):
            self.assertIn(line, out)
        self.assertNotIn("ERROR: /memory/tasks/recurring/TASK-2026-0013-d.md", out)


if __name__ == "__main__":
    unittest.main()
