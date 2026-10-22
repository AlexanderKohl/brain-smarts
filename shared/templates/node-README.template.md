---
id: NODE-ID-readme
title: NODE TITLE
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: project
status: active
parent: /PARENT
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER
skill_refs: []
knowledge_refs: []
source_refs: []
---

# NODE TITLE

Read `/CONTRACT.md` first.

## Purpose

## Scope

#### Folders

List each immediate child folder that exists, alphabetically, and remove the entries below for
folders the node does not have yet (CONTRACT §3.1). The layout is the same in memory and in a
repository's `brain/` folder, so the node moves between the two unchanged.

##### `raw/`

Contains the immutable raw files of the sources this node owns, at
`raw/YYYY/MM/<source-id>/<original-filename>` (CONTRACT §11.1). Raw files are never edited.

##### `sources/`

Contains the canonical Markdown source records of the sources this node owns; each references its
raw file in `raw/`.

##### `tasks/`

Contains this node's task store (CONTRACT §9): `inbox/`, `open/`, `completed/`, `recurring/` when
needed, and a `STATE.md` the tasks skill generates from the records. Every task whose project
reference names this node is kept here. Its `README.md` comes from
`/shared/templates/node-tasks-README.template.md`.

## Dependencies

## Navigation
