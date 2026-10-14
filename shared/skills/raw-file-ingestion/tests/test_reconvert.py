"""Tests for reconvert.py: a record converted again in place, or beside it when hand-edited.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

The fictional brain they run in is fictional_brain.py.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from fictional_brain import IngestTestCase, extracted

RECONVERT = Path(__file__).resolve().parents[1] / "scripts" / "reconvert.py"
OLD = "2026-03-02T08:15:42+00:00"
MASTER = "/memory/sources/source-0a1b2c3d4e5f-orchard-master.md"
REFS = ["/memory/projects/orchard-club", "/memory/projects/hive-survey"]


def field(record: str, key: str) -> str:
    return re.search(rf"^{key}:\s*(.*)$", record, re.M).group(1)


def keys(record: str) -> list[str]:
    """The record's top-level front-matter keys, in order."""
    head = record.split("\n---\n", 1)[0]
    return re.findall(r"^([A-Za-z_][\w-]*):", head, re.M)


class ReconvertTests(IngestTestCase):
    def reconvert(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RECONVERT), *args], cwd=self.brain.root,
                              capture_output=True, text=True, encoding="utf-8")

    def stale_record(self, name: str, content: str, *, updated: str | None = None,
                     inline_refs: bool = False, canonical: str | None = None) -> tuple[dict, Path]:
        """Ingest a sample, then make its record look like an old converter's output.

        It was made at OLD by a converter that could not read the file: pending_conversion, with that
        converter's note. It gains fields ingest_raw does not write (owner, tags, optionally
        canonical_source_md) and two project references, in the block form or the inline form.
        """
        result = self.brain.ingest_ok(self.brain.sample(name, content))
        path = self.brain.file(result["canonical_markdown"])
        text = path.read_text(encoding="utf-8")
        text = text.split("## Conversion notes", 1)[0] + (
            "## Conversion notes\n\nNo converter for this format yet.\n\n"
            "## Extracted content\n\nOld pasted text.\n")
        text = re.sub(r"^(created|updated): .*$", rf"\1: {OLD}", text, count=2, flags=re.M)
        text = re.sub(r"conversion_status: \S+", "conversion_status: pending_conversion", text, count=1)
        if canonical:
            text = text.replace("conversion_skill:", f'canonical_source_md: "{canonical}"\nconversion_skill:', 1)
        refs = (f"project_refs: ['{REFS[0]}', '{REFS[1]}']" if inline_refs
                else "project_refs:\n" + "\n".join(f"  - {ref}" for ref in REFS))
        text = text.replace("project_refs:\n  []", refs, 1)
        text = text.replace("status: active\n", "status: active\nowner: 'Orla Fernwick'\n"
                            "tags:\n  - orchard\n  - fictional\n", 1)
        if updated:
            text = re.sub(r"^updated: .*$", f"updated: {updated}", text, count=1, flags=re.M)
            text = text.replace("Old pasted text.", "Old pasted text, corrected by hand.")
        path.write_text(text, encoding="utf-8", newline="\n")
        return result, path

    def assert_fields_carried(self, before: str, after: str, extra: list[str]) -> None:
        self.assertEqual(keys(after), keys(before) + extra)
        for key in ("id", "created", "title", "raw_source", "raw_sha256", "owner"):
            self.assertEqual(field(after, key), field(before, key), key)
        self.assertIn("tags:\n  - orchard\n  - fictional\n", after)
        for ref in REFS:
            self.assertIn(ref, after)

    def test_a_record_never_edited_is_rewritten_in_place_keeping_every_field(self):
        result, path = self.stale_record("orchard-notes.txt", "Quince row pruned by Tamsin Oakhollow\n",
                                         canonical=MASTER)
        before = path.read_text(encoding="utf-8")
        self.assertEqual(field(before, "conversion_status"), "pending_conversion")
        done = self.reconvert(result["source_id"])
        self.assertEqual(done.returncode, 0, done.stderr)
        output = json.loads(done.stdout)
        self.assertEqual(output["written"], result["canonical_markdown"])
        self.assertFalse(output["hand_edited"])
        after = path.read_text(encoding="utf-8")
        self.assert_fields_carried(before, after, [])
        self.assertIn("project_refs:\n" + "\n".join(f"  - {ref}" for ref in REFS), after)
        self.assertIn("Quince row pruned by Tamsin Oakhollow", extracted(after))
        self.assertNotIn("Old pasted text.", after)
        self.assertEqual(field(after, "conversion_status"), "complete")
        self.assertEqual(field(after, "created"), OLD)
        self.assertNotEqual(field(after, "updated"), field(after, "created"))
        notes = after.split("## Conversion notes\n", 1)[1].split("## Extracted content", 1)[0]
        self.assertNotIn("No converter for this format yet.", notes)
        self.assertTrue(notes.strip())
        self.assertIn(f'canonical_source_md: "{MASTER}"', after)
        self.assertFalse(list(path.parent.glob("*.reconverted.md")))
        self.assertIn(f"Re-converted `{result['source_id']}` in place", self.brain.log.read_text(encoding="utf-8"))

    def test_a_hand_edited_record_stays_byte_identical_and_the_derivative_goes_beside_it(self):
        result, path = self.stale_record("plots.txt", "Plot B-07 held by Ferren Ashgrove\n",
                                         updated="2026-02-11T14:23:51+00:00", inline_refs=True,
                                         canonical="/memory/sources/source-ffffffffffff-stale.md")
        before = path.read_bytes()
        done = self.reconvert(result["source_id"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(path.read_bytes(), before)
        beside = path.with_name(path.stem + ".reconverted.md")
        self.assertEqual(json.loads(done.stdout)["written"], "/" + beside.relative_to(self.brain.root).as_posix())
        derivative = beside.read_text(encoding="utf-8")
        self.assert_fields_carried(before.decode("utf-8"), derivative, [])   # replaced where it stood
        self.assertNotIn("source-ffffffffffff-stale", derivative)
        self.assertIn(f'canonical_source_md: "{result["canonical_markdown"]}"', derivative)
        self.assertIn("Plot B-07 held by Ferren Ashgrove", extracted(derivative))
        self.assertIn("# Plots\n", derivative)
        self.assertIn("hand-edited and was kept", self.brain.log.read_text(encoding="utf-8"))

        # Fictional test data only: the skill itself never changes a raw file.
        self.brain.file(result["raw_file"]).write_text("Plot C-12 held by Juniper Vale\n", encoding="utf-8")
        again = self.reconvert(result["source_id"])
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(path.read_bytes(), before)
        second = beside.read_text(encoding="utf-8")
        self.assertIn("Plot C-12 held by Juniper Vale", extracted(second))
        self.assertNotIn("Ferren Ashgrove", extracted(second))
        self.assertEqual(second.count("canonical_source_md:"), 1)

    def test_list_names_pending_records_in_id_order_and_not_a_complete_one(self):
        pending = [self.brain.ingest_ok(self.brain.sample(name, data))
                   for name, data in [("hive-map.qzx", b"\x01\x02fictional"), ("gate.qzx", b"\x03fictional")]]
        complete = self.brain.ingest_ok(self.brain.sample("rota.txt", "Wren Halloway: Tuesday\n"))
        done = self.reconvert("--list")
        self.assertEqual(done.returncode, 0, done.stderr)
        expected = "\n".join(f"{r['source_id']}\tpending_conversion\t{r['raw_file']}"
                             for r in sorted(pending, key=lambda r: r["source_id"])) + "\n"
        self.assertEqual(done.stdout, expected)
        self.assertNotIn(complete["source_id"], done.stdout)

    def test_an_unknown_id_exits_2_and_writes_nothing(self):
        log_before = self.brain.log.read_bytes()
        done = self.reconvert("source-000000000000")
        self.assertEqual(done.returncode, 2)
        self.assertIn("no source record", done.stderr)
        self.assertEqual(self.brain.log.read_bytes(), log_before)

    def test_a_path_a_pattern_or_a_prefix_exits_2_and_the_exact_stem_works(self):
        result = self.brain.ingest_ok(self.brain.sample("orchard-plan.txt", "Fictional plan\n"))
        stem = Path(result["canonical_markdown"]).stem
        log_before = self.brain.log.read_bytes()
        for probe in ["/absolute", "..\\up", "source-*", "source-?", "source-[ab]",
                      result["source_id"][:-3], stem[:-3]]:
            with self.subTest(probe):
                done = self.reconvert(probe)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(self.brain.log.read_bytes(), log_before)
        self.assertEqual(self.reconvert(stem).returncode, 0)

    def test_a_record_that_is_not_utf8_does_not_stop_list_or_lookup(self):
        self.brain.ingest_ok(self.brain.sample("rota.txt", "Wren Halloway: Tuesday\n"))
        broken = self.brain.memory / "sources" / "source-badbadbadbad-broken.md"
        broken.write_bytes(b"---\nid: source-badbadbadbad\nconversion_status: complete\n---\n\xff\xfe\x81\n")
        listed = self.reconvert("--list")
        self.assertEqual((listed.returncode, listed.stdout), (0, ""), listed.stderr)
        done = self.reconvert("source-000000000000")
        self.assertEqual(done.returncode, 2)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_missing_raw_file_exits_3(self):
        result = self.brain.ingest_ok(self.brain.sample("gone.txt", "Fictional note\n"))
        self.brain.file(result["raw_file"]).unlink()
        self.assertEqual(self.reconvert(result["source_id"]).returncode, 3)


if __name__ == "__main__":
    unittest.main()
