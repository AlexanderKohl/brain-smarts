"""Behavioural tests for `new-run --plan`: up to eight workers under an approved plan (SMART-RULE-0024).

Run from the repository root:
    python -m unittest discover -s shared/skills/delegate-work/scripts/tests -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import delegation  # noqa: E402
from test_delegation import NOW, run_cli  # noqa: E402

PLAN_REF = "/temp/plans/fictional-build-plan.md"


class PlanBudgetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-plan-budget-"))
        (self.root / "CONTRACT.md").write_text("---\nid: x\n---\n# contract\n", encoding="utf-8")
        templates = self.root / "shared" / "skills" / "delegate-work" / "templates"
        templates.mkdir(parents=True)
        for name in ("run.template.md", "packet.template.md", "result.template.md"):
            shutil.copy(SKILL / "templates" / name, templates / name)
        plan = self.root / PLAN_REF.lstrip("/")
        plan.parent.mkdir(parents=True)
        plan.write_text("---\nid: fictional-plan\n---\n# A fictional build plan\n", encoding="utf-8")
        self.common = ["--root", str(self.root), "--now", NOW]

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def new_run(self, *extra: str) -> tuple[int, str]:
        return run_cli(*self.common, "new-run", "--context-tokens", "1000", "--title", "Plan run",
                       "--why-parallel", "eight disjoint packets from one plan", "--run-id", "RUN-PLAN", *extra)

    def new_packet(self) -> tuple[int, str]:
        return run_cli(*self.common, "new-packet", "--context-tokens", "1000", "--run", "RUN-PLAN",
                       "--title", "Build one part", "--objective", "Build the part the plan names.")

    def run_meta(self) -> dict:
        meta, _ = delegation.load(self.root / "temp/delegation/runs/RUN-PLAN/RUN.md")
        return meta

    def test_plan_allows_eight_packets_and_refuses_the_ninth(self) -> None:
        code, out = self.new_run("--plan", PLAN_REF, "--max-workers", "8")
        self.assertEqual(code, 0, out)
        for _ in range(8):
            code, out = self.new_packet()
            self.assertEqual(code, 0, out)
        code, out = self.new_packet()
        self.assertNotEqual(code, 0)
        self.assertIn("budget is 8", out)

    def test_plan_with_more_than_eight_is_refused_naming_the_rule_and_the_trial(self) -> None:
        code, out = self.new_run("--plan", PLAN_REF, "--max-workers", "9")
        self.assertNotEqual(code, 0)
        self.assertIn("SMART-RULE-0024", out)
        self.assertIn("--trial-workers", out)

    def test_absolute_plan_path_is_recorded_as_repository_root_path(self) -> None:
        absolute = str(self.root / PLAN_REF.lstrip("/"))
        code, out = self.new_run("--plan", absolute, "--max-workers", "6")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["plan"], PLAN_REF)

    def test_without_plan_the_fifth_packet_is_refused(self) -> None:
        code, out = self.new_run()
        self.assertEqual(code, 0, out)
        for _ in range(4):
            self.assertEqual(self.new_packet()[0], 0)
        code, out = self.new_packet()
        self.assertNotEqual(code, 0)
        self.assertIn("budget is 4", out)
        self.assertNotIn("plan", self.run_meta())

    def test_without_plan_more_than_four_is_refused(self) -> None:
        code, out = self.new_run("--max-workers", "5")
        self.assertNotEqual(code, 0)
        self.assertIn("max workers is 4", out)

    def test_missing_plan_file_is_refused(self) -> None:
        code, out = self.new_run("--plan", "/temp/plans/no-such-plan.md", "--max-workers", "6")
        self.assertNotEqual(code, 0)
        self.assertIn("error: --plan names no file: /temp/plans/no-such-plan.md", out)
        self.assertFalse((self.root / "temp/delegation/runs/RUN-PLAN").exists())

    def test_plan_with_trial_is_refused(self) -> None:
        code, out = self.new_run("--plan", PLAN_REF, "--trial-workers", "6", "--trial-reason", "measured")
        self.assertNotEqual(code, 0)
        self.assertIn("--plan and --trial-workers cannot be combined", out)

    def test_plan_is_recorded_on_the_run_and_printed_by_summarise_and_close_run(self) -> None:
        code, out = self.new_run("--plan", PLAN_REF, "--max-workers", "6")
        self.assertEqual(code, 0, out)
        meta = self.run_meta()
        self.assertEqual(meta["plan"], PLAN_REF)
        self.assertEqual(meta["max_workers"], "6")
        self.assertNotIn("trial", meta)
        code, out = run_cli(*self.common, "summarise", "--run", "RUN-PLAN")
        self.assertEqual(code, 0, out)
        self.assertIn(f"plan: {PLAN_REF}", out)
        code, out = run_cli(*self.common, "close-run", "--run", "RUN-PLAN", "--status", "synthesised",
                            "--host", "Claude Code", "--parallel", "yes", "--context-tokens", "1000")
        self.assertEqual(code, 0, out)
        self.assertIn(f"plan: {PLAN_REF}", out)


if __name__ == "__main__":
    unittest.main()
