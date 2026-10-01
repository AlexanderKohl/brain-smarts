"""Team, claimed_by and claimed_at on task records: `new --team`, `claim`, `release`, `check`.

Run from the brain root:
    python -m unittest discover -s shared/skills/tasks/scripts/tests -v

All task content below is fictional.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import task_claims  # noqa: E402
import tasks  # noqa: E402
from test_tasks import run, task  # noqa: E402

NOW = "2026-03-10T09:00:00+10:00"
LATER = "2026-03-10T10:30:00+10:00"
STATE = ("# State\n\n## Open tasks (2, ordered)\n\n| Task | Status | Priority | Review / waiting on | Title |\n"
         "|---|---|---|---|---|\n"
         "| `TASK-2026-0001` | **ready** | normal | - | Paint the fence |\n"
         "| `TASK-2026-0002` | **ready** | normal | - | Fix the gate |\n")
TEMPLATE = ("---\nid: template\ntitle: x\ntype: task\nschema_version: 0.2\ncontract: /CONTRACT.md\nstatus: inbox\n"
            "owner: OWNER_SHORT_NAME\npriority: normal\ncreated: x\nupdated: x\ndue: null\nnext_review: null\n"
            "waiting_on: null\nproject_refs: []\nskill_refs: []\ndepends_on: []\nteam: null\nclaimed_by: null\n"
            "claimed_at: null\n---\n\n# x\n\n## Outcome\n\n## History\n")


class TaskClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-claims-"))
        (self.root / "CONTRACT.md").write_text("---\nid: contract\n---\n", encoding="utf-8")
        self.store = self.root / "memory" / "tasks"
        for folder in ("inbox", "open", "completed", "templates"):
            (self.store / folder).mkdir(parents=True)
        (self.store / "templates" / "TASK_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
        (self.store / "STATE.md").write_text(STATE, encoding="utf-8")
        self.add("open", "TASK-2026-0001-fence", task("TASK-2026-0001", "Paint the fence", "ready", team="alpha"))
        self.add("open", "TASK-2026-0002-gate", task("TASK-2026-0002", "Fix the gate", "ready"))
        self.add("inbox", "TASK-2026-0003-idea", task("TASK-2026-0003", "Think about a pond", "inbox"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def add(self, folder: str, stem: str, text: str) -> None:
        (self.store / folder / f"{stem}.md").write_text(text, encoding="utf-8")

    def meta(self, folder: str, stem: str) -> dict:
        return tasks.parse_front_matter(self.record(folder, stem))

    def record(self, folder: str, stem: str) -> str:
        return (self.store / folder / f"{stem}.md").read_text(encoding="utf-8")

    def state(self) -> str:
        return (self.store / "STATE.md").read_text(encoding="utf-8")

    # ------------------------------------------------ the schema fields on new records

    def test_the_schema_and_template_carry_the_three_fields(self) -> None:
        brain = SCRIPTS.parents[3]
        for rel in ("shared/schemas/task-schema.md", "shared/templates/memory-skeleton/tasks/templates/TASK_TEMPLATE.md"):
            text = (brain / rel).read_text(encoding="utf-8")
            for line in ("team: null", "claimed_by: null", "claimed_at: null"):
                self.assertIn(line, text, rel)
        self.assertIn("set together when the card enters `in_progress`", (brain / "shared/schemas/task-schema.md").read_text(encoding="utf-8"))

    def test_new_takes_a_team_and_check_accepts_it(self) -> None:
        code, out = run("new", "--title", "Dig the pond", "--status", "ready", "--team", "beta",
                        "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        meta = self.meta("open", "TASK-2026-0004-dig-the-pond")
        self.assertEqual((meta["team"], meta["claimed_by"], meta["claimed_at"]), ("beta", None, None))
        self.assertEqual(run("check", cwd=self.root), (0, "PASS: 0 error(s), 0 warning(s)\n"))
        code, out = run("new", "--title", "Bad label", "--team", "Team Alpha!", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("not a short lowercase label", out)

    def test_new_without_a_team_leaves_the_template_null(self) -> None:
        tasks.create(self.store, "Trim the hedge", status="ready", now=NOW)
        self.assertIn("\nteam: null\n", self.record("open", "TASK-2026-0004-trim-the-hedge"))

    # ------------------------------------------------ claim

    def test_claim_sets_status_holder_and_time_together(self) -> None:
        code, out = run("claim", "TASK-2026-0002", "--by", "Session Blue", "--team", "blue", "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("claimed TASK-2026-0002 by Session Blue", out)
        meta = self.meta("open", "TASK-2026-0002-gate")
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["team"], meta["updated"]),
                         ("in_progress", "Session Blue", NOW, "blue", NOW))
        self.assertIn(f"- {NOW} – Claimed by Session Blue for team blue (in_progress).", self.record("open", "TASK-2026-0002-gate"))
        self.assertIn("| `TASK-2026-0002` | **in_progress** | normal |", self.state())
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    def test_claim_keeps_the_card_s_own_team_and_moves_an_inbox_card_to_open(self) -> None:
        tasks_path, said = task_claims.claim(self.store, "TASK-2026-0001", "Session A", now=NOW)
        self.assertEqual(self.meta("open", "TASK-2026-0001-fence")["team"], "alpha")
        self.assertIn("Claimed by Session A for team alpha (in_progress).", self.record("open", "TASK-2026-0001-fence"))
        task_claims.claim(self.store, "TASK-2026-0003", "Session A", now=NOW)
        self.assertTrue((self.store / "open" / "TASK-2026-0003-idea.md").is_file())
        self.assertFalse((self.store / "inbox" / "TASK-2026-0003-idea.md").exists())
        self.assertIn("| `TASK-2026-0003` | **in_progress** |", self.state())

    def test_claim_refuses_a_card_another_session_holds_and_names_the_holder(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=NOW)
        with self.assertRaises(ValueError) as held:
            task_claims.claim(self.store, "TASK-2026-0002", "Session Green", now=LATER)
        self.assertIn("held by Session Blue since " + NOW, str(held.exception))
        code, out = run("claim", "TASK-2026-0002", "--by", "Session Green", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("held by Session Blue", out)
        meta = self.meta("open", "TASK-2026-0002-gate")
        self.assertEqual((meta["claimed_by"], meta["claimed_at"]), ("Session Blue", NOW))
        # The same session claiming again only renews the time.
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=LATER)
        self.assertEqual(self.meta("open", "TASK-2026-0002-gate")["claimed_at"], LATER)

    def test_claim_needs_a_session_name_and_refuses_a_completed_card(self) -> None:
        with self.assertRaises(ValueError):
            task_claims.claim(self.store, "TASK-2026-0002", "  ", now=NOW)
        self.add("completed", "TASK-2026-0009-gone", task("TASK-2026-0009", "Gone", "completed"))
        with self.assertRaises(ValueError):
            task_claims.claim(self.store, "TASK-2026-0009", "Session A", now=NOW)

    # ------------------------------------------------ release

    def test_release_clears_the_claim_and_sets_ready(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0002", "Session Blue", now=NOW)
        code, out = run("release", "TASK-2026-0002", "--note", "Handing it back.", "--now", LATER, "--no-board",
                        cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("released TASK-2026-0002", out)
        text = self.record("open", "TASK-2026-0002-gate")
        meta = tasks.parse_front_matter(text)
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["updated"]),
                         ("ready", None, None, LATER))
        self.assertIn("\nclaimed_by: null\nclaimed_at: null\n", text)
        self.assertIn(f"- {LATER} – Released by Session Blue (ready).\n  The owner's note: Handing it back.", text)
        self.assertIn("| `TASK-2026-0002` | **ready** |", self.state())
        self.assertEqual(run("check", cwd=self.root)[0], 0)
        # After a release anyone may claim it.
        task_claims.claim(self.store, "TASK-2026-0002", "Session Green", now=LATER)
        self.assertEqual(self.meta("open", "TASK-2026-0002-gate")["claimed_by"], "Session Green")

    def test_done_clears_a_claim_with_the_card(self) -> None:
        task_claims.claim(self.store, "TASK-2026-0001", "Session A", now=NOW)
        tasks.complete(self.store, "TASK-2026-0001", now=LATER)
        meta = self.meta("completed", "TASK-2026-0001-fence")
        self.assertEqual((meta["status"], meta["claimed_by"], meta["claimed_at"], meta["team"]),
                         ("completed", None, None, "alpha"))
        self.assertEqual(run("check", cwd=self.root)[0], 0)

    # ------------------------------------------------ check

    def test_check_warns_about_a_claim_that_does_not_fit_the_status(self) -> None:
        self.add("open", "TASK-2026-0005-odd", task("TASK-2026-0005", "Odd one", "ready", claimed_by="Session X",
                                                    claimed_at=NOW))
        self.add("open", "TASK-2026-0006-when", task("TASK-2026-0006", "No time", "in_progress", claimed_by="Session Y"))
        report = tasks.check(self.store)
        self.assertEqual(report.errors, [])
        self.assertIn("open/TASK-2026-0005-odd.md: claimed_by Session X on a card that is ready, not in_progress",
                      report.warnings)
        self.assertIn("open/TASK-2026-0006-when.md: claimed_by Session Y without claimed_at", report.warnings)
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0)
        self.assertIn("WARN: open/TASK-2026-0006-when.md: claimed_by Session Y without claimed_at", out)


if __name__ == "__main__":
    unittest.main()
