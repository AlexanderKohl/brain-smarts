---
id: PROPOSAL-rerun-failed-tests-and-rolling-push
title: A failed test is rerun once, alone; a conductor pushes as soon as a merge is ready
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
rule_id: SMART-RULE-0049
accepted_by: brain-owner
accepted_at: 2026-11-17T05:43:03+10:00
implemented_at: 2026-11-17T05:43:03+10:00
created: 2026-11-17T05:15:23+10:00
updated: 2026-11-17T05:43:03+10:00
target_files:
  - /RULES.md
---

# A failed test is rerun once, alone; a conductor pushes as soon as a merge is ready

Read `/CONTRACT.md` first. This proposal adds two bullets to `SMART-RULE-0049` (Fast project checks
without reduced coverage) in `/RULES.md`. It is an additive amendment and keeps the rule's
identifier (CONTRACT §13.2).

## Summary in plain language

Two practices a code project adopted on 16 November 2026 become part of the rule every code project
follows.

- **For agents:** a project's check before integration reruns only the tests that failed, once and
  alone, and names them; a test that keeps needing the rerun is reported and fixed. A conductor
  merging several workers' branches pushes whenever a merge is ready and no push is running.
- **For the owner:** fewer pushes refused by one unlucky timeout, with every test still run on
  every push, and no waiting for a batch.

## Current wording

`SMART-RULE-0049` has six bullets; none covers a rerun or when a conductor pushes. They are
unchanged.

## Proposed wording

Two bullets are added at the end of `SMART-RULE-0049`:

- **A failed test is rerun once, alone, and stays named.** A check that runs before integration (a pre-push hook or CI) runs each failed test once more, on its own, after every other step has finished, so nothing else competes with it for the machine. A test that passes then counts as passed and is named in the check's output; one that fails again fails the check. Only the failed tests rerun, never the whole suite, and never more than once. A step with more failures than a small limit the project sets (5 unless it chooses another) is not rerun: that many failures is a fault. Each rerun is recorded outside the repository's tracked files, and the check warns when the same test has needed a rerun in 3 of its last 20 runs; such a test is reported to the owner and fixed, never left to the rerun.
- **Rolling push.** A conductor that merges several workers' branches pushes as soon as a merge is ready and no push is running. While a push's check runs, nothing is merged into the branch being pushed. Branches that finish during a push are merged when it returns and go out together in the next push. No push waits for a batch to be complete, and none is held back to save a check or a deployment.

## Reason

In one project, five pushes in a day were refused by browser timing failures in tests the changes
did not touch; each refusal cost a full check. The owner chose a rerun of only the failed tests,
then asked for it to be a rule for every development project rather than one project's own.

## Scope and consequences

Every code project with a check before integration. As with the rest of `SMART-RULE-0049`, a new
project builds it in, and an existing project applies it when it is next changed, or records why it
does not fit. The first bullet needs code in each project's check; the second is practice only.

## Risks and migration

A test that fails only sometimes because of a real fault can pass on its rerun. The named output,
the record and the warning keep it visible. No migration: projects adopt it when next changed.

## Rollback

Remove the two bullets from `/RULES.md` and rebuild the core files.

## Validation

`core.py build`, then the repository preflight.

## Acceptance

The owner accepted both bullets on 17 November 2026 ("1. both bullets"), answering the question that named this proposal and quoted the wording.
