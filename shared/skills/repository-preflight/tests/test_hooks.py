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
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), hooks.host_settings())
        else:
            # Only the events the list gives a Claude Code name reach the host; today the two
            # compaction hooks, which fire on a compaction and never on a light session.
            listed = {e["claude_code"] for e in json.loads(hooks.EVENTS.read_text(encoding="utf-8"))["events"]
                      if e.get("claude_code") and (not e.get("skill") or e["skill"] in hooks.active_skills())}
            self.assertEqual(set(hooks.host_settings()["hooks"]), listed)
            self.assertEqual(listed, {"PreCompact", "SessionStart"})
        self.assertEqual(hooks.host_settings(), hooks.host_settings())

    def test_a_library_skills_hook_reaches_the_host_only_when_the_skill_is_active(self):
        events = [{"event": "after a shell command", "claude_code": "PostToolUse", "matcher": "Bash",
                   "skill": "example-skill", "command": "library/skills/example-skill/scripts/hook.py"}]
        self.assertEqual(hooks.host_settings(events, active=set()), {"hooks": {}})
        self.assertEqual(hooks.host_settings(events, active={"example-skill"}), {"hooks": {"PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command",
                                            "command": "python library/skills/example-skill/scripts/hook.py"}]}]}})

    def test_active_skills_are_read_from_the_owner_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory").mkdir()
            (root / "memory" / "OWNER.md").write_text(
                "---\nid: owner-profile\nactive_skills:\n  - example-one\n  - example-two\nother: x\n---\n\n# Owner\n",
                encoding="utf-8")
            self.assertEqual(hooks.active_skills(root), {"example-one", "example-two"})
            self.assertEqual(hooks.active_skills(root / "missing"), set())

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
