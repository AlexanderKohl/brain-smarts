"""How Word (.docx) and Excel (.xlsx) files appear in the source record.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v

The files are fictional, written part by part by office_samples.py.
"""
from __future__ import annotations

import unittest

from fictional_brain import IngestTestCase, extracted
from office_samples import cell, docx, para, run, sheet, xlsx, XML, W_NS, R_NS

PAGE_BREAK = para('<w:r><w:br w:type="page"/></w:r>')
IMAGE = ('<w:r><w:drawing><wp:inline><wp:docPr id="1" name="Picture 1" descr="Pear tree in blossom"/>'
         '<a:graphic><a:graphicData><a:blip/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


class WordTests(IngestTestCase):
    def test_a_document_keeps_its_structure_in_order(self):
        table = ('<w:tbl>'
                 f'<w:tr><w:tc>{para(run("Plot"))}</w:tc><w:tc>{para(run("Crop"))}</w:tc><w:tc>{para(run("Rows"))}</w:tc></w:tr>'
                 f'<w:tr><w:tc>{para(run("A-01"))}</w:tc><w:tc>{para(run("Beans | runner"))}{para(run("second line"))}</w:tc>'
                 f'<w:tc>{para(run("4"))}</w:tc></w:tr>'
                 f'<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>{para(run("Total"))}</w:tc><w:tc>{para(run("4"))}</w:tc></w:tr>'
                 '</w:tbl>')
        text_box = ('<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><w:txbxContent>'
                    f'{para(run("Boxed note"))}</w:txbxContent></w:drawing></mc:Choice><mc:Fallback><w:pict>'
                    f'<w:txbxContent>{para(run("Boxed note"))}</w:txbxContent></w:pict></mc:Fallback>'
                    '</mc:AlternateContent></w:r>')
        body = (para(run("Orchard Club Report"), "Title")
                + para(run("Prepared for the fictional Orchard Club."))
                + para(run("# a hash, not a heading"))
                + para(run("Plantings"), "Heading1")
                + para(run("Pears"), "ListBullet")
                + para(run("Early pears"), numbering=(1, 1))
                + para(run("Plums"), "ListBullet")
                + para(run("Prune"), numbering=(2, 0))
                + para(run("Water"), numbering=(2, 0))
                + para(run("Budget"), "MyHeading")
                + table
                + PAGE_BREAK
                + para(run("See ") + f'<w:hyperlink r:id="rIdLink">{run("the club site")}</w:hyperlink>' + run("."))
                + para(run("Rainfall was high") + '<w:r><w:footnoteReference w:id="1"/></w:r>' + run("."))
                + para(f'<w:ins w:id="7" w:author="Orla Fernwick">{run("Inserted words")}</w:ins>'
                       '<w:del w:id="8" w:author="Orla Fernwick"><w:r><w:delText>Deleted words</w:delText></w:r></w:del>')
                + para(IMAGE)
                + para(text_box))
        footnote = f'<w:footnote w:id="1">{para(run("Measured at the fictional north gauge."))}</w:footnote>'
        result, record = self.brain.converted("report.docx", docx(
            body, footnotes=footnote, links={"rIdLink": "https://orchard.example.com/"}))
        self.assertEqual(result["conversion_status"], "complete")
        self.assertEqual(extracted(record).strip(), "\n".join([
            "# Orchard Club Report", "",
            "Prepared for the fictional Orchard Club.", "",
            "\\# a hash, not a heading", "",
            "# Plantings", "",
            "- Pears", "  - Early pears", "- Plums", "1. Prune", "1. Water", "",
            "## Budget", "",
            "| Plot | Crop | Rows |", "|---|---|---|",
            "| A-01 | Beans \\| runner<br>second line | 4 |",
            "| Total |  | 4 |", "",
            "_[Page break]_", "",
            "See [the club site](https://orchard.example.com/).", "",
            "Rainfall was high[^1].", "",
            "Inserted words", "",
            "_[image: Pear tree in blossom]_", "",
            "Boxed note", "",
            "[^1]: Measured at the fictional north gauge.",
        ]))
        for note in ("explicit page breaks", "1 image(s)", "tracked changes", "Bold, italic"):
            self.assertIn(note, record)

    def test_paragraphs_that_look_like_markdown_are_escaped_so_they_read_as_written(self):
        body = "".join(para(run(text)) for text in ("# hash", "- dash", "> quote", "2026. A good year", "3) third"))
        _, record = self.brain.converted("escapes.docx", docx(body))
        self.assertEqual(extracted(record).strip(), "\n\n".join(
            ["\\# hash", "\\- dash", "\\> quote", "2026\\. A good year", "3\\) third"]))

    def test_a_footnote_with_a_tracked_change_is_read(self):
        footnote = f'<w:footnote w:id="1"><w:p><w:ins w:id="3" w:author="Orla Fernwick">{run("Added note")}</w:ins></w:p></w:footnote>'
        result, record = self.brain.converted("noted.docx", docx(
            para(run("Claim") + '<w:r><w:footnoteReference w:id="1"/></w:r>'), footnotes=footnote))
        self.assertEqual(result["conversion_status"], "complete")
        self.assertIn("Claim[^1]\n\n[^1]: Added note", extracted(record))

    def test_parts_left_out_are_named(self):
        _, record = self.brain.converted("minutes.docx", docx(para(run("Minutes")), extra={
            "word/header1.xml": XML + f"<w:hdr {W_NS}/>", "word/comments.xml": XML + f"<w:comments {W_NS}/>"}))
        self.assertIn("Headers and footers are not extracted.", record)
        self.assertIn("Comments are not extracted.", record)

    def test_a_document_without_text_waits_for_ocr(self):
        result, record = self.brain.converted("scan.docx", docx(para(IMAGE)))
        self.assertEqual(result["conversion_status"], "pending_conversion")
        self.assertIn("needs OCR", record)


class DamagedPackageTests(IngestTestCase):
    def test_a_file_that_is_not_a_package_fails_and_is_preserved(self):
        result, record = self.brain.converted("broken.docx", b"PK\x03\x04 not a whole archive")
        self.assertEqual(result["conversion_status"], "failed")
        self.assertIn("Not read as an Office file", record)
        self.assertEqual(self.brain.file(result["raw_file"]).read_bytes(), b"PK\x03\x04 not a whole archive")

    def test_a_password_protected_or_legacy_file_waits_for_a_readable_copy(self):
        compound = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(504)
        for name in ("locked.docx", "locked.xlsx"):
            with self.subTest(name):
                result, record = self.brain.converted(name, compound + name.encode())
                self.assertEqual(result["conversion_status"], "pending_conversion")
                self.assertIn("protected with a password", record)

    def test_a_part_declaring_a_doctype_is_refused(self):
        hostile = (XML + '<!DOCTYPE w:document [<!ENTITY x "xxxxxxxx">]>'
                   f'<w:document {W_NS} {R_NS}><w:body>{para(run("&x;"))}</w:body></w:document>')
        result, record = self.brain.converted("entity.docx", docx("", extra={"word/document.xml": hostile}))
        self.assertEqual(result["conversion_status"], "failed")
        self.assertIn("DOCTYPE", record)
        self.assertNotIn("xxxxxxxx", extracted(record))


STRINGS = ["plot", "holder", "area", "joined", "A-01", "Orla Fernwick", "A-02", "Total",
           "Line one_x000D_\nLine two | piped"]


class ExcelTests(IngestTestCase):
    def workbook(self, **options) -> bytes:
        plots = sheet({
            1: [cell("A1", "0", "s"), cell("B1", "1", "s"), cell("C1", "2", "s"), cell("D1", "3", "s"),
                cell("E1", "fee", "inlineStr")],
            2: [cell("A2", "4", "s"), cell("B2", "5", "s"), cell("C2", "12.5"), cell("D2", "45658", style="1"),
                cell("E2", "75")],
            3: [cell("A3", "6", "s"), cell("C3", "9"), cell("D3", "45689.5", style="2"), cell("E3", "1", "b")],
            5: [cell("A5", "7", "s"), cell("C5", "21.5", formula="SUM(C2:C3)"),
                cell("E5", formula="SUM(E2:E3)", stored=False), cell("F5", "#DIV/0!", "e")],
            6: [cell("C6", "3.5", style="3"), cell("G6", "", "str", formula='IF(A6="","",A6)')],
        }, merged=["A5:B5"])
        notes = sheet({2: [cell("C2", "8", "s")]})
        return xlsx([("Plots", "visible", plots), ("Notes", "hidden", notes), ("Empty", "visible", sheet({}))],
                    STRINGS, **options)

    def test_every_sheet_is_a_table_that_keeps_cell_references(self):
        result, record = self.brain.converted("ledger.xlsx", self.workbook())
        self.assertEqual(extracted(record).strip(), "\n".join([
            "### Sheet 1: Plots", "",
            "| Row | A | B | C | D | E | F |", "|---|---|---|---|---|---|---|",
            "| 1 | plot | holder | area | joined | fee |  |",
            "| 2 | A-01 | Orla Fernwick | 12.5 | 2025-01-01 | 75 |  |",
            "| 3 | A-02 |  | 9 | 2025-02-01T12:00:00 | TRUE |  |",
            "| 5 | Total |  | 21.5 |  | =SUM(E2:E3) | #DIV/0! |",
            "| 6 |  |  | 3.5 |  |  |  |", "",
            "### Sheet 2: Notes (hidden)", "",
            "| Row | C |", "|---|---|",
            "| 2 | Line one<br>Line two \\| piped |", "",
            "### Sheet 3: Empty", "",
            "_Empty sheet._",
        ]))

    def test_a_formula_without_a_saved_value_makes_the_record_partial_and_says_why(self):
        result, record = self.brain.converted("ledger.xlsx", self.workbook())
        self.assertEqual(result["conversion_status"], "partial")
        self.assertIn("1 formula cell(s) have no calculated value saved", record)
        self.assertIn("2 formula cell(s) show the value last calculated", record)
        self.assertIn("1 merged range(s)", record)

    def test_an_escaped_half_surrogate_is_kept_as_written_and_the_record_is_made(self):
        book = xlsx([("Codes", "visible", sheet({1: [cell("A1", "0", "s")]}))], ["tab_x0009_here, half _xD800_ pair"])
        result, record = self.brain.converted("codes.xlsx", book)
        self.assertEqual(result["conversion_status"], "complete")
        self.assertIn("| 1 | tab\there, half _xD800_ pair |", record)

    def test_dates_in_a_1904_workbook(self):
        book = xlsx([("Dates", "visible", sheet({1: [cell("A1", "44196", style="1")]}))], [], date1904=True)
        result, record = self.brain.converted("mac.xlsx", book)
        self.assertEqual(result["conversion_status"], "complete")
        self.assertIn("| 1 | 2025-01-01 |", record)


if __name__ == "__main__":
    unittest.main()
