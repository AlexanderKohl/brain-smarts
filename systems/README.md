---
id: systems-readme
title: Operating Systems
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: system_library
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Operating Systems

Read `/CONTRACT.md` first.

Systems are persistent cross-cutting operational capabilities without a natural completion date.

#### Folders

##### `raw-file-management/`

Contains the canonical system node for immutable raw-file ingestion, storage, conversion and provenance. System-specific rules and mechanism state belong there; raw evidence remains canonical under `/memory/raw/`, and the owner's ingestion log and raw-store state live at `/memory/systems/raw-file-management/`.
