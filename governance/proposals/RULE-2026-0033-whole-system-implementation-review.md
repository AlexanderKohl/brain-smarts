---
id: RULE-2026-0033
title: Whole-system implementation review
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0033
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
  - RULE-2026-0025
  - RULE-2026-0029
  - RULE-2026-0030
supersedes: []
---

# RULE-2026-0033: Whole-system implementation review

## Plain-language summary

In every development project, an agent optimises for the health of the whole system, not only for
finishing the immediate task. Before introducing a new pattern, abstraction, dependency or data
flow it checks how the codebase already solves that problem and reuses or extends it. When a new
approach is genuinely needed, it says why and whether existing code should later converge on it.
When a requirement conflicts with an existing architectural decision, it surfaces the conflict
instead of quietly creating an exception. Before reporting a non-trivial change as complete, it
answers a short review checklist from the perspective of the whole repository.

This is the architecture-level counterpart of `RULE-2026-0025` (UI patterns) and `RULE-2026-0030`
(code paths and side effects), and it generalises `RULE-2026-0029` (external configuration
conflicts) to conflicts inside the codebase. It does not change `/CONTRACT.md`.

## Current problem

The live development rules were each minted after a specific incident and cover specific
surfaces: `RULE-2026-0025` covers UI elements, `RULE-2026-0030` covers duplicated functions and
writers, `RULE-2026-0029` covers mismatches in an external system's configuration. Nothing
requires an agent to check the wider codebase before introducing a new **pattern**,
**abstraction**, **dependency** or **data flow**, and nothing requires it to surface a conflict
with an existing architectural decision inside the project. The product-development skill checks
architecture at its gates, but a gate review happens once per increment, not once per
implementation, and the light path has no such step at all.

`/CONTRACT.md` §15 gives the brain repository a completion checklist. Code changes in product
repositories have none. The default is therefore local optimisation: the change that makes the
immediate feature easiest, at the cost of a second way of doing something elsewhere.

The owner supplied a set of development principles on 2026-09-14 (whole-system optimisation,
architectural coherence, low technical debt, clarity, and a ten-question review before
completion). This proposal carries the parts of those principles that no live rule covers.

## Current wording

None. This is a new root rule. `RULE-2026-0030` already covers duplication, single-use
abstractions, dead code and removal of superseded paths; that wording is not restated here.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0032` and before the contract-restatement list:

```markdown
## RULE-2026-0033 – Whole-system implementation review

- In every software or development project, optimise each change for the health of the whole
  system, not only for completing the immediate task. Evaluate it against upstream and downstream
  code, shared services, data models, APIs, workflows, state transitions and integrations.
- Before introducing a new pattern, abstraction, service, dependency or data flow, check how the
  project already solves the same problem and reuse or extend that approach where it remains
  appropriate. When a new approach is genuinely required, state the reason in the change and
  say whether existing related implementations should later converge on it.
- Leave the architecture simpler after the change, or at minimum no more complex than the
  requirement demands. Prefer the smallest clear implementation that fully satisfies it.
- When a requirement conflicts with an existing architectural, product or data-model decision,
  surface the conflict to the owner and resolve it deliberately. Do not quietly create an
  exception. This extends `RULE-2026-0029` from external configuration to decisions inside the
  codebase.
- When a workaround or compromise is unavoidable, make it visible in the code and the project
  record, and state what would be required to remove it.
- Keep code understandable to another capable engineer or agent without reconstructing hidden
  assumptions: explicit data flows, clear responsibilities, predictable naming, straightforward
  control flow, focused modules. Do not use cleverness where a simpler implementation gives the
  same result.
- Before reporting a non-trivial change complete, review it from the perspective of the whole
  repository and state, briefly, the answers to: Does it follow the strongest existing pattern
  for this problem? Has it introduced a second way of doing something that already has one? Does
  it conflict with an architectural, product or data-model decision elsewhere? Can any obsolete
  code now be removed? Has it made the system easier or harder to maintain? Clearly non-material
  changes as defined in `RULE-2026-0028` may skip this review.
```

At implementation time only, update `/RULES.md` metadata and the root-ID inventory:

```diff
-updated: 2026-09-12T14:00:00+10:00
+updated: <implementation timestamp in ISO 8601 with the owner's offset>
 owner: the owner
-accepted_proposal: RULE-2026-0032
+accepted_proposal: RULE-2026-0033
```

```diff
-Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`, `0029`, `0030`, `0032`.
+Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`, `0029`, `0030`, `0032`, `0033`.
```

If `RULE-2026-0034` or `RULE-2026-0035` are accepted in the same sitting, the inventory line and
`accepted_proposal` are updated once with the last accepted ID.

No existing rule is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

The owner asked whether the development rules capture whole-system optimisation and, on review,
they cover only the surfaces where an incident has already happened. A root rule makes the
general principle binding before the next incident rather than after it. The completion review is
the most actionable part of the supplied principles and the only mechanism that catches local
optimisation at the moment it is cheapest to fix.

## Scope and behavioural consequences

- Applies to all software and development projects governed by this brain, including external
  app repositories worked from this brain.
- Agents will search for an existing pattern before adding one, will name the reason for any new
  approach, and will put architectural conflicts to the owner instead of working around them.
- Non-trivial changes end with a short whole-system review. The review is five one-line answers,
  not a document. The light path in `RULE-2026-0028` is unaffected for clearly non-material work.
- `RULE-2026-0025`, `RULE-2026-0029` and `RULE-2026-0030` remain in force and are referenced, not
  restated.

## Risks and conflicts

- The completion review can become ceremony if applied to every trivial edit. The last bullet
  bounds it to non-trivial changes using the existing `RULE-2026-0028` definition.
- "Surface the conflict" can slow work when the owner is unavailable. `RULE-2026-0029` already
  sets the pattern: continue with everything that does not depend on the answer.
- Partial overlap with `RULE-2026-0030` (smallest implementation, obsolete code). The overlap is
  deliberate and one-directional: this rule points at 0030 for the detail rather than repeating
  it.

## Migration

None. Existing architecture is not retroactively reviewed because this rule becomes active. Apply
it to new work and to any change that already touches the affected area.

## Rollback

Remove the `RULE-2026-0033` section from `/RULES.md`, remove `0033` from its root-ID inventory,
restore the prior `accepted_proposal` metadata, and mark this proposal `reverted`.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require the same error count as before the change
   (the documented pre-existing baseline).
3. Confirm the live root rule exactly matches the accepted wording and no other rule changed.
4. Confirm the root-ID inventory contains `0033` once.

## Acceptance

**Question asked:** Do you accept `RULE-2026-0033` with exactly the wording in its proposal?

**Accepted by the owner, 2026-09-15T00:45:46+10:00**, in the words "I accept RULE-2026-0033 and 0034 and 0035",
answering the three per-proposal acceptance questions by ID.

## Implementation record

Implemented 2026-09-15T00:45:46+10:00. `RULE-2026-0033` added to `/RULES.md` with the accepted wording
unchanged, placed after `RULE-2026-0032` in numeric order and before the contract-restatement
list. `0033` appended to the root ID list; `accepted_proposal` now reads `RULE-2026-0035`
(the last of the three rules accepted together). `contract_version` unchanged at 0.9.0 – a root
rule, not contract behaviour.

**Validation:** see the brain-development log entry for 2026-09-15T00:45:46+10:00.
