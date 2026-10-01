---
id: PROPOSAL-tests-in-the-session-copy
title: Unit tests inside a worker's own paths run in the session copy
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-01T23:18:17+10:00
updated: 2026-10-01T23:19:19+10:00
rule_id: SMART-RULE-0038
accepted_by: brain-owner
accepted_at: 2026-10-01T23:18:17+10:00
implemented_at: 2026-10-01T23:19:19+10:00
previous_contract_version: 2.4.0
new_contract_version: 2.4.0
target_files:
  - /RULES.md
---

# Unit tests inside a worker's own paths run in the session copy

Read `/CONTRACT.md` first. A small amendment to `SMART-RULE-0038`, which keeps its identifier
(CONTRACT §13.2). Raised as question 4 of the reply that presented
`PROPOSAL-conductor-stays-small` on 1 October 2026; the owner said yes to the idea and then
"accept" to the exact wording below.

## Current problem

`SMART-RULE-0038` sends any worker that "builds or tests code" into its own worktree. In the run
that built the context guard (`RUN-20261001-223636`), three workers each changed and unit-tested
code in their own skill folders, on disjoint `writes: paths`, inside the conductor's session copy.
Nothing collided; one unrelated test flickered once while a sibling wrote files, then passed. A
worktree per worker would have cost three more checkouts and three merges for no isolation that
the disjoint paths did not already give. The rule's purpose – keeping work apart – was met; its
letter was not.

## Current wording

In `SMART-RULE-0038`, the bullet "A session's delegated workers share its copy and branch by
default…" ends:

> A worker gets its own worktree, branched from the session's branch and merged back by the
> conductor, only when its work cannot be kept apart: it builds or tests code, it must change a
> file another worker also changes, or it is one of several alternative attempts.

## Proposed wording

> A worker gets its own worktree, branched from the session's branch and merged back by the
> conductor, only when its work cannot be kept apart: it builds code or runs tests that write
> outside its own paths, it must change a file another worker also changes, or it is one of
> several alternative attempts. Unit tests that read and write only inside the worker's own paths
> (and their caches) run in the session copy.

## Reason

Isolation is about what a worker writes, not about whether it runs tests. A unit test confined to
the worker's own paths cannot touch another worker's files; a build, or a test that writes
build output, shared fixtures or a database, can.

## Scope and behavioural consequences

Conductors dispatch unit-test work on disjoint paths without a worktree; builds and tests with
side effects outside the paths still get one. The matching sentence in `SMART-RULE-0024` ("it
builds or tests code") is not changed by this proposal; `SMART-RULE-0038` is the more specific
rule and governs.

## Risks and conflicts

A worker that misjudges what its tests write can disturb a sibling; `check-writes` after the run
still finds any path no packet names.

## Migration

None.

## Rollback

Revert the commit to `/RULES.md`.

## Validation

Repository preflight passes with the accepted proposal; no script changes.

## Acceptance

Accepted by the owner on 2026-10-01 ("accept") to the question: "Accept
`PROPOSAL-tests-in-the-session-copy` with that wording?", which quoted the proposed wording in
full.

## Implementation record

Implemented 2026-10-01T23:19:19+10:00: the sentence in `SMART-RULE-0038` replaced with the accepted wording;
`contract_version` unchanged at 2.4.0. Owner record:
`/memory/governance/proposals/tests-in-the-session-copy-acceptance.md`.
