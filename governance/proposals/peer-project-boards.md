---
id: PROPOSAL-peer-project-boards
title: Project boards shared between peer brains in the project repository
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-21T08:11:09+10:00
updated: 2026-10-21T08:11:09+10:00
previous_contract_version: 2.5.0
new_contract_version: 2.6.0
target_files:
  - /CONTRACT.md
---

# Project boards shared between peer brains in the project repository

## Summary

Today a project's board lives in the owner's memory, so a collaborator with their own brain cannot
see or act on it. This proposal lets a project board live in the project repository's `brain/status/`
folder whenever more than one brain works on the project. Every brain is a peer: each writes only
records that carry its own author, nothing generated is committed, and each owner's tasks stay in that
owner's own memory and are never drawn into the repository. A second sentence makes every brain that
shares a repository pull before it builds and before it pushes, and derive shared state from the
repository's records.

What changes for the owner and agents: a collaborator's brain and the owner's brain save verdicts and
add cards on the same board, each applies its own saves and pushes, and each sees the other's by
pulling. Owner tasks, owner-private notes and screenshots stay private.

## Change

CONTRACT §16.2, first paragraph. Current wording ends:

> Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents;
> a collaborator without the brain reads it as the project's own rules.

Proposed: the same paragraph, followed by:

> A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more
> than one brain works on it. Every such brain is a peer: its records carry its author and are
> rewritten by no other author, its generated pages are not committed, and each owner's tasks about
> the project stay in that owner's `/memory/tasks/`, drawn only in that owner's memory, never into the
> repository.

CONTRACT §16.3. Current wording:

> The repository preflight validator validates the mechanics repository and, when present, `/library/`
> and `/memory/`. A project repository runs its own checks; its `brain/` folder follows section 15
> where it applies. Commits and pushes in a project repository follow the inherited Git rules and are
> reported separately from the brain's own repositories.

Proposed: the same paragraph, followed by:

> A brain that shares a project repository with another pulls before it builds and before it pushes,
> and derives shared state from the repository's records rather than carrying its own copy.

`contract_version` 2.5.0 becomes 2.6.0 (minor: additive behaviour, compatible with existing content).

## Reason

The owner asked on 21 October 2026 that he and a collaborator work on the same board views, with no
hierarchy between their brains: each brain applies its own verdicts and the other's board follows
through GitHub. §16.2 names the folders a project's `brain/` holds and does not name a board, and
§16.1 keeps owner tasks private; the amendment makes the board's place explicit and keeps tasks
private. The design it enables is `/temp/delegation/runs/RUN-20261021-080559/W01.plan.md`.

## Scope and risks

- Scope: project repositories with a second brain; first one shared project board. Boards of
  projects worked by the owner alone stay in memory.
- Risk: owner-private content reaching the repository. Mitigation: the board build refuses to write
  any `/memory/` content or task into `brain/status/`, with a test.
- Risk: two brains clashing. Mitigation in the design: one file per card and per event with
  author-prefixed ids, an append-only event log, generated pages rebuilt after every pull, a
  deterministic rule when both act on one card with the conflict shown on the card.
- Migration: that board moves from its memory pointer node to `brain/status/` after
  the owner-board and release-notes changes are built and tested.
- Rollback: revert the contract commit; move the board back into the pointer node.

## Validation

The repository preflight on the mechanics, library and memory; the owner-board and release-notes test
suites, including a test that the build writes no memory content into a repository and a two-author
clash test.

## Acceptance

Pending the owner's explicit acceptance of this proposal as shown.
