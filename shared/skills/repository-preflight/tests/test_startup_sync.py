"""Session start hook: syncs origin without merging, hears upstream on the skill-exchange cadence
(SMART-RULE-0034, SMART-RULE-0032), speaks in the host's SessionStart shape and never fails a session.

Fictional repositories in temporary folders only (SMART-RULE-0008)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import hooks  # noqa: E402

IDENTITY = ["-c", "user.name=Example Writer", "-c", "user.email=writer@example.com"]
NOW = "2026-01-20T09:00:00+10:00"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *IDENTITY, *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def commit(repo: Path, name: str, text: str = "x\n") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change " + name)


class Brain:
    """A brain root with an origin, a second clone that pushes to it, and an upstream."""

    def __init__(self, base: Path):
        self.root, self.origin, self.other, self.upstream = (base / n for n in ("brain", "origin.git", "other", "up.git"))
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "shared").mkdir()
        (self.root / ".gitignore").write_text("memory/\n.claude/\n", encoding="utf-8")
        commit(self.root, "CONTRACT.md", "fictional contract\n")
        git(base, "clone", "-q", "--bare", str(self.root), str(self.origin))
        git(base, "clone", "-q", "--bare", str(self.root), str(self.upstream))
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "branch", "-q", "--set-upstream-to=origin/main")
        git(base, "clone", "-q", str(self.origin), str(self.other))

    def push_from_other(self, name: str) -> None:
        commit(self.other, name)
        git(self.other, "push", "-q", "origin", "main")

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def state(self) -> Path:
        return self.root / "memory" / "skills" / "skill-exchange" / "state.json"


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_current_says_nothing(self):
        self.assertEqual(hooks.session_start(self.brain.root, now=NOW), "")
        self.assertEqual(hooks.session_start_output(""), "")

    def test_untracked_files_keep_the_message_silent(self):
        (self.brain.root / "scratch.txt").write_text("someone else", encoding="utf-8")
        self.assertEqual(hooks.session_start(self.brain.root, now=NOW), "")
        record = Path(git(self.brain.root, "rev-parse", "--absolute-git-dir")) / hooks.UNTRACKED
        self.assertEqual(record.read_text(encoding="utf-8"), "scratch.txt")

    def test_resume_keeps_the_sessions_own_snapshot(self):
        hooks.session_start(self.brain.root, now=NOW)
        (self.brain.root / "mine.txt").write_text("made in the session", encoding="utf-8")
        hooks.session_start(self.brain.root, now=NOW, source="resume")
        record = Path(git(self.brain.root, "rev-parse", "--absolute-git-dir")) / hooks.UNTRACKED
        self.assertNotIn("mine.txt", record.read_text(encoding="utf-8"))

    def test_behind_only_is_fast_forwarded(self):
        self.brain.push_from_other("notes.md")
        message = hooks.session_start(self.brain.root, now=NOW)
        self.assertEqual(self.brain.head(), git(self.brain.origin, "rev-parse", "main"))
        self.assertIn("fast-forwarded 1 commit(s)", message)

    def test_diverged_is_reported_and_left_unchanged(self):
        self.brain.push_from_other("theirs.md")
        commit(self.brain.root, "mine.md")
        before = self.brain.head()
        message = hooks.session_start(self.brain.root, now=NOW)
        self.assertEqual(self.brain.head(), before)
        self.assertIn("diverged", message)
        self.assertIn("first reply", message)

    def test_unreachable_origin_is_one_line_and_the_hook_exits_0(self):
        git(self.brain.root, "remote", "set-url", "origin", str(Path(self.tmp.name) / "missing.git"))
        run = subprocess.run([sys.executable, str(HERE / "scripts" / "hooks.py"), "session-start",
                              "--root", str(self.brain.root)], capture_output=True, text=True,
                             encoding="utf-8", stdin=subprocess.DEVNULL)
        self.assertEqual(run.returncode, 0, run.stderr)
        output = json.loads(run.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertIn("unreachable", output["additionalContext"])

    def test_an_error_becomes_a_line_and_exit_0(self):
        run = subprocess.run([sys.executable, str(HERE / "scripts" / "hooks.py"), "session-start",
                              "--root", str(Path(self.tmp.name) / "no-such-brain")], capture_output=True,
                             text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("could not", json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"])


class UpstreamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self.tmp.name))
        git(self.brain.root, "remote", "add", "upstream", str(self.brain.upstream))
        (self.brain.root / "memory").mkdir()
        work = Path(self.tmp.name) / "up-work"
        git(Path(self.tmp.name), "clone", "-q", str(self.brain.upstream), str(work))
        commit(work, "CONTRACT.md", "a governance change\n")
        commit(work, "shared/skills/example/SKILL.md", "a skill change\n")
        git(work, "push", "-q", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_upstream_ahead_is_counted_never_merged_and_the_check_is_recorded(self):
        before = self.brain.head()
        message = hooks.session_start(self.brain.root, now=NOW)
        self.assertEqual(self.brain.head(), before)
        self.assertIn("2 upstream commit(s) not in HEAD", message)
        self.assertIn("1 touch protected governance paths", message)
        self.assertIn("git -C", message)
        self.assertEqual(json.loads(self.brain.state().read_text(encoding="utf-8"))["last_checked"], NOW)

    def test_cadence_not_due_means_no_fetch(self):
        self.brain.state().parent.mkdir(parents=True, exist_ok=True)
        self.brain.state().write_text(json.dumps({"last_checked": "2026-01-18T09:00:00+10:00"}), encoding="utf-8")
        self.assertEqual(hooks.session_start(self.brain.root, now=NOW), "")
        refs = git(self.brain.root, "for-each-ref", "--format=%(refname)", "refs/remotes/upstream")
        self.assertEqual(refs, "")


class EventsTest(unittest.TestCase):
    def test_host_settings_hold_startup_resume_and_compact(self):
        start = hooks.host_settings()["hooks"]["SessionStart"]
        self.assertEqual({entry["matcher"] for entry in start}, {"startup", "resume", "compact"})
        commands = {entry["matcher"]: entry["hooks"][0]["command"] for entry in start}
        self.assertTrue(commands["startup"].endswith("hooks.py\" session-start"))
        self.assertEqual(commands["startup"], commands["resume"])
        self.assertTrue(commands["compact"].endswith("hooks.py\" post-compact"))

    def test_install_writes_the_host_settings_and_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": []}}),
                                                            encoding="utf-8")
            hooks.install(root)
            written = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(written["permissions"], {"allow": []})
            self.assertIn("SessionStart", written["hooks"])


if __name__ == "__main__":
    unittest.main()
