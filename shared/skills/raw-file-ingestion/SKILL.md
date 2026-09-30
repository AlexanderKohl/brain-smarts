---
id: skill-raw-file-ingestion
title: Raw File Ingestion
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.1.3
script_paths:
  - /shared/skills/raw-file-ingestion/scripts/ingest_raw.py
  - /shared/skills/raw-file-ingestion/scripts/convert.py
  - /shared/skills/raw-file-ingestion/tests/test_ingest_raw.py
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-30T22:47:07+00:00
---

# Raw File Ingestion

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
- optional tags

## Data sources

- The supplied local file, read once and copied unchanged.
- `/memory/raw/` for an existing file with the same SHA-256, reused instead of duplicated.
- `/shared/templates/source-document.template.md` for the source record.

## Permissions

- Read the supplied file; write only new files under `/memory/raw/`, `/memory/sources/` and the target node's `sources/`, and append to the target node's `LOG.md` and `/memory/systems/raw-file-management/LOG.md`.
- The script finds the brain root by walking up to `CONTRACT.md` and stops with an error when `<brain root>/memory/` is missing.
- A target node must be an existing folder inside `/memory/`: a source reference names an owner's file, so it never goes into the mechanics or the skill library (CONTRACT §3.4).
- Never modify, overwrite, normalise or delete an existing raw file.
- No credentials and no external systems.

## Script

```bash
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py FILE --node memory/projects/example
```

The script supports direct text extraction for common text formats. Other formats receive a source record marked `pending_conversion` until a suitable converter is run. `scripts/convert.py` does the conversion; `ingest_raw.py` stores, records and logs.

Text is read as UTF-8, or in the encoding a byte-order mark names (UTF-8, UTF-16 or UTF-32, as Windows editors save it); the mark is left out. Text that is not UTF-8 is kept with replacement characters and marked `partial`; a file with NUL bytes and no mark (binary, or UTF-16 without a mark) is marked `failed` rather than written into the record. Records, references and manifests are written with LF line ends on every platform; an appended log entry keeps the log's own line ends.

```bash
python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v
```

The tests build a fictional brain in a temporary folder and ingest fictional files.

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
- create a task when manual or specialised conversion is required

## Repository updates

- update source metadata
- append to the raw-file management log at `/memory/systems/raw-file-management/LOG.md`
- update the target node log when a target node is supplied
