"""`hooks.py project-hook`: the pre-commit block a project repository gets (P25).

It runs `preflight.py --project` when it finds the brain ($BRAIN_ROOT, else a sibling brain/),
and otherwise says it skipped, so a collaborator without a brain commits as before. The brain
here is a stub whose preflight records its arguments; the repository is fictional
(SMART-RULE-0008).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import hooks  # noqa: E402

HAS_GIT = shutil.which("git") is not None
STUB = """import sys
from pathlib import Path
Path(__file__).with_name("called.txt").write_text("\\n".join(sys.argv[1:]), encoding="utf-8")
sys.exit(1)
"""


def git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=Sam Example", "-c", "user.email=sam@example.com",
                           "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


@unittest.skipUnless(HAS_GIT, "git is required")
class ProjectHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.repo = self.base / "example-project"
        (self.repo / "brain").mkdir(parents=True)
        (self.repo / "brain" / "README.md").write_text("example\n", encoding="utf-8")
        git(self.repo, "init", "-q")
        self.env = {k: v for k, v in os.environ.items() if k != "BRAIN_ROOT"}

    def hook_file(self) -> Path:
        folder = git(self.repo, "rev-parse", "--git-path", "hooks").stdout.strip()
        path = Path(folder)
        return (path if path.is_absolute() else self.repo / path) / "pre-commit"

    def commit(self, env: dict) -> subprocess.CompletedProcess:
        git(self.repo, "add", "-A")
        return git(self.repo, "commit", "-q", "-m", "example", env=env)

    def stub_brain(self, where: Path) -> Path:
        scripts = where / "shared" / "skills" / "repository-preflight" / "scripts"
        scripts.mkdir(parents=True)
        (where / "CONTRACT.md").write_text("stub\n", encoding="utf-8")
        (scripts / "preflight.py").write_text(STUB, encoding="utf-8")
        return scripts / "called.txt"

    def test_without_a_brain_the_commit_goes_ahead_and_says_it_skipped(self) -> None:
        hooks.project_hook(self.repo)
        done = self.commit(self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("brain checks skipped", done.stderr)

    def test_a_sibling_brain_runs_the_project_preflight_and_its_failure_refuses_the_commit(self) -> None:
        called = self.stub_brain(self.base / "brain")
        hooks.project_hook(self.repo)
        done = self.commit(self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("the brain's preflight fails", done.stderr)
        args = called.read_text(encoding="utf-8").splitlines()
        self.assertIn("--project", args)
        self.assertEqual(Path(args[args.index("--project") + 1]).resolve(), self.repo.resolve())

    def test_brain_root_names_the_brain(self) -> None:
        called = self.stub_brain(self.base / "elsewhere")
        hooks.project_hook(self.repo)
        done = self.commit({**self.env, "BRAIN_ROOT": str(self.base / "elsewhere")})
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue(called.is_file())

    def test_installing_twice_adds_one_block_and_keeps_an_existing_hook(self) -> None:
        target = self.hook_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\necho existing hook\nexit 0\n", encoding="utf-8")
        self.assertTrue(hooks.project_hook(self.repo).startswith("installed"))
        self.assertTrue(hooks.project_hook(self.repo).startswith("already installed"))
        text = target.read_text(encoding="utf-8")
        self.assertEqual(text.count(hooks.PROJECT_MARK), 2)  # the opening and the closing line
        self.assertLess(text.index(hooks.PROJECT_MARK), text.index("echo existing hook"))
        done = self.commit(self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("existing hook", done.stdout + done.stderr)

    def test_a_folder_without_brain_is_refused(self) -> None:
        shutil.rmtree(self.repo / "brain")
        with self.assertRaises(SystemExit):
            hooks.project_hook(self.repo)


if __name__ == "__main__":
    unittest.main()
