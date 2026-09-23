---
id: PROPOSAL-skill-exchange
title: Skill exchange – agents suggest, offer and receive shared skills
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-23T14:00:00+10:00
updated: 2026-09-23T14:00:00+10:00
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 1.0.0
new_contract_version: 1.0.0
target_files:
  - /RULES.md
  - /ONBOARDING_AGENT.md
  - /shared/skills/README.md
  - /shared/skills/skill-exchange/SKILL.md
  - /shared/skills/skill-exchange/scripts/skill_exchange.py
skill_refs:
  - /shared/skills/skill-exchange
  - /shared/skills/learning-maintenance
---

# Skill exchange – agents suggest, offer and receive shared skills

**Draft.** No rule number is claimed: the next free `SMART-RULE` number is assigned on
acceptance (CONTRACT §13.2, *Rule identifiers*), and the rule is written as
`PROPOSAL-skill-exchange` below until then. Depends on `SMART-RULE-0029` (three layers,
`upstream` remote, `active_skills`).

## Summary

Four things become defined behaviour, each ending in a question to the owner rather than an
action:

1. An agent that notices a reusable capability inside one node records it and, at a natural
   checkpoint, suggests promoting it to a shared skill – after a scrub check proves nothing
   personal would leave memory.
2. A promoted skill can be offered to the original mechanics repository as a pull request from
   the owner's own repository, carrying a proposal file, a scrub report and tests.
3. On a cadence (default weekly, checked at session start with one cheap command) the agent
   fetches `upstream`, compares, and tells the owner only what touches their `active_skills`,
   the always-on skills, governance, and new skills. The owner decides what to merge and what
   to switch on.
4. A skill installed from someone else's brain has its source repository and commit recorded
   in `/memory/skills/installed.json`, and a local edit to it is detectable.

Suggestions follow `SMART-RULE-0010` and `SMART-RULE-0028`: batched at checkpoints, numbered with
a recommendation, never repeated without new evidence, never mid-task.

## Current problem

The owner asked whether the skills define how users suggest skills to add, so that each AI
actively suggests skills that might be useful. They do not:

- `/SETUP.md` step H mentions `git fetch upstream; git merge upstream/main` and that
  improvements "can be offered back … as a pull request", but nothing says when an agent
  checks, what it tells the owner, or what a contribution must contain.
- `SMART-RULE-0028` captures learnings, and CONTRACT §3.4 says a mechanism learnt from an owner
  incident goes to the mechanics layer in generalised form – but no rule or skill tells an
  agent to *notice* that a node-local capability has become reusable, and nothing checks for
  personal data before it moves.
- `active_skills` (proposed with `SMART-RULE-0029`) says which optional skills an owner uses,
  but nothing uses it to decide which upstream changes matter.
- Nothing records where an installed skill came from, so an owner cannot later tell whose code
  they are running or whether it was changed locally.

## Current wording

None. `/RULES.md` has no rule on skill exchange; `/ONBOARDING_AGENT.md` has no step for it.

## Proposed wording or exact diff

### 1. `/RULES.md` – a new rule, inserted in number order when the number is assigned

```markdown
## PROPOSAL-skill-exchange – Skill exchange

- **Notice and suggest.** When a node-local capability is used or copied by a second node,
  holds no owner data once its configuration is moved out, or wraps a system other owners use,
  record it as a promotion candidate and suggest promoting it to a shared skill at the next
  natural checkpoint. Procedure: `/shared/skills/skill-exchange/`.
- **Scrub before it leaves memory.** Nothing moves from `/memory/` to the mechanics repository,
  or from the mechanics repository to any other repository, until the skill-exchange scrub
  check reports no hits (CONTRACT §3.4). Allow-listed strings are justified in the commit.
- **Offer, never push.** A contribution to the upstream mechanics repository is a pull request
  from the owner's own repository, carrying a proposal file without a rule number, the scrub
  report and passing tests, opened only after the owner says yes to that contribution.
- **Hear upstream on a cadence.** At session start, when a check is due (default every seven
  days), fetch `upstream` and tell the owner what changed in their `active_skills`, the
  always-on skills, governance and new skills. Merging is the owner's decision; an upstream
  change to protected governance is presented as a proposal (CONTRACT §13.2).
- **Record provenance.** A skill installed from another brain is read in full before it runs,
  and its source repository and commit are recorded in `/memory/skills/installed.json`.
- **Suggest at checkpoints, once.** Suggestions are batched at natural checkpoints (session
  start, end of a unit of work, the weekly review), numbered with a recommendation, capped, and
  not repeated after a decline unless new evidence arrives. The owner may set them to weekly or
  off. A security fix to a skill the owner uses is the one exception and is reported at the
  next response.
```

### 2. `/ONBOARDING_AGENT.md` – one new numbered item after item 16

```markdown
17. **Skill exchange (`PROPOSAL-skill-exchange`):** at session start run
    `python shared/skills/skill-exchange/scripts/skill_exchange.py due`; when it exits 0, run
    `upstream` and keep its digest for the first natural checkpoint. Record reusable
    capabilities with `candidate add` as you notice them. Procedure and etiquette:
    `/shared/skills/skill-exchange/SKILL.md`.
```

and one row in **Shared skills (current)**, alphabetical after `repository-preflight`:

```markdown
| skill-exchange | `/shared/skills/skill-exchange/` | Notice reusable capability and suggest promotion; scrub before anything leaves memory; offer upstream as a pull request; weekly upstream digest filtered by `active_skills`; provenance of installed skills in `/memory/skills/installed.json` |
```

### 3. `/shared/skills/skill-exchange/SKILL.md`

Already written in this change set with `status: proposed` and a "Proposed – not active"
banner. On acceptance: `status: active`, the banner and the `proposal:` field removed.

### 4. `/shared/skills/README.md`

The `skill-exchange/` entry already added reads "Proposed, not active"; on acceptance it drops
that phrase.

## Reason

- The three-layer split makes skills portable between owners; without a defined exchange,
  improvements stay in whichever brain made them and upstream fixes are found by accident.
- Suggestions that are not bounded become noise. Stating the cadence, the cap and the
  no-repeat rule makes "actively suggest" compatible with `SMART-RULE-0010` and the
  *Interrupt only when needed* clause of `SMART-RULE-0028`.
- The scrub check turns CONTRACT §3.4 from a promise into a command with an exit code.
- Provenance answers "whose code is this and did we change it" without trusting memory.

## Scope and behavioural consequences

- **Agents:** one extra cheap command at session start (`due`, no network); one `git fetch`
  per week when due; candidates recorded as noticed; at most one suggestion block per
  checkpoint.
- **The owner:** a short numbered digest about once a week when something relevant changed;
  occasional promotion suggestions; no action taken without a yes.
- **Upstream maintainer:** pull requests arrive with a proposal file, a scrub report and tests.
- **Memory:** new files under `/memory/skills/skill-exchange/` and `/memory/skills/installed.json`,
  created on first use.
- Mechanics repository content is unchanged except for the four target files.

## Risks and conflicts

- **Suggestion fatigue.** Mitigated by the cap, the no-repeat rule, the `weekly` and `off`
  settings, and silence when nothing is new.
- **A scrub false negative.** The check is pattern- and denylist-based and cannot prove
  absence of personal data. It is a floor, not a substitute for reading the diff; the pull
  request still needs the owner's yes after seeing it.
- **Installing someone else's code.** Scripts run with the owner's access. Mitigated by
  reading every file first, running tests, recording provenance and `verify-installs`.
- **Private copies are not forks.** `/SETUP.md` step B3 recommends a private copy, from which
  GitHub cannot open a cross-repository pull request. The skill names the two alternatives
  (a contributor branch on upstream with the owner's go, or `git format-patch`).
- **Upstream governance arriving by merge.** A merge can change `/RULES.md` or
  `/CONTRACT.md`; the digest flags these and routes them through CONTRACT §13.2.
- **Numbering.** This proposal claims no `RULE-` number, so it cannot collide with another
  proposal's reservation (the failure recorded in `PROPOSAL-rules-file-shape`).

## Migration

None required. Files in memory are created on first use. An owner who wants no suggestions
writes `{"suggestions": "off"}` to `/memory/skills/skill-exchange/config/settings.json`.

## Rollback

Revert the commits that applied the four target-file changes; set the skill's `status` back to
`proposed`. The memory files are inert without the rule and may stay or be deleted by the
owner.

## Validation

- `python -m unittest discover -s shared/skills/skill-exchange/scripts/tests -v` – eight tests
  on a fictional upstream and brain: grouping by `active_skills`, always-on and new skills;
  digest order, cap and no-repeat; cadence; provenance and local-edit detection; scrub hits
  and allow-list; declined candidates returning only with new evidence.
- `python shared/skills/repository-preflight/scripts/preflight.py` – no new errors.
- `python shared/skills/skill-exchange/scripts/skill_exchange.py scrub shared/skills/skill-exchange`
  on a real brain – no hits outside the test fixtures, which assemble their fictional
  personal data at run time.
- Behavioural check after acceptance: in three consecutive sessions, the upstream digest
  appears at most once, at session start, and never mid-task.

## Acceptance

Not yet requested. When requested, ask one direct question that identifies
`PROPOSAL-skill-exchange` and the number the maintainer assigned. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record

None.
