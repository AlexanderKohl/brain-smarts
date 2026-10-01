---
id: PROPOSAL-align-0024-with-0038
title: SMART-RULE-0024 says the same as SMART-RULE-0038 about when a worker needs its own worktree
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-01T23:23:23+10:00
updated: 2026-10-01T23:25:20+10:00
rule_id: SMART-RULE-0024
accepted_by: brain-owner
accepted_at: 2026-10-01T23:25:20+10:00
implemented_at: 2026-10-01T23:25:20+10:00
previous_contract_version: 2.4.0
new_contract_version: 2.4.0
target_files:
  - /RULES.md
---

# SMART-RULE-0024 says the same as SMART-RULE-0038 about when a worker needs its own worktree

Read `/CONTRACT.md` first. A small amendment to `SMART-RULE-0024`, which keeps its identifier.
It mirrors the wording accepted the same evening for `SMART-RULE-0038`
(`PROPOSAL-tests-in-the-session-copy`), so the two rules no longer differ on the one phrase.

## Current problem

`SMART-RULE-0038` now sends a worker into its own worktree only when it "builds code or runs
tests that write outside its own paths"; `SMART-RULE-0024` still says "it builds or tests code".
Two rules, one question, two answers (`SMART-RULE-0033`).

## Current wording

In `SMART-RULE-0024`, the bullet "Workers do not commit…" ends:

> A worker whose work cannot be kept apart – it builds or tests code, it must change a file
> another worker also changes, or it is one of several alternative attempts – works in its own
> worktree, branched from the conductor's branch; the conductor merges it back
> (`SMART-RULE-0014`).

## Proposed wording

> A worker whose work cannot be kept apart – it builds code or runs tests that write outside its
> own paths, it must change a file another worker also changes, or it is one of several
> alternative attempts – works in its own worktree, branched from the conductor's branch; the
> conductor merges it back (`SMART-RULE-0014`). Unit tests that read and write only inside the
> worker's own paths (and their caches) run in the session copy (`SMART-RULE-0038`).

## Reason

One phrase, one meaning, in both rules.

## Scope and behavioural consequences

None beyond `PROPOSAL-tests-in-the-session-copy`, already active.

## Risks and conflicts

None.

## Migration

None.

## Rollback

Revert the commit to `/RULES.md`.

## Validation

Repository preflight passes with the accepted proposal.

## Acceptance

Accepted by the owner on 2026-10-01 ("yes") to: "Accept `PROPOSAL-align-0024-with-0038` with that
wording?", which quoted the wording in full.

## Implementation record

Implemented 2026-10-01T23:25:20+10:00: the sentence in `SMART-RULE-0024` replaced with the accepted wording;
`contract_version` unchanged at 2.4.0. Owner record:
`/memory/governance/proposals/align-0024-with-0038-acceptance.md`.
