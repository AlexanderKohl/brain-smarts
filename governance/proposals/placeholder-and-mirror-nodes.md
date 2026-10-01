---
id: PROPOSAL-placeholder-and-mirror-nodes
title: Placeholder nodes the owner lays out ahead of content, and where a system's owner records live
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-01T10:52:46+10:00
updated: 2026-10-01T12:05:38+10:00
rule_id: null
accepted_by: brain-owner
accepted_at: 2026-10-01T12:05:38+10:00
implemented_at: 2026-10-01T12:05:38+10:00
previous_contract_version: 2.2.0
new_contract_version: 2.3.0
target_files:
  - /CONTRACT.md
---

# Placeholder nodes the owner lays out ahead of content, and where a system's owner records live

Read `/CONTRACT.md` first.

## Summary

Two additions to the contract from the first test of its node rules against a real memory:

1. **Placeholder nodes.** The owner may lay out a structure before it has content (one node for
   each part of a business, say). Today the contract has no case for that: by §7 none of those
   nodes would be made. After this change each says it is a placeholder, and one review date covers
   the structure; at the review, an empty placeholder is filled, folded into its parent, or kept.
2. **A system's owner records.** A system in the mechanics (`/systems/<system>/`) holds the
   mechanism. The owner's records for it live in memory at `/memory/systems/<system>/`, a node of
   the same name. The contract says this for skills but not for systems, and agents have written
   an owner fact into the mechanics copy.

- **For agents:** two places in the contract answer two questions they now guess at.
- **For the owner:** empty structure is kept on purpose and reviewed, not left unexamined.

## Current problem

- The owner laid out five department nodes for one business on 4 August 2026, each with the five
  core files and two or three general rules. By 1 October none had content beyond the template;
  §7 ("usually justified when at least three strong reasons apply") would make none of them, and
  nothing says to review them.
- `/systems/raw-file-management/` (mechanics) and `/memory/systems/raw-file-management/` (owner
  records) both exist. §3.5 says where a skill's owner data goes (`/memory/skills/<skill>/`), and
  the path rule implies the system case, but no sentence says it. In a probe on 30 September 2026,
  agents that skipped the bootstrap wrote an owner fact into the mechanics node.

## Current wording

§7, after the strong reasons and the list of what not to make a node for:

> A new node is usually justified when at least three strong reasons apply.

§3.5, the bullet on skills:

> - Owner-specific configuration, data and notes for a shared or library skill live at
>   `/memory/skills/<skill>/`, using the same inner layout as the skill (`config/`, `data/`,
>   `knowledge/` and so on). …

## Proposed wording

§7, after "A new node is usually justified when at least three strong reasons apply.":

> The owner may lay out a structure ahead of its content – for example one node for each part of a
> business – before three strong reasons apply. Each such node says so at the top of its
> `STATE.md` (`Placeholder: laid out ahead of its content on <date>.`), and one task with
> `next_review` covers the structure. At that review, a placeholder that still holds no content of
> its own is filled, folded into its parent, or kept to a new review date, as the owner decides.

§3.5, a new bullet after the one on skills:

> - A system node in the mechanics, `/systems/<system>/`, holds the mechanism: its rules, its
>   procedure and the state of the mechanism itself. The owner's records for that system – its log
>   of use, the owner's state, decisions and configuration – live in memory at
>   `/memory/systems/<system>/`, a node of the same name. An owner fact about a system is written
>   there, never in the mechanics node.

`contract_version` 2.2.0 to 2.3.0 (minor: additive, compatible). If `PROPOSAL-tiered-bootstrap` is
accepted first, this becomes 2.4.0.

## Reason

The owner's answers of 1 October 2026 to the first pass of the node-boundary task: keep the
department nodes as placeholders with a review date, and write the system rule into the contract.

## Scope and behavioural consequences

- New nodes and the owner's structure; existing placeholders are marked once (the owner's memory,
  not part of this change).
- Agents write a system's owner records only in memory.

## Risks and conflicts

- **Placeholders that never get content** stay visible through their review task rather than
  disappearing.
- **Conflicts:** none. The path rule (§3.5) already implies the system case; this states it.

## Migration

The owner's existing placeholders were marked in their `STATE.md`, with one review task, at the
owner's answer of 1 October 2026. The mechanics' one system node already keeps owner records in memory.

## Rollback

Remove the two passages and return `contract_version` to 2.2.0.

## Validation

The repository preflight passes. The node-boundary task's next pass checks that placeholders are
marked and that no mechanics system node holds owner records.

## Acceptance

Accepted by the owner on 1 October 2026. The owner's record is kept in their memory.

## Implementation record

Implemented on 1 October 2026: CONTRACT §7 and §3.5 as worded above; `contract_version` 2.3.0
in the contract and the three repository manifests.
