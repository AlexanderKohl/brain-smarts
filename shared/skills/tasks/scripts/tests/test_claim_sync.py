"""Claims between brains: six-hour expiry, the holder's name, and push at once, through real Git.

Two clones of one origin stand in for two people's brains. All names and content are fictional.
"""

from __future__ import annotations

import os
import unittest

from brainfix import NOW, Brain, git, record
from test_tasks import run

import task_claims  # noqa: E402
import task_stores  # noqa: E402
import tasks  # noqa: E402

POINTER = "/memory/projects/example-app"
TID = "TASK-sam-2026-0001"
EARLY, SOON, LATE = "2026-01-10T09:00:00+00:00", "2026-01-10T14:59:00+00:00", "2026-01-10T15:00:00+00:00"
publish = task_claims.task_claim_sync.publish
ClaimLost = task_claims.task_claim_sync.ClaimLost


class Shared(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["BRAIN_CO_AUTHOR"] = "Example Model <model@example.com>"
        self.brain = Brain()
        self.root = self.brain.root
        self.brain.node(POINTER, "Example app", node_type="project_pointer",
                        repo_url="https://example.com/sam/example-app.git", default_branch="main")
        self.clone = self.brain.checkout("example-app")
        git(self.clone, "config", "user.name", "sam")
        git(self.clone, "config", "user.email", "sam@example.com")
        self.path = self.brain.add("open", f"{TID}-fix", record(
            TID, "Fix the form", "ready", refs=["example-app:brain"]), store=self.clone / "brain/tasks")
        git(self.clone, "add", ".")
        git(self.clone, "commit", "-q", "-m", "a task")
        git(self.clone, "push", "-q")
        self.origin = self.brain.tmp / "origins/example-app.git"

    def tearDown(self) -> None:
        os.environ.pop("BRAIN_CO_AUTHOR", None)
        self.brain.close()

    def claim(self, by: str, now: str = EARLY, *extra: str) -> tuple[int, str]:
        return run(*extra, "claim", TID, "--by", by, "--now", now, "--no-board", cwd=self.root)

    def meta(self) -> dict:
        return tasks.parse_front_matter(self.path.read_text(encoding="utf-8"))

    def on_origin(self) -> str:
        return git(self.origin, "show", f"main:brain/tasks/open/{TID}-fix.md")

    def other_brain(self):
        other = self.brain.tmp / "other"
        git(self.brain.tmp, "clone", "-q", str(self.origin), "other")
        git(other, "config", "user.name", "bo")
        git(other, "config", "user.email", "bo@example.com")
        return other

    def bo_claims(self, other, at: str = EARLY) -> None:
        path = other / "brain/tasks/open" / f"{TID}-fix.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("status: ready", text)
        text = text.replace("status: ready", f"status: in_progress\nclaimed_by: bo/blue\nclaimed_at: {at}")
        path.write_text(text, encoding="utf-8")
        git(other, "commit", "-q", "-am", "bo claims")
        git(other, "push", "-q")

    def paths(self):
        store = task_stores.store_for(self.root, POINTER)
        return store, [self.path, store.path / "STATE.md"]

    def test_a_claim_in_a_shared_repository_names_the_person_and_reaches_origin_at_once(self) -> None:
        code, out = self.claim("green")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.meta()["claimed_by"], "sam/green")
        self.assertIn("committed and pushed to origin/main", out)
        self.assertIn("claimed_by: sam/green", self.on_origin())
        message = git(self.clone, "log", "-1", "--format=%B")
        self.assertIn(f"Claim {TID} by sam/green", message)
        self.assertIn("Tool: tasks.py", message)
        self.assertIn("Co-Authored-By: Example Model", message)

    def test_only_the_claim_is_committed_and_other_work_is_never_pushed_with_it(self) -> None:
        (self.clone / "half-done.txt").write_text("work in progress", encoding="utf-8")
        git(self.clone, "add", "half-done.txt")
        git(self.clone, "commit", "-q", "-m", "unfinished work")
        (self.clone / "scratch.txt").write_text("not for anyone", encoding="utf-8")
        code, out = self.claim("green")
        self.assertEqual(code, 0, out)
        self.assertIn("1 unpushed commit(s) of its own", out)
        self.assertNotIn("claimed_by", self.on_origin())
        self.assertNotIn("scratch.txt", git(self.clone, "show", "--stat", "--format=", "HEAD"))
        self.assertIn("scratch.txt", git(self.clone, "status", "--porcelain"))

    def test_a_live_claim_of_another_brain_is_refused_and_says_when_it_lapses(self) -> None:
        self.bo_claims(self.other_brain())
        git(self.clone, "pull", "-q", "--ff-only")
        code, out = self.claim("green", SOON)
        self.assertEqual(code, 1)
        self.assertIn("held by bo/blue", out)
        self.assertIn("lapses at 2026-01-10T15:00", out)
        self.assertEqual(self.meta()["claimed_by"], "bo/blue")

    def test_a_claim_older_than_six_hours_is_taken_over_and_the_history_says_whose_it_was(self) -> None:
        self.bo_claims(self.other_brain())
        git(self.clone, "pull", "-q", "--ff-only")
        code, out = self.claim("green", LATE)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.meta()["claimed_by"], "sam/green")
        self.assertIn("taking over the lapsed claim of bo/blue", self.path.read_text(encoding="utf-8"))
        self.assertIn("claimed_by: sam/green", self.on_origin())

    def test_claiming_again_renews_the_six_hours(self) -> None:
        self.claim("green", EARLY)
        code, out = self.claim("green", SOON)
        self.assertEqual(code, 0, out)
        task = task_stores.find(self.root, TID)
        self.assertFalse(task_claims.lapsed(task, LATE))
        self.assertTrue(task_claims.lapsed(task, "2026-01-10T20:59:00+00:00"))

    def test_when_another_brain_claimed_first_the_claim_is_withdrawn_not_forced(self) -> None:
        other = self.other_brain()
        code, out = self.claim("green", EARLY, "--offline")   # written here, not yet published
        self.assertEqual(code, 0, out)
        self.bo_claims(other)
        store, paths = self.paths()
        with self.assertRaises(ClaimLost) as lost:
            publish(store, paths, f"Claim {TID} by sam/green")
        self.assertIn("another brain changed this card first", str(lost.exception))
        self.assertIn("claimed_by: bo/blue", self.on_origin())
        self.assertNotIn("claimed_by", self.meta())
        self.assertEqual(git(self.clone, "status", "--porcelain", "--untracked-files=no"), "")
        git(self.clone, "pull", "-q", "--no-rebase")
        self.assertEqual(self.meta()["claimed_by"], "bo/blue")

    def test_origin_moving_elsewhere_is_merged_and_the_claim_still_arrives(self) -> None:
        other = self.other_brain()
        code, out = self.claim("green", EARLY, "--offline")
        self.assertEqual(code, 0, out)
        (other / "elsewhere.txt").write_text("bo's own file", encoding="utf-8")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "bo's change")
        git(other, "push", "-q")
        store, paths = self.paths()
        said = publish(store, paths, f"Claim {TID} by sam/green")
        self.assertIn("merged origin/main and pushed", " ".join(said))
        self.assertIn("claimed_by: sam/green", self.on_origin())

    def test_a_release_reaches_origin_too(self) -> None:
        self.claim("green")
        code, out = run("release", TID, "--now", SOON, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertNotIn("claimed_by: sam", self.on_origin())
        self.assertIn("status: ready", self.on_origin())

    def test_session_start_lists_other_brains_claims_live_first_then_lapsed_never_its_own(self) -> None:
        self.bo_claims(self.other_brain())
        git(self.clone, "pull", "-q", "--ff-only")
        live = task_claims.held_by_others(self.root, SOON)
        self.assertEqual(len(live), 1)
        self.assertIn(f"{TID} (example-app): held by bo/blue since {EARLY}, until 2026-01-10T15:00", live[0])
        self.assertIn("lapsed", task_claims.held_by_others(self.root, LATE)[0])
        self.claim("green", LATE)
        self.assertEqual(task_claims.held_by_others(self.root, LATE), [])

    def test_a_claim_in_the_owners_own_memory_keeps_the_bare_session_name_and_commits_nothing(self) -> None:
        self.brain.add("open", "TASK-2026-0009-own", record("TASK-2026-0009", "Own card", "ready"))
        code, out = run("claim", "TASK-2026-0009", "--by", "green", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        own = (self.brain.store / "open/TASK-2026-0009-own.md").read_text(encoding="utf-8")
        self.assertIn("claimed_by: green", own)
        self.assertNotIn("pushed", out)


if __name__ == "__main__":
    unittest.main()
