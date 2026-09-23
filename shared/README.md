---
id: shared-readme
title: Shared Resources
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: shared
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Shared Resources

Read `/CONTRACT.md` first.

This area contains reusable skills, schemas and templates that may be used by multiple nodes.

Shared resources have one canonical copy. Projects reference them and store only local configuration or outputs. Owner-wide configuration, data and notes for a shared skill live in `/memory/skills/<skill>/` (CONTRACT §3.5); nothing here may carry personal data (CONTRACT §3.4).

#### Folders

##### `schemas/`

Contains canonical shared metadata and task schemas. Update schemas only for established repeated needs and migrate affected records when their version changes.

##### `skills/`

Contains canonical reusable skills and executable capabilities shared across nodes. Keep credentials outside the repository, store requesting-node outputs locally, and keep owner configuration in `/memory/skills/<skill>/`.

##### `templates/`

Contains canonical shared templates for nodes, source records, governance proposals and project pointer nodes, and the skeleton for a new owner's memory (`templates/memory-skeleton/`). Copy templates into their destination, replace placeholders and retain the contract reference.
