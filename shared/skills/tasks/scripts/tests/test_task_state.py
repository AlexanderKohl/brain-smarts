"""The generated STATE.md (task_state.py): deterministic, ordered for the reader, never hand-kept.

All content below is fictional.
"""

from __future__ import annotations

import unittest

from brainfix import Brain, record

import task_state  # noqa: E402
import task_stores  # noqa: E402

RECORDS = [
    ("open", "TASK-sam-2026-0002-b", record("TASK-sam-2026-0002", "Second by sam", "waiting", next_review="2026-04-01",
                                            waiting_on="Example Supplies | Ltd")),
    ("open", "TASK-2026-0009-legacy", record("TASK-2026-0009", "A legacy task " + "x" * 90, "ready", priority="high")),
    ("open", "TASK-bob-2026-0001-a", record("TASK-bob-2026-0001", "First by bob", "blocked", author="bob")),
    ("inbox", "TASK-sam-2026-0003-idea", record("TASK-sam-2026-0003", "An idea", "inbox")),
    ("completed", "TASK-sam-2026-0001-old", record("TASK-sam-2026-0001", "Old one", "completed",
                                                   updated="2026-03-02T09:00:00+10:00")),
    ("completed", "TASK-sam-2026-0004-new", record("TASK-sam-2026-0004", "New one", "completed",
                                                   updated="2026-03-05T09:00:00+10:00")),
]


class StateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brains = [Brain(), Brain()]

    def tearDown(self) -> None:
        for brain in self.brains:
            brain.close()

    def fill(self, brain: Brain, order: list) -> str:
        for folder, stem, text in order:
            brain.add(folder, stem, text)
        store = task_stores.owner_store(brain.root)
        self.assertTrue(task_state.write(store))
        self.assertFalse(task_state.write(store))           # nothing changed: nothing written
        return (brain.store / "STATE.md").read_bytes().decode("utf-8")

    def test_the_same_records_give_the_same_bytes_whatever_their_order_on_disk(self) -> None:
        first = self.fill(self.brains[0], RECORDS)
        second = self.fill(self.brains[1], list(reversed(RECORDS)))
        self.assertEqual(first, second)

    def test_layout_order_and_cells(self) -> None:
        text = self.fill(self.brains[0], RECORDS)
        self.assertTrue(text.startswith("---\nid: tasks-state\ntitle: Tasks – /memory/tasks\ntype: state\n"))
        self.assertIn("generated_by: /shared/skills/tasks\ncreated: 2026-03-01T09:00:00+10:00\n"
                      "updated: 2026-03-05T09:00:00+10:00\n", text)
        table = [line for line in text.splitlines() if line.startswith("| `")]
        self.assertEqual([line.split("`")[1] for line in table],
                         ["TASK-2026-0009", "TASK-bob-2026-0001", "TASK-sam-2026-0002"])
        self.assertIn("| review 2026-04-01; waiting on Example Supplies / Ltd |", text)
        self.assertIn("x" * 10 + "... |", text)
        self.assertLessEqual(len(table[0].split(" | ")[-1].rstrip(" |")), 80)
        self.assertIn("## Inbox (1)\n\n- `TASK-sam-2026-0003` An idea\n", text)
        self.assertIn("## Recently completed\n\n- `TASK-sam-2026-0004` New one (2026-03-05)\n"
                      "- `TASK-sam-2026-0001` Old one (2026-03-02)\n", text)

    def test_differs_reports_a_hand_edit_and_write_repairs_it(self) -> None:
        brain = self.brains[0]
        self.fill(brain, RECORDS)
        store = task_stores.owner_store(brain.root)
        path = brain.store / "STATE.md"
        path.write_text(path.read_text(encoding="utf-8") + "A hand-written line.\n", encoding="utf-8")
        self.assertTrue(task_state.differs(store))
        self.assertTrue(task_state.write(store))
        self.assertFalse(task_state.differs(store))

    def test_ids_of_node_pointer_and_repository_stores(self) -> None:
        Store = task_stores.Store
        root = self.brains[0].root
        self.assertEqual(task_state.state_id(Store("memory-node", root, "/memory/projects/garden/pond")),
                         "projects-garden-pond-tasks-state")
        self.assertEqual(task_state.state_id(Store("pointer-private", root, "/memory/projects/example-app")),
                         "projects-example-app-private-tasks-state")
        self.assertEqual(task_state.state_id(Store("repository", root, "/memory/projects/x", repository="Example-App")),
                         "example-app-tasks-state")

    def test_an_empty_store_never_writes_null_stamps(self) -> None:
        brain = self.brains[0]
        node = brain.node("/memory/projects/garden", "Garden")          # README created 2026-03-01T09:00:00+10:00
        (node / "tasks").mkdir()
        store = task_stores.Store("memory-node", node / "tasks", "/memory/projects/garden")
        task_state.write(store)
        text = (node / "tasks" / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("\ncreated: 2026-03-01T09:00:00+10:00\nupdated: 2026-03-01T09:00:00+10:00\n", text)
        self.assertNotIn("null", text)
        # The existing STATE.md comes first, so the text stays put even if the README changes.
        (node / "README.md").write_text("---\nid: garden\ncreated: 2026-05-05T09:00:00+10:00\n---\n", encoding="utf-8")
        self.assertFalse(task_state.differs(store))
        # With nothing at all to read, the clock gives a full timestamp.
        bare = task_stores.Store("memory-node", brain.tmp / "nowhere" / "tasks", "/memory/projects/nowhere")
        rendered = task_state.render(bare, [])
        stamp = rendered.split("\ncreated: ")[1].split("\n")[0]
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertIn(f"\nupdated: {stamp}\n", rendered)

    def test_a_store_emptied_by_a_move_keeps_its_last_stamps(self) -> None:
        brain = self.brains[0]
        path = brain.add("open", "TASK-sam-2026-0001-x", record("TASK-sam-2026-0001", "Only one", "ready",
                                                                 updated="2026-03-04T09:00:00+10:00"))
        store = task_stores.owner_store(brain.root)
        task_state.write(store)
        path.unlink()
        task_state.write(store)
        text = (brain.store / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("\ncreated: 2026-03-01T09:00:00+10:00\nupdated: 2026-03-04T09:00:00+10:00\n", text)
        self.assertIn("## Open tasks (0)", text)


if __name__ == "__main__":
    unittest.main()
