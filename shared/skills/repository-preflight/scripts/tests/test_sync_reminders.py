"""The reminder lines of sync.py: one line per due reminder after the repository lines, in --json
too, and a failed read that is named and never changes the exit code.

An invented brain root in a temporary folder (fictional owner Sam). Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/scripts/tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sync  # noqa: E402

STAMP = "2026-03-01T09:00:00+10:00"
DONE = "python shared/skills/tasks/scripts/tasks.py done"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def task(tid: str, title: str, next_review: str, reminder: bool) -> str:
    flag = "reminder: true\n" if reminder else ""
    return (f"---\nid: {tid}\ntitle: {title}\ntype: task\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"status: scheduled\nowner: Sam\nauthor: sam\npriority: normal\ncreated: {STAMP}\nupdated: {STAMP}\n"
            f"due: null\nnext_review: {next_review}\n{flag}waiting_on: null\nproject_refs: []\n---\n\n# {title}\n\n"
            f"## History\n\n- {STAMP} – sam: captured\n")


class ReminderLinesTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="sync-reminders-"))
        self.root = self.base / "brain"
        write(self.root / "CONTRACT.md", "---\nid: c\n---\n")
        write(self.root / "memory/OWNER.md", "---\nowner_short_name: Sam\ntimezone: UTC (+00:00)\n---\n")
        store = self.root / "memory/tasks"
        write(store / "open/TASK-2026-0001-hose.md", task("TASK-2026-0001", "Check the hose order", "2000-01-02", True))
        write(store / "open/TASK-2026-0002-fish.md", task("TASK-2026-0002", "Feed the fish", "2000-01-01", True))
        write(store / "open/TASK-2026-0003-plain.md", task("TASK-2026-0003", "Plain scheduled task", "2000-01-01", False))
        write(store / "open/TASK-2026-0004-later.md", task("TASK-2026-0004", "Ring the council", "2999-01-01", True))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def main(self, *argv: str) -> tuple[int, str]:
        """sync.main with no repositories, so only the notices and the reminders are printed."""
        out = io.StringIO()
        with mock.patch.object(sync, "repositories", return_value=[]), \
                mock.patch.object(sync, "not_joined", return_value=[]), \
                mock.patch.object(sync, "held_by_others", return_value=[]), contextlib.redirect_stdout(out):
            code = sync.main(["--root", str(self.root), "--no-merge", *argv])
        return code, out.getvalue()

    def test_each_due_reminder_is_one_line_earliest_first(self):
        found = sync.reminders(self.root)
        self.assertEqual([r["line"] for r in found], [
            f"reminder: Feed the fish – TASK-2026-0002, due 2000-01-01; when done: {DONE} TASK-2026-0002",
            f"reminder: Check the hose order – TASK-2026-0001, due 2000-01-02; when done: {DONE} TASK-2026-0001"])
        self.assertTrue(all(r["ok"] and r["state"] == "due" and r["name"] == "reminder" for r in found))

    def test_the_text_form_prints_the_lines_unchanged_and_json_includes_them(self):
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [r["line"] for r in sync.reminders(self.root)])
        code, out = self.main("--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual([r["detail"] for r in rows if r["name"] == "reminder"], [r["line"] for r in sync.reminders(self.root)])

    def test_no_reminder_due_prints_nothing(self):
        for path in (self.root / "memory/tasks/open").glob("*.md"):
            path.write_text(path.read_text(encoding="utf-8").replace("reminder: true\n", ""), encoding="utf-8")
        self.assertEqual(self.main(), (0, ""))

    def test_a_read_that_fails_is_named_and_keeps_the_exit_code(self):
        failures = (subprocess.TimeoutExpired("tasks.py", 60), OSError("no interpreter"),
                    subprocess.CompletedProcess([], 1, stdout="", stderr="Traceback\nImportError: example"))
        for failure in failures:
            effect = {"side_effect": failure} if isinstance(failure, BaseException) else {"return_value": failure}
            with mock.patch.object(sync.subprocess, "run", **effect):
                found = sync.reminders(self.root)
                code, out = self.main()
            self.assertEqual(len(found), 1, failure)
            self.assertTrue(found[0]["line"].startswith("reminder: could not be read ("), found[0]["line"])
            self.assertTrue(found[0]["ok"])
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("reminder: could not be read ("))
        self.assertIn("ImportError: example", found[0]["line"])

    def test_a_store_that_cannot_be_read_is_named(self):
        shutil.rmtree(self.root / "memory/tasks")
        found = sync.reminders(self.root)
        self.assertEqual([r["state"] for r in found], ["could not be read"])
        self.assertTrue(found[0]["line"].startswith("reminder: could not be read (task store not found:"))

    def test_a_failed_read_does_not_turn_a_failing_sync_into_a_passing_one(self):
        with mock.patch.object(sync.subprocess, "run", side_effect=OSError("gone")), \
                mock.patch.object(sync, "repositories", return_value=[("memory", self.base / "nowhere")]), \
                mock.patch.object(sync, "not_joined", return_value=[]), \
                mock.patch.object(sync, "held_by_others", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = sync.main(["--root", str(self.root), "--no-merge"])
        self.assertEqual(code, 1)
        self.assertIn("memory: not a repository", out.getvalue())
        self.assertIn("reminder: could not be read (gone)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
