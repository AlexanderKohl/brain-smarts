---
id: RULE-2026-0038
title: Task state enumerates every open task
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-15T08:45:00+10:00
updated: 2026-09-15T08:50:00+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T08:50:00+10:00
implemented_at: 2026-09-15T08:50:00+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /memory/tasks/RULES.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/SKILL.md
project_refs:
  - /memory/projects/brain-development
---

# Task state enumerates every open task

## Current problem

`/tasks/STATE.md` named eight of twenty open tasks on 2026-09-15, and one of those eight with a
different status word than its record (`TASK-2026-0019`). The audit that found this
(`TASK-2026-0034`) asked whether the file is meant to list every open task or only recent
ones. The owner decided: every open task.

The file was regenerated the same day to that standard. Without a rule and a validator check
it will drift again, because nothing today says the file must be complete or that its status
words must match the records.

## Current wording

`/tasks/RULES.md` has no bullet about `STATE.md` completeness. The preflight validator checks
task status values and `next_review` presence, not the state file.

## Proposed wording or exact diff

Add to `/tasks/RULES.md`, after the bullet that begins "Convert an informal open item":

```markdown
- `/tasks/STATE.md` enumerates every record under `/tasks/open/`: one entry per task carrying
  its ID and the status word from its front matter. Update the entry when the record changes
  and remove it when the record moves to `/tasks/completed/`. A task absent from the file, or
  listed with a different status word than its record, is a defect to fix in the same turn.
```

Add to the preflight validator: for every `type: task` record under `/tasks/open/`, fail when
`/tasks/STATE.md` does not contain the task ID, or contains it without the record's status word
appearing on the same line. Document the check in the preflight `SKILL.md` failure behaviour.

## Reason

One place that lists all outstanding work is the point of a central task store (CONTRACT §9).
A partial list is worse than none, because a reader trusts it. Making the check reproducible in
the validator follows the established principle that invariants should not rely on agent
judgement alone.

## Scope and behavioural consequences

Every agent that creates, changes or completes a task also touches `/tasks/STATE.md` in the
same turn, and preflight fails when it does not. Small extra work per task change; no change to
task semantics. No `contract_version` change: node rule plus validator, not contract behaviour.

## Risks and conflicts

- **Merge noise.** Every task change edits one shared file. Accepted: the file is small and
  line-oriented.
- **Status-word matching is textual.** The check looks for the status word on the ID's line;
  prose that mentions another status on the same line could pass wrongly. Mitigated by the
  table layout with the status in its own column.
- No conflict with `RULE-2026-0004` (the file stays one line per task) or with the existing
  informal-item conversion bullet, which it complements.

## Migration

None. `/tasks/STATE.md` already meets the standard as of 2026-09-15T08:45:00+10:00.

## Rollback

Remove the bullet from `/tasks/RULES.md`, remove the validator check, set this proposal to
`reverted`. The state file may stay complete.

## Validation

- Preflight passes on the regenerated state file before activation, and fails on a fixture
  where one open task is missing after the check is added.
- Preflight before and after activation reports the same error count.

## Acceptance

**Question to ask:** Do you accept proposal `RULE-2026-0038`, adding the bullet to
`/tasks/RULES.md` and the matching preflight check as set out above?

Asked as: 1. Accept as written (recommended); 2. accept the rule bullet only; 3. reject.
**Accepted by the owner, 2026-09-15T08:50:00+10:00**, with the answer "RULE-2026-0038 1".

## Implementation record

Implemented 2026-09-15T08:50:00+10:00. Bullet added to `/tasks/RULES.md` after the informal-item conversion
bullet, wording unchanged. Preflight `validate_tasks` now fails when an open task is absent from
`/tasks/STATE.md` or listed without its status word; documented in the preflight `SKILL.md`.
Negative checks run at implementation: removing one row and changing one status word each made
preflight fail with the expected message; the restored file passes. Contract version unchanged
at 0.9.0. Manifest regenerated.
