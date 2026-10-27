"""Team, claimed_by and claimed_at on task records: `new --team`, `claim`, `release`, `check`.

Run from the brain root:
    python -m unittest discover -s shared/skills/tasks/scripts/tests -v

All task content below is fictional.
"""

from __future__ import annotations

import unittest

from brainfix import LATER, NOW, SCRIPTS, Brain, record
from test_tasks import run

import task_claims  # noqa: E402
import task_state  # noqa: E402
import task_stores  # noqa: E402
import tasks  # noqa: E402


class TaskClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.root, self.store = self.brain.root, self.brain.store
        self.brain.add("open", "TASK-2026-0001-fence", record("TASK-2026-0001", "Paint the fence", "ready", team="alpha"))
        self.brain.add("open", "TASK-2026-0002-gate", record("TASK-2026-0002", "Fix the gate", "ready"))
        self.brain.add("inbox", "TASK-2026-0003-idea", record("TASK-2026-0003", "Think about a pond", "inbox"))
        task_state.write(task_stores.owner_store(self.root))

    def tearDown(self) -> None:
        self.brain.close()

    def record(self, folder: str, stem: str) -> str:
        return (self.store / folder / f"{stem}.md").read_text(encoding="utf-8")

    def meta(self, folder: str, stem: str) -> dict:
        return tasks.parse_front_matter(self.record(folder, stem))

    def state(self) -> str:
        return (self.store / "STATE.md").read_text(encoding="utf-8")

    def test_the_schema_carries_the_claim_and_store_fields(self) -> None:
        text = (SCRIPTS.parents[2] / "schemas" / "task-schema.md").read_text(encoding="utf-8")
        for line in ("team: null", "claimed_by: null", "claimed_at: null", "author: brain-owner", "schedule: null",
                     "related_tasks: []"):
            self.assertIn(line, text)
        self.assertIn("set together when the card enters `in_progress`", text)

    def test_new_takes_a_team_and_check_accepts_it(self) -> None:
        code, out = run("new", "--title", "Dig the pond", "--status", "ready", "--team", "beta",
                        "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        meta = self.meta("open", "TASK-sam-2026-0004-dig-the-pond")
        self.assertEqual((meta["team"], meta["claimed_by"], meta["claimed_at"]), ("beta", None, None))
        self.assertEqual(run("check", cwd=self.root), (0, "PASS: 0 error(s), 0 warning(s)\n"))
        code, out = run("new", "--title", "Bad label", "--team", "Team Alpha!", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("not a short lowercase label", out)

    def test_claim_sets_status_holder_and_time_together(self) -> None:
        code, out = run("claim", "TASK-2026-0002", "--by", "Session Blue", "--team", "blue", "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("claimed TASK-2026-0002 by Session Blue", out)
        meta = self.meta("open", "TASK-2026-0002-gate")
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["team"], meta["updated"]),
                         ("in_progress", "Session Blue", NOW, "blue", NOW))
        self.assertIn(f"- {NOW} – sam: claimed by Session Blue for team blue (in_progress)",
                      self.record("open", "TASK-2026-0002-gate"))
        self.assertIn("| `TASK-2026-0002` | **in_progress** | normal |", self.state())
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_claim_keeps_the_card_s_own_team_and_moves_an_inbox_card_to_open(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0001", "Session A", now=NOW)
        self.assertEqual(self.meta("open", "TASK-2026-0001-fence")["team"], "alpha")
        task_claims.claim(self.store, "TASK-2026-0003", "Session A", now=NOW)
        self.assertTrue((self.store / "open" / "TASK-2026-0003-idea.md").is_file())
        self.assertFalse((self.store / "inbox" / "TASK-2026-0003-idea.md").exists())
        self.assertIn("| `TASK-2026-0003` | **in_progress** |", self.state())

    def test_claim_refuses_a_card_another_session_holds_and_names_the_holder(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=NOW)
        with self.assertRaises(ValueError) as held:
            task_claims.claim(self.store, "TASK-2026-0002", "Session Green", now=LATER)
        self.assertIn("held by Session Blue since " + NOW, str(held.exception))
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=LATER)
        self.assertEqual(self.meta("open", "TASK-2026-0002-gate")["claimed_at"], LATER)
        with self.assertRaises(ValueError):
            task_claims.claim(self.store, "TASK-2026-0002", "  ", now=NOW)

    def test_release_clears_the_claim_and_sets_ready(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=NOW)
        code, out = run("release", "TASK-2026-0002", "--note", "Handing it back.", "--now", LATER, "--no-board",
                        cwd=self.root)
        self.assertEqual(code, 0, out)
        text = self.record("open", "TASK-2026-0002-gate")
        meta = tasks.parse_front_matter(text)
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["updated"]),
                         ("ready", None, None, LATER))
        self.assertIn(f"- {LATER} – sam: released by Session Blue (ready)\n  Note: Handing it back.", text)
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_done_clears_a_claim_with_the_card(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0001", "Session A", now=NOW)
        tasks.complete(self.store, "TASK-2026-0001", now=LATER)
        meta = self.meta("completed", "TASK-2026-0001-fence")
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["team"]),
                         ("completed", None, None, "alpha"))
        with self.assertRaises(ValueError):
            task_claims.claim(self.store, "TASK-2026-0001", "Session A", now=NOW)

    def test_check_warns_about_a_claim_that_does_not_fit_the_status(self) -> None:
        self.brain.add("open", "TASK-2026-0005-odd", record("TASK-2026-0005", "Odd one", "ready",
                                                            claimed_by="Session X", claimed_at=NOW))
        task_state.write(task_stores.owner_store(self.root))
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: /memory/tasks/open/TASK-2026-0005-odd.md: claimed_by Session X on a card that is ready", out)


if __name__ == "__main__":
    unittest.main()
