---
id: PROPOSAL-rehearse-and-list-the-surface
title: Run it with real processes first, and list the whole surface before the first review
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-11-22T10:27:31+10:00
updated: 2026-11-22T11:10:29+10:00
rule_id: null
accepted_by: brain-owner
accepted_at: 2026-11-22T11:10:02+10:00
implemented_at: 2026-11-22T11:10:29+10:00
previous_contract_version: 3.2.0
new_contract_version: 3.2.0
target_files:
  - /RULES.md
---

# Run it with real processes first, and list the whole surface before the first review

## Plain-language summary

Two existing rules each gain one bullet. Tests: a build with more than one process, or one that meets the
operating system, is first run end to end with real processes and throwaway data, and passing tests are not
called proof that the parts work together until that run has passed. Security: work that guards something lists
every path to it, with a test that fails on an unlisted path, before its first code review.

## Current problem

A build passed some four hundred unit tests and eight independent code-review rounds, and its first run with real
processes then found five faults, two of which broke every ordinary use: every test had stood in for the boundary
between two processes with a fake inside one process. In the same build, three review rounds in a row each found
one more way to reach a store that was meant to be closed; a list of every such path found seventeen gaps in one
pass, and the next review found none unlisted. The owner's record of the build holds the detail.

## Current wording

`/RULES.md`, `SMART-RULE-0022 – Tests demonstrate behaviour`: seven bullets, the last being "Proportion applies.
Clearly non-material changes as defined in `SMART-RULE-0016` need no new test; a behavioural change always does."
None speaks of processes or of running the built thing.

`/RULES.md`, `SMART-RULE-0021 – Security designed into every implementation`: nine bullets, the last being "When a
change materially widens an externally reachable surface, adds an authentication or payment path, or handles
sensitive data for the first time, escalate to at least standard depth under `SMART-RULE-0016` and say so in the
change." None asks for a list of the paths to what is guarded.

## Proposed wording or exact diff

Both rules keep every present bullet and their identifiers. `SMART-RULE-0022` gains, as its last bullet:

```markdown
- **Run it for real before trusting the tests.** When a change has more than one process, or meets
  the operating system or another program (a background service, a keychain, a pipe, a file lock,
  a scheduler, a working tree another tool rewrites), the first thing built is a thin end-to-end
  run with real processes and throwaway data, kept as a script that can be run again. It is run
  before the first review and after every fix that touches such a boundary. A test that stands in
  for a boundary with a fake proves the logic on each side, never that the two sides meet: a
  passing suite is not reported as evidence that the parts work together until that run has
  passed. The run keeps itself away from live data, refuses to start when it cannot prove that,
  and proves its own clean-up.
```

`SMART-RULE-0021` gains, as its last bullet:

```markdown
- **List the whole surface before the first review.** Work that guards something (credentials,
  money, personal data, permissions) produces, before its first code review, a list of every path
  that reads, writes, spends or copies the guarded thing, and a test that fails when the code
  gains a path the list does not name. The reviewer is given the list and asked what is missing
  from it. A finding of one more path is answered by completing the list, not by closing that
  path alone.
```

The `Applies when` entries of both rules in the index of `/RULES.md` are unchanged; `/CORE-RULES.md` is rebuilt.

## Reason

Each bullet names the one step that found, in hours, what days of tests and reviews had not.

## Scope and behavioural consequences

Every software project the brain works on. A small change inside one process, and work that guards nothing, are
untouched. For the rest, the first packet of a build plan becomes the end-to-end run or the list, and a
conductor does not send such work to its first review without them.

## Risks and conflicts

- The end-to-end run touches the real computer: the bullet requires it to isolate itself and prove its clean-up.
- More work before the first review. It replaces review rounds that each cost more.
- No conflict found with `SMART-RULE-0016` (depth still scales) or `SMART-RULE-0024` (the plan a risky build
  starts from gains these as its first items).

## Migration

None. Builds in progress adopt the bullets at their next review.

## Rollback

Remove the two bullets and rebuild `/CORE-RULES.md`.

## Validation

`core.py check` and the repository preflight after the change.

## Acceptance

Requested on 2026-11-22. Ask one direct question that identifies this proposal. Do not treat silence, adjacent
approval or general agreement as acceptance.

## Implementation record

Accepted by the owner at 2026-11-22T11:10:02+10:00 and applied at 2026-11-22T11:10:29+10:00: the two bullets added to `/RULES.md` as shown above, nothing else changed; no contract change (3.2.0). The owner's record of the acceptance is in their memory.
