"""A timestamp ahead of the clock fails the validator (CONTRACT §8.2).

Every fixture is invented. Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight  # noqa: E402
from test_preflight import Brain, md  # noqa: E402

NOW = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone(timedelta(hours=10)))


def stamp(delta: timedelta) -> str:
    return (NOW + delta).isoformat(timespec="seconds")


def future(errors: list[str]) -> list[str]:
    return [e for e in errors if "ahead of the clock" in e]


class AheadOfTheClockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.real_clock = preflight.clock
        preflight.clock = lambda: NOW

    def tearDown(self) -> None:
        preflight.clock = self.real_clock
        self.brain.close()

    def test_an_updated_stamp_ten_minutes_ahead_fails(self) -> None:
        text = md("note-a").replace("updated: 2026-01-01T09:00:00+10:00", "updated: " + stamp(timedelta(minutes=10)))
        self.brain.write("shared/note-a.md", text)
        found = future(self.brain.run().errors)
        self.assertEqual(len(found), 1)
        self.assertIn("/shared/note-a.md: updated", found[0])
        self.assertIn("10 min ahead", found[0])

    def test_two_minutes_ahead_is_within_the_tolerance(self) -> None:
        text = md("note-b").replace("updated: 2026-01-01T09:00:00+10:00", "updated: " + stamp(timedelta(minutes=2)))
        self.brain.write("shared/note-b.md", text)
        self.assertEqual(future(self.brain.run().errors), [])

    def test_a_log_heading_an_hour_ahead_fails_and_a_past_one_passes(self) -> None:
        body = "## " + stamp(-timedelta(days=1)) + "\n\n- Yesterday.\n\n## " + stamp(timedelta(hours=1)) + "\n\n- Too soon.\n"
        self.brain.write("memory/LOG.md", md("memory-log", body, type="log"))
        found = future(self.brain.run().errors)
        self.assertEqual(len(found), 1)
        self.assertIn("/memory/LOG.md: log heading", found[0])
        self.assertIn("1 h 0 min ahead", found[0])

    def test_templates_and_raw_evidence_are_not_checked(self) -> None:
        ahead = stamp(timedelta(days=2))
        self.brain.write("shared/templates/example.md", md("template-example").replace("updated: 2026-01-01T09:00:00+10:00", "updated: " + ahead))
        self.brain.write("memory/raw/2026/01/source-x/LOG.md", "## " + ahead + "\n\nEvidence.\n")
        self.assertEqual(future(self.brain.run().errors), [])


if __name__ == "__main__":
    unittest.main()
