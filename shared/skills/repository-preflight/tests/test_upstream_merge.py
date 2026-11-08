"""Follow upstream (SMART-RULE-0032, CONTRACT §13.2): with `follow_upstream` on, sync.py and the
session-start hook merge `upstream/main` with the SMART-RULE-0034 routine, record it and say so;
with it off or absent nothing is merged. Also: what today's preflight makes of protected governance
arriving through such a merge.

Fictional repositories in temporary folders only (SMART-RULE-0008). The fictional brain's
preflight is a stand-in that fails when the copy holds a file named FAIL-PREFLIGHT.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import hooks  # noqa: E402
import preflight_governance  # noqa: E402
import sync  # noqa: E402
import upstream_merge  # noqa: E402
from preflight_base import Result  # noqa: E402

NOW = "2026-01-20T09:00:00+10:00"
ENV = {"GIT_AUTHOR_NAME": "Example Writer", "GIT_AUTHOR_EMAIL": "writer@example.com",
       "GIT_COMMITTER_NAME": "Example Writer", "GIT_COMMITTER_EMAIL": "writer@example.com",
       "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
       "BRAIN_CO_AUTHOR": "Example Model <model@example.com>"}
STAND_IN = (
    "import sys, pathlib\n"
    "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1])\n"
    "if (root / 'FAIL-PREFLIGHT').exists():\n"
    "    print('FAIL fictional check'); print('ERROR: fictional failure'); sys.exit(1)\n"
    "print('PASS fictional check')\n"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def commit(repo: Path, name: str, text: str = "x\n") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change " + name)


def contract(version: str, words: str = "fictional contract") -> str:
    return f"---\ncontract_version: {version}\n---\n\n{words}\n"


class Brain:
    """Mechanics and memory, each with a bare origin; the mechanics also with an upstream."""

    def __init__(self, base: Path, follow: bool | None):
        self.base = base
        self.root, self.origin, self.upstream = base / "brain", base / "origin.git", base / "up.git"
        self.memory, self.memory_origin = self.root / "memory", base / "memory.git"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".gitignore").write_text("memory/\nlibrary/\n.claude/\n", encoding="utf-8")
        (self.root / "shared/skills/repository-preflight/scripts").mkdir(parents=True)
        (self.root / "shared/skills/repository-preflight/scripts/preflight.py").write_text(STAND_IN, encoding="utf-8")
        commit(self.root, "CONTRACT.md", contract("9.1.0"))
        commit(self.root, "notes.md", "first\n")
        git(base, "clone", "-q", "--bare", str(self.root), str(self.upstream))
        git(base, "clone", "-q", "--bare", str(self.root), str(self.origin))
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "branch", "-q", "--set-upstream-to=origin/main")
        git(self.root, "remote", "add", "upstream", str(self.upstream))
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")
        self.memory.mkdir()
        git(self.memory, "init", "-q", "-b", "main")
        settings = {} if follow is None else {"follow_upstream": follow}
        commit(self.memory, "skills/skill-exchange/config/settings.json", json.dumps(settings))
        git(base, "clone", "-q", "--bare", str(self.memory), str(self.memory_origin))
        git(self.memory, "remote", "add", "origin", str(self.memory_origin))
        git(self.memory, "fetch", "-q", "origin")
        git(self.memory, "branch", "-q", "--set-upstream-to=origin/main")
        self.work = base / "up-work"                         # the upstream maintainer's clone
        git(base, "clone", "-q", str(self.upstream), str(self.work))

    def from_upstream(self, name: str, text: str = "x\n") -> None:
        commit(self.work, name, text)
        git(self.work, "push", "-q", "origin", "main")

    def own_commit(self, name: str, text: str = "mine\n") -> None:
        commit(self.root, name, text)
        git(self.root, "push", "-q", "origin", "main")

    def head(self, repo: Path | None = None) -> str:
        return git(repo or self.root, "rev-parse", "HEAD")

    def record(self) -> Path:
        return self.memory / "governance" / "upstream-merges.md"


class Fixture(unittest.TestCase):
    follow: bool | None = True

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self.tmp.name), self.follow)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def sync_main(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(["--root", str(self.brain.root)])
        return code, out.getvalue()


class FollowingOn(Fixture):
    def test_a_clean_merge_is_merged_recorded_pushed_and_fast_forwarded(self):
        self.brain.own_commit("mine.md")
        self.brain.from_upstream("CONTRACT.md", contract("9.2.0", "a fictional governance change"))
        self.brain.from_upstream("shared/skills/example/SKILL.md")
        wanted = git(self.brain.upstream, "rev-parse", "main")
        code, out = self.sync_main()
        self.assertEqual(code, 0, out)
        self.assertIn("mechanics: upstream merged", out)
        self.assertEqual(len([l for l in out.splitlines() if "upstream merged" in l]), 1)
        root = self.brain.root
        self.assertEqual(self.brain.head(), git(self.brain.origin, "rev-parse", "main"))
        self.assertEqual(len(git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()), 3)   # a merge commit
        git(root, "merge-base", "--is-ancestor", wanted, "HEAD")
        self.assertIn("9.2.0", (root / "CONTRACT.md").read_text(encoding="utf-8"))
        record = self.brain.record().read_text(encoding="utf-8")
        self.assertTrue(record.startswith("---\n"))
        for words in (wanted, "9.1.0 to 9.2.0", "shared/skills/example/SKILL.md", "protected governance (1): CONTRACT.md"):
            self.assertIn(words, record)
        self.assertEqual(self.brain.head(self.brain.memory), git(self.brain.memory_origin, "rev-parse", "main"))
        self.assertEqual(git(root, "worktree", "list").count("\n"), 0)            # the copy is gone

    def test_a_second_merge_appends_to_the_record(self):
        self.brain.from_upstream("one.md")
        self.sync_main()
        self.brain.from_upstream("two.md")
        self.sync_main()
        self.assertEqual(self.brain.record().read_text(encoding="utf-8").count("\n## "), 2)

    def test_nothing_new_upstream_merges_nothing(self):
        before = self.brain.head()
        code, out = self.sync_main()
        self.assertEqual((code, self.brain.head()), (0, before))
        self.assertNotIn("upstream", out)
        self.assertFalse(self.brain.record().exists())

    def test_a_hand_written_conflict_stops_and_leaves_the_merge_in_the_copy(self):
        self.brain.own_commit("notes.md", "mine\n")
        self.brain.from_upstream("notes.md", "theirs\n")
        before, origin = self.brain.head(), git(self.brain.origin, "rev-parse", "main")
        code, out = self.sync_main()
        self.assertEqual(code, 1)
        self.assertIn("upstream merge stopped", out)
        self.assertIn("notes.md", out)
        self.assertEqual((self.brain.head(), git(self.brain.origin, "rev-parse", "main")), (before, origin))
        copies = [p for p in (self.brain.base / "brain-sessions").iterdir()]
        self.assertEqual(len(copies), 1)
        self.assertTrue(git(copies[0], "rev-parse", "-q", "--verify", "MERGE_HEAD"))
        self.assertFalse(self.brain.record().exists())

    def test_a_failing_preflight_pushes_nothing(self):
        self.brain.from_upstream("FAIL-PREFLIGHT")
        before = self.brain.head()
        origin, memory = git(self.brain.origin, "rev-parse", "main"), git(self.brain.memory_origin, "rev-parse", "main")
        code, out = self.sync_main()
        self.assertEqual(code, 1)
        self.assertIn("upstream merge stopped", out)
        self.assertIn("preflight", out)
        self.assertEqual(git(self.brain.origin, "rev-parse", "main"), origin)
        self.assertEqual(git(self.brain.memory_origin, "rev-parse", "main"), memory)
        self.assertEqual(self.brain.head(), before)
        self.assertFalse(self.brain.record().exists())


class FollowingOff(Fixture):
    follow = False

    def test_off_merges_nothing(self):
        self.brain.from_upstream("theirs.md")
        before = self.brain.head()
        code, out = self.sync_main()
        self.assertEqual((code, self.brain.head()), (0, before))
        self.assertNotIn("upstream", out)

    def test_off_the_hook_reports_and_does_not_ask_b4(self):
        self.brain.from_upstream("theirs.md")
        with mock.patch.object(hooks, "install", lambda root: []):
            message = hooks.session_start(self.brain.root, now=NOW, budget=120)
        self.assertIn("not merged", message)
        self.assertNotIn("Follow the original automatically?", message)


class FollowingAbsent(Fixture):
    follow = None

    def test_absent_merges_nothing(self):
        self.brain.from_upstream("theirs.md")
        before = self.brain.head()
        code, _ = self.sync_main()
        self.assertEqual((code, self.brain.head()), (0, before))

    def test_absent_with_an_upstream_the_hook_asks_b4_once(self):
        with mock.patch.object(hooks, "install", lambda root: []):
            message = hooks.session_start(self.brain.root, now=NOW, budget=120)
        self.assertIn("Follow the original automatically?", message)
        self.assertIn("follow_upstream", message)
        self.assertIn("SETUP.md step B4", message)


class Hook(Fixture):
    def test_the_hook_merges_and_gives_the_summary_for_the_first_reply(self):
        self.brain.from_upstream("CONTRACT.md", contract("9.2.0", "a fictional governance change"))
        with mock.patch.object(hooks, "install", lambda root: []):
            message = hooks.session_start(self.brain.root, now=NOW, budget=120)
        self.assertIn(hooks.HEADER, message)
        self.assertIn("mechanics: upstream merged", message)
        self.assertIn("9.1.0 to 9.2.0", message)
        self.assertNotIn("Follow the original automatically?", message)
        self.assertEqual(self.brain.head(), git(self.brain.origin, "rev-parse", "main"))

    def test_without_the_time_the_merge_is_pending_with_its_command(self):
        self.brain.from_upstream("theirs.md")
        before = self.brain.head()
        with mock.patch.object(hooks, "install", lambda root: []), \
                mock.patch.object(upstream_merge, "MERGE_SECONDS", 10 ** 6):
            message = hooks.session_start(self.brain.root, now=NOW, budget=120)
        self.assertIn("upstream merge pending", message)
        self.assertIn("sync.py", message)
        self.assertEqual(self.brain.head(), before)


def stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class PreflightCoverage(unittest.TestCase):
    """Today's protected-governance check against a merge of `upstream/main` that brings a rule
    change together with its accepted proposal (the upstream maintainer accepted and implemented it)."""

    ACCEPTED = datetime(2026, 1, 10, 9, 0, tzinfo=timezone(timedelta(hours=10)))

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self.tmp.name), True)
        self.meta = {"type": "governance_proposal", "status": "implemented", "accepted_by": "the upstream maintainer",
                     "accepted_at": stamp(self.ACCEPTED), "implemented_at": stamp(self.ACCEPTED + timedelta(minutes=20)),
                     "target_files": ["/RULES.md"]}
        proposal = "---\n" + "".join(f"{k}: {json.dumps(v)}\n" for k, v in self.meta.items()) + "---\n\nfictional\n"
        commit(self.brain.work, "governance/proposals/example.md", proposal)
        commit(self.brain.work, "RULES.md", "a fictional rule\n")
        git(self.brain.work, "push", "-q", "origin", "main")
        git(self.brain.root, "fetch", "-q", "upstream")
        self.records = {self.brain.root / "governance/proposals/example.md": self.meta}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def errors(self, now: datetime) -> list[str]:
        result = Result()
        preflight_governance.validate_governance(self.brain.root, self.records, result, now)
        return result.errors

    def test_within_the_proposals_window_it_passes_during_and_after_the_merge(self):
        within = self.ACCEPTED + timedelta(minutes=30)
        git(self.brain.root, "merge", "--no-commit", "--no-ff", "upstream/main")
        self.assertEqual(self.errors(within), [])
        git(self.brain.root, "commit", "-q", "--no-edit")
        self.assertEqual(self.errors(within), [])

    def test_after_the_window_it_refuses_during_and_after_the_merge(self):
        """The usual case: the owner's session starts more than an hour after upstream implemented it."""
        later = self.ACCEPTED + timedelta(days=3)
        git(self.brain.root, "merge", "--no-commit", "--no-ff", "upstream/main")
        self.assertTrue(any("/RULES.md: changed protected governance is not covered" in e for e in self.errors(later)))
        git(self.brain.root, "commit", "-q", "--no-edit")
        self.assertTrue(any("/RULES.md: changed protected governance is not covered" in e for e in self.errors(later)))


if __name__ == "__main__":
    unittest.main()
