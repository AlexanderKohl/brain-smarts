"""Compaction hooks: the host settings carry PreCompact and SessionStart[compact] in Claude Code's shape,
pre-compact leaves a marker and closes dispatching, post-compact says what to reload and lists the markers."""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import hooks  # noqa: E402

# Fictional events (SMART-RULE-0008): the shape is what is under test, not the brain's own list.
EVENTS = [
    {"event": "before compaction", "claude_code": "PreCompact", "command": "example/hooks.py pre-compact"},
    {"event": "after compaction", "claude_code": "SessionStart", "matcher": "compact",
     "command": "example/hooks.py post-compact"},
    {"event": "held back", "claude_code": None, "command": "example/hooks.py never"},
]
OFFSET = re.compile(r"[+-]\d\d:\d\d$|Z$")


class HostSettingsShapeTest(unittest.TestCase):
    def test_entries_take_claude_code_shape_and_a_matcher_only_when_the_event_has_one(self):
        self.assertEqual(hooks.host_settings(EVENTS), {"hooks": {
            "PreCompact": [{"hooks": [{"type": "command", "command": f'python "{(hooks.ROOT / "example/hooks.py").as_posix()}" pre-compact'}]}],
            "SessionStart": [{"matcher": "compact",
                              "hooks": [{"type": "command", "command": f'python "{(hooks.ROOT / "example/hooks.py").as_posix()}" post-compact'}]}],
        }})

    def test_the_brain_list_has_both_compaction_events(self):
        generated = hooks.host_settings()["hooks"]
        self.assertEqual(generated["PreCompact"], [{"hooks": [{"type": "command",
                         "command": f'python "{(hooks.ROOT / "shared/skills/repository-preflight/scripts/hooks.py").as_posix()}" pre-compact'}]}])
        self.assertIn({"matcher": "compact", "hooks": [{"type": "command",
                       "command": f'python "{(hooks.ROOT / "shared/skills/repository-preflight/scripts/hooks.py").as_posix()}" post-compact'}]},
                      generated["SessionStart"])


class PreCompactTest(unittest.TestCase):
    def test_writes_the_marker_and_names_the_checkpoint_done_command(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = datetime.now().astimezone()
            text = hooks.pre_compact({"session_id": "s-0001", "cwd": "/example/copy", "trigger": "auto"}, root=root)
            marker = root / "temp" / "conductor" / "compacted" / "s-0001.json"
            self.assertTrue(marker.is_file())
            record = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(set(record), {"session_id", "at", "cwd", "trigger"})
            self.assertEqual((record["session_id"], record["cwd"], record["trigger"]), ("s-0001", "/example/copy", "auto"))
            self.assertRegex(record["at"], OFFSET)
            self.assertGreaterEqual(datetime.fromisoformat(record["at"]), before.replace(microsecond=0))
            self.assertIn("write the handover now", text)
            self.assertIn(str(marker), text)
            self.assertIn("python shared/skills/delegate-work/scripts/delegation.py checkpoint-done --session s-0001", text)

    def test_empty_stdin_is_said_and_the_message_still_prints(self):
        self.assertEqual(hooks.hook_input(io.StringIO("")), ({}, "no hook input on stdin"))
        self.assertEqual(hooks.hook_input(io.StringIO("not json")), ({}, "the hook input on stdin is not JSON"))
        self.assertEqual(hooks.hook_input(io.StringIO('{"session_id": "s-0002"}')), ({"session_id": "s-0002"}, None))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = (sys.stdin, hooks.marker_root)
            sys.stdin, hooks.marker_root = io.StringIO(""), lambda root=root: root
            raw = io.BytesIO()
            out = io.TextIOWrapper(raw, encoding="utf-8")  # main() reconfigures stdout, which StringIO cannot
            try:
                with contextlib.redirect_stdout(out):
                    code = hooks.main(["pre-compact"])
                out.flush()
            finally:
                sys.stdin, hooks.marker_root = original
            printed = raw.getvalue().decode("utf-8")
            self.assertEqual(code, 0)
            self.assertIn("no hook input on stdin", printed)
            self.assertIn("write the handover now", printed)
            self.assertIn("checkpoint-done --session unknown", printed)
            self.assertTrue((root / "temp" / "conductor" / "compacted" / "unknown.json").is_file())

    def test_markers_go_to_the_brain_root_the_owner_profile_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(hooks.marker_root(root), root)
            (root / "memory").mkdir()
            (root / "memory" / "OWNER.md").write_text("---\nid: owner-profile\nbrain_root: /example/brain\n---\n",
                                                      encoding="utf-8")
            self.assertEqual(hooks.marker_root(root), Path("/example/brain"))


class PostCompactTest(unittest.TestCase):
    def test_says_what_to_reload_and_lists_the_markers_oldest_first(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "temp" / "conductor" / "compacted"
            folder.mkdir(parents=True)
            (folder / "s-0009.json").write_text(json.dumps({"session_id": "s-0009", "at": "2026-01-02T10:00:00+10:00"}),
                                                encoding="utf-8")
            (folder / "s-0003.json").write_text(json.dumps({"session_id": "s-0003", "at": "2026-01-01T09:00:00+10:00"}),
                                                encoding="utf-8")
            text = hooks.post_compact({"session_id": "s-0009", "source": "compact"}, root=root)
            self.assertRegex(text, r"compacted at \S+ \(session s-0009\); its summary was prepared at "
                                   r"2026-01-02T10:00:00\+10:00\.")
            self.assertIn("missed checkpoint under SMART-RULE-0019", text)
            for item in ("/CONTRACT-CORE.md", "/RULES-CORE.md", "/memory/RULES.md", "`## Handover`", "STATE.md",
                         "write the handover checkpoint and commit", "Start no new worker",
                         "python shared/skills/delegate-work/scripts/delegation.py checkpoint-done --session s-0009"):
                self.assertIn(item, text)
            self.assertLess(text.index(str(folder / "s-0003.json")), text.index(str(folder / "s-0009.json")))
            self.assertIn("2026-01-01T09:00:00+10:00", text)

    def test_without_a_marker_the_time_comes_from_the_clock_and_the_list_says_none(self):
        with tempfile.TemporaryDirectory() as d:
            text = hooks.post_compact({}, note="no hook input on stdin", root=Path(d))
            self.assertRegex(text.splitlines()[2], r"^This thread was compacted at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:[+-]\d\d:\d\d|Z) \(session unknown\)\.$")
            self.assertIn("Hook input: no hook input on stdin", text)
            self.assertIn("markers present (oldest first): none", text)

    def test_the_first_two_instructions_tell_the_owner_and_give_the_handover_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            first, second, third = hooks.post_compact({"session_id": "s-0004"}, root=Path(d)).splitlines()[:3]
        self.assertRegex(first, r"^Tell the owner first: open your next reply to the owner by saying that this thread "
                                r"was compacted at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:[+-]\d\d:\d\d|Z)\.$")
        for item in ("End that reply with the handover prompt (SMART-RULE-0019)", "`## Handover prompt`",
                     "STATE.md", "offer to continue in a new thread"):
            self.assertIn(item, second)
        self.assertEqual(first.split(" at ")[-1].rstrip("."), third.split(" at ")[1].split(" (")[0])  # one time


def assistant(tokens: int, sidechain: bool = False) -> dict:
    """A fictional assistant record whose usage adds up to `tokens`."""
    return {"type": "assistant", "isSidechain": sidechain, "message": {"usage": {
        "input_tokens": 10, "cache_read_input_tokens": tokens - 40, "cache_creation_input_tokens": 20,
        "output_tokens": 10}}}


def boundary(pre: int) -> dict:
    return {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "auto", "preTokens": pre}}


class ContextCheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.transcript = self.root / "session.jsonl"

    def write(self, *records, junk: str = "") -> dict:
        self.transcript.write_text(junk + "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return {"session_id": "s-0100", "transcript_path": str(self.transcript)}

    def check(self, payload: dict) -> str:
        return hooks.context_check(payload, root=self.root, state_root=self.root)

    def config(self, value) -> None:
        folder = self.root / hooks.CONTEXT_CONFIG.parent
        folder.mkdir(parents=True, exist_ok=True)
        (self.root / hooks.CONTEXT_CONFIG).write_text(json.dumps({"context_warn_tokens": value}), encoding="utf-8")

    def test_below_the_threshold_prints_nothing(self):
        self.assertEqual(self.check(self.write(assistant(599_999))), "")

    def test_at_the_default_threshold_warns_with_the_size_and_the_handover_prompt(self):
        text = self.check(self.write(assistant(1_000), assistant(600_000)))
        self.assertEqual(len(text.splitlines()), 1)
        for item in ("600,000 tokens", "threshold of 600,000 (the default)", "Finish the current step",
                     "write the checkpoint", "end this reply with the handover prompt and the context size"):
            self.assertIn(item, text)

    def test_the_last_assistant_record_of_the_thread_counts_not_a_sidechain(self):
        self.assertEqual(self.check(self.write(assistant(700_000), assistant(900_000, sidechain=True),
                                               {"type": "user"})).count("700,000 tokens"), 2)

    def test_the_config_threshold_wins(self):
        self.config(100_000)
        self.assertIn("threshold of 100,000 (context_warn_tokens in", self.check(self.write(assistant(150_000))))

    def test_without_config_70_percent_of_an_earlier_compaction(self):
        payload = self.write(boundary(500_000), assistant(30_000), assistant(349_999))
        self.assertEqual(self.check(payload), "")
        self.write(boundary(500_000), assistant(350_000))
        self.assertIn("threshold of 350,000 (70 % of 500,000", self.check(payload))

    def test_once_per_50_000_further_tokens_and_again_after_a_compaction(self):
        self.config(100_000)
        payload = self.write(assistant(120_000))
        self.assertNotEqual(self.check(payload), "")
        self.write(assistant(169_999))
        self.assertEqual(self.check(payload), "")
        self.write(assistant(170_000))
        self.assertIn("170,000 tokens", self.check(payload))
        self.write(boundary(400_000), assistant(30_000))                  # compacted: below, the warning resets
        self.assertEqual(self.check(payload), "")
        self.write(assistant(100_000))
        self.assertIn("100,000 tokens", self.check(payload))

    def test_the_largest_earlier_compaction_is_remembered_past_the_tail(self):
        payload = self.write(boundary(800_000), assistant(30_000))
        self.assertEqual(self.check(payload), "")
        self.write(assistant(560_000))                                     # the boundary is no longer in view
        self.assertIn("70 % of 800,000", self.check(payload))

    def test_only_the_tail_is_read(self):
        junk = "x" * (hooks.TAIL_BYTES * 2) + "\n"
        records = hooks.transcript_tail(Path(self.write(assistant(5), junk=junk)["transcript_path"]))
        self.assertEqual(len(records), 1)

    def test_a_bad_config_is_named_and_the_fallback_still_warns(self):
        self.config("lots")
        lines = self.check(self.write(assistant(650_000))).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("threshold of 600,000 (the default)", lines[0])
        self.assertIn("context-check: the threshold config could not be read", lines[1])


class HookFailuresExitZeroTest(unittest.TestCase):
    """A hook that exits non-zero can block a compaction and end the thread (27 October 2026)."""

    def run_hook(self, command: str, stdin: str, **patches) -> tuple[int, str]:
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="utf-8")
        original_stdin = sys.stdin
        saved = {name: getattr(hooks, name) for name in patches}
        sys.stdin = io.StringIO(stdin)
        for name, value in patches.items():
            setattr(hooks, name, value)
        try:
            with contextlib.redirect_stdout(out):
                code = hooks.main([command])
            out.flush()
        finally:
            sys.stdin = original_stdin
            for name, value in saved.items():
                setattr(hooks, name, value)
        return code, raw.getvalue().decode("utf-8")

    def test_a_missing_transcript_exits_0_with_one_line(self):
        code, printed = self.run_hook("context-check", json.dumps({"session_id": "s-1", "transcript_path": "/no/such.jsonl"}))
        self.assertEqual(code, 0)
        self.assertEqual(len(printed.strip().splitlines()), 1)
        self.assertIn("context-check: could not run (FileNotFoundError", printed)

    def test_no_hook_input_and_an_unreadable_line_exit_0_silently(self):
        self.assertEqual(self.run_hook("context-check", ""), (0, ""))
        with tempfile.TemporaryDirectory() as d:
            transcript = Path(d) / "t.jsonl"
            transcript.write_bytes(b"\xff\xfe not json {\n[1, 2]\n")
            code, printed = self.run_hook("context-check", json.dumps({"transcript_path": str(transcript)}))
        self.assertEqual((code, printed), (0, ""))

    def test_a_missing_config_falls_back_and_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            transcript = root / "t.jsonl"
            transcript.write_text(json.dumps(assistant(610_000)) + "\n", encoding="utf-8")
            code, printed = self.run_hook("context-check", json.dumps({"session_id": "s-2", "transcript_path": str(transcript)}),
                                          ROOT=root, marker_root=lambda *_a, root=root: root)
        self.assertEqual(code, 0)
        self.assertIn("threshold of 600,000 (the default)", printed)

    def test_a_read_only_state_folder_still_warns_and_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            transcript = root / "t.jsonl"
            transcript.write_text(json.dumps(assistant(610_000)) + "\n", encoding="utf-8")
            (root / "temp").write_text("a file where the state folder would go", encoding="utf-8")
            code, printed = self.run_hook("context-check", json.dumps({"session_id": "s-3", "transcript_path": str(transcript)}),
                                          ROOT=root, marker_root=lambda *_a, root=root: root)
        self.assertEqual(code, 0)
        self.assertIn("Finish the current step", printed)
        self.assertIn("context-check: the state file could not be written", printed)

    def test_compaction_hooks_exit_0_when_the_marker_folder_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "temp").write_text("not a folder", encoding="utf-8")
            code, printed = self.run_hook("pre-compact", '{"session_id": "s-4"}', marker_root=lambda *_a, root=root: root)
            self.assertEqual(code, 0)
            self.assertIn("write the handover now", printed)
            self.assertIn("Compaction marker not written", printed)
            code, printed = self.run_hook("post-compact", '{"session_id": "s-4"}', marker_root=lambda *_a, root=root: root)
            self.assertEqual(code, 0)
            self.assertIn("Tell the owner first", printed)

    def test_any_exception_in_a_hook_becomes_one_line_and_exit_0(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("example failure")
        for command, name in (("post-compact", "post_compact"), ("pre-compact", "pre_compact"),
                              ("context-check", "context_check"), ("session-start", "session_start_hook")):
            code, printed = self.run_hook(command, "{}", **{name: broken})
            self.assertEqual(code, 0, command)
            self.assertEqual(printed.strip(), f"{command}: could not run (RuntimeError: example failure)")


class SessionStartRemindersTest(unittest.TestCase):
    def fake_brain(self, body: str | None) -> Path:
        root = Path(self.dir.name)
        if body is not None:
            script = root / "shared" / "skills" / "tasks" / "scripts" / "tasks.py"
            script.parent.mkdir(parents=True)
            script.write_text(body, encoding="utf-8")
        return root

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_the_reminders_output_is_printed_unchanged(self):
        line = "reminder: Example review – TASK-0000-0001, due 2026-01-05; when done: python x done TASK-0000-0001"
        root = self.fake_brain(f"print({line!r})\n")
        self.assertEqual(hooks.reminder_lines(root), line)

    def test_a_missing_or_failing_command_prints_nothing(self):
        self.assertEqual(hooks.reminder_lines(self.fake_brain(None)), "")
        self.assertEqual(hooks.reminder_lines(self.fake_brain("import sys\nprint('partial')\nsys.exit(3)\n")), "")

    def test_reminders_follow_the_session_start_text(self):
        original = (hooks.session_start, hooks.reminder_lines, hooks.hook_input)
        hooks.hook_input = lambda: ({}, None)
        hooks.reminder_lines = lambda root: "reminder: Example – TASK-0000-0002, due 2026-01-06"
        try:
            hooks.session_start = lambda *a, **k: ""
            quiet = json.loads(hooks.session_start_hook([]))["hookSpecificOutput"]["additionalContext"]
            hooks.session_start = lambda *a, **k: hooks.HEADER + "\nmechanics: behind"
            busy = json.loads(hooks.session_start_hook([]))["hookSpecificOutput"]["additionalContext"]
        finally:
            hooks.session_start, hooks.reminder_lines, hooks.hook_input = original
        self.assertEqual(quiet, hooks.HEADER + "\nreminder: Example – TASK-0000-0002, due 2026-01-06")
        self.assertEqual(busy.splitlines(), [hooks.HEADER, "mechanics: behind", "reminder: Example – TASK-0000-0002, due 2026-01-06"])


if __name__ == "__main__":
    unittest.main()
