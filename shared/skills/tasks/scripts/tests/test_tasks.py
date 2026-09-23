"""Tests for tasks.py.

Run from the brain root:
    python -m unittest discover -s shared/skills/tasks/scripts/tests -v

All task content below is fictional.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import tasks  # noqa: E402

STAMP = "2026-03-01T09:00:00+10:00"
TODAY = "2026-03-10"


def task(tid: str, title: str, status: str, **fields: str) -> str:
    meta = {
        "id": tid,
        "title": title,
        "type": "task",
        "schema_version": "0.2",
        "contract": "/CONTRACT.md",
        "status": status,
        "owner": "brain-owner",
        "priority": "normal",
        "created": STAMP,
        "updated": STAMP,
        "due": "null",
        "next_review": "null",
        "waiting_on": "null",
        "project_refs": "[]",
    }
    meta.update(fields)
    lines = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{lines}\n---\n\n# {title}\n\n## History\n"


def run(*argv: str, cwd: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = tasks.main(list(argv), cwd=cwd)
    return code, out.getvalue()


class TasksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-tasks-"))
        (self.root / "CONTRACT.md").write_text("---\nid: contract\n---\n", encoding="utf-8")
        self.store = self.root / "memory" / "tasks"
        for folder in ("inbox", "open", "completed", "templates"):
            (self.store / folder).mkdir(parents=True)
            (self.store / folder / "README.md").write_text("---\nid: x\n---\n", encoding="utf-8")
        self.add("inbox", "TASK-2026-0007-sort-receipts", task("TASK-2026-0007", "Sort receipts", "inbox"))
        self.add("open", "TASK-2026-0001-quote-for-example-plumbing",
                 task("TASK-2026-0001", "Send a quote to Example Plumbing", "waiting",
                      next_review="2026-03-09", waiting_on="Example Plumbing Pty Ltd"))
        self.add("open", "TASK-2026-0002-renew-domain",
                 task("TASK-2026-0002", "Renew the example.org domain", "ready", due="2026-03-15"))
        self.add("open", "TASK-2026-0003-file-report",
                 task("TASK-2026-0003", "File the quarterly report", "ready", due="2026-03-02"))
        self.add("open", "TASK-2026-0004-later",
                 task("TASK-2026-0004", "Plan the offsite", "scheduled", next_review="2026-04-01"))
        self.add("open", "TASK-2026-0005-stuck",
                 task("TASK-2026-0005", "Migrate the mailbox", "blocked"))
        self.add("completed", "TASK-2026-0006-done",
                 task("TASK-2026-0006", "Order business cards", "completed"))
        self.add("templates", "TASK_TEMPLATE", task("template-TASK-YYYY-NNNN", "Template", "inbox"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def add(self, folder: str, stem: str, text: str) -> None:
        (self.store / folder / f"{stem}.md").write_text(text, encoding="utf-8")

    def test_review_lists_what_needs_attention_in_order(self) -> None:
        code, out = run("--json", "review", "--today", TODAY, cwd=self.root)
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual(
            [(r["id"], r["reasons"]) for r in rows],
            [
                ("TASK-2026-0005", ["blocked"]),
                ("TASK-2026-0007", ["inbox: process it"]),
                ("TASK-2026-0003", ["overdue since 2026-03-02"]),
                ("TASK-2026-0001", ["review due 2026-03-09"]),
                ("TASK-2026-0002", ["due 2026-03-15"]),
            ],
        )
        self.assertEqual(rows[3]["waiting_on"], "Example Plumbing Pty Ltd")

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

    def test_check_finds_misplaced_and_malformed_records(self) -> None:
        self.add("open", "TASK-2026-0008-finished",
                 task("TASK-2026-0008", "Finished but not moved", "completed"))
        self.add("completed", "TASK-2026-0009-wrong-name",
                 task("TASK-2026-0010", "Mismatched name", "cancelled"))
        self.add("open", "TASK-2026-0011-bad-date",
                 task("TASK-2026-0011", "Bad date", "waiting", next_review="next week", owner="null"))
        self.add("open", "note", "no front matter here\n")
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("open/TASK-2026-0008-finished.md: status completed does not belong in open/", out)
        self.assertIn("completed/TASK-2026-0009-wrong-name.md: file name does not start with TASK-2026-0010", out)
        self.assertIn("open/TASK-2026-0011-bad-date.md: missing owner", out)
        self.assertIn("open/TASK-2026-0011-bad-date.md: next_review next week is not a date", out)
        self.assertIn("WARN: open/TASK-2026-0011-bad-date.md: waiting without waiting_on", out)
        self.assertIn("open/note.md: missing front matter", out)

    def test_next_id_counts_every_folder(self) -> None:
        self.assertEqual(tasks.next_id(self.store, 2026), "TASK-2026-0008")
        self.assertEqual(tasks.next_id(self.store, 2027), "TASK-2027-0001")

    def test_timestamps_are_accepted_as_dates(self) -> None:
        record = tasks.Task(Path("x.md"), "open", {"next_review": "2026-03-09T08:00:00+10:00"})
        self.assertEqual(record.day("next_review"), date(2026, 3, 9))

    def state(self) -> str:
        return (self.store / "STATE.md").read_text(encoding="utf-8")

    def test_new_creates_the_record_with_the_next_number_and_its_state_row(self) -> None:
        (self.store / "STATE.md").write_text(
            "# State\n\n| Task | Status | Priority | Review / waiting on | Title |\n|---|---|---|---|---|\n"
            "| `TASK-2026-0001` | **waiting** | normal | review 2026-03-09 | Send a quote |\n\nAfter the table.\n",
            encoding="utf-8")
        code, out = run("--tasks", "/memory/tasks", "new", "--title", "Book the van: Tuesday", "--status", "waiting",
                        "--priority", "high", "--project", "/memory/projects/example-move",
                        "--next-review", "2026-03-12", "--waiting-on", "Example Vans Pty Ltd",
                        "--outcome", "The van is booked.", "--now", "2026-03-10T09:00:00+10:00", "--no-board",
                        cwd=self.root)
        self.assertEqual(code, 0, out)
        path = self.store / "open" / "TASK-2026-0008-book-the-van-tuesday.md"
        self.assertIn(f"created TASK-2026-0008: {path}", out)
        meta = tasks.parse_front_matter(path.read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], "TASK-2026-0008")
        self.assertEqual(meta["title"], "Book the van: Tuesday")
        self.assertEqual(meta["project_refs"], ["/memory/projects/example-move"])
        self.assertEqual((meta["status"], meta["next_review"], meta["created"]),
                         ("waiting", "2026-03-12", "2026-03-10T09:00:00+10:00"))
        body = path.read_text(encoding="utf-8")
        self.assertIn("# Book the van: Tuesday", body)
        self.assertIn("## Outcome\n\nThe van is booked.", body)
        self.assertNotIn("_outcome", body)
        self.assertIn("| `TASK-2026-0008` | **waiting** | high | review 2026-03-12; waiting on Example Vans Pty Ltd "
                      "| Book the van: Tuesday |\n\nAfter the table.", self.state())
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0, out)

    def test_new_inbox_task_goes_to_inbox_without_a_state_row(self) -> None:
        (self.store / "STATE.md").write_text("| Task | Status |\n|---|---|\n", encoding="utf-8")
        code, out = run("new", "--title", "Think about the garden", "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertTrue(next((self.store / "inbox").glob("TASK-2026-0008-*.md"), None))
        self.assertNotIn("TASK-2026-0008", self.state())

    def test_new_refuses_waiting_without_a_review_date(self) -> None:
        code, out = run("new", "--title", "Chase the invoice", "--status", "waiting", "--waiting-on", "Example Co",
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("needs --next-review", out)
        self.assertEqual(list((self.store / "open").glob("TASK-2026-0008-*")), [])

    def test_new_says_when_there_is_no_board_to_refresh(self) -> None:
        code, out = run("new", "--title", "Water the ferns", "--status", "ready", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("board: ", out)
        self.assertIn("STATE.md: not found", out)

    def test_new_keeps_the_heading_count_and_an_older_next_free_line(self) -> None:
        (self.store / "STATE.md").write_text(
            "# State\n\n## Open tasks (0, ordered by task number ascending)\n\n"
            "| Task | Status | Priority | Review / waiting on | Title |\n|---|---|---|---|---|\n\n"
            "Next free number: `TASK-2026-0008`.\n", encoding="utf-8")
        for title in ("Order the tiles", "Measure the hallway"):
            code, out = run("new", "--title", title, "--status", "ready",
                            "--now", "2026-03-10T09:00:00+10:00", "--no-board", cwd=self.root)
            self.assertEqual(code, 0, out)
        state = self.state()
        self.assertIn("## Open tasks (2, ordered by task number ascending)", state)
        self.assertIn("Next free number: `TASK-2026-0010`.", state)
        self.assertEqual(tasks.next_id(self.store, 2026), "TASK-2026-0010")

    def test_new_refuses_a_project_path_rewritten_by_git_bash(self) -> None:
        mangled = "C:/Program Files/Git/memory/projects/example-move"
        code, out = run("new", "--title", "Book the van", "--status", "ready", "--project", mangled,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("not a repository-root path starting with /memory/", out)
        self.assertIn("MSYS_NO_PATHCONV=1", out)
        self.assertEqual(list((self.store / "open").glob("TASK-2026-0008-*")), [])
        code, out = run("new", "--title", "Book the van", "--status", "ready", "--project", "projects/x",
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        (self.root / "systems" / "example-system").mkdir(parents=True)
        code, out = run("new", "--title", "Tidy the system node", "--status", "ready",
                        "--project", "/systems/example-system", "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)

    def test_new_stamps_the_owner_timezone_or_says_why_not(self) -> None:
        profile = self.root / "memory" / "OWNER.md"
        profile.write_text("---\nid: owner\ntimezone: UTC (+00:00)\n---\n", encoding="utf-8")
        stamp, note = tasks.owner_now(self.store)
        self.assertTrue(stamp.endswith("+00:00"), stamp)
        self.assertIsNone(note)
        profile.write_text("---\nid: owner\ntimezone: Example/Nowhere (+13:45)\n---\n", encoding="utf-8")
        stamp, note = tasks.owner_now(self.store)
        machine = tasks.datetime.now().astimezone().isoformat()[-6:]
        self.assertEqual(stamp[-6:], machine)
        if machine != "+13:45":
            self.assertIn("Example/Nowhere from OWNER.md cannot be resolved", note)

    def test_missing_store_exits_2(self) -> None:
        code, out = run("--tasks", "/memory/nowhere", "check", cwd=self.root)
        self.assertEqual(code, 2)
        self.assertIn("task store not found", out)


if __name__ == "__main__":
    unittest.main()
