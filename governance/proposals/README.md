---
id: brain-development-proposals-readme
title: Brain Development Governance Proposals
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T23:16:08+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Governance Proposals

This directory contains canonical proposals for changes to protected mechanics governance:
`/CONTRACT.md`, `/RULES.md`, governance schemas and templates, bootstrap files and the
preflight validator.

**Moved.** These records lived under `/projects/brain-development/proposals/` in the
single-repository brain and moved here under `RULE-2026-0046` (a candidate until accepted).
The copies here are generalised for the mechanics layer: owner names, client projects and
incident identifiers are replaced by generic wording, and `accepted_by` reads `brain-owner`.
The originals, with the owner's name, the real projects and the acceptance wording, are kept in
the history of the owner's memory repository; a live copy there would duplicate these IDs. The
proposals that only ever concerned owner projects (`RULE-2026-0005`, `0007`, `0008`, `0009`,
`0011`, `0026`, `0027` and `0031`) were not copied here; they live in
`/memory/governance/proposals/` with every other owner-layer proposal.

Proposal wording is not active merely because it is stored here or marked `accepted`. Active governance is the implemented content of the protected target file.

Keep existing rule IDs. Small additive or clarifying changes amend the original proposal record and are accepted under that same ID. Mint a new `RULE-YYYY-NNNN` only for a distinct new rule.

Use `/shared/templates/governance-proposal.template.md` and `/shared/schemas/governance-proposal-schema.md`.

#### Folders

Store proposal records directly in this directory.

##### `RULE-2026-0044-destination-skills/`

Draft skill text for review beside `RULE-2026-0043` and `RULE-2026-0044`, holding the procedure
those proposals move out of root `/RULES.md`. Drafts only, kept here rather than in
`/shared/skills/` so that unaccepted obligations stay out of active instruction paths. Deleted on
acceptance, when the text moves to its skill.
