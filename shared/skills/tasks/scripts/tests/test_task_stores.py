"""Store discovery, node resolution and routing of new tasks (task_stores.py, task_new.py).

All names, titles and repositories below are fictional.
"""

from __future__ import annotations

import unittest

from brainfix import NOW, Brain, record
from test_tasks import run

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
                         ("task_private_note", "example-app:brain/tasks", [POINTER, POINTER + "/notes.md"]))
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
        self.assertEqual(run("check", cwd=self.root)[0], 1)     # another-app is only a warning...
        code, out = run("check", cwd=self.root)
        self.assertNotIn("names more than one node", out)       # ...and no part names two nodes

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
