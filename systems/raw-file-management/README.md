---
id: raw-file-management-readme
title: Raw File Management
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: system
status: active
parent: /systems
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
skill_refs:
  - /shared/skills/raw-file-ingestion
---

# Raw File Management

Read `/CONTRACT.md` first.

## Purpose

Manage immutable raw source files and accessible Markdown derivatives across the brain.

This node holds the mechanism: rules, knowledge and the state of the capability. The owner's
side – the ingestion log written for each file and the state of the owner's raw store – lives
at `/memory/systems/raw-file-management/`, and the files themselves under `/memory/raw/`.

## Scope

- ingestion
- hashing and duplicate detection
- storage under `/memory/raw/`
- conversion under `/memory/sources/`
- project-local source references
- conversion quality and provenance

#### Folders

##### `data/`

Contains local structured or generated operational manifests and validation outputs owned by this system. Immutable source files remain canonical under `/memory/raw/`.

##### `skills/`

Contains local procedures or wrappers specific to this system. The general ingestion capability remains canonical under `/shared/skills/raw-file-ingestion/`.
