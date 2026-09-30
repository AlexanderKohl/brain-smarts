"""Tests for ingest_raw.py: what reaches /memory/raw/, /memory/sources/ and the logs.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

The fictional brain they run in is fictional_brain.py.
"""
from __future__ import annotations

import codecs
import hashlib
import re
import unittest
from pathlib import Path

from fictional_brain import IngestTestCase


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


class EncodingTests(IngestTestCase):
    """Text files as other editors save them; the record is always clean UTF-8 text."""

    def record_of(self, name: str, content: bytes) -> tuple[dict, str]:
        result = self.brain.ingest_ok(self.brain.sample(name, content))
        record = self.brain.file(result["canonical_markdown"]).read_bytes()
        self.assertNotIn(b"\x00", record)
        return result, record.decode("utf-8")

    def test_a_byte_order_mark_names_the_encoding_and_is_left_out(self):
        words = "Orchard café résumé\nSecond line\n"
        for label, content in [("utf-8", codecs.BOM_UTF8 + words.encode("utf-8")),
                               ("utf-16-le", codecs.BOM_UTF16_LE + words.encode("utf-16-le")),
                               ("utf-16-be", codecs.BOM_UTF16_BE + words.encode("utf-16-be")),
                               ("utf-32-le", codecs.BOM_UTF32_LE + words.encode("utf-32-le"))]:
            with self.subTest(label):
                result, record = self.record_of(f"note-{label}.txt", content)
                self.assertEqual(result["conversion_status"], "complete")
                self.assertIn("Orchard café résumé\nSecond line", record)
                self.assertNotIn("﻿", record)

    def test_utf16_without_a_mark_fails_instead_of_writing_binary_into_the_record(self):
        result, record = self.record_of("unmarked.txt", "Orchard notes\n".encode("utf-16-le"))
        self.assertEqual(result["conversion_status"], "failed")
        self.assertIn("NUL bytes", record)

    def test_text_that_is_not_utf8_is_partial_and_says_so(self):
        result, record = self.record_of("latin.csv", "plot,holder\nD-01,Zoë Quillon\n".encode("cp1252"))
        self.assertEqual(result["conversion_status"], "partial")
        self.assertIn("Zo\N{REPLACEMENT CHARACTER} Quillon", record)
        self.assertIn("not UTF-8", record)


class LineEndingTests(IngestTestCase):
    def test_a_log_with_crlf_line_ends_keeps_them(self):
        log = self.brain.log
        log.write_bytes(log.read_bytes().replace(b"\n", b"\r\n"))
        self.brain.ingest_ok(self.brain.sample("notes.txt", "Orchard notes\r\n"))
        data = log.read_bytes()
        self.assertIn(b"- Ingested `notes.txt`", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_records_references_and_manifests_are_written_with_lf(self):
        # Proves the LF contract on every platform; only a Windows run could fail without newline="\n".
        result = self.brain.ingest_ok(self.brain.sample("notes.txt", "Orchard notes\r\n"),
                                      "--node", "memory/projects/orchard-club")
        written = [self.brain.file(result["canonical_markdown"]),
                   self.brain.node / "sources" / Path(result["canonical_markdown"]).name,
                   self.brain.file(result["raw_file"]).parent / "manifest.json"]
        for path in written:
            with self.subTest(path.name):
                self.assertNotIn(b"\r", path.read_bytes())


class RefusalTests(IngestTestCase):
    """A refused run writes nothing: no raw copy, no record, no log line."""

    def written(self) -> list[str]:
        return sorted(str(p.relative_to(self.brain.root)) for p in self.brain.root.rglob("*") if p.is_file())

    def assert_refused(self, code: int, *extra: str, cwd: Path | None = None) -> str:
        before = self.written()
        log = self.brain.log.read_text(encoding="utf-8")
        done = self.brain.ingest(self.brain.sample("notes.txt", "Orchard notes\n"), *extra, cwd=cwd)
        self.assertEqual(done.returncode, code, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(self.written(), before)
        self.assertEqual(self.brain.log.read_text(encoding="utf-8"), log)
        return done.stderr

    def test_missing_node_is_refused_before_anything_is_written(self):
        self.assertIn("does not exist", self.assert_refused(5, "--node", "memory/projects/no-such-node"))

    def test_node_outside_the_memory_checkout_is_refused(self):
        (self.brain.root / "systems" / "intake").mkdir(parents=True)
        for outside in ("systems/intake", "memory/../systems/intake"):
            with self.subTest(outside):
                self.assertIn("inside the memory checkout", self.assert_refused(4, "--node", outside))

    def test_running_outside_a_brain_is_a_plain_error(self):
        self.assertIn("CONTRACT.md", self.assert_refused(6, cwd=self.brain.inbox))


class NodeReferenceTests(IngestTestCase):
    def test_every_form_of_the_node_path_gives_the_same_repository_root_reference(self):
        forms = ["memory/projects/orchard-club", "./memory/projects/orchard-club/", "/memory/projects/orchard-club",
                 "memory\\projects\\orchard-club", str(self.brain.node)]
        for number, form in enumerate(forms):
            with self.subTest(form):
                result = self.brain.ingest_ok(self.brain.sample(f"note-{number}.txt", f"Note {number}\n"),
                                              "--node", form)
                record = self.brain.file(result["canonical_markdown"]).read_text(encoding="utf-8")
                self.assertIn("project_refs:\n  - /memory/projects/orchard-club\n", record)


class ReingestTests(IngestTestCase):
    def test_reingesting_keeps_a_record_converted_since(self):
        path = self.brain.sample("ledger.xlsx", b"PK\x03\x04 fictional workbook bytes")
        first = self.brain.ingest_ok(path)
        record = self.brain.file(first["canonical_markdown"])
        converted = re.sub(r"conversion_status: \S+", "conversion_status: complete",
                           record.read_text(encoding="utf-8")) + "\nConverted by a reviewer.\n"
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
