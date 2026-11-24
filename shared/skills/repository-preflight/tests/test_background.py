"""Background jobs (background.py) and `session.py finish --background`, with real processes.

Every job here is a real process of its own, started the way a session starts one, in throwaway
folders and throwaway repositories with local bare remotes (SMART-RULE-0022, *Run it for real*).
What the tests prove: the command returns before the work is done; the work then finishes on its
own and reaches `origin`; a failure is reported once with the end of its output; a job that is
running, or whose process is gone, is told apart from one that ended; a commit beside a running
finish is refused. What they do not prove: that a host passes the report to the model, and that a
job outlives the host's own shell on every host (run for real on Windows, 24 November 2026).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import background  # noqa: E402
import hooks  # noqa: E402
import test_session  # noqa: E402  (the module, not its test class: a class named here would run twice)
from test_session import cli, commit_all, write  # noqa: E402

WAIT_SECONDS = 180


def wait_for_end(root: Path, kind: str, name: str) -> dict:
    """The job's record once it no longer runs; fails the test when it runs past the limit."""
    path = background.record_path(root, kind, name)
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        record = background.read(path)
        if record is not None and background.state(record) != "running":
            return record
        time.sleep(0.2)
    raise AssertionError(f"{kind} of {name} still running after {WAIT_SECONDS} s")


def end_with_children(pid: int) -> None:
    """End a job's process and the command it runs, as a crash or a restart of the computer would."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(pid, signal.SIGKILL)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="background-")
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def job(self, name: str, code: str) -> Path:
        return background.start(self.root, "job", name, [sys.executable, "-c", code], self.root)

    def test_a_job_that_ends_well_says_nothing_and_leaves_no_record(self):
        path = self.job("fine", "print('all merged')")
        record = wait_for_end(self.root, "job", "fine")
        self.assertEqual((record["state"], record["exit"]), ("done", 0))
        self.assertIn("all merged", Path(record["log"]).read_text(encoding="utf-8"))
        self.assertEqual(background.report(self.root), "")
        self.assertFalse(path.exists())

    def test_a_failed_job_is_reported_once_with_the_end_of_its_output(self):
        path = self.job("broken", "import sys; print('push refused: origin moved on'); sys.exit(3)")
        wait_for_end(self.root, "job", "broken")
        told = background.report(self.root)
        self.assertIn("JOB OF `BROKEN` FAILED", told)
        self.assertIn("exit code 3", told)
        self.assertIn("push refused: origin moved on", told)
        self.assertIn("Tell the owner", told)
        self.assertEqual(background.report(self.root), "")          # once, not at every prompt
        self.assertTrue(path.exists())                               # kept for `list`
        self.assertIn("failed", background.listing(self.root))

    def test_a_running_job_is_named_and_cannot_be_started_twice(self):
        self.job("slow", "import time; time.sleep(60)")
        deadline = time.monotonic() + 30
        while background.read(background.record_path(self.root, "job", "slow")).get("pid") is None:
            self.assertLess(time.monotonic(), deadline, "the job never wrote its process id")
            time.sleep(0.1)
        self.assertTrue(background.running(self.root, "job", "slow"))
        self.assertIn("still running", background.report(self.root))
        with self.assertRaises(RuntimeError):
            self.job("slow", "print('second')")
        # Its process disappears without writing a result: that is a failure, told as one.
        end_with_children(background.read(background.record_path(self.root, "job", "slow"))["pid"])
        wait_for_end(self.root, "job", "slow")
        self.assertIn("stopped without a result", background.report(self.root))

    def test_the_job_and_its_children_carry_the_job_variable(self):
        self.job("env", f"import os; print(os.environ.get('{background.JOB_ENV}'))")
        record = wait_for_end(self.root, "job", "env")
        self.assertIn("job-env.json", Path(record["log"]).read_text(encoding="utf-8"))

    def test_a_record_without_a_live_process_is_not_believed(self):
        path = background.record_path(self.root, "job", "ghost")
        background.write(path, {"kind": "job", "name": "ghost", "state": "running", "started": background.now(),
                                "pid": 2 ** 22 + 12345, "command": ["x"], "log": str(path.with_suffix(".log"))})
        self.assertFalse(background.running(self.root, "job", "ghost"))
        self.assertIn("stopped without a result", background.report(self.root))

    def test_a_name_that_could_leave_the_folder_is_refused(self):
        with self.assertRaises(ValueError):
            background.record_path(self.root, "job", "../outside")


class BackgroundFinishTests(unittest.TestCase):
    """`finish --background` on a throwaway brain with local bare remotes (test_session's own)."""

    setUp = test_session.SessionTests.setUp
    tearDown = test_session.SessionTests.tearDown
    start = test_session.SessionTests.start
    on_origin = test_session.SessionTests.on_origin

    def background_finish(self, name: str) -> tuple[int, str]:
        return cli("--root", str(self.shared), "finish", name, "--sessions", str(self.sessions),
                   "--background", "--keep")

    def test_the_command_returns_at_once_and_the_work_reaches_origin_on_its_own(self):
        copy = self.start("later")
        write(copy / "memory" / "later.md", "committed before the reply\n")
        commit_all(copy / "memory", "work of the turn")
        code, out = self.background_finish("later")
        self.assertEqual(code, 0, out)
        self.assertIn("started in the background", out)
        record = wait_for_end(self.shared, "finish", "later")
        self.assertEqual(record["state"], "done", Path(record["log"]).read_text(encoding="utf-8"))
        self.assertEqual(self.on_origin("memory", "later.md").strip(), "committed before the reply")
        self.assertEqual((self.shared / "memory" / "later.md").read_text(encoding="utf-8"),
                         "committed before the reply\n")                 # the shared checkout follows
        self.assertEqual(background.report(self.shared), "")

    def test_uncommitted_work_is_refused_at_once_and_nothing_starts(self):
        copy = self.start("dirty")
        write(copy / "memory" / "half.md", "not committed\n")
        code, out = self.background_finish("dirty")
        self.assertEqual(code, 1, out)
        self.assertIn("uncommitted changes", out)
        self.assertFalse(background.record_path(self.shared, "finish", "dirty").exists())

    def test_a_commit_beside_a_running_finish_is_refused_and_the_finish_s_own_commit_passes(self):
        copy = self.start("busy")
        path = background.record_path(self.shared, "finish", "busy")
        background.write(path, {"kind": "finish", "name": "busy", "state": "running", "started": background.now(),
                                "pid": os.getpid(), "command": ["x"], "log": str(path.with_suffix(".log"))})
        for repo in (copy, copy / "memory", copy / "library"):
            self.assertIn("still running in the background", hooks.finish_running(repo) or "", repo)
        with mock.patch.dict(os.environ, {background.JOB_ENV: str(path)}):
            self.assertIsNone(hooks.finish_running(copy / "memory"))
        self.assertIsNone(hooks.finish_running(self.shared / "memory"))  # not a session copy
        path.unlink()
        self.assertIsNone(hooks.finish_running(copy / "memory"))         # no finish running


if __name__ == "__main__":
    unittest.main()
