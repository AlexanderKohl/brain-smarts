"""The join nudge of sync.py: a cloned shared project this brain has not joined is reported.

An invented brain root, memory and project in a temporary folder (fictional owner Sam). Run from
the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/scripts/tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sync  # noqa: E402

MANIFEST = """---
id: garden-app-joining
title: Joining Garden Planner
type: joining_manifest
contract: /CONTRACT.md
joining:
  repository: https://example.com/sam/garden-app.git
  working_branch: main
  boards:
    - id: garden
      label: Garden Planner
      status: brain/status
---
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class NudgeTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="nudge-"))
        self.root = self.base / "brain"
        self.projects = self.base / "projects"
        write(self.root / "CONTRACT.md", "---\nid: c\n---\n")
        write(self.root / "memory/OWNER.md", f"---\nowner_short_name: Sam\nproject_repos_root: {self.projects}\n---\n")
        write(self.root / "memory/skills/owner-board/config/boards.json", json.dumps({"boards": []}))
        repo = self.projects / "garden-app"
        (repo / ".git").mkdir(parents=True)             # a clone, as far as the nudge looks
        write(repo / "brain" / "JOINING.md", MANIFEST)
        write(self.projects / "plain-app" / ".git" / "HEAD", "ref\n")   # no manifest: never mentioned

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_an_unjoined_project_is_nudged_without_failing_the_sync(self):
        found = sync.not_joined(self.root)
        self.assertEqual([(n["name"], n["state"], n["ok"]) for n in found], [("garden-app", "not joined", True)])
        self.assertIn("no pointer node in memory; shared board(s) not registered: garden", found[0]["detail"])
        self.assertIn("join-project/scripts/join.py", found[0]["detail"])

    def test_a_joined_project_is_not_nudged(self):
        write(self.root / "memory/projects/garden-planner/README.md",
              "---\nid: g\nrepo_url: https://example.com/sam/garden-app\nlocal_path: garden-app\n---\n")
        write(self.root / "memory/skills/owner-board/config/boards.json",
              json.dumps({"boards": [{"id": "garden", "label": "Garden", "status": "garden-app:brain/status"}]}))
        self.assertEqual(sync.not_joined(self.root), [])

    def test_a_brain_without_a_projects_root_has_no_nudge(self):
        write(self.root / "memory/OWNER.md", "---\nowner_short_name: Sam\n---\n")
        self.assertEqual(sync.not_joined(self.root), [])


if __name__ == "__main__":
    unittest.main()
