---
id: raw-file-management-knowledge
title: Raw File Management Knowledge
type: knowledge
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-30T23:00:19+00:00
---

# Knowledge

- Raw files are source evidence.
- Markdown derivatives are accessibility layers.
- Hashes identify exact file content.
- Conversion quality must be explicit.
- Project annotations must remain traceable to canonical sources.
- Word (`.docx`) and Excel (`.xlsx`) files are ZIP packages of XML parts, readable with the Python standard library; a password-protected one is a compound file instead, with the same signature as the older binary `.doc` and `.xls`.
- An Excel file stores each formula's last calculated value beside the formula. A file written by a program rather than a spreadsheet application (openpyxl, for one) may store none, so the value can only be read after a spreadsheet application recalculates and saves it.
- The Python standard library cannot read the text of a PDF. A PDF page with no text layer is an image, as a scanned page is, and its text needs OCR.
