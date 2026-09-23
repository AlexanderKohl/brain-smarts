---
id: RULE-2026-0024
title: Agent name, tool and model in Git checkpoint commit messages
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: superseded
proposal_id: RULE-2026-0024
owner: brain-owner
created: 2026-08-27T12:22:00+10:00
updated: 2026-08-27T12:57:57+10:00
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 0.6.2
new_contract_version: 0.6.2
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
supersedes: []
superseded_by: RULE-2026-0017
---

# RULE-2026-0024: Agent name, tool and model in Git checkpoint commit messages

## Plain-language summary

Checkpoint commits already require a concise message. This proposal adds what that message must identify:

1. the host/tool and model actually in use, written the way a person would name them (for example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`);
2. the specific bot name as well, when the agent has one (for example `Test Bot`).

Do not invent a model or version. Omit only the part that is genuinely unknown. Existing commits are left unchanged. `/RULES.md` is not edited until this proposal is explicitly accepted.

## Current problem

`RULE-2026-0017` tells agents to commit with a concise message, but not which agent, tool or model produced the change. In a shared repository used from several hosts, commit history cannot tell `Test Bot` on Grok Bot apart from Claude Code in VS Code.

The first draft of this proposal required only the bot name. The owner held that draft and asked that tool and model always be included, with bot name added when one exists.

## Current wording

Root `/RULES.md` checkpoint bullet:

At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.

## Proposed exact diff

In `/RULES.md`, change only the checkpoint commit-message sentence:

```diff
- At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.
+ At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message that always includes the host/tool and model in use (for example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a specific bot name, that name as well. Do not invent a model or version. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.
```

At implementation time only, update `/RULES.md` metadata:

```diff
-updated: 2026-08-26T20:12:25+10:00
+updated: <implementation timestamp in ISO 8601 with the owner's offset>
 owner: the owner
-accepted_proposal: RULE-2026-0023
+accepted_proposal: RULE-2026-0024
```

No other Git checkpoint bullet is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

Make agent-authored commits attributable to the named bot (when one exists) and to the actual host/tool and model, without adding process, tooling, or a new checkpoint type.

## Scope and behavioural consequences

- Applies to every Git checkpoint commit in every repository modified during an owner-authorised task.
- Tool and model are required in the message. A specific bot name is required only when the agent has one.
- Do not invent a model name or version; omit only the unknown part rather than guessing.
- Host or product names alone are not a substitute for the model when the model is known.
- Does not require rewriting historical commits.
- Does not change when checkpoints occur, what may be staged, or secret/unrelated-change safeguards.
- Does not change `/CONTRACT.md`; behavioural contract version remains `0.6.2`.

## Risks and conflicts

- Some hosts do not expose a stable user-facing model string; agents must then include the known tool name and omit the unknown model rather than inventing a version.
- A verbose label could crowd a short subject; keep the rest of the message concise.
- This rule covers the commit message only. It does not change `git log` author identity.

## Migration

1. After acceptance, apply only the accepted sentence change and metadata update to `/RULES.md`.
2. Begin using named commit messages on the next checkpoint.
3. Do not rewrite existing commits.

## Rollback

Restore the previous commit-message sentence and `accepted_proposal` on `/RULES.md`. Do not rewrite commits created while the rule was active.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require a pass except for clearly identified unrelated pre-existing warnings.
3. Confirm only the accepted sentence and metadata changed in `/RULES.md`.
4. Confirm the next agent-owned checkpoint commit message includes tool and model, and the bot name when one exists.

## Acceptance

Owner accepted the proposed commit-message wording on 2026-08-27T12:57:57+10:00, and directed that it be implemented as an in-place amendment of `RULE-2026-0017` rather than as this new rule number. This proposal is **superseded** by that `0017` amendment and is not active governance.

## Implementation record

Not applied as `RULE-2026-0024`. Wording implemented under `RULE-2026-0017` on 2026-08-27T12:57:57+10:00.
