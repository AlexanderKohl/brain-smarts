---
id: PROPOSAL-model-in-a-trailer
title: When a host forbids the model in the commit subject, a trailer carries it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-01T10:52:46+10:00
updated: 2026-10-01T10:52:46+10:00
rule_id: SMART-RULE-0009
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /RULES.md
---

# When a host forbids the model in the commit subject, a trailer carries it

Read `/CONTRACT.md` first.

## Summary

A small amendment to `SMART-RULE-0009`, same identifier. Every commit names the host and the model.
Some hosts forbid model names in commit subjects; a session there names the host in the subject and
the model in a trailer of the same commit, which those hosts add or allow. The rule today gives no
way to comply in such a host.

- **For agents:** in such a host, `Claude Code web: …` as the subject and
  `Co-Authored-By: <model> <address>` as a trailer satisfy the rule.
- **For the owner:** every commit still says which model made it; a few say it in the trailer.

## Current problem

On 30 September 2026 a cloud session's host forbade model names in commits. It wrote the host in
each subject (`Claude Code web: …`) and the model only in the `Co-Authored-By` trailer, and said
that this departs from `SMART-RULE-0009`. The owner agreed the rule should allow it (1 October 2026).

## Current wording

From the fifth bullet of `SMART-RULE-0009`:

> … and commit with a concise message that always includes the host/tool and model in use (for
> example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a
> specific bot name, that name as well. Do not invent a model or version. …

## Proposed wording

> … and commit with a concise message that always includes the host/tool and model in use (for
> example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a
> specific bot name, that name as well. When the host forbids the model in the subject, the subject
> names the host and a trailer of the same commit names the model (for example
> `Co-Authored-By: <model> <address>`); a host that forbids both is named in the final response.
> Do not invent a model or version. …

## Reason

The rule's purpose is that each commit says which tool and model made it. A trailer is part of the
commit and shows in `git log`; it serves the purpose where the subject cannot.

## Scope and behavioural consequences

Commits in hosts that forbid model names in subjects. No change anywhere else.

## Risks and conflicts

- Tools that read the model from the subject alone (the learning records count writers from commit
  subjects) miss these commits' model; they read the trailer too when it matters.
- No conflict with an active rule.

## Migration

None. Earlier commits keep their messages.

## Rollback

Remove the added sentence.

## Validation

The repository preflight passes. The next cloud session's commits are checked for the host in the
subject and the model in a trailer.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal.

## Implementation record

None.
