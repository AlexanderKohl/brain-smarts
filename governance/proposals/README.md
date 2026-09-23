---
id: governance-proposals-readme
title: Mechanics Governance Proposals
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T23:16:08+10:00
updated: 2026-09-23T14:12:51+10:00
owner: brain-owner
---

# Mechanics Governance Proposals

Read `/CONTRACT.md` first.

A proposal changes protected mechanics governance: `/CONTRACT.md`, `/RULES.md`, governance
schemas and templates, bootstrap files and the preflight validator (CONTRACT §13.2).

## Proposing a change

1. Copy `/shared/templates/governance-proposal.template.md` to this folder as
   `<short-slug>.md`, set its `id` to `PROPOSAL-<short-slug>`, and fill it in against
   `/shared/schemas/governance-proposal-schema.md`. Keep it free of personal data: say "the
   owner", use fictional examples, and name no private project, client or machine.
2. For a change in your own brain, present it to the owner and apply it only after an explicit
   acceptance (CONTRACT §13.2). Keep the accepted record in your memory at
   `/memory/governance/proposals/`, which is where an owner's decision history belongs.
3. To offer the change to everyone who uses these mechanics, open a pull request against the
   upstream repository with the proposal file and the exact diff it describes. The upstream
   maintainer reviews and accepts it there; once merged, the proposal file is removed from this
   folder, so the repository keeps the mechanism, not the history.

Keep existing rule identifiers. Mechanics rules are named by stable `SMART-RULE-NNNN`
identifiers, indexed in `/RULES.md`. A small additive or clarifying change amends that rule under
the same identifier. A distinct new rule gets no number while it is a proposal: the next free
number in its layer is assigned when the owner accepts it (CONTRACT §13.2, *Rule identifiers*).

Proposal wording is not active merely because it is stored here or marked `accepted`. Active
governance is the implemented content of the protected target file.

#### Folders

No immediate child folders exist. Store a proposal under review directly in this directory.
