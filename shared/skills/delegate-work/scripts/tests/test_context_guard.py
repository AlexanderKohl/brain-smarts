"""Behavioural tests for context_guard.py (SMART-RULE-0022): the context guard and the
compaction marker that delegation.py applies to new-run, new-packet and close-run.

Run from the repository root:
    python -m unittest discover -s shared/skills/delegate-work/scripts/tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import context_guard  # noqa: E402
import delegation  # noqa: E402
from test_delegation import run_cli  # noqa: E402

NOW = "2026-09-15T08:00:00+10:00"


def stamp(hours_before_now: float) -> str:
    return (datetime.fromisoformat(NOW) - timedelta(hours=hours_before_now)).isoformat(timespec="seconds")


class ContextGuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-context-guard-"))
        (self.root / "CONTRACT.md").write_text("---\nid: x\n---\n# contract\n", encoding="utf-8")
        templates = self.root / "shared" / "skills" / "delegate-work" / "templates"
        templates.mkdir(parents=True)
        for name in ("run.template.md", "packet.template.md", "result.template.md"):
            shutil.copy(SKILL / "templates" / name, templates / name)
        self.common = ["--root", str(self.root), "--now", NOW]
        self.compacted = self.root / "temp" / "conductor" / "compacted"

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ helpers

    def new_run(self, *flags: str, run_id: str = "RUN-TEST") -> tuple[int, str]:
        return run_cli(*self.common, "new-run", "--title", "Trial", "--why-parallel",
                       "independent audits", "--run-id", run_id, *flags)

    def new_packet(self, *flags: str, run: str = "RUN-TEST") -> tuple[int, str]:
        return run_cli(*self.common, "new-packet", "--run", run, "--title", "Audit skills",
                       "--objective", "Check every SKILL.md.", *flags)

    def run_meta(self, run: str = "RUN-TEST") -> dict:
        meta, _ = delegation.load(self.root / "temp" / "delegation" / "runs" / run / "RUN.md")
        return meta

    def write_marker(self, session: str, at: str | None, where: Path | None = None) -> Path:
        folder = where or self.compacted
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{session}.json"
        path.write_text(json.dumps({"session_id": session, "at": at, "cwd": str(self.root)}),
                        encoding="utf-8")
        return path

    # ------------------------------------------------------------ the flags

    def test_new_run_without_context_flags_is_refused(self) -> None:
        code, out = self.new_run()
        self.assertNotEqual(code, 0)
        self.assertIn("--context-tokens", out)
        self.assertIn("--context-unknown", out)
        self.assertFalse((self.root / "temp" / "delegation").exists())

    def test_new_packet_without_context_flags_is_refused(self) -> None:
        self.assertEqual(self.new_run("--context-tokens", "1000")[0], 0)
        code, out = self.new_packet()
        self.assertNotEqual(code, 0)
        self.assertIn("new-packet needs --context-tokens", out)

    def test_close_run_without_context_flags_is_refused(self) -> None:
        self.assertEqual(self.new_run("--context-tokens", "1000")[0], 0)
        code, out = run_cli(*self.common, "close-run", "--run", "RUN-TEST", "--status", "synthesised",
                            "--host", "Test host", "--parallel", "no")
        self.assertNotEqual(code, 0)
        self.assertIn("close-run needs --context-tokens", out)
        self.assertEqual(self.run_meta()["status"], "open")

    def test_both_context_flags_together_are_refused(self) -> None:
        code, out = self.new_run("--context-tokens", "1000", "--context-unknown", "host hides it")
        self.assertNotEqual(code, 0)
        self.assertIn("exactly one", out)

    # ------------------------------------------------------------ thresholds

    def test_new_run_is_refused_at_the_drain_threshold(self) -> None:
        code, out = self.new_run("--context-tokens", str(context_guard.DRAIN_TOKENS))
        self.assertNotEqual(code, 0)
        self.assertIn("drain – no new run, let the workers in flight finish, take the checkpoint, hand over", out)
        self.assertIn("SMART-RULE-0019", out)
        self.assertFalse((self.root / "temp" / "delegation").exists())
        code, out = self.new_run("--context-tokens", str(context_guard.DRAIN_TOKENS - 1))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["context_tokens_at_open"], str(context_guard.DRAIN_TOKENS - 1))
        self.assertNotIn("owner_override", self.run_meta())

    def test_drain_gets_through_with_the_threshold_switched_off(self) -> None:
        with mock.patch.object(context_guard, "DRAIN_TOKENS", 10 ** 9):
            code, out = self.new_run("--context-tokens", "750000")
        self.assertEqual(code, 0, out)

    def test_new_packet_passes_drain_and_is_refused_at_the_stop_threshold(self) -> None:
        self.assertEqual(self.new_run("--context-tokens", "1000")[0], 0)
        code, out = self.new_packet("--context-tokens", str(context_guard.DRAIN_TOKENS))
        self.assertEqual(code, 0, out)
        code, out = self.new_packet("--context-tokens", str(context_guard.STOP_TOKENS))
        self.assertNotEqual(code, 0)
        self.assertIn("stop – no new packet", out)
        self.assertIn(str(context_guard.STOP_TOKENS), out)
        self.assertFalse((self.root / "temp" / "delegation" / "runs" / "RUN-TEST" / "W02.md").exists())

    def test_thresholds_are_the_named_constants(self) -> None:
        self.assertEqual(context_guard.DRAIN_TOKENS, 750000)
        self.assertEqual(context_guard.STOP_TOKENS, 850000)

    # ------------------------------------------------------------ override and unknown

    def test_owner_override_proceeds_and_is_recorded_in_run_and_packet(self) -> None:
        code, out = self.new_run("--context-tokens", str(context_guard.STOP_TOKENS),
                                 "--owner-override", "owner said finish this run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["owner_override"], "owner said finish this run")
        self.assertEqual(self.run_meta()["context_tokens_at_open"], str(context_guard.STOP_TOKENS))
        code, out = self.new_packet("--context-tokens", str(context_guard.STOP_TOKENS),
                                    "--owner-override", "owner said one more packet")
        self.assertEqual(code, 0, out)
        packet, _ = delegation.load(self.root / "temp" / "delegation" / "runs" / "RUN-TEST" / "W01.md")
        self.assertEqual(packet["owner_override"], "owner said one more packet")
        self.assertEqual(self.run_meta()["owner_override"], "owner said one more packet")

    def test_unknown_context_is_recorded_with_its_reason(self) -> None:
        code, out = self.new_run("--context-unknown", "host shows no token count")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["context_tokens_at_open"], "unknown: host shows no token count")
        code, out = run_cli(*self.common, "close-run", "--run", "RUN-TEST", "--status", "synthesised",
                            "--host", "Test host", "--parallel", "no", "--context-unknown", "still no count")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["context_tokens_at_close"], "unknown: still no count")

    # ------------------------------------------------------------ compaction markers

    def test_fresh_marker_blocks_new_run_and_new_packet_and_names_the_clearing_command(self) -> None:
        self.assertEqual(self.new_run("--context-tokens", "1000")[0], 0)
        self.write_marker("sess-aaa", stamp(1))
        code, out = self.new_run("--context-tokens", "1000", run_id="RUN-TWO")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-aaa", out)
        self.assertIn(stamp(1), out)
        self.assertIn("checkpoint-done --session sess-aaa", out)
        code, out = self.new_packet("--context-tokens", "1000")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-aaa", out)

    def test_marker_gets_through_with_the_check_switched_off(self) -> None:
        self.write_marker("sess-aaa", stamp(1))
        with mock.patch.object(context_guard, "blocking_markers", lambda root, now, session: []):
            code, out = self.new_run("--context-tokens", "1000")
        self.assertEqual(code, 0, out)

    def test_another_sessions_marker_does_not_block_a_named_session(self) -> None:
        self.write_marker("sess-other", stamp(1))
        code, out = self.new_run("--context-tokens", "1000", "--session", "sess-mine")
        self.assertEqual(code, 0, out)
        code, out = self.new_packet("--context-tokens", "1000", "--session", "sess-mine")
        self.assertEqual(code, 0, out)
        code, out = self.new_run("--context-tokens", "1000", "--session", "sess-other", run_id="RUN-TWO")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-other", out)

    def test_stale_marker_is_ignored(self) -> None:
        self.write_marker("sess-old", stamp(25))
        code, out = self.new_run("--context-tokens", "1000")
        self.assertEqual(code, 0, out)
        self.write_marker("sess-edge", stamp(23.5))
        code, out = self.new_run("--context-tokens", "1000", run_id="RUN-TWO")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-edge", out)

    def test_unreadable_marker_is_dated_by_its_file_and_blocks(self) -> None:
        self.compacted.mkdir(parents=True)
        (self.compacted / "sess-broken.json").write_text("not json", encoding="utf-8")
        with mock.patch("context_guard.datetime", wraps=datetime) as fake:
            fake.fromtimestamp.return_value = datetime.fromisoformat(NOW)
            code, out = self.new_run("--context-tokens", "1000")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-broken", out)

    def test_owner_override_passes_the_marker_check(self) -> None:
        self.write_marker("sess-aaa", stamp(1))
        code, out = self.new_run("--context-tokens", "1000", "--owner-override", "checkpoint is in the log")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_meta()["owner_override"], "checkpoint is in the log")

    def test_marker_under_the_owner_profiles_brain_root_blocks_too(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="brain-other-root-"))
        self.addCleanup(shutil.rmtree, other, True)
        (self.root / "memory").mkdir()
        (self.root / "memory" / "OWNER.md").write_text(
            f"---\nid: owner-profile\nbrain_root: {other}\n---\n# Owner\n", encoding="utf-8")
        self.write_marker("sess-shared", stamp(2), where=other / "temp" / "conductor" / "compacted")
        code, out = self.new_run("--context-tokens", "1000")
        self.assertNotEqual(code, 0)
        self.assertIn("sess-shared", out)
        self.assertIn(str(other), out)

    def test_owner_profile_naming_the_same_root_adds_no_second_place(self) -> None:
        (self.root / "memory").mkdir()
        (self.root / "memory" / "OWNER.md").write_text(
            f"---\nid: owner-profile\nbrain_root: {self.root}\n---\n# Owner\n", encoding="utf-8")
        self.assertEqual(context_guard.marker_roots(self.root), [self.root.resolve()])

    # ------------------------------------------------------------ checkpoint-done

    def test_checkpoint_done_removes_the_marker_from_both_places_and_unblocks(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="brain-other-root-"))
        self.addCleanup(shutil.rmtree, other, True)
        (self.root / "memory").mkdir()
        (self.root / "memory" / "OWNER.md").write_text(
            f"---\nid: owner-profile\nbrain_root: {other}\n---\n# Owner\n", encoding="utf-8")
        here = self.write_marker("sess-aaa", stamp(1))
        there = self.write_marker("sess-aaa", stamp(1), where=other / "temp" / "conductor" / "compacted")
        keep = self.write_marker("sess-keep", stamp(30))
        code, out = run_cli(*self.common, "checkpoint-done", "--session", "sess-aaa")
        self.assertEqual(code, 0, out)
        self.assertIn(f"removed {here}", out)
        self.assertIn(f"removed {there}", out)
        self.assertFalse(here.exists())
        self.assertFalse(there.exists())
        self.assertTrue(keep.exists())
        code, out = self.new_run("--context-tokens", "1000")
        self.assertEqual(code, 0, out)

    def test_checkpoint_done_with_nothing_to_remove_says_so(self) -> None:
        code, out = run_cli(*self.common, "checkpoint-done", "--session", "sess-none")
        self.assertEqual(code, 0, out)
        self.assertIn("no compaction marker named sess-none.json", out)


if __name__ == "__main__":
    unittest.main()
