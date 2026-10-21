"""setup_guard.py: setup refuses a session copy and runs in the shared checkout.

An invented brain in a temporary Git repository (fictional owner Sam), with a session copy made as a
linked worktree in a sibling sessions folder. Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/scripts/tests -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import setup_guard  # noqa: E402


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Sam Example", "-c", "user.email=sam@example.com", *args],
                   cwd=repo, check=True, capture_output=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SetupGuardTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="setup-guard-")).resolve()
        self.root = self.base / "brain"
        write(self.root / "CONTRACT.md", "---\nid: c\n---\n")
        write(self.root / "shared" / "README.md", "shared\n")
        git(self.root, "init", "--quiet", "-b", "main")
        git(self.root, "add", ".")
        git(self.root, "commit", "--quiet", "-m", "start")
        self.copy = self.base / "brain-sessions" / "garden-work"
        git(self.root, "worktree", "add", "--quiet", "-b", "session/garden-work", str(self.copy))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_the_shared_checkout_may_run_setup(self):
        self.assertIsNone(setup_guard.refusal(self.root))
        setup_guard.refuse_session_copy(self.root)          # returns quietly

    def test_a_session_copy_is_refused_with_the_shared_path_and_the_command(self):
        message = setup_guard.refusal(self.copy / "shared", "python setup_vault.py init")
        self.assertIsNotNone(message)
        self.assertIn(str(self.copy), message)
        self.assertIn(f"cd \"{self.root}\"; python setup_vault.py init", message)
        with self.assertRaises(SystemExit):
            setup_guard.refuse_session_copy(self.copy)

    def test_the_owner_brain_root_is_named_when_it_holds_the_contract(self):
        write(self.root / "memory" / "OWNER.md", f"---\nowner_short_name: Sam\nbrain_root: {self.root}\n---\n")
        self.assertIn(f"cd \"{self.root}\"", setup_guard.refusal(self.copy))
        write(self.root / "memory" / "OWNER.md", f"---\nbrain_root: {self.base / 'elsewhere'}\n---\n")
        self.assertIn(f"cd \"{self.root}\"", setup_guard.refusal(self.copy))   # a folder without the contract is ignored

    def test_a_brain_outside_git_is_not_refused(self):
        plain = self.base / "plain"
        write(plain / "CONTRACT.md", "---\nid: c\n---\n")
        (plain / "shared").mkdir()
        self.assertIsNone(setup_guard.refusal(plain))


if __name__ == "__main__":
    unittest.main()
