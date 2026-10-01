"""SMART-RULE-0038: a commit on main in the shared checkout is refused; a session copy, another branch
or the explicit variable passes."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hooks  # noqa: E402


def git(repo, *args):
    result = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=repo,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


class WrongFolderTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.shared = self.folder / "brain"
        self.shared.mkdir()
        git(self.shared, "init", "-q", "-b", "main")
        (self.shared / "CONTRACT.md").write_text("x\n", encoding="utf-8")
        git(self.shared, "add", "CONTRACT.md")
        git(self.shared, "commit", "-qm", "start")
        patch = mock.patch.dict(os.environ, {hooks.SHARED_CHECKOUT: ""})
        patch.start()
        self.addCleanup(patch.stop)

    def test_main_in_the_shared_checkout_is_refused(self):
        refusal = hooks.shared_checkout_refusal(self.shared)
        self.assertIsNotNone(refusal)
        self.assertIn("session.py start", refusal)

    def test_the_variable_allows_it(self):
        with mock.patch.dict(os.environ, {hooks.SHARED_CHECKOUT: "1"}):
            self.assertIsNone(hooks.shared_checkout_refusal(self.shared))

    def test_a_session_copy_passes(self):
        copy = self.folder / "brain-sessions" / "work"
        git(self.shared, "worktree", "add", "-q", "-b", "session/work", str(copy))
        self.assertIsNone(hooks.shared_checkout_refusal(copy))

    def test_another_branch_in_the_shared_checkout_passes(self):
        git(self.shared, "switch", "-q", "-c", "proposal/example")
        self.assertIsNone(hooks.shared_checkout_refusal(self.shared))


if __name__ == "__main__":
    unittest.main()
