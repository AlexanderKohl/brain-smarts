"""How PDF files appear in the source record.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

The converter is tested with stand-in extractors, so every outcome is covered on any computer; the
end-to-end test runs a real fictional PDF through whichever extractor this computer has, and is
skipped when it has none.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
from pathlib import Path

from fictional_brain import IngestTestCase, extracted, headings_outside_fences

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from convert_pdf import ExtractionError, pdf_to_markdown  # noqa: E402

HAS_EXTRACTOR = bool(shutil.which("pdftotext") or importlib.util.find_spec("pypdf"))


def pdf(pages: list[list[str]]) -> bytes:
    """A fictional PDF: one page per list of lines in Helvetica; an empty list is a page with no text."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
               2: ("<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * n} 0 R" for n in range(len(pages)))
                   + f"] /Count {len(pages)} >>").encode(),
               3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    for n, lines in enumerate(pages):
        stream = ("BT /F1 12 Tf 14 TL 72 720 Td " + " ".join(f"({escape(line)}) Tj T*" for line in lines)
                  + " ET").encode("latin-1") if lines else b""
        objects[4 + 2 * n] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
                              f"<< /Font << /F1 3 0 R >> >> /Contents {5 + 2 * n} 0 R >>").encode()
        objects[5 + 2 * n] = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    table_at, size = len(out), max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[n]:010d} 00000 n \n".encode() for n in range(1, size))
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{table_at}\n%%EOF\n".encode()
    return bytes(out)


def extractor(pages: list[str]):
    return lambda path: (pages, "stand-in extractor 1.0")


def failing(message: str, password: bool = False):
    def extract(path):
        raise ExtractionError(message, password=password)
    return extract


def unavailable(path):
    return None


class PdfConverterTests(unittest.TestCase):
    def test_each_page_is_its_own_section_with_its_text_fenced(self):
        status, markdown, notes = pdf_to_markdown(Path("minutes.pdf"), [extractor(
            ["Orchard club minutes\n  Plot   Rows\n  A-01   4\n", "# not a heading\n```\nstill page two\n"])])
        self.assertEqual(status, "complete")
        self.assertEqual(markdown, "### Page 1\n\n```text\nOrchard club minutes\n  Plot   Rows\n  A-01   4\n```\n\n"
                                   "### Page 2\n\n````text\n# not a heading\n```\nstill page two\n````")
        self.assertEqual(headings_outside_fences(markdown), ["### Page 1", "### Page 2"])
        self.assertIn("stand-in extractor 1.0", notes[0])
        self.assertIn("2 page(s)", notes[0])

    def test_pages_without_text_make_the_record_partial_and_are_named(self):
        status, markdown, notes = pdf_to_markdown(Path("mixed.pdf"), [extractor(["Text", " \n", "More", ""])])
        self.assertEqual(status, "partial")
        self.assertIn("### Page 2\n\n_No text on this page._", markdown)
        self.assertIn("Page(s) 2, 4 have no text layer", " ".join(notes))

    def test_a_pdf_with_no_text_at_all_waits_for_ocr(self):
        status, _, notes = pdf_to_markdown(Path("scan.pdf"), [extractor(["", ""])])
        self.assertEqual(status, "pending_conversion")
        self.assertIn("They need OCR", " ".join(notes))

    def test_the_first_available_extractor_is_used(self):
        status, _, notes = pdf_to_markdown(Path("minutes.pdf"), [unavailable, extractor(["Text"])])
        self.assertEqual(status, "complete")
        self.assertIn("stand-in extractor", notes[0])

    def test_without_an_extractor_the_record_says_what_to_install(self):
        status, markdown, notes = pdf_to_markdown(Path("minutes.pdf"), [unavailable, unavailable])
        self.assertEqual((status, markdown), ("pending_conversion", ""))
        self.assertIn("pip install pypdf", notes[0])

    def test_a_password_waits_for_an_unprotected_copy_and_other_errors_fail(self):
        status, _, notes = pdf_to_markdown(Path("locked.pdf"), [failing("pdftotext: Incorrect password", True)])
        self.assertEqual(status, "pending_conversion")
        self.assertIn("protected with a password", notes[0])
        status, _, notes = pdf_to_markdown(Path("broken.pdf"), [failing("pdftotext: Couldn't find trailer")])
        self.assertEqual(status, "failed")
        self.assertIn("Couldn't find trailer", notes[0])


@unittest.skipUnless(HAS_EXTRACTOR, "neither pdftotext nor pypdf is installed")
class PdfIngestTests(IngestTestCase):
    def test_a_pdf_is_read_page_by_page_through_the_installed_extractor(self):
        result, record = self.brain.converted("minutes.pdf", pdf([["Orchard club minutes", "Budget (approved)"], []]))
        self.assertEqual(result["conversion_status"], "partial")
        content = extracted(record)
        page_one, page_two = content.split("### Page 2")
        self.assertIn("Orchard club minutes", page_one)
        self.assertIn("Budget (approved)", page_one)
        self.assertIn("_No text on this page._", page_two)
        self.assertIn("Page(s) 2 have no text layer", record)


if __name__ == "__main__":
    unittest.main()
