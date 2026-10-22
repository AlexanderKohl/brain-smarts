"""The preflight's task-store checks (P25), its raw-store skip (P24) and `--project` mode.

Fictional data only (SMART-RULE-0008): the authors are `sam` and `bob`, the memory node is
`garden`, the project repository is `example-project` on example.com.

Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import preflight  # noqa: E402
from preflight_base import message_layer  # noqa: E402
from test_preflight import HAS_GIT, TS, Brain, BrainTestCase, git, md, readme  # noqa: E402

LATER = "2026-01-02T09:00:00+10:00"
NODE = "/memory/projects/garden"
POINTER = "/memory/projects/example-project"
REPO = "example-project"


def task(tid: str, status: str = "ready", refs: list[str] | None = None, author: str | None = "sam",
         updated: str = TS, history: str | None = None, body: str = "") -> str:
    lines = ["---", f"id: {tid}", f"title: Example task {tid}", "type: task", "schema_version: 0.2",
             "contract: /CONTRACT.md", f"status: {status}", "owner: sam"]
    if author:
        lines.append(f"author: {author}")
    lines += ["priority: normal", f"created: {TS}", f"updated: {updated}"]
    lines += ["project_refs:"] + [f"  - {r}" for r in refs] if refs else ["project_refs: []"]
    lines += ["---", "", f"# Example task {tid}", "", body, "## History", "",
              history if history is not None else f"- {TS} – sam: created", ""]
    return "\n".join(lines)


class StoreBrain(Brain):
    """A brain with an owner store, a memory node store and one checked-out project repository."""

    def __init__(self) -> None:
        super().__init__()
        self.repos = self.root.parent / "repos"
        self.write("memory/OWNER.md", md("owner-profile", "# Owner\n", type="owner_profile", owner="sam",
                                         owner_short_name="sam", project_repos_root=self.repos.as_posix()))
        self.write("memory/projects/garden/README.md", readme("garden-readme", ["tasks"], node_type="project"))
        self.write("memory/projects/garden/tasks/README.md", readme("garden-tasks-readme", []))
        self.write("memory/projects/example-project/README.md",
                   readme("example-project-pointer", [], node_type="project", default_branch="main",
                          repo_url=f"https://example.com/sam/{REPO}.git"))
        self.checkout = self.repos / REPO
        self.write_repo("brain/README.md", md("example-project-brain", "# Example project\n", type="node_readme"))
        self.write_repo("brain/tasks/README.md", md("example-project-tasks", "# Tasks\n", type="node_readme"))
        self.state()

    def write_repo(self, relative: str, text: str) -> Path:
        path = self.checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def project(self, target: str = REPO) -> preflight.Result:
        return preflight.run_project(self.root, target)


class StoreTestCase(BrainTestCase):
    def brain(self) -> StoreBrain:
        brain = StoreBrain()
        self.addCleanup(brain.close)
        return brain

    def assertError(self, result: preflight.Result, *parts: str) -> None:
        self.assertTrue(any(all(p in e for p in parts) for e in result.errors),
                        f"no error with {parts}: {result.errors}")


class CleanStoresTests(StoreTestCase):
    def test_every_kind_of_store_passes_when_its_records_are_sound(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001"))
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0002.md",
                    task("TASK-sam-2026-0002", refs=[NODE]))
        brain.write_repo("brain/tasks/open/TASK-bob-2026-0001.md",
                         task("TASK-bob-2026-0001", refs=[f"{REPO}:brain"], author="bob"))
        brain.state()
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertFalse([w for w in result.warnings if "TASK-" in w], result.warnings)
        self.assertEqual(brain.project().errors, [])


class P25FailureTests(StoreTestCase):
    def test_a_record_without_author_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-2026-0001.md", task("TASK-2026-0001", author=None))
        brain.state()
        self.assertError(brain.run(), "/memory/tasks/open/TASK-2026-0001.md", "missing author")

    def test_a_status_its_folder_does_not_hold_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", status="completed"))
        brain.state()
        self.assertError(brain.run(), "TASK-sam-2026-0001.md", "status completed does not belong in open/")

    def test_an_invalid_status_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", status="someday"))
        brain.state()
        self.assertError(brain.run(), "TASK-sam-2026-0001.md", "status someday does not belong in open/")

    def test_an_identifier_used_in_two_memory_stores_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001"))
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md",
                    task("TASK-sam-2026-0001", refs=[NODE]))
        brain.state()
        self.assertError(brain.run(), "duplicate id TASK-sam-2026-0001")

    def test_an_identifier_used_in_memory_and_a_repository_is_named(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001"))
        brain.write_repo("brain/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"]))
        brain.state()
        self.assertTrue(any("identifier TASK-sam-2026-0001 is also used by /memory/tasks" in w
                            for w in brain.run().warnings))

    def test_a_record_whose_first_reference_names_another_node_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md",
                    task("TASK-sam-2026-0001", refs=["/memory/projects/example-project"]))
        brain.state()
        self.assertError(brain.run(), "TASK-sam-2026-0001.md", f"does not name {NODE}")

    def test_a_project_reference_in_the_owner_store_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", refs=[NODE]))
        brain.state()
        self.assertError(brain.run(), "/memory/tasks/open/TASK-sam-2026-0001.md", "not /memory/tasks")

    def test_an_open_record_naming_two_nodes_fails_and_a_completed_one_does_not(self) -> None:
        brain = self.brain()
        two = [NODE, POINTER]
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", refs=two))
        brain.write("memory/projects/garden/tasks/completed/TASK-sam-2026-0002.md",
                    task("TASK-sam-2026-0002", status="completed", refs=two))
        brain.state()
        errors = brain.run().errors
        self.assertTrue(any("TASK-sam-2026-0001.md" in e and "names more than one node" in e for e in errors))
        self.assertFalse(any("TASK-sam-2026-0002.md" in e for e in errors), errors)

    def test_a_memory_path_in_a_repository_store_fails(self) -> None:
        brain = self.brain()
        brain.write_repo("brain/tasks/open/TASK-sam-2026-0001.md",
                         task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"], body="See /memory/projects/garden.\n"))
        brain.state()
        self.assertError(brain.project(), f"{REPO}:brain/tasks/open/TASK-sam-2026-0001.md", "names a /memory/ path")

    def test_a_conflict_marker_in_a_record_or_in_state_fails(self) -> None:
        brain = self.brain()
        marker = "<<<<<<< ours\n- one side\n=======\n- other side\n>>>>>>> theirs\n"
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md",
                    task("TASK-sam-2026-0001", refs=[NODE], body=marker))
        brain.state()
        state = brain.root / "memory/projects/garden/tasks/STATE.md"
        state.write_text(state.read_text(encoding="utf-8") + marker, encoding="utf-8")
        result = brain.run()
        self.assertError(result, "TASK-sam-2026-0001.md", "conflicted")
        self.assertError(result, f"{NODE}/tasks/STATE.md", "Git conflict marker")

    def test_an_edit_nobody_is_named_for_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-sam-2026-0001.md", task("TASK-sam-2026-0001", updated=LATER))
        brain.state()
        self.assertError(brain.run(), "TASK-sam-2026-0001.md", "an edit nobody is named for")

    def test_a_legacy_history_entry_alone_is_not_attribution(self) -> None:
        brain = self.brain()
        brain.write("memory/tasks/open/TASK-2026-0001.md",
                    task("TASK-2026-0001", history=f"- {TS}: created before authors"))
        brain.state()
        self.assertError(brain.run(), "TASK-2026-0001.md", "no History entry")

    def test_a_state_file_that_differs_from_the_generated_one_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md",
                    task("TASK-sam-2026-0001", refs=[NODE]))
        self.assertError(brain.run(), f"{NODE}/tasks/STATE.md", "differs from the generated one")

    def test_a_waiting_task_without_next_review_fails(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/garden/tasks/open/TASK-sam-2026-0001.md",
                    task("TASK-sam-2026-0001", status="waiting", refs=[NODE]))
        brain.state()
        self.assertError(brain.run(), "TASK-sam-2026-0001.md", "waiting task requires next_review")

    @unittest.skipUnless(HAS_GIT, "git is required")
    def test_an_unmerged_path_in_a_repository_store_fails(self) -> None:
        brain = self.brain()
        record = "brain/tasks/open/TASK-sam-2026-0001.md"
        brain.write_repo(record, task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"]))
        repo = brain.checkout
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixture")
        git(repo, "checkout", "-q", "-b", "bob")
        brain.write_repo(record, task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"], body="Bob's side.\n"))
        git(repo, "commit", "-q", "-am", "bob")
        git(repo, "checkout", "-q", "main")
        brain.write_repo(record, task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"], body="Sam's side.\n"))
        git(repo, "commit", "-q", "-am", "sam")
        merged = subprocess.run(["git", "-C", str(repo), "merge", "bob"], capture_output=True, text=True)
        self.assertNotEqual(merged.returncode, 0)
        result = brain.project()
        self.assertError(result, f"{REPO}:{record}", "unmerged in Git")
        self.assertError(result, f"{REPO}:{record}", "conflicted")


class WarningOrFailureTests(StoreTestCase):
    def test_a_repository_store_failure_is_a_warning_from_the_brain_root(self) -> None:
        brain = self.brain()
        brain.write_repo("brain/tasks/open/TASK-sam-2026-0001.md",
                         task("TASK-sam-2026-0001", refs=[f"{REPO}:brain"], author=None))
        brain.state()
        result = brain.run()
        self.assertFalse(any("TASK-sam-2026-0001" in e for e in result.errors), result.errors)
        warned = [w for w in result.warnings if "TASK-sam-2026-0001.md" in w and "missing author" in w]
        self.assertTrue(warned, result.warnings)
        # Named after the pointer node, so the message is memory's and no project name reaches
        # the mechanics manifest.
        self.assertEqual({message_layer(w) for w in warned}, {"memory"})
        self.assertError(brain.project(), f"{REPO}:brain/tasks/open/TASK-sam-2026-0001.md", "missing author")

    def test_a_repository_not_checked_out_is_a_warning_without_a_machine_path(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/elsewhere/README.md",
                    readme("elsewhere-pointer", [], node_type="project", default_branch="main",
                           repo_url="https://example.com/bob/elsewhere.git"))
        result = brain.run()
        self.assertIn("/memory/projects/elsewhere: repository store elsewhere:brain/tasks not checked: "
                      "not checked out here", result.warnings)
        self.assertEqual(result.errors, [])
        self.assertError(brain.project("elsewhere"), "--project elsewhere", "not checked out here")


class ProjectModeTests(StoreTestCase):
    def test_the_repository_is_found_by_name_and_by_path(self) -> None:
        brain = self.brain()
        self.assertEqual(brain.project(REPO).errors, [])
        self.assertEqual(brain.project(str(brain.checkout)).errors, [])
        self.assertError(brain.project("no-such-repository"), "no pointer node names this repository")

    def test_a_checkout_no_pointer_names_is_checked_under_its_folder_name(self) -> None:
        brain = self.brain()
        other = brain.repos / "loose"
        (other / "brain").mkdir(parents=True)
        (other / "brain" / "README.md").write_text("no front matter\n", encoding="utf-8")
        self.assertError(preflight.run_project(brain.root, str(other)), "loose:brain/README.md")

    def test_project_mode_validates_the_brain_folder_and_skips_its_raw_store(self) -> None:
        brain = self.brain()
        brain.write_repo("brain/raw/2026/01/src-0001/notes.md", "Raw evidence, no front matter.\n")
        self.assertEqual(brain.project().errors, [])
        brain.write_repo("brain/NOTES.md", "No front matter.\n")
        self.assertError(brain.project(), f"{REPO}:brain/NOTES.md")

    def test_project_mode_ignores_the_brain_roots_own_problems(self) -> None:
        brain = self.brain()
        brain.write("memory/NOTE.md", "No front matter.\n")
        self.assertTrue(brain.run().errors)
        self.assertEqual(brain.project().errors, [])


class RawStoreSkipTests(StoreTestCase):
    def test_raw_evidence_in_a_memory_node_or_a_pointer_node_is_skipped(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/garden/raw/2026/01/src-0001/notes.md", "Raw evidence.\n")
        brain.write("memory/projects/example-project/raw/2026/01/src-0002/notes.md", "Raw evidence.\n")
        self.assertEqual(brain.run().errors, [])

    def test_a_raw_folder_that_is_not_a_node_store_is_still_validated(self) -> None:
        brain = self.brain()
        brain.write("memory/projects/garden/sources/raw/notes.md", "No front matter.\n")
        self.assertError(brain.run(), "/memory/projects/garden/sources/raw/notes.md")


if __name__ == "__main__":
    unittest.main()
