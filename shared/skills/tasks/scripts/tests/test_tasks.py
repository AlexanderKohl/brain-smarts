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

    def test_missing_store_exits_2(self) -> None:
        code, out = run("--tasks", "/memory/nowhere", "check", cwd=self.root)
        self.assertEqual(code, 2)
        self.assertIn("task store not found", out)


if __name__ == "__main__":
    unittest.main()
