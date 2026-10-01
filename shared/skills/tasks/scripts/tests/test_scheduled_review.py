"""The scheduled review writes only the ignored /temp/due.md, changes nothing Git tracks, and says
what needs the owner's attention."""
import importlib.util
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
        run = subprocess.run([sys.executable, str(SCRIPT), "--no-notify"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        due = (ROOT / "temp" / "due.md").read_text(encoding="utf-8")
        for heading in ("## Checkout compared with origin", "## Weekly learning digest",
                        "## Tasks due, blocked or waiting", "## Repository preflight"):
            self.assertIn(heading, due)
        self.assertNotIn("�", due, "a child's output was decoded in the wrong code page")
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_digest_is_due_only_once_its_time_has_passed(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / scheduled_review.DIGEST_INDEX
            index.parent.mkdir(parents=True)
            index.write_text("- delivered; the next is due 2026-10-04T16:41:23+10:00. No scheduler.", encoding="utf-8")
            before = datetime.fromisoformat("2026-10-04T16:41:22+10:00")
            after = datetime.fromisoformat("2026-10-04T16:41:23+10:00")
            self.assertIsNone(scheduled_review.digest_due(Path(folder), before))
            self.assertEqual(scheduled_review.digest_due(Path(folder), after), "due since 2026-10-04T16:41:23+10:00")

    def test_missing_digest_index_is_not_due(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(scheduled_review.digest_due(Path(folder), datetime.now().astimezone()))

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
