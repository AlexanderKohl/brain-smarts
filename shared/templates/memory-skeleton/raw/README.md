---
id: template-raw-readme
title: Raw Source Files
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Raw Source Files

Read `/CONTRACT.md` first.

Immutable source evidence (CONTRACT §11.1). Store each file at
`/memory/raw/YYYY/MM/<source-id>/<original-filename>` through
`/shared/skills/raw-file-ingestion/`, which records its SHA-256 hash and creates the companion
source record under `/memory/sources/`. Never edit, overwrite, normalise or delete a raw file.
Markdown files under this folder are evidence and are exempt from the metadata rules.

#### Folders

One folder per year (`YYYY/`), then per month (`MM/`), then per source ID. Year folders need no
separate summary.
