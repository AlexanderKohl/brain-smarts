---
id: PROPOSAL-raise-ambition-for-every-user
title: Raise the ambition of every request
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-23T07:37:45+10:00
updated: 2026-10-23T08:06:02+10:00
rule_id: SMART-RULE-0044
accepted_by: brain-owner
accepted_at: 2026-10-23T08:06:02+10:00
implemented_at: 2026-10-23T08:06:02+10:00
previous_contract_version: 2.7.0
new_contract_version: 2.7.0
target_files:
  - /RULES.md
  - /shared/skills/README.md
  - /library/skills/raise-ambition/SKILL.md
  - /library/skills/README.md
---

# Raise the ambition of every request

Read `/CONTRACT.md` first.

## Plain-language summary

Every agent working in the brain checks each request for a bigger version – an outcome kept true
instead of a task done once, an expert's methods and a harder target, or other fields and roles
brought in – and offers it as the first, recommended option whenever it asks a clarifying
question. Nothing is widened without the user's yes. The method is the skill `raise-ambition`,
which moves from the skill library to the core skills because a mechanics rule now requires it
(CONTRACT §3.4).

## Current problem

People ask models for far less than the models can do: the task in front of them rather than
the outcome behind it. A skill alone is used only when an agent chooses to; a rule in `/RULES.md`
is read at every bootstrap (CONTRACT §1), so it applies to every request in every brain that adopts
the mechanics.

## Current wording

None. The highest identifier in the `/RULES.md` index is `SMART-RULE-0043`.

## Proposed wording

A new row in the `/RULES.md` index:

```markdown
| `SMART-RULE-0044` | Raise the ambition of every request | this file; `/shared/skills/raise-ambition/` |
```

and a new section in `/RULES.md`:

```markdown
## SMART-RULE-0044 – Raise the ambition of every request

- At the intake of every request, the agent applies `/shared/skills/raise-ambition/`: it names
  the outcome behind the request and checks whether a bigger version would serve the user better
  – one that reaches higher (an outcome kept true, not a task done once), deeper (an expert's
  methods and a harder, measurable target) or wider (other fields and roles, including an
  adversarial reviewer). The user is the person whose request it is: the owner, or a
  collaborator working in a shared project.
- When a bigger version would serve the user better, the agent's clarifying question offers it
  as option 1, marked recommended, with what it would take; the request as asked is option 2.
  When no question is otherwise needed, the agent does what was asked and adds one line naming
  the bigger version.
- The agent never widens the work without the user's yes, does not repeat a bigger version the
  user declined for the same request, and keeps the suggestion to a few lines. Safety, cost,
  side-effect and governance rules are unchanged.
```

## Other changes in the same set

- `/library/skills/raise-ambition/` moves to `/shared/skills/raise-ambition/` (a core skill: a
  `SMART-RULE` requires it), with `scope: core` and its `canonical_source` updated; both skill
  indexes are updated.
- Its wording says "the user" where it said "the owner", defined as in the rule.
- `raise-ambition` leaves `active_skills` in `/memory/OWNER.md`, since core skills are always on.
- The owner-layer draft `PROPOSAL-raise-ambition` in `/memory/governance/proposals/` is withdrawn
  in favour of this one.

## Reason

The owner asked on 23 October 2026 that the brain always guide its users towards more ambitious
requests, and that this be a public brain rule rather than an owner preference, because it serves
any owner.

## Scope and consequences

Every agent in every brain that adopts the mechanics. Replies gain at most a few lines: the bigger
version as option 1 of a question, or a one-line note. Trivial requests get nothing.

## Risks and conflicts

- Scope creep or noise: contained by the "never without the user's yes", "once per request" and
  "a few lines" clauses.
- Cost: a bigger version may need more allowance or money; the skill requires the cost to be
  stated.
- `SMART-RULE-0010` (communication efficiency): compatible – the suggestion rides inside a
  question that is asked anyway, or is one line.

## Migration

The skill folder moves between repositories (library to mechanics) and each repository commits its
side. No data migration.

## Rollback

Delete the `SMART-RULE-0044` section and its index row, move the skill back to the library (or
delete it), and log the withdrawal. The number `0044` is not reused.

## Validation

Repository preflight on the mechanics, library and memory, including the personal-data check on
the moved skill; then the next three requests are checked for an offered bigger version where one
exists, and the outcome is recorded as a learning under `SMART-RULE-0028`.
