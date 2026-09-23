---
id: RULE-2026-0030
title: One canonical implementation, no duplicated side effects
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0030
owner: brain-owner
created: 2026-09-10T14:55:00+10:00
updated: 2026-09-10T14:56:00+10:00
accepted_by: brain-owner
accepted_at: 2026-09-10T14:56:00+10:00
implemented_at: 2026-09-10T14:56:00+10:00
previous_contract_version: 0.8.0
new_contract_version: 0.8.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
supersedes: []
---

# RULE-2026-0030: One canonical implementation, no duplicated side effects

## Plain-language summary

In every development project, agents must keep one live way of doing a job. Before adding a
function, write, or extra trip through the system, they look for the code that already does it and
call that. They do not copy the sequence, leave the old writer running beside a new one, or
re-apply the same field/API/state change from a second place "to be safe." When a new path
replaces an old one, the superseded code comes out in the same change.

This is the code counterpart of `RULE-2026-0025` (UI reuse). It does not change `/CONTRACT.md`.

## Current problem

Nothing in the root rules requires agents to collapse duplicate live paths when they add a better
one. The default is to leave the old writer in place. On 2026-09-10, bill session ID in
a client API project was written by the new `writeBillSessionIdsOnUpload` helper **and** by leftover
confirm-details, contact-create, opportunity-create, and a second frontend
`/api/leadconnector/process` call after upload had already done the same work.

The cost is not only extra API calls. Two live writers make it unclear which path is authoritative,
and a later change has to be made in both or they drift.

## Current wording

There is no active repository-wide rule requiring a single canonical implementation for a side
effect. `RULE-2026-0025` covers UI pattern reuse only. CONTRACT §3.3 requires one canonical home
for durable knowledge, not for runtime code paths. `RULE-2026-0029` stops configuration
workarounds; it does not cover duplicated writers of the same field.

## Proposed wording

To be added to `/RULES.md` as a new numbered rule, after `RULE-2026-0029`:

```markdown
## RULE-2026-0030 – One canonical implementation, no duplicated side effects

- In every software or development project, before adding a function, write, call, or extra
  control-flow path, search the active project for an existing implementation that already performs
  the same job.
- Prefer one canonical implementation and call it. Do not copy a working sequence into a second
  place, wrap the old path while leaving it live, or add a new write that repeats an existing
  side effect (the same field, file, API call, or state change).
- When a new path replaces an old one, remove the superseded code in the same change: leftover
  writers, leftover callers, and any second frontend or backend trip that only existed to do the
  same work.
- Extract a shared helper only when two or more live call sites need the same behaviour. Do not
  add an abstraction for a single use, and do not keep both the helper and the inlined original.
- Lean code means fewer live paths, not denser cleverness. Delete dead code. Do not preserve a
  known duplicate "for safety" when the remaining path already covers the cases.
- Distinct later stages may write the same field only when that stage has a different meaning
  (for example a later workflow step that must refresh it). Do not treat a second write at the
  same stage as a backup.
```

At implementation time only, update `/RULES.md` metadata and the root-ID inventory:

```diff
-updated: 2026-09-09T12:30:00+10:00
+updated: <implementation timestamp in ISO 8601 with the owner's offset>
 owner: the owner
-accepted_proposal: RULE-2026-0029
+accepted_proposal: RULE-2026-0030
```

```diff
-Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`, `0029`.
+Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`, `0029`, `0030`.
```

No existing rule is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

The owner asked for a durable rule after the bill-session-ID double-write: keep development-project
code efficient instead of duplicating things, using lean-code practice. A root rule makes that
binding for every project, not a one-off cleanup note.

## Scope and behavioural consequences

- Applies to all software and development projects governed by this brain, including external
  app repos worked from this brain.
- Agents will search for an existing writer before adding another, and will delete superseded
  paths in the same change as the replacement.
- `RULE-2026-0025` remains the UI-pattern rule. This rule covers behaviour, writes, and control
  flow.
- Does not change `/CONTRACT.md`; contract version remains `0.8.0`.

## Risks and conflicts

- Over-collapsing can merge two stages that look similar but mean different things (upload vs a
  later authority or payment step). The last bullet requires a distinct meaning before a second
  write is kept.
- A project with several inconsistent legacy paths needs a chosen canonical one; the first search
  hit is not automatically authoritative. Prefer the path the current feature actually uses.
- Partial overlap with `RULE-2026-0025` (reuse) and CONTRACT §3.3 (canonical home). Those stay;
  this rule is the runtime-code form of the same idea.

## Migration

None. Existing duplicate paths are not retroactively cleaned solely because this rule becomes
active. Apply it to new work and to any change that already touches a duplicated path.

## Rollback

Remove the `RULE-2026-0030` section from `/RULES.md`, remove `0030` from its root-ID inventory, and
restore the prior `accepted_proposal` metadata. Mark this proposal `reverted`.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require a pass except for clearly identified,
   unrelated pre-existing warnings.
3. Confirm the live root rule exactly matches the accepted wording and no other rule changed.
4. Confirm the root-ID inventory contains `0030` once and the metadata names `RULE-2026-0030`.

## Acceptance

Explicitly accepted by the owner on 2026-09-10T14:56:00+10:00 with “accept, push it”, in direct
response to the acceptance question identifying `RULE-2026-0030` and its exact displayed
`/RULES.md` wording.

## Implementation record

Applied the accepted root-rule wording, root-ID inventory and metadata changes to `/RULES.md` on
2026-09-10T14:56:00+10:00. Contract version remains `0.8.0`. Repository preflight reported 11
pre-existing errors (YAML delimiter, `source_refs` anchors, waiting-task `next_review`); none
were introduced by this change.
