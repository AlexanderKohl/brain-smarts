"""The migration (task_migrate.py): split, node, owner store, repository with a cleared list, reverse.

All names, addresses and content below are fictional.
"""

from __future__ import annotations

import json
import unittest

from brainfix import NOW, Brain, record
from test_tasks import run

import task_history  # noqa: E402
import tasks  # noqa: E402

POINTER = "/memory/projects/example-app"
GARDEN = "/memory/projects/garden"
CLUB = "/memory/projects/pond-club"


class MigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        b = self.brain = Brain()
        self.root, self.store = b.root, b.store
        b.node(GARDEN, "Garden")
        b.node(CLUB, "Pond club")
        b.node(POINTER, "Example app", node_type="project_pointer",
               repo_url="https://example.com/sam/example-app.git", default_branch="main")
        self.clone = b.checkout("example-app")
        legacy = dict(author=None, history="- 2026-03-01T09:00:00+10:00 – captured by hand.")
        b.add("open", "TASK-2026-0001-beds", record("TASK-2026-0001", "Weed the beds", "ready", refs=[GARDEN], **legacy))
        b.add("open", "TASK-2026-0002-pump", record("TASK-2026-0002", "Buy a pump", "ready", refs=[GARDEN, CLUB],
                                                    body="## Outcome\n\nA pump that runs quietly.\n\n", **legacy))
        b.add("completed", "TASK-2026-0003-hose", record("TASK-2026-0003", "Fix the hose", "completed",
                                                         refs=[GARDEN, POINTER], **legacy))
        b.add("open", "TASK-2026-0004-login", record(
            "TASK-2026-0004", "Fix the login page", "ready", refs=[POINTER],
            body="The quote was $1,200 last week.\nNotes in /memory/projects/example-app/notes.md.\n\n", **legacy))
        b.add("completed", "TASK-2026-0005-docs", record("TASK-2026-0005", "Write the docs", "completed",
                                                         refs=[POINTER], **legacy))
        b.add("open", "TASK-2026-0006-fees", record("TASK-2026-0006", "Agree the fees", "ready", refs=[POINTER], **legacy))
        b.add("open", "TASK-2026-0007-tidy", record("TASK-2026-0007", "Tidy the desk", "ready", **legacy))

    def tearDown(self) -> None:
        self.brain.close()

    def migrate(self, *args: str) -> tuple[int, str]:
        return run("migrate", *args, "--now", NOW, cwd=self.root)

    def listing(self, name: str) -> dict:
        return json.loads((self.root / "temp/migration" / f"{name}.json").read_text(encoding="utf-8"))

    def meta(self, path) -> dict:
        return tasks.parse_front_matter(path.read_text(encoding="utf-8"))

    # ------------------------------------------------ split

    def test_split_lists_then_makes_the_cleared_parts(self) -> None:
        code, out = self.migrate("--split", "--dry-run")
        self.assertEqual(code, 0, out)
        items = self.listing("split-all")["items"]
        self.assertEqual([(i["n"], i["id"], i["decision"]) for i in items], [(1, "TASK-2026-0002", None)])
        self.assertEqual(items[0]["parts"][0]["title"], "Buy a pump (Pond club)")
        lst = str(self.root / "temp/migration/split-all.json")
        code, out = self.migrate("--split", "--list", lst)
        self.assertEqual(code, 1)
        self.assertIn("have no decision; nothing was moved", out)
        self.assertEqual(self.migrate("--decide", lst, "--all", "move")[0], 0)
        code, out = self.migrate("--split", "--list", lst)
        self.assertEqual(code, 0, out)
        original = self.store / "open/TASK-2026-0002-pump.md"
        part = self.store / "open/TASK-sam-2026-0008-buy-a-pump-pond-club.md"
        split = f"- {NOW} – sam: split: part of work for several projects (TASK-2026-0002, TASK-sam-2026-0008)"
        self.assertEqual((self.meta(original)["project_refs"], self.meta(original)["related_tasks"]),
                         ([GARDEN], ["TASK-sam-2026-0008"]))
        self.assertEqual(self.meta(original)["author"], "sam")
        part_meta = self.meta(part)
        self.assertEqual((part_meta["project_refs"], part_meta["related_tasks"], part_meta["created"]),
                         ([CLUB], ["TASK-2026-0002"], NOW))
        part_text = part.read_text(encoding="utf-8")
        self.assertIn("## Outcome\n\nThe part of `TASK-2026-0002` for `/memory/projects/pond-club`. A pump that runs "
                      "quietly.\n", part_text)
        for text in (original.read_text(encoding="utf-8"), part_text):
            self.assertIn(split, text)
        self.assertNotIn("captured by hand", part_text)
        self.assertEqual(self.migrate("--split", "--dry-run")[0], 0)
        self.assertEqual(self.listing("split-all")["items"], [])       # nothing left to split

    def test_a_stale_list_is_refused(self) -> None:
        self.migrate("--split", "--dry-run")
        lst = str(self.root / "temp/migration/split-all.json")
        self.migrate("--decide", lst, "--all", "move")
        path = self.store / "open/TASK-2026-0002-pump.md"
        path.write_text(path.read_text(encoding="utf-8") + "One more line.\n", encoding="utf-8")
        code, out = self.migrate("--split", "--list", lst)
        self.assertEqual(code, 1)
        self.assertIn("is stale", out)
        self.assertFalse(list(self.store.glob("open/TASK-sam-*")))

    # ------------------------------------------------ node and owner store

    def test_node_move_keeps_names_adds_author_and_reverses(self) -> None:
        code, out = self.migrate("--node", GARDEN, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.store / "open/TASK-2026-0001-beds.md").is_file())
        code, out = self.migrate("--node", GARDEN)
        self.assertEqual(code, 0, out)
        moved = self.root / "memory/projects/garden/tasks/open/TASK-2026-0001-beds.md"
        text = moved.read_text(encoding="utf-8")
        self.assertEqual((self.meta(moved)["author"], self.meta(moved)["updated"]), ("sam", NOW))
        self.assertIn(f"- {NOW} – sam: moved into the node's tasks/ (PROPOSAL-shared-project-tasks-in-the-repository)",
                      text)
        self.assertIn("captured by hand", text)
        self.assertTrue((self.root / "memory/projects/garden/tasks/completed/TASK-2026-0003-hose.md").is_file())
        self.assertFalse((self.store / "open/TASK-2026-0001-beds.md").exists())
        self.assertIn("`TASK-2026-0001`", (self.root / "memory/projects/garden/tasks/STATE.md").read_text(encoding="utf-8"))
        self.assertNotIn("`TASK-2026-0001`", (self.store / "STATE.md").read_text(encoding="utf-8"))
        code, out = run("check", "--store", GARDEN + "/tasks", cwd=self.root)
        self.assertIn("TASK-2026-0002-pump.md: names more than one node", out)   # not split first
        self.assertNotIn("TASK-2026-0003-hose.md: names more than one node", out)  # completed: not split
        ledger = next((self.store / "migrations").glob("*-node-memory-projects-garden.json"))
        code, out = self.migrate("--reverse", str(ledger))
        self.assertEqual(code, 0, out)
        back = (self.store / "open/TASK-2026-0001-beds.md").read_text(encoding="utf-8")
        self.assertIn("sam: moved back to /memory/tasks (migrate --reverse)", back)
        self.assertFalse(moved.exists())

    def test_owner_store_gains_author_and_an_attributed_entry(self) -> None:
        code, out = self.migrate("--owner-store")
        self.assertEqual(code, 0, out)
        path = self.store / "open/TASK-2026-0007-tidy.md"
        self.assertEqual(self.meta(path)["author"], "sam")
        self.assertEqual(task_history.newest_attributed(path.read_text(encoding="utf-8")).at.isoformat(), NOW)
        self.assertIsNone(self.meta(self.store / "open/TASK-2026-0001-beds.md").get("author"))   # has a project

    # ------------------------------------------------ repository

    def test_repository_move_follows_the_cleared_list(self) -> None:
        code, out = self.migrate("--repo", "example-app", "--dry-run")
        self.assertEqual(code, 0, out)
        listing = self.listing("repository-example-app")
        self.assertEqual([(i["n"], i["id"]) for i in listing["items"]],
                         [(1, "TASK-2026-0004"), (2, "TASK-2026-0006"), (3, "TASK-2026-0005")])
        flagged = {f["line"]: f["flags"] for f in listing["items"][0]["flags"]}
        amount = next(n for n, f in flagged.items() if "amount" in f)
        memory = next(n for n, f in flagged.items() if "/memory/ path" in f)
        md = (self.root / "temp/migration/repository-example-app.md").read_text(encoding="utf-8")
        self.assertIn(f"line {amount}: amount", md)
        lst = str(self.root / "temp/migration/repository-example-app.json")
        self.migrate("--decide", lst, "--all", "move", "--private", "2")
        code, out = self.migrate("--repo", "example-app", "--list", lst)
        self.assertEqual(code, 1)
        self.assertIn(f"--private-lines 1:{memory}", out)
        self.assertFalse((self.clone / "brain/tasks").exists())               # nothing was moved
        self.migrate("--decide", lst, "--private-lines", f"1:{amount},{memory}")
        code, out = self.migrate("--repo", "example-app", "--list", lst)
        self.assertEqual(code, 0, out)
        moved = self.clone / "brain/tasks/open/TASK-2026-0004-login.md"
        text = moved.read_text(encoding="utf-8")
        self.assertEqual(self.meta(moved)["project_refs"], ["example-app:brain"])
        self.assertNotIn("/memory/", text)
        self.assertNotIn("1,200", text)
        companion = (self.root / "memory/tasks/private/TASK-2026-0004.md").read_text(encoding="utf-8")
        self.assertIn("The quote was $1,200 last week.", companion)
        self.assertIn(POINTER, companion)
        self.assertTrue((self.root / "memory/projects/example-app/tasks/open/TASK-2026-0006-fees.md").is_file())
        self.assertTrue((self.clone / "brain/tasks/completed/TASK-2026-0005-docs.md").is_file())
        self.assertEqual(run("check", "--store", "example-app:brain/tasks", cwd=self.root)[0], 0)
        ledger = next((self.store / "migrations").glob("*-repository-example-app.json"))
        code, out = self.migrate("--reverse", str(ledger))
        self.assertEqual(code, 0, out)
        back = self.store / "open/TASK-2026-0004-login.md"
        self.assertEqual(self.meta(back)["project_refs"], [POINTER])
        self.assertIn("## Private notes (restored)\n\nThe quote was $1,200 last week.", back.read_text(encoding="utf-8"))
        self.assertTrue((self.store / "open/TASK-2026-0006-fees.md").is_file())
        self.assertFalse(moved.exists())

    def test_hold_moves_nothing(self) -> None:
        self.migrate("--repo", "example-app", "--dry-run")
        lst = str(self.root / "temp/migration/repository-example-app.json")
        self.migrate("--decide", lst, "--all", "hold")
        code, out = self.migrate("--repo", "example-app", "--list", lst)
        self.assertEqual(code, 0, out)
        self.assertIn("held TASK-2026-0004", out)
        self.assertTrue((self.store / "open/TASK-2026-0004-login.md").is_file())
        self.assertFalse(list((self.clone / "brain").glob("tasks/*/*.md")))


if __name__ == "__main__":
    unittest.main()
