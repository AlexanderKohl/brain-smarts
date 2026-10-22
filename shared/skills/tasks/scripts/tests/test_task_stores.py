"""Store discovery, node resolution and routing of new tasks (task_stores.py, task_new.py).

All names, titles and repositories below are fictional.
"""

from __future__ import annotations

import unittest

from brainfix import NOW, Brain, record
from test_tasks import run

import task_state  # noqa: E402
import task_stores  # noqa: E402
import tasks  # noqa: E402

POINTER = "/memory/projects/workshop/tools/apps/example-app"


class StoresTest(unittest.TestCase):
    def setUp(self) -> None:
        b = self.brain = Brain()
        self.root = b.root
        b.node("/memory/projects/garden", "Garden")
        b.node("/memory/projects/garden/pond", "Pond")
        b.node("/memory/projects/garden/pond/skills/filter", "Filter skill")
        b.node("/memory/projects/shelf", "Shelf", node_type="project_library")
        b.node("/memory/projects/shelf/reading", "Reading")
        b.node("/memory/projects/workshop", "Workshop", node_type="collection")
        b.node("/memory/projects/workshop/tools", "Tools")
        b.node("/memory/projects/workshop/tools/apps", "Apps")
        b.node(POINTER, "Example app", node_type="project_pointer",
               repo_url="https://example.com/sam/example-app.git", local_path="example-app", default_branch="main")
        b.node("/memory/projects/zine", "Zine", node_type="project_pointer",
               repo_url="https://example.com/sam/another-app", default_branch="main")
        for rel in ("memory/projects/garden/tasks/open", "memory/projects/garden/pond/tasks/open",
                    "memory/projects/workshop/tools/apps/example-app/tasks/open"):
            (self.root / rel).mkdir(parents=True)
        self.clone = b.checkout("example-app")

    def tearDown(self) -> None:
        self.brain.close()

    def write_states(self) -> None:
        for store in task_stores.stores(self.root):
            if store.reachable and store.path.is_dir():
                task_state.write(store)

    def repo_task(self, tid: str, title: str, owner: str, author: str) -> None:
        self.brain.add("open", f"{tid}-x", record(tid, title, "blocked", author=author, owner=owner,
                                                  refs=["example-app:brain"]), store=self.clone / "brain/tasks")

    # ------------------------------------------------ round 2: refusals, review, numbering

    def test_a_memory_path_in_any_field_of_a_repository_task_is_refused_before_a_number_is_taken(self) -> None:
        for flag, value in (("--skill", "/memory/skills/example"), ("--waiting-on", "see /memory/projects/garden"),
                            ("--schedule", "Example Cron | /memory/job | daily"), ("--owner", "/memory/OWNER.md")):
            extra = ["--status", "waiting", "--next-review", "2026-03-20"] if flag == "--waiting-on" else []
            code, out = run("new", "--title", "Fix the form", "--project", POINTER, flag, value, *extra,
                            "--no-board", cwd=self.root)
            self.assertEqual(code, 1, flag)
            self.assertIn("names a /memory/ path, which is never written into example-app:brain/tasks", out, flag)
        self.assertFalse((self.clone / "brain" / "tasks").exists())
        self.assertFalse((self.root / "memory/tasks/private").exists())
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0001")

    def test_a_repository_task_naming_only_its_pointer_has_no_companion_file(self) -> None:
        code, out = run("new", "--title", "Fix the form", "--status", "ready", "--project", POINTER, "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / "memory/tasks/private").exists())

    def test_a_reference_in_no_node_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            task_stores.store_for(self.root, "/memory/projects/no-such-node/notes.md")
        for ref in ("/memory/projects/no-such-node", "/memory/projects/workshop/notes.md", "/shared/skills/tasks"):
            code, out = run("new", "--title", "Somewhere", "--project", ref, "--no-board", cwd=self.root)
            self.assertEqual(code, 1, ref)
        code, out = run("new", "--title", "Two", "--project", "/memory/projects/garden", "--project",
                        "/memory/projects/no-such-node", "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("is in no node", out)
        self.assertFalse(list(self.root.glob("memory/**/TASK-sam-*.md")))

    def test_check_refuses_an_owner_store_task_with_a_project_reference(self) -> None:
        self.brain.add("open", "TASK-sam-2026-0001-x", record("TASK-sam-2026-0001", "Lost", "ready",
                                                              refs=["/memory/projects/no-such-node"]))
        code, out = run("check", "--store", "/memory/tasks", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("carries the project reference /memory/projects/no-such-node, which names no node", out)

    def test_repository_names_match_without_case(self) -> None:
        self.brain.node("/memory/projects/garden/second", "Second", node_type="project_pointer",
                        repo_url="https://example.com/sam/Example-App")
        self.assertEqual([s.label.lower() for s in task_stores.stores(self.root) if s.kind == "repository"],
                         ["another-app:brain/tasks", "example-app:brain/tasks"])     # one store, not two
        with self.assertRaises(ValueError):
            task_stores.store_for(self.root, POINTER)

    def test_review_shows_this_brain_s_repository_tasks_unless_all(self) -> None:
        self.repo_task("TASK-sam-2026-0005", "Sam's blocked task", "Sam", "sam")
        self.repo_task("TASK-bob-2026-0002", "Bob's blocked task", "Bob", "bob")
        code, out = run("review", "--today", "2026-03-10", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("| TASK-sam-2026-0005 | blocked |", out)
        self.assertIn("example-app:brain/tasks |", out)
        self.assertNotIn("TASK-bob-2026-0002", out)
        self.assertIn("Not read: another-app:brain/tasks (not checked out here)", out)
        code, out = run("review", "--all", "--today", "2026-03-10", cwd=self.root)
        self.assertIn("| TASK-bob-2026-0002 | blocked |", out)

    def test_next_id_reads_node_and_repository_stores(self) -> None:
        self.brain.add("open", "TASK-sam-2026-0012-x", record("TASK-sam-2026-0012", "In the node", "ready",
                                                              refs=["/memory/projects/garden"]),
                       store=self.root / "memory/projects/garden/tasks")
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0013")
        self.repo_task("TASK-sam-2026-0030", "In the repository", "Sam", "sam")
        self.repo_task("TASK-bob-2026-0041", "Bob's", "Bob", "bob")
        self.assertEqual(tasks.next_id(self.root, "sam", 2026), "TASK-sam-2026-0031")
        self.assertEqual(run("next-id", "--year", "2026", "--author", "Bob", cwd=self.root)[1].strip(),
                         "TASK-bob-2026-0042")

    def test_stores_are_found_at_any_depth_in_their_fixed_order(self) -> None:
        found = [(s.kind, s.label, s.reachable) for s in task_stores.stores(self.root)]
        self.assertEqual(found, [
            ("owner", "/memory/tasks", True),
            ("memory-node", "/memory/projects/garden/tasks", True),
            ("memory-node", "/memory/projects/garden/pond/tasks", True),
            ("pointer-private", POINTER + "/tasks", True),
            ("repository", "another-app:brain/tasks", False),
            ("repository", "example-app:brain/tasks", True),
        ])
        pointer = [p for p in task_stores.pointers(self.root) if p.repository == "example-app"][0]
        self.assertEqual((pointer.node, pointer.checkout, pointer.branch), (POINTER, self.clone, "main"))
        self.assertIn("not checked out", task_stores.stores(self.root)[4].reason)

    def test_the_store_branch_is_the_joining_working_branch(self) -> None:
        (self.clone / "brain" / "JOINING.md").write_text(
            "---\nid: joining\ntitle: Joining\njoining:\n  working_branch: testing\n---\n", encoding="utf-8")
        pointer = [p for p in task_stores.pointers(self.root) if p.repository == "example-app"][0]
        self.assertEqual(pointer.branch, "testing")

    def test_node_of_takes_the_deepest_node_and_skips_what_is_no_node(self) -> None:
        node_of = lambda ref: task_stores.node_of(self.root, ref)  # noqa: E731
        self.assertEqual(node_of("/memory/projects/garden/pond/notes.md"), "/memory/projects/garden/pond")
        self.assertEqual(node_of("/memory/projects/garden/pond/skills/filter/README.md"), "/memory/projects/garden/pond")
        self.assertEqual(node_of("/memory/projects/garden/tasks/open/x.md"), "/memory/projects/garden")
        self.assertEqual(node_of("/memory/projects/shelf/list.md"), None)            # a library is no node
        self.assertEqual(node_of("/memory/projects/shelf/reading"), "/memory/projects/shelf/reading")
        self.assertEqual(node_of("/memory/projects/workshop/notes.md"), None)        # a collection is no node
        self.assertEqual(node_of("/memory/projects/README.md"), None)
        self.assertEqual(node_of("/shared/skills/tasks"), None)

    def test_store_for_routes_by_node_pointer_and_private(self) -> None:
        store_for = lambda ref, private=False: task_stores.store_for(self.root, ref, private)  # noqa: E731
        self.assertEqual(store_for(None).label, "/memory/tasks")
        self.assertEqual(store_for("/memory/projects/garden/pond/a.md").label, "/memory/projects/garden/pond/tasks")
        self.assertEqual(store_for(POINTER).label, "example-app:brain/tasks")
        self.assertEqual(store_for(POINTER, True).label, POINTER + "/tasks")
        with self.assertRaises(ValueError):
            store_for("/memory/projects/garden", True)
        self.brain.node("/memory/projects/garden/second", "Second", node_type="project_pointer",
                        repo_url="https://example.com/sam/example-app")
        with self.assertRaises(ValueError) as two:
            store_for(POINTER)
        self.assertIn("both point at the repository example-app", str(two.exception))

    def test_find_names_both_paths_of_a_duplicate(self) -> None:
        text = record("TASK-sam-2026-0001", "Twice", "ready", refs=["/memory/projects/garden"])
        self.brain.add("open", "TASK-sam-2026-0001-twice", text, store=self.root / "memory/projects/garden/tasks")
        self.brain.add("open", "TASK-sam-2026-0001-twice", text)
        with self.assertRaises(ValueError) as twice:
            task_stores.find(self.root, "TASK-sam-2026-0001")
        self.assertIn("more than one place", str(twice.exception))
        with self.assertRaises(LookupError) as none:
            task_stores.find(self.root, "TASK-sam-2026-0099")
        self.assertIn("not read: another-app:brain/tasks", str(none.exception))

    # ------------------------------------------------ new, routed

    def test_new_goes_to_the_deepest_node_store(self) -> None:
        code, out = run("new", "--title", "Clean the pump", "--status", "ready", "--project",
                        "/memory/projects/garden/pond/pump.md", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        path = self.root / "memory/projects/garden/pond/tasks/open/TASK-sam-2026-0001-clean-the-pump.md"
        self.assertTrue(path.is_file(), out)
        self.assertIn("`TASK-sam-2026-0001`", (path.parent.parent / "STATE.md").read_text(encoding="utf-8"))
        self.assertEqual(run("check", "--store", "/memory/projects/garden/pond/tasks", cwd=self.root)[0], 0)

    def test_new_for_a_pointer_goes_to_its_repository_and_keeps_memory_refs_private(self) -> None:
        code, out = run("new", "--title", "Fix the login page", "--status", "ready", "--project", POINTER,
                        "--project", POINTER + "/notes.md", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("example-app is of unrecorded visibility", out)
        path = self.clone / "brain/tasks/open/TASK-sam-2026-0001-fix-the-login-page.md"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(tasks.parse_front_matter(text)["project_refs"], ["example-app:brain"])
        self.assertNotIn("/memory/", text)
        companion = self.root / "memory/tasks/private/TASK-sam-2026-0001.md"
        meta = tasks.parse_front_matter(companion.read_text(encoding="utf-8"))
        self.assertEqual((meta["type"], meta["store"], meta["memory_refs"]),
                         ("task_private_note", "example-app:brain/tasks", [POINTER + "/notes.md"]))
        self.assertEqual(run("check", "--store", "example-app:brain/tasks", cwd=self.root)[0], 0)

    def test_a_memory_path_in_a_repository_task_is_refused(self) -> None:
        code, out = run("new", "--title", "Read /memory/projects/garden first", "--status", "ready",
                        "--project", POINTER, "--no-board", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("names a /memory/ path", out)
        self.assertFalse((self.clone / "brain" / "tasks").exists())

    def test_new_private_goes_to_the_pointer_node(self) -> None:
        code, out = run("new", "--title", "Ask about the invoice", "--status", "ready", "--project", POINTER,
                        "--private", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertTrue(next((self.root / POINTER.strip("/") / "tasks/open").glob("TASK-sam-2026-0001-*.md"), None))
        self.assertFalse((self.clone / "brain" / "tasks").exists())

    def test_new_for_several_projects_splits_into_related_parts(self) -> None:
        code, out = run("new", "--title", "Order compost", "--status", "ready", "--project", "/memory/projects/garden",
                        "--project", "/memory/projects/garden/pond", "--project", POINTER, "--now", NOW,
                        "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        parts = {
            "TASK-sam-2026-0001": self.root / "memory/projects/garden/tasks/open/TASK-sam-2026-0001-order-compost.md",
            "TASK-sam-2026-0002": self.root / "memory/projects/garden/pond/tasks/open/TASK-sam-2026-0002-order-compost.md",
            "TASK-sam-2026-0003": self.clone / "brain/tasks/open/TASK-sam-2026-0003-order-compost.md",
        }
        split = f"- {NOW} – sam: split: part of work for several projects (TASK-sam-2026-0001, " \
                "TASK-sam-2026-0002, TASK-sam-2026-0003)"
        for tid, path in parts.items():
            text = path.read_text(encoding="utf-8")
            meta = tasks.parse_front_matter(text)
            self.assertEqual(sorted(meta["related_tasks"]), sorted(set(parts) - {tid}))
            self.assertIn(split, text)
        self.assertEqual(tasks.parse_front_matter(parts["TASK-sam-2026-0002"].read_text(encoding="utf-8"))["title"],
                         "Order compost (Pond)")
        self.write_states()
        code, out = run("check", cwd=self.root)
        self.assertEqual(code, 0, out)                          # the parts pass every check...
        self.assertIn("WARN: another-app:brain/tasks: not checked (not checked out here)", out)  # ...one warning
        self.assertNotIn("ERROR", out)

    def test_changes_to_a_repository_task_and_its_private_note(self) -> None:
        run("new", "--title", "Fix the login page", "--status", "ready", "--project", POINTER, "--now", NOW,
            "--no-board", cwd=self.root)
        path = self.clone / "brain/tasks/open/TASK-sam-2026-0001-fix-the-login-page.md"
        code, out = run("note", "TASK-sam-2026-0001", "--private", "--note", "The client prefers mornings.",
                        "--now", NOW, cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertNotIn("mornings", path.read_text(encoding="utf-8"))
        self.assertIn("mornings", (self.root / "memory/tasks/private/TASK-sam-2026-0001.md").read_text(encoding="utf-8"))
        code, out = run("note", "TASK-sam-2026-0001", "--note", "See /memory/projects/garden.", "--no-board",
                        cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("never written into example-app:brain/tasks", out)
        code, out = run("done", "TASK-sam-2026-0001", "--now", NOW, "--no-board", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.clone / "brain/tasks/completed" / path.name).is_file())
        self.assertIn("## Recently completed\n\n- `TASK-sam-2026-0001`",
                      (self.clone / "brain/tasks/STATE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
