"""join.py on an invented brain, an invented memory and an invented shared project (SMART-RULE-0022).

Everything is in a temporary folder: a fake brain root with the contract and the pointer
template, a fake memory for the fictional owner Sam, and a fictional repository `garden-app`
with `brain/JOINING.md` whose `origin` is a local bare repository. The vault is a listing file
with names only. Run from the brain root:

    python -m unittest discover -s shared/skills/join-project/tests -v
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1] / "scripts"
REAL_ROOT = HERE.parents[4]
sys.path.insert(0, str(SCRIPTS))

import join  # noqa: E402
import joining  # noqa: E402

HAS_GIT = shutil.which("git") is not None

MANIFEST = """---
id: garden-app-joining
title: Joining Garden Planner
type: joining_manifest
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-01-05T09:12:31+10:00
updated: 2026-01-05T09:12:31+10:00
owner: Sam
joining:
  repository: https://example.com/sam/garden-app.git
  project_title: Garden Planner
  working_branch: testing
  minimum_contract_version: 2.6.0
  pointer_node: garden-planner
  skills:
    - path: /shared/skills/owner-board
      minimum_version: 1.0.0
  active_skills:
    - product-feedback
  library_skills: [release-notes]
  boards:
    - id: garden
      label: Garden Planner
      status: brain/status
  vault_entries:
    - entry: garden-inbox-pull
      fields: [pull_key]
      purpose: pulls the feedback items you take
  feedback:
    inbox_url: https://garden.example.com
    vault_entry: garden-inbox-pull
    key_page: Admin, Feedback
  read_first:
    - brain/STATE.md#Handover
---

# Joining Garden Planner

Run join.py against this repository.
"""


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=Sam Example", "-c", "user.email=sam@example.com",
                           "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def remove(path: Path) -> None:
    """rmtree that clears the read-only bit Git sets on object files (Windows refuses them otherwise)."""
    def retry(func, name, _exc):
        os.chmod(name, stat.S_IWRITE)
        func(name)
    shutil.rmtree(path, onerror=retry)


@unittest.skipUnless(HAS_GIT, "git is not installed")
class JoinTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="join-"))
        self.root = self.base / "brain"
        self.projects = self.base / "projects"
        self.projects.mkdir()
        write(self.root / "CONTRACT.md", "---\nid: c\ncontract_version: 2.6.0\n---\n")
        (self.root / join.TEMPLATE).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_ROOT / join.TEMPLATE, self.root / join.TEMPLATE)
        write(self.root / "shared/skills/owner-board/SKILL.md", "---\nid: s\nversion: 1.0.0\n---\n")
        write(self.root / "memory/OWNER.md", "---\nowner_short_name: Sam\nproject_repos_root: "
              + str(self.projects) + "\nactive_skills:\n  - owner-board\n---\n")
        write(self.root / "memory/projects/README.md", "---\nid: p\n---\n# Projects\n\n#### Folders\n\n"
              "##### `apple/`\n\nContains apple.\n\n##### `zebra/`\n\nContains zebra.\n")
        write(self.root / joining.BOARDS_CONFIG, json.dumps({"boards": []}))
        self.listing = self.base / "vault-names.txt"
        self.listing.write_text("other-entry\n", encoding="utf-8")
        # the fictional project: origin with main and testing, cloned under projects/
        origin = self.base / "garden-app.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(origin))
        seed = self.base / "seed"
        git(self.base, "clone", "-q", str(origin), str(seed))
        write(seed / "brain" / "JOINING.md", MANIFEST)
        git(seed, "add", "brain/JOINING.md")
        git(seed, "commit", "-q", "-m", "manifest")
        git(seed, "push", "-q", "origin", "main")
        git(seed, "checkout", "-q", "-b", "testing")
        git(seed, "push", "-q", "origin", "testing")
        self.origin = origin
        self.repo = self.projects / "garden-app"
        git(self.base, "clone", "-q", str(origin), str(self.repo))   # on main, so a checkout is needed

    def tearDown(self):
        remove(self.base)

    def run_join(self, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = join.main([str(self.repo), "--root", str(self.root), "--no-sync",
                              "--vault-listing", str(self.listing), *extra])
        return code, out.getvalue()

    def test_dry_run_changes_nothing_and_says_what_it_would_do(self):
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("would check out testing", out)
        self.assertIn("would create the pointer node", out)
        self.assertIn("would register board garden as garden-app:brain/status", out)
        self.assertFalse((self.root / "memory/projects/garden-planner").exists())
        self.assertEqual(json.loads((self.root / joining.BOARDS_CONFIG).read_text())["boards"], [])
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_join_sets_up_branch_pointer_board_and_names_the_persons_steps(self):
        code, out = self.run_join()
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "testing")
        readme = (self.root / "memory/projects/garden-planner/README.md").read_text(encoding="utf-8")
        self.assertIn("repo_url: https://example.com/sam/garden-app.git", readme)
        self.assertIn("local_path: garden-app", readme)
        self.assertIn("default_branch: testing", readme)
        self.assertIn("# Garden Planner", readme)
        self.assertNotIn("YYYY", readme)
        parent = (self.root / "memory/projects/README.md").read_text(encoding="utf-8")
        self.assertLess(parent.index("`apple/`"), parent.index("`garden-planner/`"))
        self.assertLess(parent.index("`garden-planner/`"), parent.index("`zebra/`"))
        boards = json.loads((self.root / joining.BOARDS_CONFIG).read_text())["boards"]
        self.assertEqual(boards, [{"id": "garden", "label": "Garden Planner", "status": "garden-app:brain/status",
                                   "node": "/memory/projects/garden-planner"}])
        self.assertIn("contract 2.6.0 (manifest needs 2.6.0)", out)
        self.assertIn("skill /shared/skills/owner-board 1.0.0", out)
        self.assertIn("list `product-feedback` under active_skills", out)
        self.assertIn("create your own vault entry garden-inbox-pull", out)
        self.assertIn("put-entry --entry garden-inbox-pull --secret pull_key", out)
        self.assertIn("set up the Brain Feedback companion", out)
        self.assertIn("Admin, Feedback (New pull key)", out)
        self.assertIn("read garden-app:brain/STATE.md#Handover", out)
        # the second run finds everything in place and changes nothing more
        code, again = self.run_join()
        self.assertEqual(code, 0, again)
        self.assertIn("pointer node /memory/projects/garden-planner already names this repository", again)
        self.assertIn("board garden registered", again)
        self.assertIn("on testing", again)
        self.assertNotIn("would", again)
        self.assertEqual(json.loads((self.root / joining.BOARDS_CONFIG).read_text())["boards"], boards)

    def test_an_existing_vault_entry_and_companion_are_reported_ready(self):
        self.listing.write_text("garden-inbox-pull\nother-entry\n", encoding="utf-8")
        write(self.root / join.COMPANION, json.dumps({"inbox_url": "https://garden.example.com/",
                                                       "inbox_vault_entry": "garden-inbox-pull"}))
        code, out = self.run_join()
        self.assertEqual(code, 0, out)
        self.assertIn("vault entry garden-inbox-pull exists", out)
        self.assertIn("companion configured for https://garden.example.com", out)
        self.assertNotIn("put-entry", out)

    def test_a_board_registered_elsewhere_is_left_for_the_person(self):
        write(self.root / joining.BOARDS_CONFIG, json.dumps({"boards": [
            {"id": "garden", "label": "Garden", "status": "projects/garden/status"}]}))
        code, out = self.run_join()
        self.assertEqual(code, 0, out)
        self.assertIn("board garden is registered as projects/garden/status but the manifest expects "
                      "garden-app:brain/status", out)
        self.assertEqual(len(json.loads((self.root / joining.BOARDS_CONFIG).read_text())["boards"]), 1)

    def test_an_old_contract_or_skill_is_the_persons_step(self):
        write(self.root / "CONTRACT.md", "---\nid: c\ncontract_version: 2.5.0\n---\n")
        write(self.root / "shared/skills/owner-board/SKILL.md", "---\nid: s\nversion: 0.9.0\n---\n")
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("bring the brain to contract 2.6.0 (this copy reads 2.5.0)", out)
        self.assertIn("skill /shared/skills/owner-board is 0.9.0; the manifest needs 1.0.0", out)

    def test_a_missing_library_skill_is_the_persons_step_with_the_command(self):
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)   # a report, not a failure
        self.assertIn("library skill release-notes is needed but /library/ is not checked out", out)
        self.assertIn("git clone <your skill library URL> library", out)
        (self.root / "library" / ".git").mkdir(parents=True)
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("library skill release-notes is not in /library/skills/; pull the skill library", out)
        self.assertIn("git -C library pull", out)
        write(self.root / "library/skills/release-notes/SKILL.md", "---\nname: release-notes\n---\n")
        code, out = self.run_join("--dry-run")
        self.assertIn("library skill release-notes present", out)
        self.assertNotIn("git -C library pull", out)

    def test_library_skills_that_are_not_plain_names_are_malformed_lines_not_a_crash(self):
        (self.root / "library" / ".git").mkdir(parents=True)
        manifest = self.repo / "brain" / "JOINING.md"
        for value, shown in (("[../../shared/skills/owner-board, release-notes]", "'../../shared/skills/owner-board'"),
                             ("[release-notes, a/b, c\\\\d]", "'a/b'"),
                             ("true", "True"),
                             ("release-notes", "'release-notes'")):
            write(manifest, MANIFEST.replace("library_skills: [release-notes]", "library_skills: " + value))
            code, out = self.run_join("--dry-run")
            self.assertEqual(code, 0, out)
            self.assertIn("malformed brain/JOINING.md line, skipped: library_skills", out)
            self.assertIn(shown, out)
            self.assertNotIn("owner-board present", out)   # a path never finds another skill's SKILL.md
            self.assertNotIn("library skill r ", out)       # a scalar is not walked letter by letter
            self.assertIn("git checkout testing", out)     # the rest of the report still runs

    def test_a_dirty_clone_is_not_switched(self):
        with (self.repo / "brain" / "JOINING.md").open("a", encoding="utf-8") as handle:
            handle.write("\nA line added here, not committed.\n")
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("on main with 1 changed file(s)", out)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_a_repository_without_a_manifest_cannot_be_joined(self):
        plain = self.projects / "plain"
        git(self.base, "init", "-q", str(plain))
        out = io.StringIO()
        with redirect_stdout(out):
            code = join.main([str(plain), "--root", str(self.root), "--no-sync"])
        self.assertEqual(code, 1)
        self.assertIn("plain has no brain/JOINING.md", out.getvalue())

    def test_a_url_in_a_dry_run_is_not_cloned(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = join.main(["https://example.com/sam/new-app.git", "--root", str(self.root), "--no-sync", "--dry-run"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("would clone https://example.com/sam/new-app.git", out.getvalue())
        self.assertFalse((self.projects / "new-app").exists())

    def test_a_url_is_cloned_under_project_repos_root(self):
        remove(self.repo)
        out = io.StringIO()
        with redirect_stdout(out):
            code = join.main([str(self.origin), "--root", str(self.root), "--no-sync",
                              "--vault-listing", str(self.listing)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertTrue((self.projects / "garden-app" / "brain" / "JOINING.md").is_file())
        self.assertEqual(git(self.projects / "garden-app", "rev-parse", "--abbrev-ref", "HEAD"), "testing")

    def test_not_joined_lists_only_what_is_missing(self):
        before = joining.not_joined(self.root)
        self.assertEqual([(n["name"], n["detail"]) for n in before],
                         [("garden-app", "no pointer node in memory; shared board(s) not registered: garden")])
        self.assertIn("join.py", before[0]["command"])
        self.run_join()
        self.assertEqual(joining.not_joined(self.root), [])

    def test_the_manifest_parser_reads_lists_of_mappings(self):
        manifest = joining.load_manifest(self.repo)
        self.assertEqual(manifest["boards"][0]["id"], "garden")
        self.assertEqual(manifest["vault_entries"][0]["fields"], ["pull_key"])
        self.assertEqual(manifest["feedback"]["key_page"], "Admin, Feedback")
        self.assertEqual(manifest["read_first"], ["brain/STATE.md#Handover"])

    # -- the repository's task store and the pointer list (B3) --

    def test_a_pointer_at_depth_four_is_found(self):
        node = self.root / "memory/projects/orchard/beds/north/garden-planner"
        write(node / "README.md", "---\nid: g\ntitle: Garden Planner\ntype: node_readme\nnode_type: project\n"
              "repo_url: https://example.com/sam/garden-app.git\nlocal_path: garden-app\n---\n")
        self.assertEqual([path for path, _ in joining.pointer_nodes(self.root / "memory")], [node / "README.md"])
        self.assertEqual(joining.find_pointer(self.root / "memory", "https://example.com/sam/garden-app.git",
                                              "garden-app"), node)
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertNotIn("would create the pointer node", out)
        self.assertFalse((self.root / "memory/projects/garden-planner").exists())

    def test_a_repository_without_a_task_store_is_reported(self):
        code, out = self.run_join("--dry-run", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertIn("task store garden-app:brain/tasks: not there yet (no brain/tasks/ in garden-app); the "
                      "project's first task creates it", data["ready"])
        self.assertEqual(data["task_store"]["present"], False)

    def test_the_task_store_counts_and_the_persons_own_tasks_are_reported(self):
        tasks = self.repo / "brain" / "tasks"
        write(tasks / "open" / "TASK-sam-2026-0001-water-beds.md", task("TASK-sam-2026-0001", "Water the beds", "ready", "Sam"))
        write(tasks / "open" / "TASK-bob-2026-0001-fix-gate.md", task("TASK-bob-2026-0001", "Fix the gate", "waiting", "Bob"))
        write(tasks / "inbox" / "TASK-bob-2026-0002-seeds.md", task("TASK-bob-2026-0002", "Order seeds", "inbox", "Sam"))
        write(tasks / "completed" / "TASK-sam-2026-0002-plan.md", task("TASK-sam-2026-0002", "Draw the plan", "done", "Sam"))
        code, out = self.run_join()
        self.assertEqual(code, 0, out)
        self.assertIn("task store garden-app:brain/tasks: 2 open, 1 in the inbox", out)
        self.assertIn("your 2 open task(s) in garden-app:brain/tasks: TASK-bob-2026-0002 (inbox) Order seeds; "
                      "TASK-sam-2026-0001 (ready) Water the beds", out)
        self.assertNotIn("Draw the plan", out)
        self.assertNotIn("Fix the gate", out)
        code, out = self.run_join("--json")
        data = json.loads(out)["task_store"]
        self.assertEqual((data["label"], data["present"], data["open"], data["inbox"]),
                         ("garden-app:brain/tasks", True, 2, 1))
        self.assertEqual([t["id"] for t in data["yours"]], ["TASK-bob-2026-0002", "TASK-sam-2026-0001"])

    def test_a_conflicted_task_record_is_the_persons_step(self):
        path = self.repo / "brain" / "tasks" / "open" / "TASK-sam-2026-0001-water-beds.md"
        write(path, task("TASK-sam-2026-0001", "Water the beds", "ready", "Sam")
              + "<<<<<<< ours\n=======\n>>>>>>> theirs\n")
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("task record brain/tasks/open/TASK-sam-2026-0001-water-beds.md in garden-app: conflicted: "
                      "resolve by hand", out)
        self.assertIn("task store garden-app:brain/tasks: 0 open, 0 in the inbox", out)

    def test_a_minimum_contract_below_three_is_warned(self):
        code, out = self.run_join("--dry-run")
        self.assertIn("warning: the manifest's minimum_contract_version is 2.6.0, below 3.0.0", out)
        write(self.root / "CONTRACT.md", "---\nid: c\ncontract_version: 3.0.0\n---\n")
        manifest = self.repo / "brain" / "JOINING.md"
        write(manifest, MANIFEST.replace("minimum_contract_version: 2.6.0", "minimum_contract_version: 3.0.0"))
        code, out = self.run_join("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertNotIn("below 3.0.0", out)
        self.assertIn("contract 3.0.0 (manifest needs 3.0.0)", out)
        write(manifest, MANIFEST.replace("  minimum_contract_version: 2.6.0\n", ""))
        code, out = self.run_join("--dry-run")
        self.assertIn("minimum_contract_version is not stated, below 3.0.0", out)


def task(tid: str, title: str, status: str, owner: str) -> str:
    """A fictional task record in the shape the tasks skill reads."""
    author = tid.split("-")[1]
    return (f"---\nid: {tid}\ntitle: {title}\ntype: task\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"status: {status}\nowner: {owner}\nauthor: {author}\npriority: normal\n"
            "created: 2026-01-06T09:00:00+10:00\nupdated: 2026-01-06T09:00:00+10:00\nproject_refs:\n"
            f"  - garden-app:brain\n---\n\n# {title}\n\n## History\n\n- 2026-01-06T09:00:00+10:00 – {author}: captured\n")


if __name__ == "__main__":
    unittest.main()
