"""Session start names a failed latest CI run (ci_status.py) and says nothing otherwise.

A fake `gh` on PATH answers from FAKE_GH_MODE; fictional repositories in temporary folders only
(SMART-RULE-0008). `origin` is a GitHub URL that Git rewrites to a local bare repository
(url.<path>.insteadOf), so the sync stays offline while the check sees a GitHub remote."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import ci_status  # noqa: E402
import hooks  # noqa: E402

IDENTITY = ["-c", "user.name=Example Writer", "-c", "user.email=writer@example.com"]
NOW = "2026-01-20T09:00:00+10:00"
BRAIN_URL = "https://github.com/example-owner/example-brain.git"
PROJECT_URL = "https://github.com/example-owner/example-project"
SHA = "0123456789abcdef0123456789abcdef01234567"

FAKE_GH = '''import json, os, sys, time
# One file per call: two calls appending to one file at once can lose a line on Windows.
with open(os.path.join(os.environ["FAKE_GH_LOG"], str(os.getpid()) + ".json"), "w", encoding="utf-8") as log:
    json.dump(sys.argv[1:], log)
mode = os.environ.get("FAKE_GH_MODE", "passed")
if mode == "slow":
    time.sleep(20)
if mode == "signed-out":
    sys.stderr.write("To get started with GitHub CLI, please run:  gh auth login\\n")
    sys.exit(4)
runs = {"failed": [{"status": "completed", "conclusion": "failure", "workflowName": "Example tests"}],
        "passed": [{"status": "completed", "conclusion": "success", "workflowName": "Example tests"}],
        "running": [{"status": "in_progress", "conclusion": "", "workflowName": "Example tests"}],
        "none": []}[mode]
shas = json.loads(os.environ.get("FAKE_GH_SHAS") or "{}")
asked = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else ""
for run in runs:
    run.update(headSha=shas.get(asked, "%s"), url="https://github.com/example-owner/example/actions/runs/1")
print(json.dumps(runs))
''' % SHA


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *IDENTITY, *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def repository(path: Path, url: str) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("fictional\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "start")
    git(path, "remote", "add", "origin", url)
    return path


class CiStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = repository(base / "brain", BRAIN_URL)
        (self.root / "shared").mkdir()
        (self.root / "CONTRACT.md").write_text("fictional contract\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("memory/\n.claude/\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "contract")
        bare = base / "origin.git"
        git(base, "clone", "-q", "--bare", str(self.root), str(bare))
        git(self.root, "config", f"url.{bare.as_posix()}.insteadOf", BRAIN_URL)
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "branch", "-q", "--set-upstream-to=origin/main")
        self.project = repository(base / "project", PROJECT_URL)
        (self.project / "src").mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        (self.bin / "fake_gh.py").write_text(FAKE_GH, encoding="utf-8")
        if os.name == "nt":
            (self.bin / "gh.cmd").write_text(f'@"{sys.executable}" "%~dp0fake_gh.py" %*\r\n', encoding="utf-8")
        else:
            gh = self.bin / "gh"
            gh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.bin / "fake_gh.py"}" "$@"\n', encoding="utf-8")
            gh.chmod(0o755)
        self.log = base / "gh-calls"
        self.log.mkdir()
        self.env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                                                "FAKE_GH_LOG": str(self.log)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def start(self, mode: str, budget: float = hooks.BUDGET_SECONDS, at_tip: bool = True) -> str:
        os.environ["FAKE_GH_MODE"] = mode
        shas = {"example-owner/example-brain": git(self.root, "rev-parse", "HEAD"),
                "example-owner/example-project": git(self.project, "rev-parse", "HEAD")}
        os.environ["FAKE_GH_SHAS"] = json.dumps(shas if at_tip else {})
        return hooks.session_start(self.root, now=NOW, budget=budget, cwd=str(self.project / "src"))

    def calls(self) -> list[list[str]]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.log.iterdir())]

    def test_failed_run_is_one_line_per_repository(self):
        message = self.start("failed")
        lines = [line for line in message.splitlines() if "CI run" in line]
        self.assertEqual(len(lines), 2, message)
        tip = git(self.root, "rev-parse", "HEAD")[:7]
        self.assertIn(f"mechanics: the latest CI run on main failed – Example tests at {tip}: "
                      "https://github.com/example-owner/example/actions/runs/1", lines)
        self.assertTrue(any(line.startswith("project: ") for line in lines), lines)
        self.assertTrue(message.startswith(hooks.HEADER))
        repos = sorted(call[call.index("--repo") + 1] for call in self.calls())
        self.assertEqual(repos, ["example-owner/example-brain", "example-owner/example-project"])
        self.assertTrue(all(call[call.index("--branch") + 1] == "main" for call in self.calls()))

    def test_a_failure_on_an_older_commit_is_silent(self):
        # Checks that moved off GitHub leave an old failed run as the latest; it is not news.
        self.assertEqual(self.start("failed", at_tip=False), "")
        self.assertEqual(len(self.calls()), 2)

    def test_passed_running_or_no_run_is_silent(self):
        for mode in ("passed", "running", "none"):
            with self.subTest(mode=mode):
                self.assertEqual(self.start(mode), "")
        self.assertEqual(len(self.calls()), 6)

    def test_gh_signed_out_is_silent(self):
        self.assertEqual(self.start("signed-out"), "")
        self.assertEqual(len(self.calls()), 2)

    def test_gh_missing_is_silent(self):
        real = ci_status.shutil.which
        with mock.patch.object(ci_status.shutil, "which",
                               side_effect=lambda name, *a, **k: None if name == "gh" else real(name, *a, **k)):
            self.assertEqual(self.start("failed"), "")
        self.assertEqual(self.calls(), [])

    def test_gh_timing_out_is_silent_within_the_budget(self):
        with mock.patch.object(ci_status, "TIMEOUT_SECONDS", 1.0):
            began = time.monotonic()
            self.assertEqual(self.start("slow", budget=5.0), "")
            self.assertLess(time.monotonic() - began, 5.0)

    def test_the_whole_budget_bounds_a_slow_gh(self):
        # A per-call timeout longer than the budget still stops at the hook's deadline.
        began = time.monotonic()
        self.assertEqual(self.start("slow", budget=3.0), "")
        self.assertLess(time.monotonic() - began, 4.5)

    def test_a_repository_without_a_github_origin_is_not_asked(self):
        git(self.project, "remote", "set-url", "origin", "https://example.com/example/project.git")
        self.start("failed")
        self.assertEqual([c[c.index("--repo") + 1] for c in self.calls()], ["example-owner/example-brain"])

    def test_the_hook_reads_cwd_from_its_input_and_exits_0(self):
        run = subprocess.run([sys.executable, str(HERE / "scripts" / "hooks.py"), "session-start",
                              "--root", str(self.root)], capture_output=True, text=True, encoding="utf-8",
                             input=json.dumps({"source": "startup", "cwd": str(self.project)}),
                             env={**os.environ, "FAKE_GH_MODE": "failed", "FAKE_GH_SHAS": json.dumps(
                                 {"example-owner/example-project": git(self.project, "rev-parse", "HEAD")})})
        self.assertEqual(run.returncode, 0, run.stderr)
        context = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("project: the latest CI run on main failed", context)


if __name__ == "__main__":
    unittest.main()
