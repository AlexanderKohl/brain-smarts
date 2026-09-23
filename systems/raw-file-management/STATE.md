---
id: raw-file-management-state
title: Raw File Management Current State
type: state
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Current State

## Implemented

- immutable raw storage convention
- SHA-256 identity
- canonical Markdown source convention
- project-local source reference convention
- basic ingestion script for text-like files
- ISO 8601 timestamp metadata and log entries
- authenticated Google Drive text snapshots with source provenance and transformation notes
- raw files, source records and the ingestion log live in the owner's memory (`/memory/raw/`, `/memory/sources/`, `/memory/systems/raw-file-management/LOG.md`); candidate layout under `RULE-2026-0046`

## Pending

- PDF extraction
- DOCX extraction
- spreadsheet extraction
- image transcription and metadata
- automated conversion-quality checks
