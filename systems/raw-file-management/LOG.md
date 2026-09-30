---
id: raw-file-management-log
title: Raw File Management Activity Log
type: log
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-30T23:02:25+00:00
---

# Activity Log

## 2026-08-04T15:16:31+10:00

- Created raw file management system.
- Defined immutable raw storage.
- Defined canonical Markdown source records.
- Added basic ingestion script.

## 2026-09-23T12:00:00+10:00

- This node keeps the mechanism. Per-file ingestion entries name the owner's files, so the
  ingestion skill writes them to `/memory/systems/raw-file-management/LOG.md`.

## 2026-09-30T23:00:19+00:00

- Tested `/shared/skills/raw-file-ingestion/` (owner task TASK-2026-0004) on fictional files made for the
  test (SMART-RULE-0008), one per format plus an image-only PDF, in a throwaway brain; no owner file
  was read. Samples: Markdown with front matter and a table; text with CRLF line ends, a `#` line and
  `<angle brackets>`; CSV with quoted commas, quotes and a pipe; minified JSON; a Word file with
  headings, lists, a table and a page break (python-docx); a three-sheet workbook with dates, a sparse
  cell and formulas saved without values (openpyxl); a two-page PDF with text and an image-only PDF
  (fpdf2). LibreOffice would not start in the test container, so no sample came from Word or Excel.
- Every raw file was kept byte for byte, with its SHA-256, at every version below.
- As found (0.1.0), per format – what the derivative captured, and the failure:

  | Format | Derivative | Failure |
  |---|---|---|
  | CSV | the text pasted in as Markdown | one run-together paragraph, no table |
  | DOCX | nothing | `pending_conversion` |
  | JSON | the text pasted in as Markdown | not fenced; readable only by luck |
  | Markdown | as written | the front matter read as a heading inside the record |
  | PDF | nothing | `pending_conversion` |
  | Text | the text pasted in as Markdown | a `#` line became a heading of the record, `<approved>` vanished as HTML, line breaks ran together |
  | XLSX | nothing | `pending_conversion` |

  Across formats: an identical file ingested again rewrote its record, losing a later conversion, and
  under another title made a second record with the same id; a missing `--node` left a raw file and
  record behind unlogged; `./`, Windows and absolute `--node` paths gave broken `project_refs`; a
  UTF-8 byte-order mark stayed in the record as U+FEFF and a UTF-16 file put NUL bytes into it.
- Fixed, each in its own commit with tests that fail before it: 0.1.1 re-ingesting keeps the record;
  0.1.2 a refused run writes nothing and every node path gives one reference; 0.1.3 byte-order marks,
  NUL bytes and log line ends; 0.2.0 text, CSV, JSON and Markdown as readable Markdown; 0.3.0 Word and
  Excel; 0.4.0 PDF; 0.4.1 SKILL.md.
- At 0.4.1, per format – what the derivative captures, and what it does not:

  | Format | Status | Derivative | Left out or failing |
  |---|---|---|---|
  | CSV | `complete` | a table, header and 3 rows, quoted commas, quotes and the pipe in their cells | nothing |
  | DOCX | `complete` | headings, paragraphs, the bulleted list, the table and a page-break marker, in order | bold and other formatting, by design |
  | JSON | `complete` | verbatim in a `json` block, checked valid | nothing |
  | Markdown | `complete` | as written, front matter in a `yaml` block | nothing |
  | PDF, text | `complete` | two `### Page` sections, the same text through `pdftotext` 24.02.0 and `pypdf` 6.19.0 | images, by design |
  | PDF, image only | `pending_conversion` | the page, marked as having no text layer | needs OCR, not built |
  | Text | `complete` | verbatim in a `text` block | nothing |
  | XLSX | `partial` | three sheets as tables with cell references, dates in ISO form, the empty sheet named | the two formulas saved without values show their formulas, as the record says |

- Re-ingesting all eight under another title reused every raw file and record. The repository
  preflight over the resulting fictional memory reported no error in anything the skill wrote.

## 2026-09-30T23:02:25+00:00

- 0.4.2, from reviewing 0.4.1 (TASK-2026-0004): an Excel string escape for half a surrogate pair
  stopped the run while the record was being written, leaving the raw file with a truncated record
  and no log line. Now that escape stays as written, any unexpected converter error becomes a
  `failed` record naming it, and records are written whole or not at all. The eight fictional
  samples give the same results as at 0.4.1.

