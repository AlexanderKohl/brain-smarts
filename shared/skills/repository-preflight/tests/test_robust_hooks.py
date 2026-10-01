"""Robust hooks: each repository's own hook finds the brain or steps aside; checks are scoped to it."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "shared" / "skills" / "repository-preflight" / "scripts"))
import hooks  # noqa: E402

SH = shutil.which("sh")


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=repo,
                          capture_output=True, text=True)


class RobustHooksTest(unittest.TestCase):
    @unittest.skipIf(SH is None, "no POSIX shell")
    def test_a_repository_cloned_alone_still_commits(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "library"
            (repo / ".githooks").mkdir(parents=True)
            shutil.copy(ROOT / "library" / ".githooks" / "pre-commit" if (ROOT / "library").is_dir()
                        else ROOT / "shared/templates/memory-skeleton/.githooks/pre-commit", repo / ".githooks" / "pre-commit")
            git(repo, "init", "-q")
            git(repo, "config", "core.hooksPath", ".githooks")
            (repo / "a.md").write_text("x\n", encoding="utf-8")
            git(repo, "add", "a.md")
            result = git(repo, "commit", "-qm", "alone")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("brain checks skipped", result.stderr)

    def test_the_layer_is_the_repository_being_committed(self):
        self.assertEqual(hooks.layer_of(ROOT / "memory", ROOT), "memory")
        self.assertEqual(hooks.layer_of(ROOT / "library", ROOT), "library")
        self.assertEqual(hooks.layer_of(ROOT, ROOT), "mechanics")

    def test_preflight_layer_reports_only_that_repository(self):
        run = subprocess.run([sys.executable, str(ROOT / "shared/skills/repository-preflight/scripts/preflight.py"),
                              "--root", str(ROOT), "--layer", "library", "--json"], capture_output=True, text=True,
                             encoding="utf-8")
        import json
        payload = json.loads(run.stdout)
        self.assertTrue(all("/memory/" not in e for e in payload["errors"] + payload["warnings"]))


    def test_a_proposal_branch_may_hold_its_draft_diff(self):
        import re
        # preflight.py and the modules split out of it, read as one text.
        scripts = ROOT / "shared/skills/repository-preflight/scripts"
        text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(scripts.glob("preflight*.py")))
        self.assertIn('branch.startswith("proposal/")', text)
        self.assertRegex(text, re.compile(r'status"\) in \("proposed", "draft"\)'))


if __name__ == "__main__":
    unittest.main()
