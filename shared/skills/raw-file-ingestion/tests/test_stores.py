"""Tests for the raw store choice (P13): which store a new source goes to, the flags asked before
a write into a repository (exit 7), --private and --keep-in-repository, and the hash reused across
stores but never across the memory/repository boundary (P15, exit 8).

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

Fictional data only (SMART-RULE-0008); the brain is fictional_brain.StoreBrain.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from fictional_brain import StoreTestCase, git

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import raw_stores  # noqa: E402

CLEAN = "season,trees\n2026,14\n"
FLAGGED = "picker,contact,owed\nOrla Fernwick,ceo@send.example.org,$412.50\n"


class ChooseTests(StoreTestCase):
    def test_each_place_gets_its_store(self):
        root = self.brain.root
        cases = [(None, False, "owner", self.brain.memory / "raw"),
                 ("/memory/projects/orchard-club", False, "owner", self.brain.memory / "raw"),
                 ("/memory/projects/hedgerow", False, "memory-node", self.brain.hedgerow / "raw"),
                 ("/memory/projects/cider-press", False, "repository", self.brain.checkout / "brain" / "raw"),
                 ("/memory/projects/cider-press", True, "pointer-private", self.brain.pointer / "raw")]
        for node, private, kind, raw in cases:
            with self.subTest(node=node, private=private):
                store = raw_stores.choose(root, node, private)
                self.assertEqual((store.kind, store.raw), (kind, raw))
                self.assertEqual(store.sources, raw.parent / "sources")

    def test_private_needs_a_pointer_node(self):
        for node in (None, "/memory/projects/hedgerow", "/memory/projects/orchard-club"):
            with self.subTest(node=node), self.assertRaises(ValueError):
                raw_stores.choose(self.brain.root, node, True)

    def test_flags_name_each_kind_of_possibly_private_text(self):
        found = raw_stores.flags("Paid $412.50 to ceo@send.example.org, see /memory/KNOWLEDGE.md",
                                 self.brain.root)
        self.assertEqual(found, ["/memory/ path", "amount", "contact detail"])
        self.assertEqual(raw_stores.flags("Notes from Sam Rowan", self.brain.root), ["owner term"])
        self.assertEqual(raw_stores.flags("fourteen trees", self.brain.root), [])


class IngestIntoStoresTests(StoreTestCase):
    def test_a_memory_node_keeps_its_source_in_its_own_raw_and_sources(self):
        result = self.brain.ingest_ok(self.brain.sample("survey.csv", CLEAN), "--node", "memory/projects/hedgerow")
        self.assertTrue(result["raw_file"].startswith("/memory/projects/hedgerow/raw/"))
        self.assertTrue(result["canonical_markdown"].startswith("/memory/projects/hedgerow/sources/"))
        record = self.brain.file(result["canonical_markdown"]).read_text(encoding="utf-8")
        self.assertIn("project_refs:\n  - /memory/projects/hedgerow\n", record)
        self.assertIn("type: source_document", record)
        self.assertEqual(len(list((self.brain.hedgerow / "sources").glob("*.md"))), 1)   # no reference beside it
        self.assertFalse((self.brain.memory / "sources").exists())
        self.assertIn("Ingested source `survey.csv`", (self.brain.hedgerow / "LOG.md").read_text(encoding="utf-8"))

    def test_a_pointer_node_writes_into_the_repository_with_repository_paths_only(self):
        result = self.brain.ingest_ok(self.brain.sample("press-log.csv", CLEAN), "--node",
                                      "memory/projects/cider-press", "--offline")
        self.assertEqual(result["store"], "cider-press:brain/raw")
        self.assertTrue(result["raw_file"].startswith("cider-press:brain/raw/"))
        record = next((self.brain.checkout / "brain" / "sources").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn('raw_source: "brain/raw/', record)
        self.assertIn('project_refs:\n  - cider-press:brain\n', record)
        self.assertNotIn("/memory/", self.brain.repo_text())
        manifest = json.loads(next((self.brain.checkout / "brain" / "raw").rglob("manifest.json")).read_text(encoding="utf-8"))
        self.assertNotIn("original_path", manifest)
        self.assertIn("cider-press is private", " ".join(result["notes"]))
        self.assertIn("Ingested source `press-log.csv`", (self.brain.checkout / "brain" / "LOG.md").read_text(encoding="utf-8"))
        self.assertFalse((self.brain.pointer / "sources").exists())

    def test_a_repository_whose_visibility_is_not_recorded_is_treated_as_public(self):
        self.brain.readmes(visibility="unknown")
        result = self.brain.ingest_ok(self.brain.sample("press-log.csv", CLEAN), "--node",
                                      "memory/projects/cider-press", "--offline")
        self.assertIn("treat it as public", " ".join(result["notes"]))


class RepositoryRefusalTests(StoreTestCase):
    def assert_nothing_written(self, code: int, *extra: str, name: str = "pickers.csv",
                               content: str = FLAGGED) -> dict:
        sample = self.brain.sample(name, content)
        before = self.brain.files()
        done = self.brain.ingest(sample, "--node", "memory/projects/cider-press", "--offline", *extra)
        self.assertEqual(done.returncode, code, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(self.brain.files(), before)
        return json.loads(done.stdout) if done.stdout.strip() else {}

    def test_a_flagged_source_is_refused_with_exit_7_and_its_flags(self):
        result = self.assert_nothing_written(7)
        self.assertFalse(result["written"])
        self.assertEqual(result["repository"], "cider-press")
        flagged = {f["where"]: f["flags"] for f in result["flags"]}
        self.assertIn(["amount", "contact detail"], flagged.values())

    def test_a_file_name_or_title_is_flagged_too(self):
        self.assert_nothing_written(7, name="Sam Rowan notes.csv", content=CLEAN)
        self.assert_nothing_written(7, "--title", "Owed $12", content=CLEAN)

    def test_a_file_whose_content_cannot_be_read_is_flagged(self):
        result = self.assert_nothing_written(7, name="press.bin", content="\x00\x01")
        self.assertIn("nothing in it was checked", json.dumps(result["flags"]))

    def test_private_puts_a_flagged_source_in_the_pointer_node(self):
        result = self.brain.ingest_ok(self.brain.sample("pickers.csv", FLAGGED), "--node",
                                      "memory/projects/cider-press", "--private")
        self.assertTrue(result["raw_file"].startswith("/memory/projects/cider-press/raw/"))
        self.assertEqual(result["store"], "/memory/projects/cider-press/raw")
        self.assertFalse((self.brain.checkout / "brain" / "raw").exists())

    def test_keep_in_repository_writes_a_flagged_source_and_says_what_was_flagged(self):
        result = self.brain.ingest_ok(self.brain.sample("pickers.csv", FLAGGED), "--node",
                                      "memory/projects/cider-press", "--keep-in-repository", "--offline")
        self.assertTrue(result["raw_file"].startswith("cider-press:brain/raw/"))
        self.assertIn("though flagged", " ".join(result["notes"]))

    def test_private_on_a_memory_node_is_refused(self):
        done = self.brain.ingest(self.brain.sample("survey.csv", CLEAN), "--node", "memory/projects/hedgerow",
                                 "--private")
        self.assertEqual(done.returncode, 4, done.stderr)

    def test_a_checkout_off_the_store_branch_is_refused(self):
        git(self.brain.checkout, "checkout", "-q", "-b", "elsewhere")
        self.assert_nothing_written(9, content=CLEAN)

    def test_a_repository_not_checked_out_is_refused(self):
        shutil.rmtree(self.brain.checkout / "brain")
        sample = self.brain.sample("press-log.csv", CLEAN)
        done = self.brain.ingest(sample, "--node", "memory/projects/cider-press", "--offline")
        self.assertEqual(done.returncode, 9, done.stderr)
        self.assertIn("no brain/ folder", done.stderr)


class DuplicateAcrossStoresTests(StoreTestCase):
    def test_a_duplicate_in_a_memory_node_is_reused_for_another_folder_by_reference(self):
        sample = self.brain.sample("survey.csv", CLEAN)
        first = self.brain.ingest_ok(sample, "--node", "memory/projects/hedgerow")
        again = self.brain.ingest_ok(sample, "--node", "memory/projects/orchard-club")
        self.assertTrue(again["duplicate_reused"] and again["source_record_reused"])
        reference = self.brain.node / "sources" / Path(first["canonical_markdown"]).name
        text = reference.read_text(encoding="utf-8")
        self.assertIn("type: source_reference", text)
        self.assertIn(f'canonical_source_md: "{first["canonical_markdown"]}"', text)
        self.assertEqual(len(list(self.brain.memory.rglob("manifest.json"))), 1)

    def test_a_duplicate_in_memory_is_refused_for_a_repository(self):
        sample = self.brain.sample("survey.csv", CLEAN)
        first = self.brain.ingest_ok(sample, "--node", "memory/projects/hedgerow")
        before = self.brain.files()
        done = self.brain.ingest(sample, "--node", "memory/projects/cider-press", "--offline")
        self.assertEqual(done.returncode, 8, done.stderr)
        self.assertIn(first["canonical_markdown"], done.stderr)
        self.assertEqual(self.brain.files(), before)

    def test_a_duplicate_in_the_repository_is_reused_from_memory_with_the_repository_form(self):
        sample = self.brain.sample("press-log.csv", CLEAN)
        first = self.brain.ingest_ok(sample, "--node", "memory/projects/cider-press", "--offline")
        again = self.brain.ingest_ok(sample, "--node", "memory/projects/hedgerow")
        self.assertEqual(again["canonical_markdown"], first["canonical_markdown"])
        reference = (self.brain.hedgerow / "sources" / Path(first["canonical_markdown"]).name).read_text(encoding="utf-8")
        self.assertIn('canonical_source_md: "cider-press:brain/sources/', reference)
        self.assertIn('raw_source: "cider-press:brain/raw/', reference)

    def test_a_duplicate_in_the_same_repository_is_reused_and_nothing_is_written_there(self):
        sample = self.brain.sample("press-log.csv", CLEAN)
        self.brain.ingest_ok(sample, "--node", "memory/projects/cider-press", "--offline")
        before = self.brain.files(self.brain.checkout)
        again = self.brain.ingest_ok(sample, "--node", "memory/projects/cider-press", "--offline")
        self.assertTrue(again["source_record_reused"])
        self.assertEqual(self.brain.files(self.brain.checkout), before)
        self.assertFalse((self.brain.pointer / "sources").exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
