"""The morning jobs run in order from the brain root after the scheduled review, each logged and
reported in one line; a failure or a timeout is reported and never stops the next job; a missing
or invalid config is no jobs and one line."""
import importlib.util
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import morning_jobs  # noqa: E402

spec = importlib.util.spec_from_file_location("scheduled_review", SCRIPTS / "scheduled_review.py")
scheduled_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduled_review)


def python(code: str) -> list[str]:
    return ["python", "-c", code]


def append_name(name: str) -> list[str]:
    # Written relative to the working directory, so the file proves the job ran from the root.
    return python(f"open('order.txt', 'a').write('{name}\\n'); print('done {name}')")


class MorningJobsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "CONTRACT.md").write_text("", encoding="utf-8")
        self.config = self.root / morning_jobs.CONFIG
        self.config.parent.mkdir(parents=True)

    def tearDown(self):
        self.folder.cleanup()

    def write_config(self, data) -> None:
        self.config.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_jobs_run_in_order_from_the_root_with_a_log_each(self):
        self.write_config({"jobs": [
            {"name": "first-example", "command": append_name("first"), "timeout_s": 60},
            {"name": "second-example", "command": append_name("second"), "timeout_s": 60}]})
        results, problem = morning_jobs.run_jobs(self.root)
        self.assertIsNone(problem)
        self.assertEqual((self.root / "order.txt").read_text(encoding="utf-8"), "first\nsecond\n")
        self.assertEqual([r.name for r in results], ["first-example", "second-example"])
        for result, word in zip(results, ("first", "second")):
            self.assertTrue(result.ran)
            self.assertEqual(result.exit_code, 0)
            self.assertFalse(result.failed)
            self.assertEqual(result.last_line, f"done {word}")
            log = (self.root / morning_jobs.LOG_DIR / f"{result.name}.log").read_text(encoding="utf-8")
            self.assertIn(f"# morning job {result.name}", log)
            self.assertIn(f"done {word}", log)
            self.assertIn("# exit 0 after", log)
        lines = morning_jobs.report_lines(results, None)
        self.assertEqual(lines[-1], f"- second-example: ran, exit 0, {results[1].seconds:.1f} s – done second")
        self.assertEqual(morning_jobs.reasons(results), [])

    def test_a_failing_job_is_reported_with_its_needs_and_the_next_still_runs(self):
        self.write_config({"jobs": [
            {"name": "failing-example", "timeout_s": 60, "needs": "the example service running",
             "command": python("import sys; print('starting'); print('example: cannot connect'); sys.exit(3)")},
            {"name": "after-example", "command": append_name("after"), "timeout_s": 60}]})
        results, _ = morning_jobs.run_jobs(self.root)
        failing, after = results
        self.assertTrue(failing.failed)
        self.assertEqual(failing.exit_code, 3)
        self.assertEqual(failing.line(), f"- failing-example: ran, exit 3, {failing.seconds:.1f} s – "
                                         "example: cannot connect (needs: the example service running)")
        self.assertEqual(after.exit_code, 0, "the next job still ran")
        self.assertEqual((self.root / "order.txt").read_text(encoding="utf-8"), "after\n")
        self.assertEqual(morning_jobs.reasons(results), ["morning job failing-example failed"])
        self.assertEqual([r.name for r in morning_jobs.failures(results)], ["failing-example"])

    def test_a_timed_out_job_is_killed_reported_and_the_next_still_runs(self):
        self.write_config({"jobs": [
            {"name": "slow-example", "timeout_s": 1, "needs": "a faster example",
             "command": python("import time; print('started', flush=True); time.sleep(30); print('never')")},
            {"name": "after-example", "command": append_name("after"), "timeout_s": 60}]})
        results, _ = morning_jobs.run_jobs(self.root)
        slow, after = results
        self.assertTrue(slow.timed_out)
        self.assertTrue(slow.failed)
        self.assertIsNone(slow.exit_code)
        self.assertLess(slow.seconds, 20, "the job was killed at its timeout, not waited for")
        self.assertEqual(slow.line(), f"- slow-example: timed out after {slow.seconds:.0f} s, killed – started "
                                      "(needs: a faster example)")
        self.assertIn("# timed out after 1 s, killed", (self.root / morning_jobs.LOG_DIR / "slow-example.log")
                      .read_text(encoding="utf-8"))
        self.assertEqual(after.exit_code, 0)
        self.assertEqual(morning_jobs.reasons(results), ["morning job slow-example timed out"])

    def test_a_timeout_kills_the_processes_the_job_started_too(self):
        # The child inherits the job's output pipe; only its death lets the output be collected.
        self.write_config({"jobs": [{"name": "nested-example", "timeout_s": 1, "command": python(
            "import subprocess, sys, time; print('parent up', flush=True); "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)")}]})
        clock = time.monotonic()
        (nested,), _ = morning_jobs.run_jobs(self.root)
        self.assertTrue(nested.timed_out)
        self.assertEqual(nested.last_line, "parent up", "the pipe closed, so the child was killed too")
        self.assertLess(time.monotonic() - clock, morning_jobs.COLLECT_AFTER_KILL_S + 5)

    def test_a_job_that_cannot_start_is_reported_and_the_next_still_runs(self):
        self.write_config({"jobs": [
            {"name": "absent-example", "command": ["no-such-program-example", "--flag"], "timeout_s": 60},
            {"name": "after-example", "command": append_name("after"), "timeout_s": 60}]})
        results, _ = morning_jobs.run_jobs(self.root)
        absent, after = results
        self.assertFalse(absent.ran)
        self.assertTrue(absent.failed)
        self.assertTrue(absent.line().startswith("- absent-example: not started – "))
        self.assertEqual(after.exit_code, 0)
        self.assertEqual(morning_jobs.reasons(results), ["morning job absent-example did not start"])

    def test_a_missing_config_is_no_jobs_and_one_line(self):
        results, problem = morning_jobs.run_jobs(self.root)
        self.assertEqual(results, [])
        self.assertEqual(problem, f"no morning jobs: /{morning_jobs.CONFIG} not found")
        self.assertEqual(morning_jobs.report_lines(results, problem), [f"- {problem}"])
        self.assertFalse((self.root / morning_jobs.LOG_DIR).exists())

    def test_an_invalid_config_is_no_jobs_and_one_line_naming_the_fault(self):
        faults = {
            "{not json": "is not valid JSON",
            json.dumps(["list"]): 'must be an object with a "jobs" list',
            json.dumps({"jobs": [{"name": "../escape", "command": ["x"], "timeout_s": 1}]}): '"name" must match',
            json.dumps({"jobs": [{"name": "ok", "command": [], "timeout_s": 1}]}): '"command" must be a non-empty list',
            json.dumps({"jobs": [{"name": "ok", "command": ["x"], "timeout_s": 0}]}): '"timeout_s" must be a whole number',
            json.dumps({"jobs": [{"name": "ok", "command": ["x"], "timeout_s": 1, "needs": 5}]}): '"needs" must be text',
            json.dumps({"jobs": [{"name": "ok", "command": ["x"], "timeout_s": 1}] * 2}): 'job "ok" is listed twice',
            json.dumps({"jobs": []}): "lists none",
        }
        for text, expected in faults.items():
            with self.subTest(expected=expected):
                self.write_config(text)
                results, problem = morning_jobs.run_jobs(self.root)
                self.assertEqual(results, [])
                self.assertEqual(len(problem.splitlines()), 1)
                self.assertTrue(problem.startswith("no morning jobs: "), problem)
                self.assertIn(expected, problem)

    def test_the_review_report_carries_the_job_lines_and_the_notification_names_the_failure(self):
        self.write_config({"jobs": [
            {"name": "page-example", "command": python("print('page written')"), "timeout_s": 60},
            {"name": "broken-example", "timeout_s": 60, "needs": "the example vault unlocked",
             "command": python("import sys; print('locked'); sys.exit(1)")}]})
        report, reasons, failed = scheduled_review.review(self.root, datetime.now().astimezone())
        section = report.split("## Morning jobs")[1]
        self.assertIn("- page-example: ran, exit 0,", section)
        self.assertIn("locked (needs: the example vault unlocked)", section)
        self.assertEqual(reasons[-1], "morning job broken-example failed")
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0].startswith("- broken-example: ran, exit 1,"))
        skipped, _, none_failed = scheduled_review.review(self.root, datetime.now().astimezone(), jobs=False)
        self.assertIn("- skipped (--no-jobs)", skipped.split("## Morning jobs")[1])
        self.assertEqual(none_failed, [])


if __name__ == "__main__":
    unittest.main()
