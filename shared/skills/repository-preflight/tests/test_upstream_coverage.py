"""Protected-governance coverage for a recorded upstream merge (SMART-RULE-0032, CONTRACT §13.2).

A protected change that arrived in a merge of `upstream/main` recorded in
`/memory/governance/upstream-merges.md` is covered when the record names the file and the merge's
upstream commit is an ancestor of HEAD, with the file as that commit brought it in. Fictional data.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from preflight_base import Result  # noqa: E402
from preflight_governance import validate_governance  # noqa: E402

HAS_GIT = shutil.which("git") is not None
NOT_COVERED = "not covered by an accepted proposal"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "core.hooksPath=", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, relative: str, text: str) -> None:
    (repo / relative).parent.mkdir(parents=True, exist_ok=True)
    (repo / relative).write_text(text, encoding="utf-8")


@unittest.skipIf(not HAS_GIT, "git not available")
class UpstreamMergeCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.tmp.name) / "brain"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        write(root, "RULES.md", "# Rules\n\nThe fictional rule one.\n")
        write(root, "AGENTS.md", "# Agents\n")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "start")
        git(root, "update-ref", "refs/remotes/origin/main", git(root, "rev-parse", "HEAD"))
        memory = root / "memory"
        memory.mkdir()
        git(memory, "init", "-q", "-b", "main")
        write(memory, "README.md", "memory\n")
        git(memory, "add", "-A")
        git(memory, "commit", "-qm", "start")
        # The proposal behind the upstream change, implemented long before this merge.
        self.proposal = root / "governance" / "proposals" / "upstream-rule.md"
        self.records = {self.proposal: {
            "type": "governance_proposal", "status": "implemented", "accepted_by": "brain-owner",
            "accepted_at": "2020-01-01T10:00:00+10:00", "implemented_at": "2020-01-01T11:00:00+10:00",
            "target_files": ["/RULES.md"]}}

    def tearDown(self):
        self.tmp.cleanup()

    def merge_upstream(self) -> str:
        """Merge a fictional upstream commit that changes RULES.md; its commit."""
        root = self.root
        git(root, "checkout", "-qb", "upstream-side", "origin/main")
        write(root, "RULES.md", "# Rules\n\nThe fictional rule one, as upstream accepted it.\n")
        git(root, "commit", "-qam", "upstream rule change")
        commit = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-q", "main")
        git(root, "merge", "-q", "--no-ff", "-m", "Merge upstream/main", commit)
        return commit

    def record(self, commit: str, files: str) -> None:
        write(self.root / "memory", "governance/upstream-merges.md",
              "---\nid: memory-governance-upstream-merges\ntype: register\n---\n\n# Upstream merges\n\n"
              f"## 2026-01-01T10:00:00+10:00 – mechanics\n\n- upstream commit: {commit}\n"
              "- contract_version: 1.0.0 to 1.0.0\n"
              f"- files changed (1): {files}\n- protected governance (1): {files}\n")

    def errors(self) -> list[str]:
        result = Result()
        validate_governance(self.root, self.records, result, datetime.now().astimezone())
        return [error for error in result.errors if NOT_COVERED in error]

    def test_a_recorded_upstream_merge_outside_its_proposal_window_is_covered(self):
        self.record(self.merge_upstream(), "RULES.md")
        self.assertEqual(self.errors(), [])

    def test_the_same_change_without_a_record_is_refused(self):
        self.merge_upstream()
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("/RULES.md", self.errors()[0])

    def test_a_record_naming_a_different_file_does_not_cover(self):
        self.record(self.merge_upstream(), "AGENTS.md")
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("/RULES.md", self.errors()[0])

    def test_an_ordinary_local_change_without_a_proposal_is_refused(self):
        self.records = {}
        write(self.root, "RULES.md", "# Rules\n\nA fictional local rule.\n")
        git(self.root, "commit", "-qam", "local rule")
        self.assertEqual(len(self.errors()), 1)

    def test_a_local_edit_on_top_of_a_recorded_merge_is_refused(self):
        self.record(self.merge_upstream(), "RULES.md")
        write(self.root, "RULES.md", "# Rules\n\nA fictional local rule, edited after the merge.\n")
        self.assertEqual(len(self.errors()), 1)


if __name__ == "__main__":
    unittest.main()
