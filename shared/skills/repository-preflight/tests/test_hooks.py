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
            self.assertEqual(hooks.host_settings(), {"hooks": {}})
        self.assertEqual(hooks.host_settings(), hooks.host_settings())

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
