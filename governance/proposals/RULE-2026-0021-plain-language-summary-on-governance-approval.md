---
id: RULE-2026-0021
title: Require plain-language summary when requesting governance approval
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0021
owner: brain-owner
created: 2026-08-12T10:20:35+10:00
updated: 2026-08-12T10:37:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-12T10:36:37+10:00
implemented_at: 2026-08-12T10:36:37+10:00
verified_at: 2026-08-12T10:37:00+10:00
previous_contract_version: 0.6.1
new_contract_version: 0.6.2
target_files:
  - /CONTRACT.md
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0021: Plain-language summary on governance approval requests

## Status

**Verified.** the owner explicitly accepted this proposal with “yes” at 2026-08-12T10:36:37+10:00. Exact CONTRACT §13.2 diff applied; `contract_version` is `0.6.2`. Repository preflight passed at 2026-08-12T10:37:00+10:00.

## Current problem

When agents request owner acceptance of a protected governance or rule change, they sometimes present only exact diffs or technical proposal text. The owner asked for a durable preference: always include a plain-language summary of the changes when requesting approval, so the decision can be made without reading the full diff first.

## Exact diffs (protected)

### A. `/CONTRACT.md` §13.2 – extend “Before requesting acceptance, present:”

**Current:**

```markdown
Before requesting acceptance, present:

1. a stable proposal ID
2. the current and proposed wording or exact diff
3. the reason for the change
4. the affected scope and expected behavioural consequences
5. risks, conflicts and migration requirements
6. a rollback method
7. the planned validation
```

**Proposed:**

```markdown
Before requesting acceptance, present:

1. a stable proposal ID
2. a plain-language summary of the changes (what will be different for the owner and agents), stated before or alongside the exact diffs
3. the current and proposed wording or exact diff
4. the reason for the change
5. the affected scope and expected behavioural consequences
6. risks, conflicts and migration requirements
7. a rollback method
8. the planned validation
```

Also set front matter `contract_version: 0.6.2` and update `updated` on acceptance.

## Reason

Owner preference stated when accepting `RULE-2026-0020`: always give a summary of the changes when requesting approval of a rule change.

## Scope and behavioural consequences

- Every protected-governance acceptance request must lead with (or clearly include) a short plain-language summary, not only raw diffs.
- Exact diffs remain required; the summary does not replace them.
- No change to acceptance standards (explicit acceptance of the identified proposal or exact change set is still required).

## Risks / conflicts / migration

- Low risk. Slightly longer approval prompts. No content migration.

## Rollback

Revert `/CONTRACT.md` §13.2 list and restore `contract_version` to `0.6.1`.

## Planned validation

1. Apply only the accepted diff.
2. Confirm §13.2 includes the plain-language summary requirement.
3. Run repository preflight.
4. Report result.

## Acceptance

the owner explicitly accepted with “yes” at 2026-08-12T10:36:37+10:00, authorising the CONTRACT §13.2 summary requirement and the contract-version increase from `0.6.1` to `0.6.2`.

## Implementation record

Accepted change applied to `/CONTRACT.md` on 2026-08-12T10:36:37+10:00. `contract_version` is `0.6.2`.

Full repository preflight passed at 2026-08-12T10:37:00+10:00 (`contract_version` `0.6.2`; 2344 Markdown files; 0 errors). Proposal status → **verified**.
