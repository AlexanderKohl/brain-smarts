---
id: PROPOSAL-memory-removed-files-register
title: A removed-files register in memory for files the owner's memory removed
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-20T16:04:30+10:00
updated: 2026-10-20T16:58:30+10:00
accepted_by: brain-owner
accepted_at: 2026-10-20T16:49:22+10:00
implemented_at: 2026-10-20T16:58:30+10:00
previous_contract_version: 2.5.0
new_contract_version: 2.5.0
target_files:
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight_references.py
---

# A removed-files register in memory for files the owner's memory removed

## Summary

A closed proposal's `target_files` may name a file that has since been removed; the repository
preflight accepts that only when `/governance/removed-files.md` lists the file. That register is in
the mechanics repository, which may hold no personal data, so a file removed from the owner's memory
(a node moved into its own repository under CONTRACT §7.1, for example) can never be listed: the
personal-data check refuses the row, and the preflight then fails on every closed proposal that named
the file. This proposal adds a second register in memory, `/memory/governance/removed-files.md`, with
the same table, read for `/memory/` paths only.

## Change

1. `preflight_references.py`, `removed_files(root)`: also read `/memory/governance/removed-files.md`
   when memory is present, accepting only rows whose path starts `/memory/`.
2. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, the bullet that begins "fail on
   missing required Markdown metadata": after "broken declared references (a `#fragment` after the
   path must match the start of a Markdown heading in the referenced file)" insert: ", except a closed
   proposal's `target_files` entry for a file that is gone and is listed, with where its content
   went, in `/governance/removed-files.md` (a mechanics path) or `/memory/governance/removed-files.md`
   (a `/memory/` path)".
3. `/shared/templates/memory-skeleton/governance/removed-files.md`: an empty register for new owners
   (not protected).

## Reason

Moving a node out of memory is a routine extraction (CONTRACT §7.1); its history must stay intact
(CONTRACT §13.2), and its removed files must stay findable without putting owner names into the
mechanics.

## Scope and risks

Only references from closed proposals' `target_files` to `/memory/` paths are affected; mechanics
paths keep their register. Risk: a stale row hides a broken reference; mitigated because each row
names where the content went. Rollback: revert the two files; the memory register is then ignored.

## Validation

A test: a closed proposal naming a removed `/memory/` file fails without the memory register row and
passes with it; a `/memory/` row in the mechanics register and a mechanics path in the memory
register are both ignored. The full preflight test suite passes.

## Acceptance

Accepted by the owner on 2026-10-20T16:49:22+10:00 in the conversation with the conductor ("I accept PROPOSAL-memory-removed-files-register and PROPOSAL-atlas-node-rules-into-repository as shown.").
