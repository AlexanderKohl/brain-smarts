---
id: raw-file-management-rules
title: Raw File Management Rules
type: rules
schema_version: 0.2
contract: /CONTRACT.md
scope: /systems/raw-file-management
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-08-04T15:40:17+10:00
---

# Rules

Read `/CONTRACT.md` first.

- Never modify raw files.
- Use SHA-256 for file identity.
- Reuse existing raw files when hashes match.
- Produce canonical Markdown source records.
- Mark unsupported or incomplete conversion.
- Preserve source order and identifiers.
- Create visible tasks for unresolved conversion problems.
