"""cleanup.py `tidy` and threads.py: only what is certainly no longer needed is removed, and nothing is reached through a link."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cleanup  # noqa: E402
import threads  # noqa: E402


def git_in(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="Example", GIT_AUTHOR_EMAIL="author@example.com",
               GIT_COMMITTER_NAME="Example", GIT_COMMITTER_EMAIL="author@example.com")
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=", *args], check=True, capture_output=True,
                          text=True, env=env)
    return done.stdout


def project(tmp: Path) -> Path:
    """A repository with a remote, a working branch `testing` and one commit on it."""
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(tmp / "origin.git")], check=True, capture_output=True)
    git_in(repo, "init", "-q", "-b", "testing")
    git_in(repo, "config", "user.email", "author@example.com")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    git_in(repo, "add", "a.txt", ".gitignore")
    git_in(repo, "commit", "-q", "-m", "first")
    git_in(repo, "remote", "add", "origin", str(tmp / "origin.git"))
    git_in(repo, "push", "-q", "-u", "origin", "testing")
    return repo


class ThreadsTest(unittest.TestCase):
    def test_a_host_record_says_which_threads_are_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "app" / "claude-code-sessions" / "account" / "organisation"
            folder.mkdir(parents=True)
            (folder / "local_one.json").write_text(json.dumps({"cliSessionId": "thread-one", "isArchived": True,
                                                                "title": "Done work", "lastActivityAt": 1755501000000}), encoding="utf-8")
            (folder / "local_two.json").write_text(json.dumps({"cliSessionId": "thread-two", "title": "Live work",
                                                                "lastAssistantCliSessionId": "thread-two-earlier"}), encoding="utf-8")
            (folder / "local_bad.json").write_text("not json", encoding="utf-8")
            known = threads.known([Path(tmp)])
            self.assertTrue(known["thread-one"].archived)
            self.assertFalse(known["thread-two"].archived)
            self.assertEqual(known["thread-two-earlier"].title, "Live work")
            self.assertIsNone(threads.known([Path(tmp) / "nothing-here"]))

    def test_a_copy_remembers_the_thread_that_started_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("CLAUDE_CODE_SESSION_ID")
            os.environ["CLAUDE_CODE_SESSION_ID"] = "thread-one"
            try:
                self.assertTrue(threads.record_copy(Path(tmp), "example-copy", "2026-03-20T09:00:00+10:00"))
            finally:
                if old is None:
                    del os.environ["CLAUDE_CODE_SESSION_ID"]
                else:
                    os.environ["CLAUDE_CODE_SESSION_ID"] = old
            self.assertEqual(threads.copy_thread(Path(tmp), "example-copy"), "thread-one")
            self.assertIsNone(threads.copy_thread(Path(tmp), "another-copy"))


class MarkersTest(unittest.TestCase):
    def test_only_the_marker_of_an_archived_thread_goes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "temp" / "conductor" / "compacted"
            folder.mkdir(parents=True)
            for name in ("archived", "live", "unknown"):
                (folder / f"{name}.json").write_text("{}", encoding="utf-8")
            known = {"archived": threads.Thread("archived", "", True, 0), "live": threads.Thread("live", "", False, 0)}
            self.assertEqual(cleanup.tidy_markers(Path(tmp), known), ["1 compaction marker(s) of archived threads removed"])
            self.assertEqual(sorted(p.stem for p in folder.iterdir()), ["live", "unknown"])
            self.assertEqual(cleanup.tidy_markers(Path(tmp), None), [])


class ArchiveListTest(unittest.TestCase):
    def test_only_live_threads_idle_for_a_week_are_put_to_the_owner(self) -> None:
        now = 1755501000.0 + 30 * 86400
        known = {"a": threads.Thread("a", "Old and live", False, now - 9 * 86400),
                 "b": threads.Thread("b", "Old and archived", True, now - 9 * 86400),
                 "c": threads.Thread("c", "Fresh and live", False, now - 3600)}
        lines = cleanup.threads_to_archive(known, now)
        self.assertEqual(len(lines), 2)
        self.assertIn("Old and live", lines[0])
        self.assertIn("1 thread(s)", lines[1])
        self.assertEqual(len(cleanup.threads_to_archive(None, now)), 1)


class WorktreeTest(unittest.TestCase):
    def test_a_merged_clean_copy_at_rest_is_removed_and_a_link_inside_it_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = project(tmp)
            shared = tmp / "shared-modules"
            shared.mkdir()
            (shared / "keep.txt").write_text("must survive\n", encoding="utf-8")
            done, busy, open_ = tmp / "wt-done", tmp / "wt-busy", tmp / "wt-open"
            git_in(repo, "worktree", "add", "-q", str(done), "-b", "feature/done")
            git_in(repo, "worktree", "add", "-q", str(busy), "-b", "feature/busy")
            git_in(repo, "worktree", "add", "-q", str(open_), "-b", "feature/open")
            (busy / "a.txt").write_text("edited\n", encoding="utf-8")
            (open_ / "a.txt").write_text("two\n", encoding="utf-8")
            git_in(open_, "commit", "-q", "-am", "not merged")
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(done / "node_modules"), str(shared)], check=True, capture_output=True)
            else:
                os.symlink(shared, done / "node_modules")
            now = datetime.datetime.now().timestamp()
            self.assertEqual(cleanup.done_worktrees(repo, "origin/testing", now), [])          # made a moment ago
            found = cleanup.done_worktrees(repo, "origin/testing", now + 7 * 3600)
            self.assertEqual([(p.name, b) for p, b in found], [("wt-done", "feature/done")])
            self.assertEqual([p.name for p in cleanup.links_inside(done)], ["node_modules"])
            self.assertTrue(cleanup.remove_worktree(repo, *found[0]))
            self.assertFalse(done.exists())
            self.assertEqual((shared / "keep.txt").read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(busy.exists() and open_.exists())
            self.assertNotIn("feature/done", git_in(repo, "branch", "--list"))


class RemoteBranchesTest(unittest.TestCase):
    def test_only_my_own_merged_branches_are_named_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = project(tmp)
            git_in(repo, "branch", "feature/mine-merged")
            git_in(repo, "branch", "main")
            git_in(repo, "checkout", "-q", "-b", "feature/mine-open")
            (repo / "a.txt").write_text("two\n", encoding="utf-8")
            git_in(repo, "commit", "-q", "-am", "open work")
            git_in(repo, "checkout", "-q", "testing")
            git_in(repo, "checkout", "-q", "-b", "feature/theirs-merged")
            subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=", "-c", "user.name=Other", "-c",
                            "user.email=other@example.com", "commit", "-q", "--allow-empty", "-m", "theirs"], check=True,
                           capture_output=True)
            git_in(repo, "checkout", "-q", "testing")
            git_in(repo, "merge", "-q", "--ff-only", "feature/theirs-merged")
            git_in(repo, "push", "-q", "origin", "testing", "main", "feature/mine-merged", "feature/mine-open", "feature/theirs-merged")
            git_in(repo, "fetch", "-q", "origin")
            now = datetime.datetime.now().timestamp()
            own, others = cleanup.merged_remote(repo, "origin/testing", now)
            self.assertEqual(own, ["feature/mine-merged"])
            self.assertEqual(others, 1)                       # theirs; main is protected, testing is the branch itself
            self.assertEqual(cleanup.merged_remote(repo, "origin/testing", now, older_than=14)[0], [])
            self.assertEqual(cleanup.delete_remote(repo, own), 1)
            left = git_in(repo, "branch", "-r")
            self.assertNotIn("origin/feature/mine-merged", left)
            self.assertIn("origin/feature/mine-open", left)
            self.assertIn("origin/feature/theirs-merged", left)


if __name__ == "__main__":
    unittest.main()
