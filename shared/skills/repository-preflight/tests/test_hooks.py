"""Hooks from one list: generated host settings match the list, and a swept foreign file is refused."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import hooks  # noqa: E402


class HooksTest(unittest.TestCase):
    def test_committed_settings_are_generated_from_the_list(self):
        settings = hooks.ROOT / ".claude" / "settings.json"
        if settings.is_file():
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["hooks"], hooks.host_settings()["hooks"])
        else:
            # Only the events the list gives a Claude Code name reach the host: the compaction hooks,
            # the session-start sync and the per-prompt context check, each silent when all is well.
            listed = {e["claude_code"] for e in hooks.brain_events() if e.get("claude_code")}
            self.assertEqual(set(hooks.host_settings()["hooks"]), listed)
            self.assertEqual(listed, {"PreCompact", "SessionStart", "UserPromptSubmit"})
        self.assertEqual(hooks.host_settings(), hooks.host_settings())

    def test_the_context_check_is_wired_once_with_an_absolute_script_path(self):
        prompt = hooks.host_settings()["hooks"]["UserPromptSubmit"]
        script = (hooks.ROOT / "shared/skills/repository-preflight/scripts/hooks.py").as_posix()
        self.assertEqual(prompt, [{"hooks": [{"type": "command", "command": f'python "{script}" context-check'}]}])
        self.assertTrue(Path(script).is_absolute())
        # Once the event list carries its own UserPromptSubmit event, the built-in one is not added again.
        listed = [dict(hooks.CONTEXT_CHECK_EVENT, command="example/hooks.py context-check")]
        original = hooks.EVENTS
        with tempfile.TemporaryDirectory() as d:
            hooks.EVENTS = Path(d) / "events.json"
            hooks.EVENTS.write_text(json.dumps({"events": listed}), encoding="utf-8")
            try:
                self.assertEqual(hooks.brain_events(), listed)
            finally:
                hooks.EVENTS = original

    def test_a_file_untracked_at_session_start_cannot_be_committed(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "theirs.md").write_text("another session\n", encoding="utf-8")
            (repo / "mine.md").write_text("this session\n", encoding="utf-8")
            (hooks.git_dir(repo) / hooks.UNTRACKED).write_text("theirs.md", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            self.assertEqual(hooks.pre_commit(repo), 1)


if __name__ == "__main__":
    unittest.main()
