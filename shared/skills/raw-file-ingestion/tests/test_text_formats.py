"""How text formats appear in the source record: Markdown, plain text, CSV and TSV, JSON and code.

    python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v
"""
from __future__ import annotations

import unittest

from fictional_brain import IngestTestCase, extracted, headings_outside_fences

RECORD_HEADINGS = ["## Source", "## Conversion notes", "## Extracted content"]


class PlainTextTests(IngestTestCase):
    def test_text_is_shown_verbatim_and_adds_no_structure_to_the_record(self):
        text = ("Orchard club minutes\n\n  * indented, not a list\n# a hash, not a heading\n"
                "Budget: $1,250.00 <approved>\n")
        result, record = self.brain.converted("minutes.txt", text)
        self.assertEqual(result["conversion_status"], "complete")
        self.assertEqual(extracted(record), "```text\n" + text + "```\n")
        self.assertEqual(headings_outside_fences(record), ["# Minutes"] + RECORD_HEADINGS)

    def test_backticks_in_the_text_cannot_close_its_block(self):
        text = "Before\n```\n# still inside\n````\nAfter\n"
        _, record = self.brain.converted("snippet.log", text)
        self.assertTrue(extracted(record).startswith("`````text\n" + text + "`````"))
        self.assertEqual(headings_outside_fences(record), ["# Snippet"] + RECORD_HEADINGS)

    def test_code_and_data_files_are_fenced_with_their_language(self):
        for name, language in [("rota.yaml", "yaml"), ("page.html", "html"), ("tally.py", "python")]:
            with self.subTest(name):
                _, record = self.brain.converted(name, f"# first line\n{name}\n")
                self.assertTrue(extracted(record).startswith(f"```{language}\n# first line\n"))

    def test_an_empty_file_says_so(self):
        result, record = self.brain.converted("blank.txt", "\n")
        self.assertEqual(result["conversion_status"], "complete")
        self.assertEqual(extracted(record).strip(), "_The file is empty._")


class DelimitedTests(IngestTestCase):
    def test_csv_becomes_a_table_with_quoted_commas_and_pipes_kept_in_their_cells(self):
        csv_text = ('plot,holder,notes\r\nA-01,Orla Fernwick,"Beans, leeks"\r\n'
                    'A-02,Bram Tollish,"Says ""hi"" | waves"\r\nA-03,Ines Quarrow\r\n')
        result, record = self.brain.converted("plots.csv", csv_text)
        self.assertEqual(result["conversion_status"], "complete")
        self.assertEqual(extracted(record).strip(), "\n".join([
            "| plot | holder | notes |",
            "|---|---|---|",
            "| A-01 | Orla Fernwick | Beans, leeks |",
            '| A-02 | Bram Tollish | Says "hi" \\| waves |',
            "| A-03 | Ines Quarrow |  |",
        ]))
        self.assertIn("3 data rows", record)

    def test_semicolon_csv_and_tsv_are_split_on_their_own_delimiter(self):
        for name, text in [("rates.csv", "plot;rate\nA-01;12,50\nA-02;9,75\n"),
                           ("rates.tsv", "plot\trate\nA-01\t12,50\nA-02\t9,75\n")]:
            with self.subTest(name):
                _, record = self.brain.converted(name, text)
                self.assertIn("| A-01 | 12,50 |", extracted(record))

    def test_a_cell_with_a_line_break_stays_in_its_row(self):
        _, record = self.brain.converted("notes.csv", 'plot,notes\nA-01,"first line\nsecond line"\n')
        self.assertIn("| A-01 | first line<br>second line |", extracted(record))

    def test_csv_that_will_not_parse_is_kept_as_text(self):
        text = 'plot,notes\nA-01,"unclosed quote\n'
        result, record = self.brain.converted("broken.csv", text)
        self.assertEqual(result["conversion_status"], "complete")
        self.assertEqual(extracted(record), "```text\n" + text + "```\n")
        self.assertIn("Not read as a table", record)


class JsonTests(IngestTestCase):
    def test_json_is_verbatim_so_numbers_keep_their_written_form(self):
        text = '{"plot": "A-01", "area_m2": 12.50, "rate": 1e2}'
        _, record = self.brain.converted("plot.json", text)
        self.assertEqual(extracted(record), "```json\n" + text + "\n```\n")
        self.assertIn("Valid JSON", record)

    def test_invalid_json_is_kept_and_named(self):
        _, record = self.brain.converted("broken.json", '{"plot": "A-01",}')
        self.assertIn('```json\n{"plot": "A-01",}\n```', record)
        self.assertIn("Not valid JSON", record)


class MarkdownTests(IngestTestCase):
    def test_markdown_is_kept_as_written_with_its_front_matter_in_a_yaml_block(self):
        body = "# Orchard plan\n\n- Plant pears\n\n| Bed | Crop |\n|---|---|\n| North | Beans |\n"
        _, record = self.brain.converted("plan.md", "---\ntitle: Orchard plan\nauthor: Orla Fernwick\n---\n\n" + body)
        self.assertEqual(extracted(record), "Front matter of the raw file:\n\n"
                                            "```yaml\ntitle: Orchard plan\nauthor: Orla Fernwick\n```\n\n" + body)
        # The raw file's front matter no longer reads as a heading: only its own heading joins the record's.
        self.assertEqual(headings_outside_fences(record), ["# Plan"] + RECORD_HEADINGS + ["# Orchard plan"])

    def test_markdown_without_front_matter_is_unchanged(self):
        body = "Orchard plan\n\n## Pears\n"
        _, record = self.brain.converted("plan.markdown", body)
        self.assertEqual(extracted(record), body)


if __name__ == "__main__":
    unittest.main()
