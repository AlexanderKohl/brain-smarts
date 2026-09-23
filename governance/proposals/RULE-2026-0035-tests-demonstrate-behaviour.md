---
id: RULE-2026-0035
title: Tests demonstrate behaviour
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0035
owner: brain-owner
created: 2026-09-14T21:26:19+10:00
updated: 2026-09-15T00:45:46+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T00:45:46+10:00
implemented_at: 2026-09-15T00:45:46+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
related_rules:
  - RULE-2026-0016
  - RULE-2026-0028
supersedes: []
---

# RULE-2026-0035: Tests demonstrate behaviour

## Plain-language summary

In every development project, tests exist to prove that required behaviour works, not merely to
exercise the code that was written. Before or while implementing a change the agent identifies
the important behaviours, invariants, edge cases and failure conditions, then makes sure tests
cover them. A bug fix adds a test that would have failed before the fix. A passing suite is not
evidence that new behaviour is covered unless a test actually asserts it. Tests should survive a
change to the internal implementation.

This does not change `/CONTRACT.md`.

## Current problem

No root rule says anything about tests in product code. `RULE-2026-0016` governs the data used
in fixtures. The product-development skill's process reference defines a test strategy at
Gates 5 and 6 (`shared/skills/product-development/references/process.md`), but that applies
only when work runs at standard or high-assurance depth, and the reference is operational
detail that `RULE-2026-0028` says may not carry mandatory semantics on its own.

The observable result across the product nodes is uneven. one client form project records
tests being added routinely; a CRM documentation project and a client API project log barely
mention them. Nothing today prevents an agent from reporting "the suite is green" as proof that a
changed behaviour works when no test asserts that behaviour.

## Current wording

None. This is a new root rule.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0034` (or after the last accepted rule in this set) and
before the contract-restatement list:

```markdown
## RULE-2026-0035 – Tests demonstrate behaviour

- In every software or development project, tests must prove that the required behaviour
  works, not merely exercise the implementation. For each change, identify the important
  behaviours, invariants, boundary cases and failure conditions first, then make sure tests
  cover them.
- When fixing a bug, add a test that would have failed before the fix, wherever practical. If it
  is not practical, say so in the change and why.
- Include negative and boundary cases where they materially affect correctness: the empty input,
  the missing permission, the second tenant, the failed external call.
- Prefer tests that remain valid if the internal implementation changes. Assert on observable
  behaviour and outputs, not on private structure or call sequences.
- Do not report an existing green suite as evidence for new or changed behaviour unless a test
  actually asserts that behaviour. State what the tests prove and what they do not.
- Fixture and sample data remain subject to `RULE-2026-0016`: entirely fictional.
- Proportion applies. Clearly non-material changes as defined in `RULE-2026-0028` need no new
  test; a behavioural change always does.
```

At implementation time only, update `/RULES.md` metadata and add `0035` to the root-ID inventory
in the same manner as `RULE-2026-0033`.

No existing rule is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

The owner's supplied development principles include "make tests demonstrate behaviour". It is
the one heading with no root coverage at all and the one whose absence is easiest to hide: a
green suite looks the same whether or not it covers the change. Putting the requirement at root
makes it apply on the light path and in every node, not only where the product-development
process happens to run at full depth.

## Scope and behavioural consequences

- Applies to all software and development projects governed by this brain, including external
  app repositories worked from this brain.
- Agents will name the behaviours a change must preserve or add before implementing, add tests
  for them, and report what the tests prove rather than reporting a pass count.
- Bug fixes carry a regression test by default. The exception must be stated, not silent.
- No change to how tests are run or which frameworks are used; each project keeps its own.

## Risks and conflicts

- "Wherever practical" could be over-used to skip tests. The second bullet requires the reason to
  be stated, which makes the skip visible in the change and the log.
- Projects with no test harness at all (some early prototypes) cannot comply immediately. For
  them the first behavioural change under this rule should establish a minimal harness or record
  a task to do so; this is a migration note, not an exemption.
- No conflict with the product-development process reference; that reference already asks for
  the same thing at standard depth and this rule makes it binding at every depth for behavioural
  changes.

## Migration

None retroactively. Existing untested behaviour is not required to gain tests because this rule
becomes active. Apply it to new work and to any change that already touches the affected
behaviour.

## Rollback

Remove the `RULE-2026-0035` section from `/RULES.md`, remove `0035` from its root-ID inventory,
restore the prior `accepted_proposal` metadata, and mark this proposal `reverted`.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require the same error count as before the change.
3. Confirm the live root rule exactly matches the accepted wording and no other rule changed.
4. Confirm the root-ID inventory contains `0035` once.

## Acceptance

**Question asked:** Do you accept `RULE-2026-0035` with exactly the wording in its proposal?

**Accepted by the owner, 2026-09-15T00:45:46+10:00**, in the words "I accept RULE-2026-0033 and 0034 and 0035",
answering the three per-proposal acceptance questions by ID.

## Implementation record

Implemented 2026-09-15T00:45:46+10:00. `RULE-2026-0035` added to `/RULES.md` with the accepted wording
unchanged, placed after `RULE-2026-0032` in numeric order and before the contract-restatement
list. `0035` appended to the root ID list; `accepted_proposal` now reads `RULE-2026-0035`
(the last of the three rules accepted together). `contract_version` unchanged at 0.9.0 – a root
rule, not contract behaviour.

**Validation:** see the brain-development log entry for 2026-09-15T00:45:46+10:00.
