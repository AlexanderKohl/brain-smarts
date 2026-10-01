"""Behavioural tests for delegation.py (SMART-RULE-0022).

Run from the repository root:
    python -m unittest discover -s shared/skills/delegate-work/scripts/tests -v
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import delegation  # noqa: E402

NOW = "2026-09-15T08:00:00+10:00"


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        try:
            code = delegation.main(list(argv))
        except SystemExit as exc:  # argparse and explicit SystemExit both land here
            code = exc.code if isinstance(exc.code, int) else 1
            if not isinstance(exc.code, int):
                out.write(str(exc.code))
    return code, out.getvalue()


class DelegationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-delegation-"))
        (self.root / "CONTRACT.md").write_text("---\nid: x\n---\n# contract\n", encoding="utf-8")
        templates = self.root / "shared" / "skills" / "delegate-work" / "templates"
        templates.mkdir(parents=True)
        for name in ("run.template.md", "packet.template.md", "result.template.md"):
            shutil.copy(SKILL / "templates" / name, templates / name)
        (self.root / "RULES.md").write_text("---\nid: r\n---\n# rules\n", encoding="utf-8")
        self.common = ["--root", str(self.root), "--now", NOW]

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ helpers

    def new_run(self, **overrides) -> str:
        args = [*self.common, "new-run", "--context-tokens", "1000", "--title", "Trial", "--why-parallel",
                "three independent read-only audits", "--run-id", overrides.get("run_id", "RUN-TEST")]
        if "max_workers" in overrides:
            args += ["--max-workers", str(overrides["max_workers"])]
        code, out = run_cli(*args)
        self.assertEqual(code, 0, out)
        return overrides.get("run_id", "RUN-TEST")

    def new_packet(self, run: str, *extra: str) -> tuple[int, str]:
        return run_cli(*self.common, "new-packet", "--context-tokens", "1000", "--run", run,
                       "--title", "Audit skills", "--objective", "Check every SKILL.md.", *extra)

    def result_path(self, run: str, short: str) -> Path:
        return self.root / "temp" / "delegation" / "runs" / run / f"{short}.result.md"

    def fill_result(self, run: str, short: str, status: str = "completed", **fields) -> None:
        path = self.result_path(run, short)
        meta, body = delegation.load(path)
        meta.update({"status": status, "host": "Test host", "model": "unknown"})
        meta.update(fields)
        filled = []
        for line in body.splitlines():
            filled.append(line)
            if line.startswith("## "):
                filled.append(f"Content for {line[3:]}.")
        delegation.write(path, meta, "\n".join(filled))

    # ------------------------------------------------------------ runs

    def test_new_run_creates_manifest_with_why_parallel(self) -> None:
        run = self.new_run()
        meta, body = delegation.load(self.root / "temp/delegation/runs" / run / "RUN.md")
        self.assertEqual(meta["type"], "delegation_run")
        self.assertEqual(meta["status"], "open")
        self.assertEqual(meta["contract"], "/CONTRACT.md")
        self.assertEqual(meta["created"], NOW)
        self.assertIn("three independent read-only audits", body)

    def test_new_run_requires_why_parallel(self) -> None:
        code, _ = run_cli(*self.common, "new-run", "--title", "Trial")
        self.assertNotEqual(code, 0)

    def test_new_run_rejects_budget_above_four(self) -> None:
        code, out = run_cli(*self.common, "new-run", "--context-tokens", "1000", "--title", "T",
                            "--why-parallel", "x", "--max-workers", "5")
        self.assertNotEqual(code, 0)
        self.assertIn("max workers is 4", out)

    # ------------------------------------------------------------ packets

    def test_packets_number_sequentially_and_create_pending_result(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip().endswith("/W01.md"))
        code, out = self.new_packet(run)
        self.assertTrue(out.strip().endswith("/W02.md"))
        meta, body = delegation.load(self.result_path(run, "W02"))
        self.assertEqual(meta["status"], "pending")
        self.assertEqual(meta["packet"], "W02")
        self.assertEqual(meta["id"], f"{run}-W02-result")
        for name in delegation.REQUIRED_RESULT_SECTIONS:
            self.assertIn(f"## {name}", body)

    def test_fifth_packet_is_refused(self) -> None:
        run = self.new_run()
        for _ in range(4):
            self.assertEqual(self.new_packet(run)[0], 0)
        code, out = self.new_packet(run)
        self.assertNotEqual(code, 0)
        self.assertIn("budget is 4", out)

    def test_packet_defaults_are_isolated_readonly_no_external(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        meta, body = delegation.load(self.root / "temp/delegation/runs" / run / "W01.md")
        self.assertEqual(meta["context_mode"], "isolated")
        self.assertEqual(meta["writes"], "none")
        self.assertEqual(meta["external"], "none")
        self.assertEqual(meta["model"], "inherit")
        self.assertIn("scoped bootstrap", body)
        self.assertIn("Do not commit", body)
        self.assertIn("Depth is one", body)

    def test_fork_requires_reason(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run, "--context-mode", "fork")
        self.assertNotEqual(code, 0)
        self.assertIn("--fork-reason", out)
        code, _ = self.new_packet(run, "--context-mode", "fork", "--fork-reason",
                                  "needs the conductor's diagnosis")
        self.assertEqual(code, 0)

    def test_external_write_requires_confirmed_target(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run, "--external", "write")
        self.assertNotEqual(code, 0)
        self.assertIn("--target", out)

    def test_writes_paths_requires_paths_and_instructs_full_bootstrap(self) -> None:
        run = self.new_run()
        code, _ = self.new_packet(run, "--writes", "paths")
        self.assertNotEqual(code, 0)
        code, _ = self.new_packet(run, "--writes", "paths", "--path", "/RULES.md")
        self.assertEqual(code, 0)
        _, body = delegation.load(self.root / "temp/delegation/runs" / run / "W01.md")
        self.assertIn("full bootstrap", body)
        self.assertIn("`/RULES.md`", body)

    def test_facts_are_run_at_packet_time_and_pasted(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run, "--fact", f"skills={sys.executable} -c \"print(13)\"")
        self.assertEqual(code, 0, out)
        meta, body = delegation.load(self.root / "temp/delegation/runs" / run / "W01.md")
        self.assertEqual(meta["facts_verified"], ["skills"])
        self.assertIn("**skills**", body)
        self.assertIn("13", body)

    def test_packet_without_facts_says_so(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        _, body = delegation.load(self.root / "temp/delegation/runs" / run / "W01.md")
        self.assertIn("None recorded", body)

    def test_over_budget_result_warns_but_passes(self) -> None:
        run = self.new_run()
        self.new_packet(run, "--max-output-words", "5")
        self.fill_result(run, "W01")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN", out)
        self.assertIn("against a budget of 5", out)

    def test_worktree_worker_commits_on_its_branch(self) -> None:
        run = self.new_run()
        self.new_packet(run, "--writes", "worktree")
        _, body = delegation.load(self.root / "temp/delegation/runs" / run / "W01.md")
        self.assertIn("Commit on your own branch", body)
        self.assertIn("never merge", body)
        self.new_packet(run)
        _, body2 = delegation.load(self.root / "temp/delegation/runs" / run / "W02.md")
        self.assertIn("Do not commit", body2)

    def test_missing_context_reference_is_refused(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run, "--context", "/does/not/exist.md")
        self.assertNotEqual(code, 0)
        self.assertIn("does not exist", out)

    def test_dispatch_prompt_points_at_packet_and_result(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        code, out = run_cli(*self.common, "dispatch-prompt", "--run", run, "--packet", "W01")
        self.assertEqual(code, 0)
        self.assertIn(f"/temp/delegation/runs/{run}/W01.md", out)
        self.assertIn(f"/temp/delegation/runs/{run}/W01.result.md", out)
        self.assertIn("writes: none", out)

    # ------------------------------------------------------------ results

    def test_pending_result_fails_validation(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("status pending", out)

    def test_filled_result_passes(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_missing_section_is_rejected(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01")
        path = self.result_path(run, "W01")
        path.write_text(path.read_text(encoding="utf-8").replace("## Negative findings", "## Findings"),
                        encoding="utf-8")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("missing section '## Negative findings'", out)

    def test_changed_paths_rejected_when_packet_forbids_writes(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", changed_paths=["/RULES.md"], validation=["tests pass"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("allows no writes", out)

    def test_changed_paths_inside_run_folder_are_not_repository_writes(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", changed_paths=[f"/temp/delegation/runs/{run}/W01.result.md"],
                         validation=["read-only"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)

    def test_changed_paths_need_validation_and_must_exist(self) -> None:
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/RULES.md")
        self.fill_result(run, "W01", changed_paths=["/RULES.md"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("without validation", out)
        self.fill_result(run, "W01", changed_paths=["/missing.md"], validation=["ran"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertIn("changed path does not exist", out)

    def test_artifact_must_exist(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", artifacts=[f"/temp/delegation/runs/{run}/W01.table.md"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("artifact does not exist", out)

    def test_a_worktree_packet_may_name_paths_of_another_repository(self) -> None:
        """A worktree worker edits another repository, so its paths cannot resolve here."""
        run = self.new_run()
        self.new_packet(run, "--writes", "worktree")
        self.fill_result(run, "W01", changed_paths=["src/app/storage/answer.ts"], validation=["npm run check passed"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)
        self.assertIn("not in this repository", out)

    def test_a_paths_packet_still_must_name_paths_that_exist(self) -> None:
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/RULES.md")
        self.fill_result(run, "W01", changed_paths=["/missing.md"], validation=["ran"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("changed path does not exist", out)

    def test_artifact_that_is_not_a_path_is_free_text(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", artifacts=["git branch feature/x at 1a2b3c4, pushed to origin", "https://example.invalid/build/7"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)
        self.assertNotIn("artifact does not exist", out)

    def test_blocked_result_needs_a_question(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", status="blocked")
        path = self.result_path(run, "W01")
        text = path.read_text(encoding="utf-8").replace("Content for Open questions.", "")
        path.write_text(text, encoding="utf-8")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("blocked result must state the question", out)

    def test_secret_like_content_is_rejected(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01")
        path = self.result_path(run, "W01")
        path.write_text(path.read_text(encoding="utf-8")
                        + "\nfound token: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n",
                        encoding="utf-8")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("secret pattern", out)

    def test_unknown_model_is_accepted_but_empty_is_not(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.fill_result(run, "W01", model="")
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("model must be set", out)

    # ------------------------------------------------------------ synthesis

    def test_summarise_lists_every_packet_and_collects_routing_sections(self) -> None:
        run = self.new_run()
        self.new_packet(run)
        self.new_packet(run)
        self.fill_result(run, "W01")
        code, out = run_cli(*self.common, "summarise", "--run", run)
        self.assertEqual(code, 0)
        self.assertIn("| W01 |", out)
        self.assertIn("| W02 |", out)
        self.assertIn("| pending |", out)
        self.assertIn("## Facts to route", out)
        self.assertIn("### W01", out)
        self.assertIn("Content for Facts to route.", out)

    def test_close_run_records_host_and_parallel_flag(self) -> None:
        run = self.new_run()
        code, _ = run_cli(*self.common, "close-run", "--run", run, "--status", "synthesised",
                          "--host", "Claude Code", "--parallel", "no", "--context-tokens", "180000")
        self.assertEqual(code, 0)
        meta, _ = delegation.load(self.root / "temp/delegation/runs" / run / "RUN.md")
        self.assertEqual(meta["status"], "synthesised")
        self.assertEqual(meta["host"], "Claude Code")
        self.assertEqual(meta["parallel"], "false")
        self.assertEqual(meta["context_tokens_at_close"], "180000")

    # ------------------------------------------------------------ workers stay apart (SMART-RULE-0038)
    # Each check is also run switched off, and the fault must then get through: that shows the
    # test depends on the check rather than passing on its own.

    def test_two_packets_cannot_name_the_same_file_or_a_folder_around_it(self) -> None:
        run = self.new_run()
        code, out = self.new_packet(run, "--writes", "paths", "--path", "/notes/a.md")
        self.assertEqual(code, 0, out)
        code, out = self.new_packet(run, "--writes", "paths", "--path", "/notes/a.md")
        self.assertNotEqual(code, 0)
        self.assertIn("overlaps /notes/a.md, already named by W01", out)
        code, out = self.new_packet(run, "--writes", "paths", "--path", "/notes")
        self.assertNotEqual(code, 0)
        self.assertIn("overlaps", out)
        code, out = self.new_packet(run, "--writes", "paths", "--path", "/notes/b.md")
        self.assertEqual(code, 0, out)

    def test_overlap_gets_through_with_the_check_switched_off(self) -> None:
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/notes/a.md")
        with mock.patch.object(delegation, "within", lambda path, scope: False):
            code, out = self.new_packet(run, "--writes", "paths", "--path", "/notes/a.md")
        self.assertEqual(code, 0, out)

    def test_a_result_outside_its_write_paths_fails(self) -> None:
        (self.root / "OTHER.md").write_text("x\n", encoding="utf-8")
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/RULES.md")
        self.fill_result(run, "W01", changed_paths=["/OTHER.md"], validation=["ran"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 1)
        self.assertIn("outside the packet's write_paths: /OTHER.md", out)
        self.fill_result(run, "W01", changed_paths=["/RULES.md"], validation=["ran"])
        code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)

    def test_outside_write_paths_gets_through_with_the_check_switched_off(self) -> None:
        (self.root / "OTHER.md").write_text("x\n", encoding="utf-8")
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/RULES.md")
        self.fill_result(run, "W01", changed_paths=["/OTHER.md"], validation=["ran"])
        with mock.patch.object(delegation, "within", lambda path, scope: True):
            code, out = run_cli(*self.common, "validate-result", "--run", run)
        self.assertEqual(code, 0, out)

    def git_brain(self) -> None:
        """Make the temporary brain a Git repository with everything committed."""
        def git(*args: str) -> None:
            subprocess.run(["git", "-c", "user.name=Example Tester", "-c", "user.email=tester@example.com",
                            "-c", "commit.gpgsign=false", "-C", str(self.root), *args],
                           capture_output=True, text=True, check=True)
        for name in ("a.md", "b.md", "before.md", "mine.md"):
            (self.root / name).write_text("first\n", encoding="utf-8")
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "-m", "start")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_check_writes_reports_changes_no_packet_named(self) -> None:
        self.git_brain()
        (self.root / "before.md").write_text("changed before the run\n", encoding="utf-8")
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/a.md")
        (self.root / "a.md").write_text("the worker's change\n", encoding="utf-8")
        (self.root / "b.md").write_text("a stray change\n", encoding="utf-8")
        (self.root / "c.md").write_text("a stray new file\n", encoding="utf-8")
        (self.root / "mine.md").write_text("the conductor's change\n", encoding="utf-8")
        code, out = run_cli(*self.common, "check-writes", "--run", run, "--mine", "/mine.md")
        self.assertEqual(code, 1, out)
        self.assertIn("named by no packet: /b.md", out)
        self.assertIn("named by no packet: /c.md", out)
        for fine in ("/a.md", "/mine.md", "/before.md", "/temp/"):
            self.assertNotIn(f"named by no packet: {fine}", out)
        (self.root / "b.md").write_text("first\n", encoding="utf-8")
        (self.root / "c.md").unlink()
        code, out = run_cli(*self.common, "check-writes", "--run", run, "--mine", "/mine.md")
        self.assertEqual(code, 0, out)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_stray_change_gets_through_with_the_check_switched_off(self) -> None:
        self.git_brain()
        run = self.new_run()
        self.new_packet(run, "--writes", "paths", "--path", "/a.md")
        (self.root / "b.md").write_text("a stray change\n", encoding="utf-8")
        with mock.patch.object(delegation, "brain_changes", lambda root: []):
            code, out = run_cli(*self.common, "check-writes", "--run", run)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
