"""Tests for ingest_raw.py: what reaches /memory/raw/, /memory/sources/ and the logs.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

Each test builds a fictional brain in a temporary folder and ingests fictional files
(SMART-RULE-0008); the script finds that brain from its working directory.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_raw.py"
STAMP = "2026-01-05T09:00:00+00:00"


def front_matter(id_: str, type_: str) -> str:
    return (f"---\nid: {id_}\ntitle: {id_}\ntype: {type_}\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"created: {STAMP}\nupdated: {STAMP}\n---\n")


class Brain:
    """A fictional brain: a contract, a memory checkout, one project node and the ingestion log."""

    def __init__(self, folder: Path):
        self.root = folder / "brain"
        self.memory = self.root / "memory"
        self.node = self.memory / "projects" / "orchard-club"
        self.node.mkdir(parents=True)
        (self.root / "CONTRACT.md").write_text(front_matter("brain-contract", "contract"), encoding="utf-8")
        (self.node / "LOG.md").write_text(front_matter("orchard-club-log", "log") + "\n# Activity Log\n",
                                          encoding="utf-8")
        log = self.memory / "systems" / "raw-file-management" / "LOG.md"
        log.parent.mkdir(parents=True)
        log.write_text(front_matter("raw-file-management-log", "log") + "\n# Activity Log\n", encoding="utf-8")
        self.log = log
        self.inbox = folder / "inbox"
        self.inbox.mkdir()

    def sample(self, name: str, content: bytes | str) -> Path:
        path = self.inbox / name
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def ingest(self, path: Path, *extra: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), str(path), *extra], cwd=cwd or self.root,
                              capture_output=True, text=True, encoding="utf-8")

    def ingest_ok(self, path: Path, *extra: str) -> dict:
        done = self.ingest(path, *extra)
        if done.returncode:
            raise AssertionError(f"ingest failed ({done.returncode}): {done.stderr}")
        return json.loads(done.stdout)

    def file(self, repo_path: str) -> Path:
        return self.root / repo_path.lstrip("/")

    def records(self) -> list[Path]:
        return sorted((self.memory / "sources").glob("*.md"))


class IngestTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


class RawStoreTests(IngestTestCase):
    def test_raw_file_is_an_unchanged_copy_with_its_hash_recorded(self):
        content = b"plot,holder\r\nA-01,Orla Fernwick\r\n"
        result = self.brain.ingest_ok(self.brain.sample("plots.csv", content))
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(self.brain.file(result["raw_file"]).read_bytes(), content)
        self.assertEqual(result["source_id"], "source-" + digest[:12])
        record = self.brain.file(result["canonical_markdown"]).read_text(encoding="utf-8")
        self.assertIn(f"raw_sha256: {digest}", record)
        self.assertIn(f'raw_source: "{result["raw_file"]}"', record)


class ReingestTests(IngestTestCase):
    def test_reingesting_keeps_a_record_converted_since(self):
        path = self.brain.sample("ledger.xlsx", b"PK\x03\x04 fictional workbook bytes")
        first = self.brain.ingest_ok(path)
        record = self.brain.file(first["canonical_markdown"])
        converted = record.read_text(encoding="utf-8").replace(
            "conversion_status: pending_conversion", "conversion_status: complete") + "\nConverted by a reviewer.\n"
        record.write_text(converted, encoding="utf-8")

        again = self.brain.ingest_ok(path)

        self.assertEqual(record.read_text(encoding="utf-8"), converted)
        self.assertEqual(again["canonical_markdown"], first["canonical_markdown"])
        self.assertEqual(again["conversion_status"], "complete")
        self.assertTrue(again["duplicate_reused"])
        self.assertTrue(again["source_record_reused"])
        self.assertIn("again: identical to", self.brain.log.read_text(encoding="utf-8"))

    def test_reingesting_under_another_title_makes_no_second_record(self):
        path = self.brain.sample("minutes.txt", "Orchard club minutes\n")
        self.brain.ingest_ok(path)
        self.brain.ingest_ok(path, "--title", "Minutes copy")
        self.assertEqual(len(self.brain.records()), 1)

    def test_reingesting_for_a_new_node_references_the_existing_record(self):
        path = self.brain.sample("minutes.txt", "Orchard club minutes\n")
        first = self.brain.ingest_ok(path)
        again = self.brain.ingest_ok(path, "--node", "memory/projects/orchard-club")
        reference = self.brain.node / "sources" / Path(first["canonical_markdown"]).name
        self.assertIn(f'canonical_source_md: "{first["canonical_markdown"]}"', reference.read_text(encoding="utf-8"))
        self.assertEqual(again["canonical_markdown"], first["canonical_markdown"])
        self.assertIn("Referenced existing source", (self.brain.node / "LOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
