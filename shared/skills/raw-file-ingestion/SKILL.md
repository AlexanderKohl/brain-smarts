---
id: skill-raw-file-ingestion
title: Raw File Ingestion
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.6.0
script_paths:
  - /shared/skills/raw-file-ingestion/scripts/ingest_raw.py
  - /shared/skills/raw-file-ingestion/scripts/convert.py
  - /shared/skills/raw-file-ingestion/scripts/convert_office.py
  - /shared/skills/raw-file-ingestion/scripts/convert_pdf.py
  - /shared/skills/raw-file-ingestion/scripts/markdown_blocks.py
  - /shared/skills/raw-file-ingestion/scripts/reconvert.py
  - /shared/skills/raw-file-ingestion/scripts/raw_stores.py
  - /shared/skills/raw-file-ingestion/scripts/source_migrate.py
  - /shared/skills/raw-file-ingestion/tests/test_ingest_raw.py
  - /shared/skills/raw-file-ingestion/tests/test_text_formats.py
  - /shared/skills/raw-file-ingestion/tests/test_office_formats.py
  - /shared/skills/raw-file-ingestion/tests/test_pdf.py
  - /shared/skills/raw-file-ingestion/tests/test_reconvert.py
  - /shared/skills/raw-file-ingestion/tests/test_stores.py
  - /shared/skills/raw-file-ingestion/tests/test_source_migrate.py
created: 2026-08-04T03:31:56+10:00
updated: 2026-10-23T08:57:29+10:00
---

# Raw File Ingestion

Read `/CONTRACT.md` first.

## Purpose

Preserve an uploaded or imported file unchanged in the raw store it belongs to, calculate its identity, create an accessible Markdown source representation beside it and link it to relevant nodes.

## Raw stores

Where a new source goes (CONTRACT §11.1, P13), decided by `raw_stores.choose`:

| `--node` names | Raw file in | Record in |
|---|---|---|
| nothing, or a folder in no node | `/memory/raw/` | `/memory/sources/`, with a reference in that folder's `sources/` |
| a memory node, or a folder inside one | `<node>/raw/` | `<node>/sources/` |
| a pointer node | the repository's `brain/raw/` | its `brain/sources/` |
| a pointer node, with `--private` | `<pointer node>/raw/` | `<pointer node>/sources/` |

A node, a pointer, its checkout, its store branch and its `repo_visibility` are the tasks skill's
own definitions (`task_stores`), so a source and a task about one project land in one place. Inside
every raw store the layout is `YYYY/MM/<source-id>/<original-filename>` with its `manifest.json`.

A record names the files of its own store: `/memory/...` paths in memory; repository paths
(`brain/raw/...`) in a repository, where `project_refs` start with `<repository>:brain` and never
name `/memory/` (P15). A file in memory that names a repository file writes
`<repository>:brain/...`, `<repository>` being the remote's name. A manifest written into a
repository leaves out `original_path`, so no machine path enters it.

**Before anything is written into a repository** the script names the repository and says who can
read it (`repo_visibility` public or private; not recorded is treated as public), and flags the
file name, the title and every line of the converted text (`raw_stores.flags`, which is
`task_private.flags`: a `/memory/` path, an amount, a contact detail, a personal-data pattern, an
owner term). A file whose content could not be read (`pending_conversion` or `failed`) is flagged
too, since nothing in it was checked. Anything flagged, and neither `--private` nor
`--keep-in-repository` given: exit 7, the flags listed, nothing written. The agent asks the owner
whether to mark the source private and runs again with the answer. The checkout is then checked as
for a task write (`task_git.ready_to_write`, widened to `brain/`): on the store branch, fetched, not
behind, nothing unmerged. `--offline` skips the fetch, only once the owner agrees (`SMART-RULE-0034`).

**The same file again** (same SHA-256) is looked for in every raw store the brain can reach. It is
reused when its store can be read from the target: any store for a target in memory, only the same
repository for a repository target. A copy in memory, or in another repository, for a repository
target is refused (exit 8) with the existing record named, for the owner to decide: `--private`
reuses it from the pointer node, or `migrate` moves it.

## Allowed operations

- read a supplied local file
- copy it into the raw store `raw_stores.choose` names
- calculate SHA-256
- create or reuse a canonical Markdown source in the `sources/` folder beside that raw store
- create a node-local source reference in memory
- append an ingestion event to the relevant log
- with `migrate`, move a source record and its raw folder out of `/memory/sources/` and `/memory/raw/` into its node's store, and back with `--reverse`

The skill must not modify or delete an existing raw file. `migrate` is the one exception: it moves
a raw folder unchanged, and removes the original only after the copy's SHA-256 matches the record.

An identical file ingested again (same SHA-256) reuses the raw file and keeps the source record it
already has, whatever title it arrives with: nothing in it is rewritten, so a manual or specialised
conversion made there since is never lost. Only a node reference that does not exist yet is added.

## Inputs

- source file path
- optional target node path: a folder inside `/memory/`, written as `memory/projects/example`, `/memory/projects/example` or an absolute path inside the brain
- optional title
- `--private` (a pointer node only: keep the source in the pointer node) or `--keep-in-repository` (write into the repository although something was flagged), each the owner's answer
- `--offline` (skip the fetch before a write into a repository, once the owner agrees)
- optional tags (not yet taken by the script)

## Data sources

- The supplied local file, read once and copied unchanged.
- For a PDF, the first text extractor this computer has: poppler's `pdftotext` on PATH, then the `pypdf` Python package. Neither ships with Python; with neither, a PDF's record is `pending_conversion` with a note saying what to install, and the raw file is kept as always. Which extractor read a file, and its version, is in the record's notes.
- Every reachable raw store's `manifest.json` files, for an existing file with the same SHA-256, reused instead of duplicated.
- The pointer READMEs under `/memory/projects/`, `/memory/OWNER.md` and a checkout's `brain/JOINING.md`, through `task_stores`, to choose the store.
- The repository preflight's personal-data patterns and the owner's terms, through `task_private.flags`.
- `/shared/templates/source-document.template.md` for the source record.

## Permissions

- Read the supplied file; write only new files in the chosen raw store, the `sources/` beside it and the target folder's `sources/`; append to the target folder's `LOG.md`, a repository's `brain/LOG.md` when it wrote there, and `/memory/systems/raw-file-management/LOG.md`.
- Before a write into a repository, run `git` in that checkout (status, rev-parse, a fetch of the store branch unless `--offline`). It never stages, commits or pushes: the conductor commits memory and each repository separately.
- `migrate` writes the list files `/temp/migration/sources-<node>.md` and `.json`, the moved records and raw folders, every text file in memory and in the repository's `brain/` that names a moved path (never inside a raw store, a `LOG.md` or a migration ledger), and its ledger under `/memory/systems/raw-file-management/migrations/`.
- The script finds the brain root by walking up to `CONTRACT.md` and stops with an error when `<brain root>/memory/` is missing.
- A target node must be an existing folder inside `/memory/`: a source reference names an owner's file, so it never goes into the mechanics or the skill library (CONTRACT §3.4).
- Never modify, overwrite, normalise or delete an existing raw file.
- `reconvert.py SOURCE-ID` writes in exactly one of two places: the record `/memory/sources/<SOURCE-ID>.md` itself, rewritten in place, when its `updated` equals its `created`; otherwise `/memory/sources/<SOURCE-ID>.reconverted.md` beside it, overwritten if it exists, and the record stays byte-identical. Either way it appends one line to `/memory/systems/raw-file-management/LOG.md`. It never touches the raw file or a node's `sources/`.
- No credentials. The only network use is that `git fetch`, through the checkout's own remote. For a PDF it may run `pdftotext` as a local child process (no network), limited to 300 seconds.

## Script

```bash
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py FILE --node memory/projects/example
```

```bash
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py FILE --node memory/projects/example-pointer --private
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py FILE --node memory/projects/example-pointer --keep-in-repository
```

`ingest_raw.py` stores, records and logs; `scripts/convert.py` converts, as the Formats section below describes for each format. A format with no converter gets a record marked `pending_conversion`, and the raw file is kept as always. The script prints the source ID, the raw and record paths, the `conversion_status`, and whether the raw file and record were reused.

Text is read as UTF-8, or in the encoding a byte-order mark names (UTF-8, UTF-16 or UTF-32, as Windows editors save it); the mark is left out. Text that is not UTF-8 is kept with replacement characters and marked `partial`; a file with NUL bytes and no mark (binary, or UTF-16 without a mark) is marked `failed` rather than written into the record. Records, references and manifests are written with LF line ends on every platform; an appended log entry keeps the log's own line ends.

```bash
python -m unittest discover -s shared/skills/raw-file-ingestion/tests -v
```

The tests build a fictional brain in a temporary folder and ingest fictional files; the store
tests add a memory node, a pointer node and a Git checkout of its repository beside the brain.

### Moving sources into their node's store (`migrate`)

```bash
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py migrate --node memory/projects/example --dry-run
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py migrate --decide temp/migration/<list>.json --all move --private 3 --hold 5
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py migrate --node memory/projects/example --list temp/migration/<list>.json
python shared/skills/raw-file-ingestion/scripts/ingest_raw.py migrate --reverse memory/systems/raw-file-management/migrations/<ledger>.json
```

The sources of a node are the records in `/memory/sources/` whose every `project_refs` entry is in
that node. The list protocol is the tasks skill's (`task_migrate_lists`): the dry run writes the
numbered list for the owner, with each source's raw size, the weight a repository gains, its
visibility and, for a repository, the flags a new source would get (`raw_stores.source_flags`, the
one check for both): the record's lines, and beside the item its file name, its title, a
derivative's lines and a source that was never read. A source that cannot move (its raw file
outside `/memory/raw/`, missing or changed, a conflict marker in its record) is listed with the
reason. The dry run prints the list's path; `--decide` records the
owner's answer; the move follows `--list` and refuses a list whose records changed since (the
fingerprint) or an item with no decision. A memory node needs no list (nothing leaves memory); a
pointer node moves only what the owner cleared, `private` going to the pointer node's own `raw/`
and `sources/`. A source moves whole, so `--private-lines` is refused.

Each source: its raw folder is copied unchanged and the copy's SHA-256 checked against
`raw_sha256`; the record, and a `.reconverted.md` derivative beside it, is written in the store's
`sources/` with its paths in the store's form and `updated` set; then the originals are removed. In
a repository the manifest loses `original_path` and any other machine path. A reference to the
record in the target node's `sources/` is replaced by the record; a reference in the pointer node
to a source moving into the repository is removed, since the pointer node keeps no copy of the
project's sources (P17). Every text file in memory and in the repository's `brain/` that names the
old record or raw folder is rewritten, memory files with `<repository>:brain/...` (CONTRACT §16.2):
a task record gets an attributed History entry (P23) and its store's `STATE.md` is generated
again, another file with front matter a new `updated`, and a CRLF file keeps its line ends.
Everything is checked first: a missing raw file, a hash that no longer matches, a target that
exists, an unreadable manifest, a repository record that would still name `/memory/`, or a file to
rewrite that carries a Git conflict marker refuses the whole move with nothing written.
`--reverse LEDGER` moves each source back and restores `project_refs`, the memory manifest, the
`updated` of files unchanged since, any replaced or removed reference and the `STATE.md` of the
task stores it rewrote, so
an untouched move and its reverse leave memory byte-identical apart from task History and logs.
Repository files still naming a moved path are listed for the owner, never rewritten to name
`/memory/`. A ledger is reversed once. Exit 1: refused, with the reason; 6: no brain or memory.

`reconvert.py` still reads only `/memory/sources/`: a record moved into a node or a repository is
not yet reconverted by it.

```bash
python shared/skills/raw-file-ingestion/scripts/reconvert.py --list
python shared/skills/raw-file-ingestion/scripts/reconvert.py SOURCE-ID
```

Re-ingesting a file never rewrites its record, so `reconvert.py` converts a record's raw file again on purpose, through the same `convert.py` path. `--list` prints one tab-separated line per record whose `conversion_status` is not `complete` – id, status, raw source – sorted by id. `SOURCE-ID` (exactly the front-matter id or the record's file name without `.md`, never a prefix) decides by one rule: a record whose `updated` differs from its `created` is hand-edited, so it is left byte-identical and the new conversion is written beside it as `<SOURCE-ID>.reconverted.md` with `canonical_source_md` naming the record; any other record is rewritten in place. Either way every front-matter field the record had (owner, tags, node references and the rest) is carried through in its order; only `updated` (from the clock) and `conversion_status` change, and the derivative sets `canonical_source_md` to the record, replacing any value; an in-place rewrite keeps the record's own `canonical_source_md`. It logs which happened and prints the source id, the path written and the `conversion_status`. Exit 2: no such record, or a SOURCE-ID containing `/`, `\`, `*`, `?` or `[`; 3: its raw file is missing; 6: no brain or memory.

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

- immutable raw file in its raw store
- SHA-256 hash
- canonical Markdown source record beside it
- optional node-local source reference in memory
- printed JSON: `source_id`, `store`, `raw_file` and `canonical_markdown` (in the memory form), `conversion_status`, `duplicate_reused`, `source_record_reused` and `notes` (the repository and its visibility, flags the owner chose to keep, Git notes); on exit 7 and 8, a JSON with `written: false` and the flags or the existing record

## Failure behaviour

- check the brain root, the memory checkout, the target node and the chosen store before anything is written, so a refused run leaves no raw copy, record or log line (exit 6: no brain or memory; 4: node outside `/memory/`, `--private` without a pointer node, or two pointers naming one repository; 5: node missing; 7: flagged content bound for a repository; 8: the same file already in memory or in another repository, for a repository target; 9: the repository is not checked out, has no `brain/`, or its checkout may not be written now)
- do not overwrite conflicting raw files
- report unsupported conversion
- preserve the raw file even when conversion fails; an unexpected error in a converter becomes a `failed` record that names the error, so the raw file never stays without its record and log line
- write records, references and manifests through a temporary file moved into place, so a failure never leaves half a file
- the script does not create tasks: when `conversion_status` is not `complete`, the calling agent creates one (CONTRACT §11.2 step 8) naming the source record and the note in it that says why – OCR, a missing PDF extractor, an unprotected copy, a formula value to save

## Repository updates

- update source metadata
- append to the raw-file management log at `/memory/systems/raw-file-management/LOG.md`
- update the target node log when a target node is supplied, and the repository's `brain/LOG.md` when a source was written there
- `migrate` writes its ledger under `/memory/systems/raw-file-management/migrations/`; commits stay with the conductor, memory and each repository separately
