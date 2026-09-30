---
id: raw-file-management-state
title: Raw File Management Current State
type: state
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-30T23:00:19+00:00
owner: brain-owner
---

# Current State

## Implemented

- immutable raw storage convention
- SHA-256 identity
- canonical Markdown source convention
- project-local source reference convention
- ingestion script, `/shared/skills/raw-file-ingestion/` 0.4.1, with 43 tests on fictional files
- conversion to Markdown of text, logs, code and data (fenced), Markdown (as written), CSV and TSV (tables), JSON (verbatim), Word `.docx` and Excel `.xlsx` (standard library), and PDF page by page (through `pdftotext` or `pypdf` where installed); each record's notes say what was left out
- an identical file ingested again keeps its raw file and source record; a refused run writes nothing
- ISO 8601 timestamp metadata and log entries
- authenticated Google Drive text snapshots with source provenance and transformation notes
- raw files, source records and the ingestion log live in the owner's memory (`/memory/raw/`, `/memory/sources/`, `/memory/systems/raw-file-management/LOG.md`)

## Pending

- OCR for scanned PDFs and image-only Word files (marked `pending_conversion` today)
- a way to convert again a record made before a converter existed: re-ingesting keeps a record unchanged by design, so records made before 0.2.0 keep their old content
- PowerPoint, images, and the legacy binary `.doc` and `.xls`
- a test run on files saved by Word and Excel themselves, and on Windows (0.4.1 was checked with files made by python-docx, openpyxl and fpdf2, on Linux)
- the skill's tests in the continuous-integration workflow, which today runs only the preflight tests
- automated conversion-quality checks
