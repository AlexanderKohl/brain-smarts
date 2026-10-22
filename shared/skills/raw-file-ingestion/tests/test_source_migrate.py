"""Tests for `ingest_raw.py migrate`: sources leave /memory/sources/ for the store of their node, the
raw file's hash re-verified, references rewritten, a ledger written, and `--reverse` undoing it.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

Fictional fixtures only (SMART-RULE-0008): the brain is fictional_brain.StoreBrain, built without
node READMEs first, so the sources it ingests land where every source lived before P13.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fictional_brain import STAMP, StoreTestCase

CLEAN = "season,trees\n2026,14\n"
FLAGGED = "picker,owed\nOrla Fernwick,$412.50\n"
NOW = "2026-02-01T10:00:00+00:00"


class LegacyBrain(StoreTestCase):
    readmes = False

    def setUp(self) -> None:
        super().setUp()
        b = self.brain
        self.survey = b.ingest_ok(b.sample("survey.csv", CLEAN), "--node", "memory/projects/hedgerow")
        self.press = b.ingest_ok(b.sample("press-log.csv", "batch,litres\n7,120\n"), "--node",
                                 "memory/projects/cider-press")
        self.pickers = b.ingest_ok(b.sample("pickers.csv", FLAGGED), "--node", "memory/projects/cider-press")
        self.loose = b.ingest_ok(b.sample("weather.txt", "Frost on the fifth\n"))
        b.readmes()
        self.knowledge = b.memory / "KNOWLEDGE.md"
        self.knowledge.write_text(
            f"---\nid: knowledge\ntitle: Knowledge\ntype: knowledge\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"created: {STAMP}\nupdated: {STAMP}\n---\n\n# Knowledge\n\n- Tree counts: `{self.survey['canonical_markdown']}`.\n"
            f"- Press batches: `{self.press['canonical_markdown']}`.\n", encoding="utf-8")
        task = b.memory / "tasks" / "open" / "TASK-sam-2026-0001.md"
        task.parent.mkdir(parents=True)
        task.write_text(
            f"---\nid: TASK-sam-2026-0001\ntitle: Count the trees\ntype: task\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"status: ready\nowner: Sam\nauthor: sam\ncreated: {STAMP}\nupdated: {STAMP}\nproject_refs:\n"
            f"  - /memory/projects/hedgerow\n---\n\n# Count the trees\n\nSee `{self.survey['canonical_markdown']}`.\n\n"
            f"## History\n\n- {STAMP} – sam: captured\n", encoding="utf-8")
        self.task = task

    def path(self, shown: str) -> Path:
        if shown.startswith("cider-press:"):
            return self.brain.checkout / shown.split(":", 1)[1]
        return self.brain.file(shown)

    def ok(self, *args: str) -> str:
        done = self.brain.migrate(*args)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def ledger(self, out: str) -> Path:
        return self.brain.file(re.search(r"ledger: (\S+)", out).group(1))

    def dry_run(self, node: str) -> Path:
        out = self.ok("--node", node, "--dry-run")
        return self.brain.file(re.search(r"on the list for \S+: (\S+)", out).group(1)).with_suffix(".json")

    def cleared(self, *decide: str) -> Path:
        listing = self.dry_run("memory/projects/cider-press")
        self.ok("--decide", str(listing), *decide)
        return listing


class MemoryNodeTests(LegacyBrain):
    def test_a_memory_node_takes_its_sources_with_the_hash_reverified_and_references_rewritten(self):
        old_record = self.brain.file(self.survey["canonical_markdown"])
        old_raw = self.brain.file(self.survey["raw_file"])
        digest = hashlib.sha256(old_raw.read_bytes()).hexdigest()
        out = self.ok("--node", "memory/projects/hedgerow")
        new_record = self.brain.hedgerow / "sources" / old_record.name
        new_raw = self.brain.hedgerow / "raw" / old_raw.relative_to(self.brain.memory / "raw")
        self.assertFalse(old_record.exists() or old_raw.parent.exists())
        self.assertEqual(hashlib.sha256(new_raw.read_bytes()).hexdigest(), digest)
        text = new_record.read_text(encoding="utf-8")
        self.assertIn("type: source_document", text)                    # the reference was replaced by the record
        self.assertIn(f'raw_source: "/memory/projects/hedgerow/raw/', text)
        self.assertIn(f"updated: {NOW}", text)
        new_ref = "/memory/projects/hedgerow/sources/" + old_record.name
        self.assertIn(new_ref, self.knowledge.read_text(encoding="utf-8"))
        self.assertIn(f"updated: {NOW}", self.knowledge.read_text(encoding="utf-8"))
        task = self.task.read_text(encoding="utf-8")
        self.assertIn(new_ref, task)
        self.assertRegex(task, rf"- {re.escape(NOW)} – sam: source source-\w+ moved into /memory/projects/hedgerow/raw")
        self.assertTrue(self.ledger(out).is_file())
        # Only the hedgerow source moved; the loose one and the cider-press ones stay.
        self.assertTrue(self.brain.file(self.loose["canonical_markdown"]).is_file())
        self.assertTrue(self.brain.file(self.press["canonical_markdown"]).is_file())

    def test_reverse_puts_everything_back_byte_for_byte(self):
        def snapshot():
            return {k: v for k, v in self.brain.files().items()
                    if not k.endswith("LOG.md") and "/tasks/" not in k and "/migrations/" not in k}
        before = snapshot()
        out = self.ok("--node", "memory/projects/hedgerow")
        self.ok("--reverse", str(self.ledger(out)))
        self.assertEqual(snapshot(), before)
        self.assertIn("moved back to /memory/sources/", self.task.read_text(encoding="utf-8"))
        again = self.brain.migrate("--reverse", str(self.ledger(out)))
        self.assertEqual(again.returncode, 1)
        self.assertIn("moved back already", again.stderr)

    def test_a_raw_file_that_no_longer_matches_its_hash_stops_the_move_before_anything_is_written(self):
        raw = self.brain.file(self.survey["raw_file"])
        raw.write_bytes(raw.read_bytes() + b"tampered\n")
        before = self.brain.files()
        done = self.brain.migrate("--node", "memory/projects/hedgerow")
        self.assertEqual(done.returncode, 1)
        self.assertIn("no longer matches raw_sha256", done.stderr)
        self.assertEqual(self.brain.files(), before)

    def test_private_is_refused_for_a_memory_node(self):
        listing = self.dry_run("memory/projects/hedgerow")
        self.ok("--decide", str(listing), "--private", "1")
        done = self.brain.migrate("--node", "memory/projects/hedgerow", "--list", str(listing))
        self.assertEqual(done.returncode, 1)
        self.assertIn("private already", done.stderr)


class RepositoryTests(LegacyBrain):
    def test_a_pointer_node_moves_only_from_a_cleared_list(self):
        before = self.brain.files()
        done = self.brain.migrate("--node", "memory/projects/cider-press", "--offline")
        self.assertEqual(done.returncode, 1)
        self.assertIn("only from a list the owner cleared", done.stderr)
        self.assertEqual(self.brain.files(), before)

    def test_the_dry_run_lists_the_flags_and_the_weight_and_moves_nothing(self):
        before = self.brain.files()
        out = self.ok("--node", "memory/projects/cider-press", "--dry-run")
        self.assertIn("cider-press is private", out)
        self.assertIn("bytes of raw files", out)
        listing = json.loads(self.dry_run("memory/projects/cider-press").read_text(encoding="utf-8"))
        self.assertEqual(len(listing["items"]), 2)
        flagged = [i for i in listing["items"] if i["flags"]]
        self.assertEqual([i["id"] for i in flagged], [self.pickers["source_id"]])
        self.assertIn("amount", flagged[0]["flags"][0]["flags"])
        self.assertTrue(all(i["decision"] is None for i in listing["items"]))
        after = {k: v for k, v in self.brain.files().items() if "/temp/" not in k}
        self.assertEqual(after, before)

    def test_move_and_private_follow_the_list_and_the_repository_never_names_memory(self):
        press = next(i for i in self.list_items() if i["id"] == self.press["source_id"])["n"]
        pickers = next(i for i in self.list_items() if i["id"] == self.pickers["source_id"])["n"]
        listing = self.cleared("--move", str(press), "--private", str(pickers))
        out = self.ok("--node", "memory/projects/cider-press", "--list", str(listing), "--offline")
        name = Path(self.press["canonical_markdown"]).name
        record = (self.brain.checkout / "brain" / "sources" / name).read_text(encoding="utf-8")
        self.assertIn('raw_source: "brain/raw/', record)
        self.assertIn("project_refs:\n  - cider-press:brain\n", record)
        self.assertNotIn("/memory/", self.brain.repo_text())
        reference = (self.brain.pointer / "sources" / name).read_text(encoding="utf-8")
        self.assertIn(f'canonical_source_md: "cider-press:brain/sources/{name}"', reference)
        self.assertIn(f"cider-press:brain/sources/{name}", self.knowledge.read_text(encoding="utf-8"))
        private = (self.brain.pointer / "sources" / Path(self.pickers["canonical_markdown"]).name).read_text(encoding="utf-8")
        self.assertIn("type: source_document", private)
        self.assertIn('raw_source: "/memory/projects/cider-press/raw/', private)
        self.assertIn("Moved sources into `brain/sources/`", (self.brain.checkout / "brain" / "LOG.md").read_text(encoding="utf-8"))
        self.ok("--reverse", str(self.ledger(out)), "--offline")
        self.assertTrue(self.brain.file(self.press["canonical_markdown"]).is_file())
        self.assertFalse((self.brain.checkout / "brain" / "sources" / name).exists())
        self.assertIn(self.press["canonical_markdown"], self.knowledge.read_text(encoding="utf-8"))

    def test_hold_keeps_a_source_in_memory(self):
        listing = self.cleared("--all", "hold")
        self.ok("--node", "memory/projects/cider-press", "--list", str(listing), "--offline")
        self.assertTrue(self.brain.file(self.pickers["canonical_markdown"]).is_file())
        self.assertFalse((self.brain.checkout / "brain" / "sources").exists())

    def test_a_list_is_stale_once_a_record_changes(self):
        listing = self.cleared("--all", "move")
        record = self.brain.file(self.press["canonical_markdown"])
        record.write_text(record.read_text(encoding="utf-8") + "\nA reviewer's note.\n", encoding="utf-8")
        done = self.brain.migrate("--node", "memory/projects/cider-press", "--list", str(listing), "--offline")
        self.assertEqual(done.returncode, 1)
        self.assertIn("stale", done.stderr)
        self.assertFalse((self.brain.checkout / "brain" / "sources").exists())

    def list_items(self) -> list[dict]:
        return json.loads(self.dry_run("memory/projects/cider-press").read_text(encoding="utf-8"))["items"]


if __name__ == "__main__":
    import unittest
    unittest.main()
