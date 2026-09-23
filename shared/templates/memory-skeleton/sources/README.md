---
id: template-sources-readme
title: Source Records
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Source Records

Read `/CONTRACT.md` first.

Canonical Markdown representations of raw files, one per source ID, created from
`/shared/templates/source-document.template.md`. Each record keeps `raw_source` and
`raw_sha256` pointing at its immutable file under `/memory/raw/` (CONTRACT §11.2 and §11.3).

#### Folders

No immediate child folders exist. Source records are stored directly in this directory.
