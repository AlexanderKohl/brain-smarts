"""The scheduled review writes only the ignored /temp/due.md, changes nothing Git tracks, and says
what needs the owner's attention."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "shared/skills/tasks/scripts/scheduled_review.py"
spec = importlib.util.spec_from_file_location("scheduled_review", SCRIPT)
scheduled_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduled_review)


class ScheduledReviewTest(unittest.TestCase):
    def test_writes_due_file_and_leaves_git_clean(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        # --no-jobs: the owner's morning jobs are theirs to run, not a test's (test_morning_jobs.py proves them).
        run = subprocess.run([sys.executable, str(SCRIPT), "--no-notify", "--no-jobs"], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        due = (ROOT / "temp" / "due.md").read_text(encoding="utf-8")
        for heading in ("## Reminders", "## Checkout compared with origin",
                        "## Tasks due, blocked or waiting", "## Repository preflight", "## Morning jobs"):
            self.assertIn(heading, due)
        self.assertLess(due.index("## Reminders"), due.index("## Checkout compared with origin"))
        self.assertNotIn("## Weekly learning digest", due)
        self.assertIn("- skipped (--no-jobs)", due)
        self.assertNotIn("�", due, "a child's output was decoded in the wrong code page")
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    # ------------------------------------------------ reminders (fictional titles)

    def canned(self, reminders_json: str, task_count: int = 2):
        """review() with every child command answered by a canned output, no Git and no jobs."""
        def run(root, *args):
            if args[-2:] == ("reminders", "--json"):
                return reminders_json
            if args[-1] == "review":
                return f"Reminders for the owner (0)\n\n{task_count} task(s) need attention\n0 reminder(s) due"
            return "PASS: preflight" if "preflight" in args[0] else ""
        saved = scheduled_review.run, scheduled_review.freshness
        scheduled_review.run, scheduled_review.freshness = run, lambda root: ["- mechanics: up to date"]
        try:
            with tempfile.TemporaryDirectory() as folder:
                return scheduled_review.review(Path(folder), datetime.fromisoformat("2026-03-10T07:00:00+10:00"),
                                               jobs=False)
        finally:
            scheduled_review.run, scheduled_review.freshness = saved

    @staticmethod
    def reminders(*titles: str, not_read: tuple = ()) -> str:
        rows = [{"id": f"TASK-sam-2026-{n:04d}", "title": t, "next_review": "2026-03-09", "store": "/memory/tasks",
                 "entry": f"- {t} – TASK-sam-2026-{n:04d}, due 2026-03-09, /memory/tasks; when done: "
                          f"python shared/skills/tasks/scripts/tasks.py done TASK-sam-2026-{n:04d}"}
                for n, t in enumerate(titles, 1)]
        return json.dumps({"reminders": rows, "not_read": list(not_read), "lines": []})

    def test_the_report_opens_with_the_reminders_and_the_notification_names_them_first(self):
        report, reasons, _ = self.canned(self.reminders("Water the ferns", "Ring the plumber"))
        lines = report.splitlines()
        start = lines.index("## Reminders")
        self.assertEqual(lines[:start], [lines[0], "", "Written by the scheduled review; read-only, regenerated each run.", ""])
        self.assertTrue(lines[start + 2].startswith("- Water the ferns – TASK-sam-2026-0001, due 2026-03-09"))
        self.assertIn("tasks.py done TASK-sam-2026-0002", lines[start + 3])
        self.assertLess(start, lines.index("## Checkout compared with origin"))
        self.assertEqual(reasons, ["Water the ferns", "Ring the plumber", "2 task(s) need attention"])

    def test_the_notification_names_three_reminders_then_how_many_more(self):
        _, reasons, _ = self.canned(self.reminders("One", "Two", "Three", "Four", "Five"), task_count=0)
        self.assertEqual(reasons, ["One", "Two", "Three", "and 2 more"])

    def test_no_reminder_due_says_none_due(self):
        report, reasons, _ = self.canned(self.reminders())
        self.assertIn("## Reminders\n\n- none due\n", report)
        self.assertEqual(reasons, ["2 task(s) need attention"])

    def test_a_failed_reminder_read_is_named_never_silent(self):
        report, reasons, _ = self.canned(self.reminders("Water the ferns", not_read=["example-app:brain/tasks: offline"]))
        self.assertIn("- reminder: could not be read (example-app:brain/tasks: offline)", report)
        self.assertIn("- Water the ferns – TASK-sam-2026-0001", report)
        report, reasons, _ = self.canned("Traceback (most recent call last):\nOSError: disk gone")
        self.assertIn("## Reminders\n\n- reminder: could not be read (OSError: disk gone)\n", report)
        self.assertEqual(reasons[0], "reminders could not be read")

    def test_the_weekly_digest_phrase_is_no_longer_read(self):
        for name in ("digest_due", "digest_reason", "DIGEST_INDEX", "DIGEST_DUE_PHRASE", "DIGEST_DUE"):
            self.assertFalse(hasattr(scheduled_review, name), name)
        report, _, _ = self.canned(self.reminders())
        self.assertNotIn("learning digest", report)

    SCRIPT = Path("/brain/shared/skills/tasks/scripts/scheduled_review.py")
    PYTHON = Path("/usr/bin/python3")
    HOME = Path(tempfile.gettempdir()) / "owner-home"

    def plan(self, action, system):
        return scheduled_review.plan(action, self.SCRIPT, self.PYTHON, self.HOME, system, uid=501)

    def test_windows_runs_the_script_daily_and_catches_up(self):
        command = " ".join(self.plan("register", "windows").commands[0])
        self.assertIn(str(self.SCRIPT), command)
        self.assertIn(scheduled_review.TASK_NAME, command)
        self.assertIn("-StartWhenAvailable", command)
        self.assertIn(f"-Daily -At {scheduled_review.DAILY_AT}", command)
        # The limit must cover the review and its morning jobs together.
        self.assertIn(f"-ExecutionTimeLimit (New-TimeSpan -Minutes {scheduled_review.EXECUTION_LIMIT_MINUTES})", command)
        self.assertGreaterEqual(scheduled_review.EXECUTION_LIMIT_MINUTES, 30)

    def test_macos_writes_a_valid_launch_agent_in_the_login_session(self):
        import plistlib
        registered = self.plan("register", "macos")
        (agent, text), = registered.write.items()
        self.assertEqual(agent, self.HOME / "Library/LaunchAgents/local.brain.scheduled-review.plist")
        agent_plist = plistlib.loads(text.encode("utf-8"))
        self.assertEqual(agent_plist["ProgramArguments"], [str(self.PYTHON), str(self.SCRIPT)])
        self.assertEqual(agent_plist["StartCalendarInterval"], {"Hour": 7, "Minute": 0})
        self.assertEqual(agent_plist["WorkingDirectory"], str(self.SCRIPT.parents[4]))
        self.assertEqual(registered.commands[-1], ["launchctl", "bootstrap", "gui/501", str(agent)])
        self.assertEqual(self.plan("unregister", "macos").delete, [agent])

    def test_linux_writes_a_persistent_user_timer(self):
        registered = self.plan("register", "linux-systemd")
        units = {path.name: text for path, text in registered.write.items()}
        self.assertIn(f"ExecStart={self.PYTHON} {self.SCRIPT}", units["brain-scheduled-review.service"])
        self.assertIn("OnCalendar=*-*-* 07:00:00", units["brain-scheduled-review.timer"])
        self.assertIn("Persistent=true", units["brain-scheduled-review.timer"])
        self.assertIn(["systemctl", "--user", "enable", "--now", "brain-scheduled-review.timer"], registered.commands)
        self.assertEqual(set(self.plan("unregister", "linux-systemd").delete), set(registered.write))

    def test_cron_replaces_its_own_line_only(self):
        command = self.plan("register", "linux-cron").commands[0][-1]
        self.assertIn("0 7 * * *", command)
        self.assertIn(f"grep -v '# {scheduled_review.TASK_NAME}'", command)
        self.assertNotIn("echo", self.plan("unregister", "linux-cron").commands[0][-1])

    def test_every_system_can_show_and_remove_what_it_registered(self):
        for system in ("windows", "macos", "linux-systemd", "linux-cron"):
            for action in ("status", "unregister"):
                self.assertTrue(self.plan(action, system).commands, (system, action))

    def test_registration_targets_the_owner_checkout_not_a_session_copy(self):
        with tempfile.TemporaryDirectory() as shared, tempfile.TemporaryDirectory() as session:
            (Path(shared) / "CONTRACT.md").write_text("", encoding="utf-8")
            (Path(session) / "memory").mkdir()
            (Path(session) / "memory" / "OWNER.md").write_text(f"---\nbrain_root: {shared}\n---\n", encoding="utf-8")
            self.assertEqual(scheduled_review.owner_brain_root(Path(session)), Path(shared))
            self.assertEqual(scheduled_review.owner_brain_root(Path(shared)), Path(shared))


if __name__ == "__main__":
    unittest.main()
