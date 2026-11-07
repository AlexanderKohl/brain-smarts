"""Tests for tasks.py in the owner store: review, check, next-id, new, done, do-now, note, edit.

Run from the brain root:
    python -m unittest discover -s shared/skills/tasks/scripts/tests -v

All task content below is fictional.
"""

from __future__ import annotations

import base64
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from brainfix import NOW, STAMP, Brain, record

import task_history  # noqa: E402
import tasks  # noqa: E402

TODAY = "2026-03-10"


def run(*argv: str, cwd: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = tasks.main(list(argv), cwd=cwd)
    return code, out.getvalue()


class TasksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.root, self.store = self.brain.root, self.brain.store
        add = self.brain.add
        add("inbox", "TASK-2026-0007-sort-receipts", record("TASK-2026-0007", "Sort receipts", "inbox"))
        add("open", "TASK-2026-0001-quote", record("TASK-2026-0001", "Send a quote to Example Plumbing", "waiting",
                                                   next_review="2026-03-09", waiting_on="Example Plumbing Pty Ltd"))
        add("open", "TASK-2026-0002-renew-domain", record("TASK-2026-0002", "Renew the example.org domain", "ready",
                                                          due="2026-03-15"))
        add("open", "TASK-2026-0003-file-report", record("TASK-2026-0003", "File the quarterly report", "ready",
                                                         due="2026-03-02"))
        add("open", "TASK-2026-0004-later", record("TASK-2026-0004", "Plan the offsite", "scheduled",
                                                   next_review="2026-04-01"))
        add("open", "TASK-2026-0005-stuck", record("TASK-2026-0005", "Migrate the mailbox", "blocked"))
        add("completed", "TASK-2026-0006-done", record("TASK-2026-0006", "Order business cards", "completed"))
        self.state_now()

    def state_now(self) -> None:
        import task_state
        import task_stores
        task_state.write(task_stores.owner_store(self.root))

    def tearDown(self) -> None:
        self.brain.close()

    def text(self, folder: str, stem: str) -> str:
        return (self.store / folder / f"{stem}.md").read_text(encoding="utf-8")

    def meta(self, folder: str, stem: str) -> dict:
        return tasks.parse_front_matter(self.text(folder, stem))

    def state(self) -> str:
        return (self.store / "STATE.md").read_text(encoding="utf-8")

    # ------------------------------------------------ review and check

    def test_review_lists_what_needs_attention_in_order(self) -> None:
        code, out = run("--json", "review", "--today", TODAY, cwd=self.root)
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual([(r["id"], r["reasons"]) for r in rows], [
            ("TASK-2026-0005", ["blocked"]),
            ("TASK-2026-0007", ["inbox: process it"]),
            ("TASK-2026-0003", ["overdue since 2026-03-02"]),
            ("TASK-2026-0001", ["review due 2026-03-09"]),
            ("TASK-2026-0002", ["due 2026-03-15"]),
        ])
        self.assertEqual({r["store"] for r in rows}, {"/memory/tasks"})

    def test_review_horizon_and_table(self) -> None:
        code, out = run("review", "--today", TODAY, "--horizon", "2", cwd=self.root)
        self.assertEqual(code, 0)
        self.assertNotIn("TASK-2026-0002", out)
        self.assertIn("| TASK-2026-0001 | waiting | normal | review due 2026-03-09 |", out)
        self.assertIn("4 task(s) need attention", out)

    def test_clean_store_passes_check(self) -> None:
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS: 0 error(s), 0 warning(s)", out)

    def test_check_finds_misplaced_malformed_and_unattributed_records(self) -> None:
        add = self.brain.add
        add("open", "TASK-2026-0008-finished", record("TASK-2026-0008", "Finished but not moved", "completed"))
        add("completed", "TASK-2026-0009-wrong-name", record("TASK-2026-0010", "Mismatched name", "cancelled"))
        add("open", "TASK-2026-0011-bad-date", record("TASK-2026-0011", "Bad date", "waiting",
                                                      next_review="next week", owner="null"))
        add("open", "TASK-2026-0012-no-author", record("TASK-2026-0012", "No author", "ready", author=None))
        add("open", "TASK-2026-0013-edited", record("TASK-2026-0013", "Edited silently", "ready", updated=NOW))
        add("open", "note", "no front matter here\n")
        self.state_now()
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 1)
        for line in ("open/TASK-2026-0008-finished.md: status completed does not belong in open/",
                     "completed/TASK-2026-0009-wrong-name.md: file name does not start with TASK-2026-0010",
                     "open/TASK-2026-0011-bad-date.md: missing owner",
                     "open/TASK-2026-0011-bad-date.md: next_review next week is not a date",
                     "WARN: /memory/tasks/open/TASK-2026-0011-bad-date.md: waiting without waiting_on",
                     "open/TASK-2026-0012-no-author.md: missing author",
                     "open/TASK-2026-0013-edited.md: updated 2026-03-10T09:00:00+10:00 is later than its newest",
                     "open/note.md: missing front matter"):
            self.assertIn(line, out)

    def test_check_finds_a_hand_edited_state_file(self) -> None:
        (self.store / "STATE.md").write_text(self.state().replace("**ready**", "**waiting**", 1), encoding="utf-8")
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("/memory/tasks/STATE.md: differs from the generated one", out)
        self.assertEqual(run("state", cwd=self.root)[0], 0)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    # ------------------------------------------------ identifiers

    def test_next_id_continues_the_highest_number_per_author(self) -> None:
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0008")
        self.assertEqual(tasks.next_id(self.root, "sam", 2027), "TASK-sam-2027-0001")
        self.assertEqual(tasks.next_id(self.root, "bob", 2026), "TASK-bob-2026-0001")
        # A legacy record that names another author counts for that author only.
        self.brain.add("open", "TASK-2026-0040-bobs", record("TASK-2026-0040", "Bob's legacy task", "ready", author="bob"))
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0008")
        self.assertEqual(tasks.next_id(self.root, "bob", 2026), "TASK-bob-2026-0041")
        # A legacy record in this brain's memory without an author is this brain's own.
        self.brain.add("open", "TASK-2026-0020-unsigned", record("TASK-2026-0020", "Unsigned", "ready", author=None))
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0021")
        self.assertEqual(run("next-id", "--year", "2026", cwd=self.root)[1].strip(), "TASK-sam-2026-0021")

    # ------------------------------------------------ new

    def test_new_writes_an_attributed_record_with_the_new_fields_and_generates_state(self) -> None:
        code, out = run("--tasks", "/memory/tasks", "new", "--title", "Book the van: Tuesday", "--status", "waiting",
                        "--priority", "high", "--next-review", "2026-03-12", "--waiting-on", "Example Vans Pty Ltd",
                        "--schedule", "Example Calendar | van-reminder | weekly", "--outcome", "The van is booked.",
                        "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        path = self.store / "open" / "TASK-sam-2026-0008-book-the-van-tuesday.md"
        self.assertIn(f"created TASK-sam-2026-0008: {path}", out)
        text = path.read_text(encoding="utf-8")
        meta = tasks.parse_front_matter(text)
        self.assertEqual((meta["id"], meta["author"], meta["owner"], meta["related_tasks"]),
                         ("TASK-sam-2026-0008", "sam", "Sam", []))
        self.assertEqual(meta["schedule"], "Example Calendar | van-reminder | weekly")
        keys = [line.split(":")[0] for line in text.split("---")[1].splitlines() if line and not line.startswith(" ")]
        self.assertEqual(keys[keys.index("owner") + 1], "author")
        self.assertEqual(keys[keys.index("waiting_on") + 1], "schedule")
        self.assertEqual(keys[keys.index("depends_on") + 1], "related_tasks")
        self.assertIn("## Outcome\n\nThe van is booked.", text)
        self.assertIn(f"- {NOW} \u2013 sam: captured with `tasks.py new` (waiting)", text)
        self.assertEqual(task_history.newest_attributed(text).at.isoformat(), NOW)
        self.assertIn("| `TASK-sam-2026-0008` | **waiting** | high | review 2026-03-12; waiting on Example Vans Pty Ltd "
                      "| Book the van: Tuesday |", self.state())
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_new_inbox_task_goes_to_inbox_and_the_state_inbox_list(self) -> None:
        code, out = run("new", "--title", "Think about the garden", "--no-board", "--now", NOW, cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.store / "inbox" / "TASK-sam-2026-0008-think-about-the-garden.md").is_file())
        self.assertIn("## Inbox (2)\n\n- `TASK-2026-0007` Sort receipts\n- `TASK-sam-2026-0008` Think about the garden",
                      self.state())

    def test_new_refuses_bad_input_and_writes_nothing(self) -> None:
        code, out = run("new", "--title", "Chase the invoice", "--status", "waiting", "--waiting-on", "Example Co",
                        "--no-board", cwd=self.root)
        self.assertEqual((code, "needs --next-review" in out), (1, True))
        code, out = run("new", "--title", "Run it", "--schedule", "only two | parts", "--no-board", cwd=self.root)
        self.assertEqual((code, "is not \"<app> | <job> | <cadence>\"" in out), (1, True))
        mangled = "C:/Program Files/Git/memory/projects/example-move"
        code, out = run("new", "--title", "Book the van", "--project", mangled, "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("MSYS_NO_PATHCONV=1", out)
        self.assertEqual(list(self.store.rglob("TASK-sam-*")), [])

    def test_every_write_refuses_without_an_author_name(self) -> None:
        self.brain.profile(None)
        code, out = run("new", "--title", "Water the ferns", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("no owner_short_name", out)
        code, out = run("done", "TASK-2026-0002", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertEqual(self.meta("open", "TASK-2026-0002-renew-domain")["status"], "ready")

    def test_new_stamps_the_owner_timezone_or_says_why_not(self) -> None:
        stamp, note = tasks.owner_now(self.root)
        self.assertTrue(stamp.endswith("+00:00"), stamp)
        self.assertIsNone(note)
        profile = self.root / "memory" / "OWNER.md"
        profile.write_text("---\nid: owner\nowner_short_name: Sam\ntimezone: Example/Nowhere (+13:45)\n---\n",
                           encoding="utf-8")
        stamp, note = tasks.owner_now(self.root)
        machine = task_history.datetime.now().astimezone().isoformat()[-6:]
        self.assertEqual(stamp[-6:], machine)
        if machine != "+13:45":
            self.assertIn("Example/Nowhere from OWNER.md cannot be resolved", note)

    # ------------------------------------------------ done, do-now, note

    def test_done_completes_moves_attributes_and_regenerates_state(self) -> None:
        code, out = run("done", "TASK-2026-0002", "--note", "Renewed for two years.\nReceipt filed.",
                        "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertFalse((self.store / "open" / "TASK-2026-0002-renew-domain.md").exists())
        text = self.text("completed", "TASK-2026-0002-renew-domain")
        meta = tasks.parse_front_matter(text)
        self.assertEqual((meta["status"], meta["updated"]), ("completed", NOW))
        self.assertIn(f"- {NOW} \u2013 sam: done (completed)\n  Note: Renewed for two years.\n  Receipt filed.\n", text)
        state = self.state()
        self.assertIn("## Open tasks (4)", state)
        self.assertIn("## Recently completed\n\n- `TASK-2026-0002` Renew the example.org domain (2026-03-10)\n"
                      "- `TASK-2026-0006` Order business cards (2026-03-01)", state)
        with self.assertRaises(ValueError):
            tasks.complete(self.store, "TASK-2026-0002", now=NOW)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_do_now_raises_priority_and_sets_ready_unless_in_progress(self) -> None:
        tasks.do_now(self.store, "TASK-2026-0001", note="Before Friday, please.", now=NOW)
        meta = self.meta("open", "TASK-2026-0001-quote")
        self.assertEqual((meta["status"], meta["priority"], meta["updated"]), ("ready", "high", NOW))
        self.assertIn("sam: asked for now (priority high, ready)\n  Note: Before Friday, please.",
                      self.text("open", "TASK-2026-0001-quote"))
        self.brain.add("open", "TASK-2026-0009-going", record("TASK-2026-0009", "Paint the fence", "in_progress"))
        tasks.do_now(self.store, "TASK-2026-0009", now=NOW)
        self.assertEqual(self.meta("open", "TASK-2026-0009-going")["status"], "in_progress")
        tasks.do_now(self.store, "TASK-2026-0007", now=NOW)
        self.assertTrue((self.store / "open" / "TASK-2026-0007-sort-receipts.md").is_file())
        self.assertIn("| `TASK-2026-0007` | **ready** | high |", self.state())
        with self.assertRaises(ValueError):
            tasks.do_now(self.store, "TASK-2026-0006", now=NOW)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_note_adds_an_attributed_entry_only(self) -> None:
        before = self.meta("open", "TASK-2026-0005-stuck")
        code, out = run("note", "TASK-2026-0005", "--note", "The new host is Example Mail.", "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        text = self.text("open", "TASK-2026-0005-stuck")
        self.assertIn(f"- {NOW} \u2013 sam: note\n  Note: The new host is Example Mail.", text)
        after = tasks.parse_front_matter(text)
        self.assertEqual((after["status"], after["updated"]), (before["status"], NOW))

    def test_note_run_records_a_scheduled_run_and_warns_on_another_job(self) -> None:
        self.brain.add("open", "TASK-2026-0009-backup", record(
            "TASK-2026-0009", "Back up the photos", "scheduled", next_review="2026-04-01",
            schedule="\"Example Backup | photo-sync | daily\""))
        code, out = run("note", "TASK-2026-0009", "--run", "photo-sync", "--note", "312 files copied", "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn(f"- {NOW} \u2013 sam: run of `photo-sync`: 312 files copied", self.text("open", "TASK-2026-0009-backup"))
        self.assertNotIn("warning", out)
        code, out = run("note", "TASK-2026-0009", "--run", "video-sync", "--note", "nothing new", "--no-board",
                        cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("warning: TASK-2026-0009 schedules photo-sync, not video-sync", out)

    def test_note_private_is_refused_for_a_task_in_memory(self) -> None:
        code, out = run("note", "TASK-2026-0005", "--private", "--note", "x", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("already private", out)

    def test_an_unknown_task_id_is_an_error(self) -> None:
        code, out = run("done", "TASK-2026-0999", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("no task TASK-2026-0999 in any reachable store", out)

    def test_only_plain_images_are_kept_and_linked(self) -> None:
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG fictional").decode()
        shots = [png, "data:text/html;base64,PHA+", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,@@"]
        tasks.add_note(self.store, "TASK-2026-0004", note="", shots=shots, now=NOW)
        self.assertEqual(sorted(p.name for p in (self.store / "img").iterdir()), ["TASK-2026-0004-20260310090000-1.png"])
        self.assertIn("![Screenshot 1](../img/TASK-2026-0004-20260310090000-1.png)", self.text("open", "TASK-2026-0004-later"))
        with self.assertRaises(ValueError):
            tasks.add_note(self.store, "TASK-2026-0004", note=" ", shots=shots[1:], now=NOW)

    # ------------------------------------------------ edit

    def test_edit_changes_allowed_fields_with_old_and_new_in_history(self) -> None:
        code, out = run("edit", "TASK-2026-0002", "--set", "priority=high", "--set", "due=2026-03-20",
                        "--set", "related_tasks=TASK-2026-0003,TASK-2026-0004", "--note", "The registrar moved the date.",
                        "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        text = self.text("open", "TASK-2026-0002-renew-domain")
        meta = tasks.parse_front_matter(text)
        self.assertEqual((meta["priority"], meta["due"], meta["related_tasks"], meta["updated"]),
                         ("high", "2026-03-20", ["TASK-2026-0003", "TASK-2026-0004"], NOW))
        self.assertIn(f"- {NOW} \u2013 sam: edit: due: 2026-03-15 -> 2026-03-20; priority: normal -> high; "
                      "related_tasks: null -> [TASK-2026-0003, TASK-2026-0004]\n  Note: The registrar moved the date.", text)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_edit_refusals(self) -> None:
        for setting, said in (("id=TASK-2026-0100", "an identifier never changes"),
                              ("author=bob", "the author never changes"),
                              ("created=2026-01-01", "the creation time never changes"),
                              ("project_refs=/memory/projects/x", "tasks.py migrate"),
                              ("colour=green", "not an editable field"),
                              ("status=completed", "does not belong in open/"),
                              ("due=soon", "is not a date")):
            code, out = run("edit", "TASK-2026-0002", "--set", setting, "--note", "why", "--no-board", cwd=self.root)
            self.assertEqual(code, 1, setting)
            self.assertIn(said, out, setting)
        self.assertEqual(self.meta("open", "TASK-2026-0002-renew-domain")["updated"], STAMP)

    # ------------------------------------------------ round 2

    def test_check_refuses_bad_timestamps_and_author_names(self) -> None:
        add = self.brain.add
        add("open", "TASK-2026-0020-a", record("TASK-2026-0020", "Placeholder stamp", "ready",
                                               updated="YYYY-MM-DDTHH:mm:ss+HH:MM"))
        add("open", "TASK-2026-0021-b", record("TASK-2026-0021", "Bare date", "ready", created="2026-03-01"))
        add("open", "TASK-2026-0022-c", record("TASK-2026-0022", "Capital author", "ready", author="Sam"))
        self.state_now()
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("TASK-2026-0020-a.md: updated YYYY-MM-DDTHH:mm:ss+HH:MM is not ISO 8601", out)
        self.assertIn("TASK-2026-0021-b.md: created 2026-03-01 is not ISO 8601", out)
        self.assertIn("TASK-2026-0022-c.md: author Sam is not an author name", out)

    def test_next_id_normalises_the_author_it_is_given(self) -> None:
        self.assertEqual(run("next-id", "--year", "2026", "--author", "Sam", cwd=self.root)[1].strip(),
                         "TASK-sam-2026-0008")
        code, out = run("next-id", "--author", "!!", cwd=self.root)
        self.assertEqual(code, 1)

    def test_a_record_with_two_history_headings_is_read_and_written_as_one(self) -> None:
        text = record("TASK-2026-0030", "Two histories", "ready").rstrip("\n") + \
            "\n\n## History\n\n- 2026-03-05T09:00:00+10:00 – bob: second block\n\n## Notes\n\nKept.\n"
        path = self.brain.add("open", "TASK-2026-0030-two", text)
        self.assertEqual([e.what for e in task_history.entries(text)], ["captured", "second block"])
        self.assertEqual(task_history.newest_attributed(text).author, "bob")
        tasks.add_note(self.store, "TASK-2026-0030", note="After both.", now=NOW)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.count("## History"), 1)
        self.assertEqual([e.what for e in task_history.entries(after)], ["captured", "second block", "note"])
        self.assertIn("## Notes\n\nKept.", after)

    def test_a_refused_write_is_a_value_error(self) -> None:
        import task_git
        self.assertTrue(issubclass(task_git.WriteRefused, ValueError))

    def test_missing_store_exits_2(self) -> None:
        code, out = run("--tasks", "/memory/nowhere", "check", cwd=self.root)
        self.assertEqual(code, 2)
        self.assertIn("task store not found", out)

    def test_dates_and_timestamps_read_as_days(self) -> None:
        task = tasks.Task(Path("x.md"), "open", {"next_review": "2026-03-09T08:00:00+10:00"})
        self.assertEqual(task.day("next_review"), date(2026, 3, 9))


if __name__ == "__main__":
    unittest.main()
