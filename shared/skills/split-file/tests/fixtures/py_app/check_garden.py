"""Tests of the fixture garden module, split by the split-file tests (named check_* so the skill's
own test run does not collect them)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import garden  # noqa: E402


def make_plant(name: str = "Mint") -> garden.Plant:
    return garden.Plant(name=name)


class NameTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(garden.clean_name(" Sage "), "Sage")

    def test_bad(self):
        with self.assertRaises(ValueError):
            garden.clean_name("R2")


class ReportTests(unittest.TestCase):
    def test_report(self):
        self.assertEqual(garden.report(), ["Basil (herb) every 2 days", "Olive (tree) every 7 days"])

    def test_watering_patched(self):
        with mock.patch.object(garden, "watering_days", return_value=9):
            self.assertIn("every 9 days", garden.report()[0])

    def test_describe(self):
        self.assertEqual(garden.describe(make_plant()), "Mint (herb)")


if __name__ == "__main__":
    unittest.main()
