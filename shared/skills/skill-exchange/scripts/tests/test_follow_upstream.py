"""Follow upstream in skill-exchange (SMART-RULE-0032): no "due" question while following, and the
upstream digest describes a completed merge. Fictional repositories in temporary folders only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import skill_exchange as sx  # noqa: E402

ENV = {"GIT_AUTHOR_NAME": "Example Writer", "GIT_AUTHOR_EMAIL": "writer@example.com",
       "GIT_COMMITTER_NAME": "Example Writer", "GIT_COMMITTER_EMAIL": "writer@example.com",
       "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}
NOW = "2026-01-20T09:00:00+10:00"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def commit(repo: Path, name: str) -> None:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change " + name)


class FollowUpstream(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        commit(self.root, "CONTRACT.md")
        self.settings = self.root / "memory/skills/skill-exchange/config/settings.json"
        self.settings.parent.mkdir(parents=True)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def follow(self, value) -> sx.Brain:
        self.settings.write_text(json.dumps({} if value is None else {"follow_upstream": value}), encoding="utf-8")
        return sx.Brain(str(self.root), NOW)

    def test_while_following_no_check_is_due(self):
        due, why = sx.due(self.follow(True))
        self.assertFalse(due)
        self.assertIn("follow", why)

    def test_off_or_absent_the_cadence_applies(self):
        self.assertTrue(sx.due(self.follow(False))[0])
        self.assertTrue(sx.due(self.follow(None))[0])

    def test_the_digest_describes_a_completed_merge(self):
        brain = self.follow(True)
        before = git(self.root, "rev-parse", "HEAD")
        commit(self.root, "RULES.md")
        commit(self.root, "shared/skills/example-new/SKILL.md")
        after = git(self.root, "rev-parse", "HEAD")
        changes = sx.merged_changes(brain, self.root, before, after)
        lines = sx.digest(brain, changes, merged=True)
        self.assertTrue(lines[0].startswith("Merged 2 upstream commit(s)"), lines)
        text = "\n".join(lines)
        self.assertIn("governance changed: RULES.md", text)
        self.assertIn("accepted by your follow_upstream setting", text)
        self.assertIn("example-new", text)
        self.assertNotIn("needs your acceptance", text)


if __name__ == "__main__":
    unittest.main()
