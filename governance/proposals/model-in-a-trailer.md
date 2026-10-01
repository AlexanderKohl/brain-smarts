---
id: PROPOSAL-model-in-a-trailer
title: The tool and the model go in a commit's trailers, never its subject
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-01T10:52:46+10:00
updated: 2026-10-01T12:07:12+10:00
rule_id: SMART-RULE-0009
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.3.0
new_contract_version: 2.3.0
target_files:
  - /RULES.md
  - /shared/skills/repository-preflight/scripts/hooks.py
  - /shared/skills/repository-preflight/SKILL.md
---

# The tool and the model go in a commit's trailers, never its subject

Read `/CONTRACT.md` first.

## Summary

An amendment to `SMART-RULE-0009`, same identifier. Revised on 1 October 2026 at the owner's
question "wouldn't it be easier to say never put it in the subject and always in the trailer?":
yes. Every commit names its tool and model in two trailers, in every host, and the subject says only
what changed. The commit-message hook checks it.

- **For agents:** one form everywhere. Claude Code already adds the model's trailer itself; the
  agent adds `Tool:`. No guessing which host allows what.
- **For the owner:** shorter subjects. The tool and model no longer show in a one-line history or
  in GitHub's commit list; `git log` shows them under each commit, and
  `git log --format="%h %s – %(trailers:key=Tool,valueonly,separator=%x2C)"` puts them on one line.

## Current problem

On 30 September 2026 a cloud session's host forbade model names in commits. It wrote the host in
each subject and the model only in the `Co-Authored-By` trailer, which departs from
`SMART-RULE-0009`. A rule that puts the model in the subject cannot be met in such a host, and the
prefix (`Claude Code desktop Opus 5.5: `) takes about 30 characters of every subject. Nothing checks
the rule today.

## Current wording

From the fifth bullet of `SMART-RULE-0009`:

> … and commit with a concise message that always includes the host/tool and model in use (for
> example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a
> specific bot name, that name as well. Do not invent a model or version. …

## Proposed wording

> … and commit with a concise message whose subject says what changed and never names the tool or
> the model. Two trailers of the same commit name them: `Tool: <host or tool>` (for example
> `Tool: Claude Code desktop` or `Tool: Cursor`, with the agent's bot name when it has one) and
> `Co-Authored-By: <model> <address>` (for example
> `Co-Authored-By: Claude Opus 5.5 <the host's no-reply address>`). In the brain's repositories the
> commit-message hook refuses a commit, other than a merge, without both. Do not invent a model or
> version. …

## Reason

One form that every host allows, checked where every commit passes. The owner asked for the simpler
rule.

## Scope and behavioural consequences

- Every commit by an agent in every repository it changes. The hook checks the brain's three
  repositories; a project repository follows the rule without the hook unless it adds one.
- Merge commits (`session.py finish`, `sync.py`) are exempt; they make no change of their own.

## Risks and conflicts

- **History reading:** the one-line view loses the tool and model; the log format above restores it.
- **Earlier commits** keep their subjects; nothing reads the model from subjects today.
- **A commit made by hand by the owner** in a brain repository needs the two trailers too, or the
  hook refuses it; the refusal says what to add.
- No conflict with an active rule.

## Migration

None. The first commit after acceptance uses the new form.

## Rollback

Restore the sentence and remove the hook's check.

## Validation

- Tests: a message without `Tool:` is refused, one without `Co-Authored-By:` is refused, one with both
  passes, a merge passes.
- The repository preflight passes.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal.

## Implementation record

None.
