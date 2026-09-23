---
id: RULE-2026-0004
title: Formal Task Conversion And Token-Efficient Operation
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
owner: brain-owner
created: 2026-08-05T08:30:00+10:00
updated: 2026-08-05T08:33:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-05T08:33:00+10:00
implemented_at: 2026-08-05T08:33:00+10:00
previous_contract_version: 0.3.0
new_contract_version: 0.3.0
target_files:
  - /RULES.md
  - /memory/tasks/RULES.md
---

# Formal Task Conversion And Token-Efficient Operation

## Status

Accepted and implemented from the owner's explicit acceptance of the exact diffs shown below for both target files, obtained before either live file was changed, at 2026-08-05T08:33:00+10:00.

## Current problem

Two gaps identified by the owner in this interaction:

1. Outstanding work currently accumulates in two disconnected places: formal records under `/tasks/open/` and informal "Active priorities" / "Active work" notes inside individual projects' `STATE.md` files (e.g. `projects/brain-development/STATE.md`, `projects/credential-management/STATE.md` and several client project and sub-project `STATE.md` files). An owner who wants a single place to see everything outstanding must currently check both `/tasks/open/` and every project `STATE.md`, which contradicts the repository's own "one canonical home for every durable item" principle already in `/RULES.md`.
2. Neither `/RULES.md` nor any inherited rule instructs agents to read and prompt minimally, or to structure repository content so it can be read in small, targeted pieces. Nothing currently discourages loading whole large files or unrelated context when a small, targeted read would do, which affects token usage and response latency for every future agent session.

## Current wording

`/RULES.md`, "Repository rules" section, relevant excerpt before this change:

```markdown
- Use one canonical home for every durable item.
- Prefer links and dependencies over copies.
- Keep metadata minimal, explicit and useful.
- Preserve raw files unchanged.
```

`/tasks/RULES.md`, full current content of the rule list:

```markdown
- Use one canonical task record.
- Use one owner.
- Do not store a separate follow-up owner.
- Use `waiting_on` to identify the external dependency.
- Use `next_review` to tell the system when to surface waiting or scheduled work.
- Do not create a task for work completed immediately.
- Link tasks to all relevant projects.
- Move completed and cancelled tasks to `/tasks/completed/`.
- Update related project state when completion changes current reality.
```

## Proposed wording or exact diff

Insert into `/RULES.md`, "Repository rules" section, between the existing `Keep metadata minimal, explicit and useful.` and `Preserve raw files unchanged.` bullets:

```markdown
- Read and prompt with only the minimum context relevant to the current task; avoid loading unrelated files, restating unchanged context, or repeating information already available elsewhere.
- Structure nodes, files and skills so related content can be read independently in small, targeted pieces; split large or mixed-purpose files where that measurably improves token efficiency and response time.
```

Insert into `/tasks/RULES.md`, immediately after the existing `Do not create a task for work completed immediately.` bullet:

```markdown
- Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record under `/tasks/open/` once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
```

## Reason

1. Restores the repository's own "one canonical home" principle to outstanding work: an owner (or agent) should be able to see everything open by looking at `/tasks/open/` alone, instead of also scanning every project `STATE.md` for informally tracked priorities.
2. Reduces unnecessary token consumption and response latency across future sessions by making minimal, targeted reading a default operating habit, and by encouraging repository content to be structured so it can be consumed in small pieces rather than requiring whole large files to be read for a narrow question.

## Scope and behavioural consequences

- `/RULES.md` change applies repository-wide to every agent and node; it changes agent reading/prompting behaviour, not repository structure by itself. It does not mandate any specific file-size limit or immediate restructuring of existing nodes; it directs preference and future decisions (including the still-open `TASK-2026-0001` work on node/shared boundaries) toward efficiency-aware structuring rather than dictating exact thresholds now, consistent with `projects/brain-development/RULES.md`'s existing instruction to "test rules against real work before expanding metadata."
- `/tasks/RULES.md` change applies to `/tasks/` only. Going forward, when an agent or the owner identifies or updates an informal "Active priorities"-style item in any project `STATE.md`, the agent should also create or update a matching task record under `/tasks/open/` (using the existing `tasks/templates/TASK_TEMPLATE.md`) referencing that project via `project_refs`, rather than leaving it only in `STATE.md`.
- This does not retroactively require converting every existing informal item immediately in this same change; it establishes the rule going forward. The owner may separately ask for the current informal items (already listed earlier in this conversation) to be converted now as a distinct follow-up action, in which case a batch of new task records would be created (this is ordinary task creation, not itself a protected-governance change, so it would not require a separate proposal).
- No `/CONTRACT.md` behavioural change; `contract_version` remains `0.3.0`.

## Risks and conflicts

- Risk of task-record sprawl if every minor informal note is converted into a task. Mitigated by the qualifier "once it represents real outstanding work" and by the existing `/tasks/RULES.md` rule "Do not create a task for work completed immediately."
- The token-efficiency bullets are directional principles, not enforceable thresholds; they could be read inconsistently by different agents. Accepted as a reasonable first step; `TASK-2026-0001` remains the place where concrete node/file-splitting thresholds get tested and validated before any stricter rule is proposed.
- No conflicts identified with existing rules in `/RULES.md`, `/tasks/RULES.md`, or `projects/brain-development/RULES.md`.

## Migration

No historical content migration is required by this proposal itself. Converting the specific informal items already identified in this conversation into task records is a separate, ordinary (non-governance) action the owner can request next.

## Rollback

Revert the two added bullets in `/RULES.md` and the one added bullet in `/tasks/RULES.md` as one version-control change; mark this proposal `reverted` and record the reason.

## Validation

- run `/shared/skills/repository-preflight/scripts/preflight.py`
- confirm both `/RULES.md` and `/tasks/RULES.md` still parse correctly and are not flagged as uncovered protected-governance changes
- inspect the complete diff for both target files against the wording shown above

## Acceptance

The owner explicitly accepted the exact diffs shown above for `/RULES.md` and `/tasks/RULES.md` in this proposal (`RULE-2026-0004`) at 2026-08-05T08:33:00+10:00, before either live file was changed.

## Implementation record

- Applied the two accepted bullets verbatim to `/RULES.md`, "Repository rules" section, between "Keep metadata minimal, explicit and useful." and "Preserve raw files unchanged." (2026-08-05T08:33:00+10:00).
- Applied the one accepted bullet verbatim to `/tasks/RULES.md`, immediately after "Do not create a task for work completed immediately." (2026-08-05T08:33:00+10:00).
- Logged the owner's acceptance and the applied change in `/LOG.md` and `/tasks/LOG.md`.
- Ran the repository preflight validator and confirmed both target files remain covered by this proposal's `target_files`.
- Converted the informal open items already identified in this conversation into formal task records under `/tasks/open/` as a separate, ordinary (non-governance) follow-up action, per the "Migration" section above.
