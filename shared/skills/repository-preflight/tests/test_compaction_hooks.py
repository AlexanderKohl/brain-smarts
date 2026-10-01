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
            "PreCompact": [{"hooks": [{"type": "command", "command": "python example/hooks.py pre-compact"}]}],
            "SessionStart": [{"matcher": "compact",
                              "hooks": [{"type": "command", "command": "python example/hooks.py post-compact"}]}],
        }})

    def test_the_brain_list_has_both_compaction_events(self):
        generated = hooks.host_settings()["hooks"]
        self.assertEqual(generated["PreCompact"], [{"hooks": [{"type": "command",
                         "command": "python shared/skills/repository-preflight/scripts/hooks.py pre-compact"}]}])
        self.assertEqual(generated["SessionStart"], [{"matcher": "compact", "hooks": [{"type": "command",
                         "command": "python shared/skills/repository-preflight/scripts/hooks.py post-compact"}]}])


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
            self.assertIn("compacted at 2026-01-02T10:00:00+10:00 (session s-0009)", text)
            self.assertIn("missed checkpoint under SMART-RULE-0019", text)
            for item in ("/CONTRACT.md", "/RULES.md", "/memory/RULES.md", "`## Handover`", "STATE.md",
                         "write the handover checkpoint and commit", "Start no new worker",
                         "python shared/skills/delegate-work/scripts/delegation.py checkpoint-done --session s-0009"):
                self.assertIn(item, text)
            self.assertLess(text.index(str(folder / "s-0003.json")), text.index(str(folder / "s-0009.json")))
            self.assertIn("2026-01-01T09:00:00+10:00", text)

    def test_without_a_marker_the_time_comes_from_the_clock_and_the_list_says_none(self):
        with tempfile.TemporaryDirectory() as d:
            text = hooks.post_compact({}, note="no hook input on stdin", root=Path(d))
            self.assertRegex(text.splitlines()[0], r"^This thread was compacted at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:[+-]\d\d:\d\d|Z) \(session unknown\)\.$")
            self.assertIn("Hook input: no hook input on stdin", text)
            self.assertIn("markers present (oldest first): none", text)


if __name__ == "__main__":
    unittest.main()
