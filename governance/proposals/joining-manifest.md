---
id: PROPOSAL-joining-manifest
title: A shared project carries a joining manifest, and bootstrap joins from it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-21T12:12:20+10:00
updated: 2026-10-21T12:12:20+10:00
previous_contract_version: 2.6.0
new_contract_version: 2.7.0
target_files:
  - /CONTRACT.md
  - /BOOTSTRAP.md
---

# A shared project carries a joining manifest, and bootstrap joins from it

## Summary

A project shared between brains already carries `brain/JOINING.md` and the core skill
`/shared/skills/join-project/` joins from it, and `sync.py` reminds a person who has cloned such a
project without joining it. Nothing in the contract or the bootstrap names the manifest yet, so an
agent working inside a project repository is not told that the file exists or that it should join
first. This proposal names it in CONTRACT §16.2 and adds one sentence to bootstrap step 9.

What changes for the owner and agents: a collaborator's agent that opens a shared project it has
not joined is told by the bootstrap to run the join (dry run first) before any work, so the pointer
node, the working branch and the shared boards exist; the owner no longer relays setup prompts by
hand.

## Change

CONTRACT §16.2, after the sentence "A board the owner-board skill keeps for the project lives there
too, in `brain/status/`, when more than one brain works on it.", insert:

> A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the
> repository, the working branch, the contract and skill versions it assumes, its shared boards, the
> vault entries each person creates for themselves (names only) and the records to read first; a
> brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying
> another brain's memory.

`/BOOTSTRAP.md` step 9. Current wording:

> 9. Inside an external project repository (`/CONTRACT.md` §16), bootstrap from the brain root, then
> read the repository's `brain/README.md` and `brain/STATE.md` as the active node.

Proposed: the same step, followed by:

> When the repository carries `brain/JOINING.md` and this brain has no pointer node for it, join
> first (`python shared/skills/join-project/scripts/join.py <path> --dry-run`, then without
> `--dry-run`), so the pointer node and boards exist before work starts.

`contract_version` 2.6.0 becomes 2.7.0 (minor: additive behaviour, compatible with existing content).

## Reason

The owner asked on 21 October 2026 that a future collaborator's brain guide them through joining a
shared project by itself. The skill and the session-start reminder are built; naming the manifest in
the contract and the bootstrap makes an agent that starts inside the repository act on it.

## Scope and risks

- Scope: project repositories that carry `brain/JOINING.md`; a project worked alone needs none.
- Risk: a join run on the wrong brain or memory. Mitigation: the skill writes only the running
  brain's own memory, starts with a dry run, never reads or prints a secret, never pushes a project
  repository.
- Migration: none; the three current shared projects already carry the manifest.
- Rollback: revert the contract and bootstrap commit; the skill and manifests stay harmless.

## Validation

The repository preflight; the join-project tests (11) and the sync tests; a dry run of the join
against each shared repository with a fictional memory.

## Acceptance

Pending the owner's explicit acceptance of this proposal as shown.
