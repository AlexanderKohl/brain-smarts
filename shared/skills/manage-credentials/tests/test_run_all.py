"""run_all.py: every test file in its own process, a failing file rerun once alone, exit code 1 on a failure."""

import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_all  # noqa: E402

PASSING = """
import unittest


class Passing(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)

    def test_two(self):
        self.assertEqual(1 + 1, 2)
"""

FAILING = """
import unittest


class Failing(unittest.TestCase):
    def test_broken(self):
        self.fail("the reason this file fails")
"""

# Fails on its first run and passes on the second: the marker file is written by the first run.
FLAKY = """
import unittest
from pathlib import Path


class Flaky(unittest.TestCase):
    def test_second_time_lucky(self):
        marker = Path(__file__).with_name("ran-once.marker")
        if not marker.exists():
            marker.write_text("x", "utf-8")
            self.fail("first run")
"""


def _run(folder: Path, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = run_all.main(["--folder", str(folder), "--jobs", "2", *extra])
    return code, out.getvalue()


class RunAllTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def _write(self, name: str, body: str) -> None:
        (self.folder / name).write_text(textwrap.dedent(body), "utf-8")

    def test_every_file_passes(self) -> None:
        self._write("test_a.py", PASSING)
        self._write("test_b.py", PASSING)
        code, text = _run(self.folder)
        self.assertEqual(code, 0, text)
        self.assertIn("ok    test_a.py: 2 tests", text)
        self.assertIn("ok    test_b.py: 2 tests", text)
        self.assertIn("Total: 2 files, 4 tests, 0 failed", text)

    def test_a_failing_file_prints_its_output_and_fails_the_run(self) -> None:
        self._write("test_a.py", PASSING)
        self._write("test_bad.py", FAILING)
        code, text = _run(self.folder)
        self.assertEqual(code, 1, text)
        self.assertIn("FAIL  test_bad.py", text)
        self.assertIn("the reason this file fails", text)
        self.assertIn("Total: 2 files, 3 tests, 1 failed: test_bad.py", text)

    def test_a_file_that_passes_alone_counts_as_passed_and_is_named(self) -> None:
        self._write("test_a.py", PASSING)
        self._write("test_flaky.py", FLAKY)
        code, text = _run(self.folder)
        self.assertEqual(code, 0, text)
        self.assertIn("ok    test_flaky.py: 1 tests", text)
        self.assertIn("passed when rerun alone: test_flaky.py", text)

    def test_more_failures_than_the_limit_are_not_rerun(self) -> None:
        self._write("test_flaky.py", FLAKY)
        code, text = _run(self.folder, "--rerun-limit", "0")
        self.assertEqual(code, 1, text)
        self.assertNotIn("passed when rerun alone", text)

    def test_an_empty_folder_fails(self) -> None:
        code, text = _run(self.folder)
        self.assertEqual(code, 1, text)
        self.assertIn("no test files", text)

    def test_a_file_that_runs_no_tests_fails(self) -> None:
        self._write("test_empty.py", "import unittest\n")
        code, text = _run(self.folder)
        self.assertEqual(code, 1, text)
        self.assertIn("FAIL  test_empty.py", text)


if __name__ == "__main__":
    unittest.main()
