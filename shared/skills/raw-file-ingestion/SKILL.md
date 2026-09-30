---
id: skill-raw-file-ingestion
title: Raw File Ingestion
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.4.1
script_paths:
  - /shared/skills/raw-file-ingestion/scripts/ingest_raw.py
  - /shared/skills/raw-file-ingestion/scripts/convert.py
  - /shared/skills/raw-file-ingestion/scripts/convert_office.py
  - /shared/skills/raw-file-ingestion/scripts/convert_pdf.py
  - /shared/skills/raw-file-ingestion/scripts/markdown_blocks.py
  - /shared/skills/raw-file-ingestion/tests/test_ingest_raw.py
  - /shared/skills/raw-file-ingestion/tests/test_text_formats.py
  - /shared/skills/raw-file-ingestion/tests/test_office_formats.py
  - /shared/skills/raw-file-ingestion/tests/test_pdf.py
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-30T22:59:39+00:00
---

# Raw File Ingestion

Read `/CONTRACT.md` first.

## Purpose

Preserve an uploaded or imported file unchanged, calculate its identity, create an accessible Markdown source representation and link it to relevant nodes.

## Allowed operations

- read a supplied local file
- copy it into `/memory/raw/`
- calculate SHA-256
- create or reuse a canonical Markdown source under `/memory/sources/`
- create a project-local source reference
- append an ingestion event to the relevant log

The skill must not modify or delete an existing raw file.

An identical file ingested again (same SHA-256) reuses the raw file and keeps the source record it
already has, whatever title it arrives with: nothing in it is rewritten, so a manual or specialised
conversion made there since is never lost. Only a node reference that does not exist yet is added.

## Inputs

- source file path
- optional target node path: a folder inside `/memory/`, written as `memory/projects/example`, `/memory/projects/example` or an absolute path inside the brain
- optional title
- optional tags (not yet taken by the script)

## Data sources

- The supplied local file, read once and copied unchanged.
- For a PDF, the first text extractor this computer has: poppler's `pdftotext` on PATH, then the `pypdf` Python package. Neither ships with Python; with neither, a PDF's record is `pending_conversion` with a note saying what to install, and the raw file is kept as always. Which extractor read a file, and its version, is in the record's notes.
- `/memory/raw/` for an existing file with the same SHA-256, reused instead of duplicated.
- `/shared/templates/source-document.template.md` for the source record.

## Permissions

- Read the supplied file; write only new files under `/memory/raw/`, `/memory/sources/` and the target node's `sources/`, and append to the target node's `LOG.md` and `/memory/systems/raw-file-management/LOG.md`.
- The script finds the brain root by walking up to `CONTRACT.md` and stops with an error when `<brain root>/memory/` is missing.
- A target node must be an existing folder inside `/memory/`: a source reference names an owner's file, so it never goes into the mechanics or the skill library (CONTRACT §3.4).
- Never modify, overwrite, normalise or delete an existing raw file.
- No credentials and no external systems. For a PDF it may run `pdftotext` as a local child process (no network), limited to 300 seconds.

## Script

```bash
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py FILE --node memory/projects/example
```

`ingest_raw.py` stores, records and logs; `scripts/convert.py` converts, as the Formats section below describes for each format. A format with no converter gets a record marked `pending_conversion`, and the raw file is kept as always. The script prints the source ID, the raw and record paths, the `conversion_status`, and whether the raw file and record were reused.

Text is read as UTF-8, or in the encoding a byte-order mark names (UTF-8, UTF-16 or UTF-32, as Windows editors save it); the mark is left out. Text that is not UTF-8 is kept with replacement characters and marked `partial`; a file with NUL bytes and no mark (binary, or UTF-16 without a mark) is marked `failed` rather than written into the record. Records, references and manifests are written with LF line ends on every platform; an appended log entry keeps the log's own line ends.

```bash
python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v
```

The tests build a fictional brain in a temporary folder and ingest fictional files.

## Formats

How each format appears under `## Extracted content` in the source record. Every record's
`## Conversion notes` says how its file was read and shown, and what was left out.

| Format | Shown as | Left out or changed |
|---|---|---|
| CSV (`.csv`), TSV (`.tsv`) | a table, the first row as its header; the CSV delimiter is detected (comma, semicolon, tab or pipe) | blank lines; a pipe in a cell is escaped and a line break becomes `<br>`; a file that will not parse is shown as text |
| JSON (`.json`) | verbatim in a `json` block, checked for validity | nothing: it is not reformatted, so numbers keep their written form |
| Markdown (`.md`, `.markdown`) | as written | its front matter moves into a `yaml` block, so it does not read as part of the record |
| Excel workbook (`.xlsx`, `.xlsm`) | one table per sheet, in workbook order, under `### Sheet N: name`; the columns are headed by their letters and each row starts with its row number, so every value keeps its cell reference | empty rows and columns; number display formats (a number is shown as stored, a date or time in ISO form); charts, images and cell comments. A formula shows the value saved with the file; one with no saved value (written by a program, not a spreadsheet application) shows its formula and makes the record `partial`. Merged ranges and hidden sheets are named |
| Word document (`.docx`, `.docm`) | headings, paragraphs, bulleted and numbered lists, tables, links and footnotes, in document order; explicit page breaks as `_[Page break]_`, images as `_[image: alt text]_` | bold, italic, fonts and colours; headers, footers and comments (named when present); tracked changes are shown as if accepted. A document with no text at all is `pending_conversion` (it needs OCR) |
| PDF (`.pdf`) | one section per page, `### Page N`, its text in a fenced block that keeps the layout's line breaks and spacing | images, and text drawn as images: a page with no text layer is marked, makes the record `partial`, or `pending_conversion` (needs OCR) when no page has text. Needs an extractor (see Data sources) |
| Plain text, logs, code and data (`.txt`, `.log`, `.css`, `.htm`, `.html`, `.js`, `.py`, `.sql`, `.ts`, `.xml`, `.yaml`, `.yml`) | verbatim in a fenced block with its language | nothing: in a block the text keeps its line breaks and cannot add a heading, list or HTML to the record |
| anything else | nothing yet: `pending_conversion` | – |

Word and Excel files are read with the Python standard library alone: they are ZIP packages of XML.
A package part over 200 MB uncompressed, or one declaring a DOCTYPE (Office never writes one; entity
tricks need one), is refused and the record marked `failed`. A password-protected file, or the older
binary `.doc` and `.xls`, is `pending_conversion` with a note: an unprotected `.docx` or `.xlsx` copy
can be converted.

## Outputs

- immutable raw file
- SHA-256 hash
- canonical Markdown source record
- optional project-local source reference

## Failure behaviour

- check the brain root, the memory checkout and the target node before anything is written, so a refused run leaves no raw copy, record or log line (exit 6: no brain or memory; 4: node outside `/memory/`; 5: node missing)
- do not overwrite conflicting raw files
- report unsupported conversion
- preserve the raw file even when conversion fails
- the script does not create tasks: when `conversion_status` is not `complete`, the calling agent creates one (CONTRACT §11.2 step 8) naming the source record and the note in it that says why – OCR, a missing PDF extractor, an unprotected copy, a formula value to save

## Repository updates

- update source metadata
- append to the raw-file management log at `/memory/systems/raw-file-management/LOG.md`
- update the target node log when a target node is supplied
