"""Behaviour of the filter: what it shortens, what it always keeps, and when it leaves output alone.

Every fixture is invented test-runner, build and diff output (SMART-RULE-0008).
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import filtering  # noqa: E402

RULES = filtering.load_rules()


def failing_pytest(passing: int = 400) -> str:
    lines = ["============================= test session starts =============================",
             "platform win32 -- Python 3.13.0, pytest-8.3.0", "collected 403 items", ""]
    lines += [f"tests/test_module_{i:03d}.py ....                                    [{i % 100:3d}%]"
              for i in range(passing)]
    lines += ["", "=================================== FAILURES ===================================",
              "_______________________________ test_invoice_total _______________________________", "",
              "    def test_invoice_total():", ">       assert total([2, 3]) == 6",
              "E       assert 5 == 6", "", "tests/test_invoice.py:12: AssertionError",
              "=========================== short test summary info ============================",
              "FAILED tests/test_invoice.py::test_invoice_total - assert 5 == 6",
              "======================== 1 failed, 402 passed in 3.21s ========================="]
    return "\n".join(lines) + "\n"


def passing_jest(tests: int = 300) -> str:
    lines = ["PASS src/cart.test.ts"]
    lines += [f"  \u2713 adds item number {i} to the cart (3 ms)" for i in range(tests)]
    lines += ["", "Test Suites: 12 passed, 12 total", f"Tests:       {tests} passed, {tests} total",
              "Snapshots:   0 total", "Time:        4.2 s", "Ran all test suites."]
    return "\n".join(lines) + "\n"


def long_diff(files: int = 12, hunk: int = 40) -> str:
    lines = []
    for f in range(files):
        lines += [f"diff --git a/src/file_{f}.py b/src/file_{f}.py", "index 1a2b3c4..5d6e7f8 100644",
                  f"--- a/src/file_{f}.py", f"+++ b/src/file_{f}.py", f"@@ -1,{hunk} +1,{hunk} @@"]
        for i in range(hunk):
            lines.append(f" unchanged line {i} in file {f}")
        lines += [f"-old_value_{f} = 1", f"+new_value_{f} = 2"]
    return "\n".join(lines) + "\n"


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "temp" / "command-output"
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop(filtering.SWITCH, None)
        os.environ.pop(filtering.FOLDER, None)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def shrink(self, command, text, code, **kw):
        return filtering.shrink(command, text, code, root=self.root, rules=RULES, **kw)

    def saved_path(self, short: str) -> Path:
        return Path(short.rsplit("Full output: ", 1)[1].rstrip("]\n"))


class LeavesAlone(Folder):
    def test_short_output_is_unchanged(self):
        self.assertIsNone(self.shrink("npm test", "PASS\nTests: 3 passed\n", 0))

    def test_unrecognised_command_is_unchanged(self):
        self.assertIsNone(self.shrink("python make_report.py", failing_pytest(), 1))

    def test_command_that_narrows_its_own_output_is_unchanged(self):
        self.assertIsNone(self.shrink("pytest -q | tail -40", failing_pytest(), 1))
        self.assertIsNone(self.shrink("npm test 2>&1 | Select-String FAIL", passing_jest(), 0))

    def test_switched_off_is_unchanged(self):
        with mock.patch.dict(os.environ, {filtering.SWITCH: "off"}):
            self.assertIsNone(self.shrink("pytest", failing_pytest(), 1))

    def test_no_saving_worth_having_is_unchanged(self):
        varied = "\n".join(f"error {i}: something distinct happened here" for i in range(120)) + "\n"
        self.assertIsNone(self.shrink("npm run build", varied, 1))

    def test_output_that_cannot_be_saved_is_unchanged(self):
        blocked = self.root / "temp"
        blocked.write_text("a file where the folder would go", encoding="utf-8")
        self.assertIsNone(self.shrink("pytest", failing_pytest(), 1))

    def test_nothing_is_written_when_unchanged(self):
        self.shrink("npm test", "PASS\n", 0)
        self.assertFalse(self.folder.exists())


class Recognises(unittest.TestCase):
    def family(self, command, explicit=False):
        found = filtering.family_for(command, RULES, explicit)
        return found.name if found else None

    def test_families(self):
        cases = {
            "pytest -q": "test",
            "python -m pytest tests": "test",
            ".venv\\Scripts\\python.exe -m pytest": "test",
            "python -m unittest discover -s tests": "test",
            "cd /c/dev/example && npm test 2>&1": "test",
            "& npm run test:unit": "test",
            "CI=1 npx vitest run": "test",
            "go test ./...": "test",
            "npm run build": "build",
            "npx tsc --noEmit": "build",
            "npm ci": "install",
            "pip install -r requirements.txt": "install",
            "git diff HEAD~1": "git-diff",
            "git -C ../repo --no-pager show abc123": "git-diff",
            "git log --stat": "git-log",
            "docker compose up --build": "docker",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(self.family(command), expected)

    def test_not_recognised(self):
        for command in ["git status", "ls -la", "cat build.log", "python script.py", "Get-ChildItem"]:
            with self.subTest(command=command):
                self.assertIsNone(self.family(command))

    def test_wrapper_asks_for_the_generic_filter(self):
        self.assertEqual(self.family("python script.py", explicit=True), "generic")

    def test_wrapper_itself_is_never_filtered_twice(self):
        command = "python shared/skills/command-output/scripts/run.py -- npm test"
        self.assertIsNone(self.family(command))


class Keeps(Folder):
    def test_failing_tests_keep_every_failure_and_the_exit_code(self):
        text = failing_pytest()
        short = self.shrink("pytest", text, 1)
        self.assertIsNotNone(short)
        for needed in ["E       assert 5 == 6", "tests/test_invoice.py:12: AssertionError",
                       "FAILED tests/test_invoice.py::test_invoice_total - assert 5 == 6",
                       "1 failed, 402 passed", "=== FAILURES ==="]:
            self.assertIn(needed, short)
        self.assertIn("exit code 1", short.splitlines()[-1])
        self.assertLess(len(short), len(text) / 4)

    def test_the_full_output_is_saved_and_named(self):
        text = failing_pytest()
        short = self.shrink("pytest", text, 1, cwd="C:/work/example")
        saved = self.saved_path(short).read_text(encoding="utf-8")
        self.assertIn("command: pytest", saved)
        self.assertIn("exit code: 1", saved)
        self.assertTrue(saved.endswith(text))

    def test_passing_tests_drop_the_ticks_and_keep_the_summary(self):
        short = self.shrink("npx jest", passing_jest(), 0)
        self.assertNotIn("\u2713 adds item number 150", short)
        self.assertIn("Tests:       300 passed, 300 total", short)
        self.assertIn("Test Suites: 12 passed, 12 total", short)

    def test_a_long_diff_keeps_every_file_and_hunk_header_and_every_change(self):
        short = self.shrink("git diff", long_diff(), 0)
        for f in range(12):
            self.assertIn(f"diff --git a/src/file_{f}.py b/src/file_{f}.py", short)
            self.assertIn(f"+new_value_{f} = 2", short)
        self.assertNotIn("index 1a2b3c4..5d6e7f8", short)
        self.assertNotIn("unchanged line 5 in file 3", short)

    def test_error_words_in_a_git_log_are_content_not_failures(self):
        lines = []
        for i in range(200):
            lines += [f"commit {i:040x}", "Author: Example Tester <tester@localhost>", "",
                      f"    Fix failing test number {i}", ""]
        short = self.shrink("git log", "\n".join(lines) + "\n", 0)
        self.assertIn(f"commit {0:040x}", short)
        self.assertNotIn("error lines", short)
        self.assertNotIn("Fix failing test number 100", short)

    def test_an_unknown_exit_code_is_left_out_of_the_footer(self):
        short = self.shrink("pytest", failing_pytest(), None)
        self.assertNotIn("exit code", short.splitlines()[-1])
        self.assertIn("Full output: ", short.splitlines()[-1])

    def test_errors_beyond_the_budget_are_counted_not_lost_silently(self):
        lines = ["build started"] + [f"src/part_{i}.ts(4,2): error TS2322: Type mismatch {i}" for i in range(300)]
        lines += ["Found 300 errors."]
        short = self.shrink("npx tsc", "\n".join(lines) + "\n", 2)
        self.assertIsNotNone(short)
        self.assertIn("more error lines not shown", short)
        self.assertIn("Found 300 errors.", short)

    def test_statistics_hold_sizes_never_the_command_or_output(self):
        self.shrink("pytest --secret-flag", failing_pytest(), 1)
        entry = json.loads((self.folder / "stats.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["family"], "test")
        self.assertEqual(entry["exit_code"], 1)
        self.assertNotIn("secret", json.dumps(entry))

    def test_saved_outputs_older_than_a_week_are_removed(self):
        self.folder.mkdir(parents=True)
        old = self.folder / "20200101-000000-aaaaaa.log"
        old.write_text("old", encoding="utf-8")
        week_ago = time.time() - 8 * 86400
        os.utime(old, (week_ago, week_ago))
        self.shrink("pytest", failing_pytest(), 1)
        self.assertFalse(old.exists())


class Cleans(unittest.TestCase):
    def test_repeats_collapse_to_one_marker(self):
        self.assertEqual(filtering.collapse(["a", "a", "a", "a", "b"]),
                         ["a", "[... the line above repeats 3 more times]", "b"])

    def test_two_repeats_stay_as_they_are(self):
        self.assertEqual(filtering.collapse(["a", "a", "b"]), ["a", "a", "b"])

    def test_blank_runs_become_one_blank(self):
        self.assertEqual(filtering.collapse(["a", "", "", "", "b"]), ["a", "", "b"])

    def test_colour_codes_and_progress_redraws_are_removed(self):
        self.assertEqual(filtering.clean_lines("\x1b[31mred\x1b[0m\n10%\r50%\r100%"), ["red", "100%"])

    def test_windows_line_endings_keep_their_text(self):
        self.assertEqual(filtering.clean_lines("first\r\nsecond\r\n"), ["first", "second", ""])


class WindowsOutput(Folder):
    def test_failing_tests_with_windows_line_endings_keep_every_failure(self):
        short = self.shrink("pytest", failing_pytest().replace("\n", "\r\n"), 1)
        self.assertIn("E       assert 5 == 6", short)
        self.assertIn("1 failed, 402 passed", short)


if __name__ == "__main__":
    unittest.main()
