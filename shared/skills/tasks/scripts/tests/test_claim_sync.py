"""Claims between brains: six-hour expiry, the holder's name, and "reaches origin or is not made".

Two clones of one origin stand in for two people's brains: `self.clone` is Sam's, worked through
tasks.py; `other` is Bo's, worked with plain Git. A race is made by letting Bo push between Sam's
write and Sam's push (`between`). All names and content are fictional.
"""

from __future__ import annotations

import os
import unittest

from brainfix import NOW, STAMP, Brain, git, record
from test_tasks import run

import task_claim_sync  # noqa: E402
import task_claims  # noqa: E402
import task_stores  # noqa: E402
import tasks  # noqa: E402

POINTER = "/memory/projects/example-app"
TID, TID2, TID3 = "TASK-sam-2026-0001", "TASK-sam-2026-0002", "TASK-sam-2026-0003"
EARLY, SOON, LATE = "2026-01-10T09:00:00+00:00", "2026-01-10T14:59:00+00:00", "2026-01-10T15:00:00+00:00"
REFS = ["example-app:brain"]


class Shared(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["BRAIN_CO_AUTHOR"] = "Example Model <model@example.com>"
        self.real_publish = task_claim_sync.publish
        self.brain = Brain()
        self.root = self.brain.root
        self.brain.node(POINTER, "Example app", node_type="project_pointer",
                        repo_url="https://example.com/sam/example-app.git", default_branch="main")
        self.clone = self.brain.checkout("example-app")
        git(self.clone, "config", "user.name", "sam")
        git(self.clone, "config", "user.email", "sam@example.com")
        self.tasks = self.clone / "brain/tasks"
        self.path = self.brain.add("open", f"{TID}-fix", record(TID, "Fix the form", "ready", refs=REFS), store=self.tasks)
        self.brain.add("open", f"{TID2}-paint", record(TID2, "Paint the door", "ready", refs=REFS), store=self.tasks)
        self.brain.add("inbox", f"{TID3}-idea", record(TID3, "Think about a pond", "inbox", refs=REFS), store=self.tasks)
        run("state", "--store", "example-app:brain/tasks", cwd=self.root)
        git(self.clone, "add", ".")
        git(self.clone, "commit", "-q", "-m", "three tasks")
        git(self.clone, "push", "-q")
        self.origin = self.brain.tmp / "origins/example-app.git"

    def tearDown(self) -> None:
        task_claim_sync.publish = self.real_publish
        os.environ.pop("BRAIN_CO_AUTHOR", None)
        self.brain.close()

    # --- helpers -------------------------------------------------------------------------------

    def claim(self, by: str = "green", now: str = EARLY, tid: str = TID, *extra: str) -> tuple[int, str]:
        return run(*extra, "claim", tid, "--by", by, "--now", now, "--no-board", cwd=self.root)

    def meta(self, path=None) -> dict:
        return tasks.parse_front_matter((path or self.path).read_text(encoding="utf-8"))

    def on_origin(self, rel: str = f"open/{TID}-fix.md") -> str:
        return git(self.origin, "show", f"main:brain/tasks/{rel}")

    def log(self) -> list[str]:
        return git(self.clone, "log", "--format=%s").splitlines()

    def other_brain(self):
        other = self.brain.tmp / "other"
        git(self.brain.tmp, "clone", "-q", str(self.origin), "other")
        git(other, "config", "user.name", "bo")
        git(other, "config", "user.email", "bo@example.com")
        return other

    def bo_claims(self, other, at: str = EARLY, rel: str = f"open/{TID}-fix.md", holder: str = "bo/blue",
                  author: str = "bo") -> None:
        path = other / "brain/tasks" / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn("status: ready", text)
        text = text.replace("status: ready", f"status: in_progress\nclaimed_by: {holder}\nclaimed_at: {at}")
        text = text.replace(f"updated: {STAMP}", f"updated: {at}")
        path.write_text(text + f"- {at} – {author}: claimed by {holder} (in_progress)\n", encoding="utf-8")
        state = other / "brain/tasks/STATE.md"
        state.write_text(state.read_text(encoding="utf-8").replace(f"updated: {STAMP}", f"updated: {at}"), encoding="utf-8")
        git(other, "commit", "-q", "-am", "bo claims")
        git(other, "push", "-q")

    def between(self, action) -> None:
        """Run `action` after Sam's claim is written and before it is pushed."""
        def publish(*args, **kwargs):
            action()
            return self.real_publish(*args, **kwargs)
        task_claim_sync.publish = publish

    def pull(self) -> None:
        git(self.clone, "pull", "-q", "--ff-only")

    # --- the ordinary path ---------------------------------------------------------------------

    def test_a_claim_names_the_person_reaches_origin_at_once_and_commits_only_the_card_and_the_state(self) -> None:
        (self.clone / "scratch.txt").write_text("not for anyone", encoding="utf-8")
        code, out = self.claim()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.meta()["claimed_by"], "sam/green")
        self.assertIn("committed and pushed to origin/main", out)
        self.assertIn("claimed_by: sam/green", self.on_origin())
        message = git(self.clone, "log", "-1", "--format=%B")
        self.assertIn(f"Claim {TID} by sam/green", message)
        self.assertIn("Tool: tasks.py", message)
        self.assertIn("Co-Authored-By: Example Model", message)
        files = sorted(git(self.clone, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(files, ["brain/tasks/STATE.md", f"brain/tasks/open/{TID}-fix.md"])
        self.assertIn("?? scratch.txt", git(self.clone, "status", "--porcelain"))

    def test_a_card_claimed_from_the_inbox_moves_to_open_on_origin(self) -> None:
        code, out = self.claim(tid=TID3)
        self.assertEqual(code, 0, out)
        self.assertIn("claimed_by: sam/green", self.on_origin(f"open/{TID3}-idea.md"))
        with self.assertRaises(RuntimeError):
            self.on_origin(f"inbox/{TID3}-idea.md")

    def test_a_release_reaches_origin_too(self) -> None:
        self.claim()
        code, out = run("release", TID, "--now", SOON, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertNotIn("claimed_by: sam", self.on_origin())
        self.assertIn("status: ready", self.on_origin())

    def test_a_claim_in_the_owners_own_memory_keeps_the_bare_session_name_and_commits_nothing(self) -> None:
        self.brain.add("open", "TASK-2026-0009-own", record("TASK-2026-0009", "Own card", "ready"))
        code, out = run("claim", "TASK-2026-0009", "--by", "green", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("claimed_by: green", (self.brain.store / "open/TASK-2026-0009-own.md").read_text(encoding="utf-8"))
        self.assertNotIn("pushed", out)

    # --- refused before anything is written ----------------------------------------------------

    def test_unpushed_work_refuses_the_claim_and_nothing_is_written_or_pushed(self) -> None:
        (self.clone / "half-done.txt").write_text("work in progress", encoding="utf-8")
        git(self.clone, "add", "half-done.txt")
        git(self.clone, "commit", "-q", "-m", "unfinished work")
        before = self.path.read_text(encoding="utf-8")
        code, out = self.claim()
        self.assertEqual(code, 1)
        self.assertIn("1 unpushed commit(s) of its own", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertEqual(self.log()[0], "unfinished work")
        with self.assertRaises(RuntimeError):
            git(self.origin, "show", "main:half-done.txt")

    def test_a_staged_file_refuses_the_claim_and_stays_staged_and_uncommitted(self) -> None:
        (self.clone / "notes.txt").write_text("mine", encoding="utf-8")
        git(self.clone, "add", "notes.txt")
        before = self.path.read_text(encoding="utf-8")
        code, out = self.claim()
        self.assertEqual(code, 1)
        self.assertIn("files are staged", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertIn("A  notes.txt", git(self.clone, "status", "--porcelain"))
        self.assertEqual(self.log()[0], "three tasks")

    def test_offline_makes_a_local_claim_and_says_nobody_else_sees_it(self) -> None:
        code, out = self.claim("green", EARLY, TID, "--offline")
        self.assertEqual(code, 0, out)
        self.assertIn("only this computer sees this change", out)
        self.assertNotIn("claimed_by", self.on_origin())
        self.assertEqual(self.log()[0], "three tasks")

    # --- expiry --------------------------------------------------------------------------------

    def test_a_live_claim_of_another_brain_is_refused_and_says_when_it_lapses(self) -> None:
        self.bo_claims(self.other_brain())
        self.pull()
        code, out = self.claim("green", SOON)
        self.assertEqual(code, 1)
        self.assertIn("held by bo/blue", out)
        self.assertIn("lapses at 2026-01-10T15:00", out)
        self.assertEqual(self.meta()["claimed_by"], "bo/blue")

    def test_a_claim_older_than_six_hours_is_taken_over_and_the_history_says_whose_it_was(self) -> None:
        self.bo_claims(self.other_brain())
        self.pull()
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

    def test_the_same_instant_in_two_offsets_lapses_at_the_same_moment(self) -> None:
        self.bo_claims(self.other_brain(), at="2026-01-10T19:00:00+10:00")
        self.pull()
        task = task_stores.find(self.root, TID)
        self.assertFalse(task_claims.lapsed(task, SOON))
        self.assertTrue(task_claims.lapsed(task, LATE))

    # --- two brains at once --------------------------------------------------------------------

    def test_when_another_brain_claimed_the_same_card_first_the_claim_is_withdrawn_and_the_command_fails(self) -> None:
        other = self.other_brain()
        self.between(lambda: self.bo_claims(other))
        code, out = self.claim()
        self.assertEqual(code, 1, out)
        self.assertIn("another brain changed this card first", out)
        self.assertIn("withdrawn here", out)
        self.assertIn("claimed_by: bo/blue", self.on_origin())
        self.assertNotIn("claimed_by", self.meta())
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")
        log = self.log()
        self.assertEqual(log[0], f"Withdraw: Claim {TID} by sam/green")
        self.assertEqual(log[1], f"Claim {TID} by sam/green")
        git(self.clone, "pull", "-q", "--no-rebase")
        self.assertEqual(self.meta()["claimed_by"], "bo/blue")
        code, out = self.claim("green", SOON)      # the next attempt is refused for the right reason
        self.assertIn("held by bo/blue", out)

    def test_a_lost_claim_from_the_inbox_puts_the_card_back_in_the_inbox(self) -> None:
        other = self.other_brain()

        def bo_takes_it() -> None:
            git(other, "mv", f"brain/tasks/inbox/{TID3}-idea.md", f"brain/tasks/open/{TID3}-idea.md")
            path = other / f"brain/tasks/open/{TID3}-idea.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "status: inbox", f"status: in_progress\nclaimed_by: bo/blue\nclaimed_at: {EARLY}"), encoding="utf-8")
            git(other, "commit", "-q", "-am", "bo claims the idea")
            git(other, "push", "-q")

        self.between(bo_takes_it)
        code, out = self.claim(tid=TID3)
        self.assertEqual(code, 1, out)
        self.assertTrue((self.tasks / f"inbox/{TID3}-idea.md").is_file())
        self.assertFalse((self.tasks / f"open/{TID3}-idea.md").exists())
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")

    def test_two_brains_claiming_different_cards_at_once_both_keep_their_claim(self) -> None:
        other = self.other_brain()
        self.between(lambda: self.bo_claims(other, rel=f"open/{TID2}-paint.md"))
        code, out = self.claim()
        self.assertEqual(code, 0, out)
        self.assertIn("merged origin/main and pushed", out)
        self.assertIn("claimed_by: sam/green", self.on_origin())
        self.assertIn("claimed_by: bo/blue", self.on_origin(f"open/{TID2}-paint.md"))
        state = self.on_origin("STATE.md")
        self.assertNotIn("<<<<<<<", state)
        self.assertIn(TID, state)
        self.assertIn(TID2, state)
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")

    def test_origin_moving_elsewhere_is_merged_and_the_claim_still_arrives(self) -> None:
        other = self.other_brain()

        def bo_works() -> None:
            (other / "elsewhere.txt").write_text("bo's own file", encoding="utf-8")
            git(other, "add", ".")
            git(other, "commit", "-q", "-m", "bo's change")
            git(other, "push", "-q")

        self.between(bo_works)
        code, out = self.claim()
        self.assertEqual(code, 0, out)
        self.assertIn("merged origin/main and pushed", out)
        self.assertIn("claimed_by: sam/green", self.on_origin())

    # --- the push or the commit is refused -----------------------------------------------------

    def test_a_push_the_server_refuses_withdraws_the_claim_and_fails_the_command(self) -> None:
        hook = self.origin / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho protected branch >&2\nexit 1\n", encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        code, out = self.claim()
        self.assertEqual(code, 1, out)
        self.assertIn("the push was refused", out)
        self.assertIn("withdrawn here", out)
        self.assertNotIn("claimed_by", self.meta())
        self.assertNotIn("claimed_by", self.on_origin())
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")
        hook.unlink()
        code, out = self.claim("green", SOON)      # a claim and its withdrawal do not block the next claim
        self.assertEqual(code, 0, out)
        self.assertIn("claimed_by: sam/green", self.on_origin())

    def test_a_commit_a_hook_refuses_changes_nothing(self) -> None:
        hook = self.clone / ".git/hooks/commit-msg"
        hook.write_text("#!/bin/sh\necho no trailers today >&2\nexit 1\n", encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        before = self.path.read_text(encoding="utf-8")
        code, out = self.claim(tid=TID3)
        self.assertEqual(code, 1, out)
        self.assertIn("the commit was refused", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertTrue((self.tasks / f"inbox/{TID3}-idea.md").is_file())
        self.assertFalse((self.tasks / f"open/{TID3}-idea.md").exists())
        self.assertEqual(git(self.clone, "status", "--porcelain"), "")
        self.assertEqual(self.log()[0], "three tasks")

    # --- who may release, and whose claim a bare name is ----------------------------------------

    def test_another_brains_live_claim_cannot_be_released_but_a_lapsed_one_can(self) -> None:
        self.bo_claims(self.other_brain())
        self.pull()
        code, out = run("release", TID, "--now", SOON, "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("only its holder releases a live claim", out)
        self.assertIn("claimed_by: bo/blue", self.on_origin())
        code, out = run("release", TID, "--now", LATE, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertNotIn("claimed_by: bo", self.on_origin())

    def test_a_bare_name_from_before_the_prefix_is_its_authors_own_and_renews(self) -> None:
        self.bo_claims(self.other_brain(), holder="green", author="sam")
        self.pull()
        self.assertEqual(task_claims.held_by_others(self.root, SOON), [])
        code, out = self.claim("green", SOON)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.meta()["claimed_by"], "sam/green")
        self.assertNotIn("taking over", self.path.read_text(encoding="utf-8"))

    def test_a_bare_name_another_author_wrote_is_still_another_brains(self) -> None:
        self.bo_claims(self.other_brain(), holder="green", author="bo")
        self.pull()
        self.assertEqual(len(task_claims.held_by_others(self.root, SOON)), 1)
        code, out = self.claim("green", SOON)
        self.assertEqual(code, 1)
        self.assertIn("held by green", out)

    # --- session start -------------------------------------------------------------------------

    def test_session_start_lists_other_brains_claims_live_first_by_instant_then_lapsed_never_its_own(self) -> None:
        other = self.other_brain()
        self.bo_claims(other, at="2026-01-10T12:00:00+00:00")
        self.bo_claims(other, at="2026-01-10T08:00:00-05:00", rel=f"open/{TID2}-paint.md")   # 13:00 UTC, later
        self.pull()
        lines = task_claims.held_by_others(self.root, "2026-01-10T14:00:00+00:00")
        self.assertEqual([line.split(" ")[0] for line in lines], [TID, TID2])
        self.assertIn(f"{TID} (example-app): held by bo/blue since 2026-01-10T12:00:00+00:00, until 2026-01-10T18:00", lines[0])
        later = task_claims.held_by_others(self.root, "2026-01-10T18:30:00+00:00")
        self.assertIn("held by", later[0])
        self.assertTrue(later[0].startswith(TID2))
        self.assertIn("lapsed", later[1])
        code, out = self.claim("green", "2026-01-10T18:30:00+00:00")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(task_claims.held_by_others(self.root, "2026-01-10T18:30:00+00:00")), 1)


if __name__ == "__main__":
    unittest.main()
