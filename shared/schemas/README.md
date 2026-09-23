---
id: schemas-readme
title: Shared Schemas
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T19:36:19+10:00
---

# Shared Schemas

Read `/CONTRACT.md` first.

Schemas define repeated metadata patterns. They should evolve only when repeated practical needs justify change.

Schemas here are brain-wide: any project, skill or tool may rely on them, whether or not the skill that keeps the records is switched on. Alphabetical:

- `card-schema.md` – a board card, one thing the owner asked for (`/shared/skills/owner-board/`)
- `contact-schema.md` – a contact and a persona (enforced by `/library/skills/crm/`)
- `governance-proposal-schema.md` – the proposal lifecycle and the acceptance evidence required before protected governance becomes active
- `metadata-schema.md` – the front matter every Markdown file carries
- `task-schema.md` – a task record (`/shared/skills/tasks/`)

A test beside each skill fails when its code and its schema disagree.

#### Folders

No immediate child folders exist. Canonical shared schema documents are stored directly in this directory.
