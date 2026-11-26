"""cleanup.py: the weekly report reads sizes, dates, warnings and commit messages as it says it does."""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cleanup  # noqa: E402

TODAY = datetime.date(2026, 3, 20)


class SizeTest(unittest.TestCase):
    def test_a_file_is_over_near_or_neither(self) -> None:
        self.assertEqual(cleanup.size_class(28_001), "over")
        self.assertEqual(cleanup.size_class(28_000), "near")
        self.assertEqual(cleanup.size_class(25_201), "near")
        self.assertIsNone(cleanup.size_class(25_200))
        self.assertIsNone(cleanup.size_class(0))


class HandoverDateTest(unittest.TestCase):
    def test_the_newest_past_date_at_the_top_of_the_section_counts(self) -> None:
        text = ("# State\n\n## Current position\n\nWritten 2026-03-19.\n\n## Handover\n\n"
                "**Checkpoint of 3 February 2026, 13:03:** testing is at 1.2.0; review by 2026-12-31.\n\n"
                "- an earlier note of 2026-01-15\n\n## Handover prompt\n\nRead it. Written 2026-03-18.\n")
        self.assertEqual(cleanup.handover_date(text, TODAY), datetime.date(2026, 2, 3))

    def test_a_file_without_the_section_or_without_a_date_has_none(self) -> None:
        self.assertIsNone(cleanup.handover_date("# State\n\n## Current position\n\n2026-03-01\n", TODAY))
        self.assertIsNone(cleanup.handover_date("## Handover\n\nNothing dated, and 31 February 2026 is no date.\n", TODAY))


class WarningKindTest(unittest.TestCase):
    def test_warnings_about_different_files_are_one_kind(self) -> None:
        a = cleanup.warning_kind("WARNING: /memory/projects/one/README.md: undocumented immediate folders: tasks")
        b = cleanup.warning_kind("WARNING: /memory/skills/two/README.md: undocumented immediate folders: config, runs")
        self.assertEqual(a, b)
        self.assertEqual(a, "undocumented immediate folders")

    def test_names_and_paths_inside_the_message_do_not_split_a_kind(self) -> None:
        a = cleanup.warning_kind("WARNING: /memory/projects/one: example-repo:brain/tasks/open/TASK-1.md: the claim of thread-a lapsed (older than 6 h): claim again")
        b = cleanup.warning_kind("WARNING: /memory/projects/two: other-repo:brain/tasks/open/TASK-2.md: the claim of thread-b lapsed (older than 6 h): claim again")
        self.assertEqual(a, b)
        c = cleanup.warning_kind("WARNING: /memory/a.md: source_refs reference /temp/runs/W01.result.md not checked: the target is absent")
        self.assertEqual(c, "source_refs reference <path> not checked")


class ReasonTest(unittest.TestCase):
    def test_a_body_counts_and_trailers_do_not(self) -> None:
        trailers = "\n\nTool: Example Host\nCo-Authored-By: Example Model <model@example.com>\n"
        self.assertFalse(cleanup.gives_reason("Fix the total" + trailers))
        self.assertFalse(cleanup.gives_reason("Fix the total\n\nSee above." + trailers))
        self.assertTrue(cleanup.gives_reason("Fix the total\n\nThe sum left out the delivery line, so every quote was low." + trailers))

    def test_a_commit_a_script_wrote_is_left_out(self) -> None:
        self.assertIsNone(cleanup.gives_reason("Finish: release notes and boards rebuilt\n\nTool: Example Host\n"))
        self.assertIsNone(cleanup.gives_reason("Merge origin/main into session/example\n"))


class MergedBranchesTest(unittest.TestCase):
    def test_only_merged_session_branches_not_checked_out_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            env = dict(os.environ, GIT_AUTHOR_NAME="Example", GIT_AUTHOR_EMAIL="author@example.com",
                       GIT_COMMITTER_NAME="Example", GIT_COMMITTER_EMAIL="author@example.com")

            def run(*args: str) -> None:
                subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=", *args], check=True, capture_output=True, env=env)

            run("init", "-q", "-b", "main")
            (repo / "a.txt").write_text("one\n", encoding="utf-8")
            run("add", "a.txt")
            run("commit", "-q", "-m", "first")
            subprocess.run(["git", "init", "-q", "--bare", str(Path(tmp) / "origin.git")], check=True, capture_output=True)
            run("remote", "add", "origin", str(Path(tmp) / "origin.git"))
            run("push", "-q", "-u", "origin", "main")
            run("branch", "session/merged")
            run("branch", "other/merged")
            run("checkout", "-q", "-b", "session/open")
            (repo / "a.txt").write_text("two\n", encoding="utf-8")
            run("commit", "-q", "-am", "second")
            run("checkout", "-q", "main")
            run("worktree", "add", "-q", str(Path(tmp) / "copy"), "-b", "session/in-use")
            local, remote = cleanup.merged_session_branches(repo)
            self.assertEqual(local, ["session/merged"])
            self.assertEqual(remote, 0)


if __name__ == "__main__":
    unittest.main()
