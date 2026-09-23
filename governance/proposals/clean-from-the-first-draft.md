---
id: PROPOSAL-clean-from-the-first-draft
title: Shareable repositories are written free of personal data, and the validator confirms it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-23T17:14:00+10:00
updated: 2026-09-23T17:14:00+10:00
rule_id: SMART-RULE-0008 (amendment A1, keeps its identifier)
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 1.1.0
new_contract_version: 1.1.0
target_files:
  - /RULES.md
  - /shared/skills/repository-preflight/
  - /shared/skills/skill-exchange/scripts/skill_exchange.py
---

# Shareable repositories are written free of personal data, and the validator confirms it

## Summary

Two changes that work together:

1. **The rule.** `SMART-RULE-0008` today says sample data must be fictional. Amendment A1 widens
   it to everything written into a shareable repository (the mechanics, and the skill library if
   `PROPOSAL-skill-library` is accepted): it is written free of personal data at the first draft,
   a lesson from the owner's own incident is split between the shareable repository and memory as
   it is written, and the final check is a confirmation, not a clean-up.
2. **The check.** The personal-data check becomes part of the validator that runs before every
   commit, with a small, reasoned list of generic exemptions, so a clean repository reports
   nothing and any hit is real.

## Current problem

- CONTRACT §3.4 forbids personal data in the mechanics, but nothing says *when* it is kept out.
  In practice files are written with real values to hand and cleaned afterwards, which is where
  leaks and rework come from.
- The validator only warns when a mechanics file's `owner` field names someone; it says itself
  that it "cannot find personal data in prose".
- The only prose check, `skill_exchange.py scrub`, is inside a proposed skill and is noisy. Run on
  the mechanics today it reports 212 hits, and on inspection none is a leak: generic node names
  that every brain has (the skeleton's own `credential-management`), the documented default
  install path, and sample values in a vendor's published API documentation. A check that always
  cries wolf is not run, and a real hit would be lost in the noise.

## Current wording

```markdown
## SMART-RULE-0008 – No real data in mock or sample data

- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data - including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
```

## Proposed wording or exact diff

```markdown
## SMART-RULE-0008 – No real data in sample data or shareable repositories

- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data - including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
- **Shareable repositories are written clean, not cleaned.** Everything written into a shareable repository – the mechanics and the skill library: rules, skills, scripts, tests, templates, proposals and commit messages – is free of personal data from its first draft (CONTRACT §3.4). Say "the owner". Read concrete values – names, paths, accounts, identifiers, locations, project and client names – at run time from `/memory/OWNER.md` or `/memory/skills/<skill>/config/`, never inline. Write examples with fictional values: `example.com` addresses, numbers reserved for fiction, invented names.
- **Split a lesson as you write it.** When a rule or skill comes out of the owner's own incident, write the generalised mechanism in the shareable repository and the incident, with its real identifiers, in memory at the node that owns it, in the same piece of work. Never write one file to be split later.
- **The check confirms; it does not clean.** The validator runs the personal-data check on every shareable repository before each commit, and a hit fails it. Fix a hit at its source. Exempt a value only when it is genuinely public or generic – a vendor's published documentation, a documented default – and give the reason beside the exemption. When a writing habit or a template invited the hit, record it as a learning (`SMART-RULE-0028`).
```

Index row in `/RULES.md`: "`SMART-RULE-0008` | No real data in sample data or shareable repositories | this file; `/shared/skills/repository-preflight/`".

### Validator (`/shared/skills/repository-preflight/`)

- The personal-data check moves from `skill-exchange` into the validator, as its one
  implementation (`SMART-RULE-0018`); `skill_exchange.py scrub` calls it.
- When memory is present, the validator builds the list of owner terms from memory – the owner
  profile's values, the names of memory's own projects and systems, and an optional
  `/memory/skills/repository-preflight/config/denylist.txt` – and never writes it anywhere
  else. Node names that the memory skeleton itself ships are not owner terms.
- It scans every text file in each shareable repository for those terms and for patterns (email
  addresses, phone numbers, absolute machine paths, long identifiers). A hit is an **error**.
- Generic exemptions live in `/shared/skills/repository-preflight/config/exemptions.txt`, one per
  line with its reason: a folder of vendor documentation (such as an API's published OpenAPI
  files), a documented default path, a reserved example domain. Owner-specific exemptions are
  not allowed there.
- Without memory (a fresh clone, or the upstream maintainer's own checks), only the patterns run.

## Reason

- Writing clean is cheaper than cleaning: the author knows at the moment of writing which value
  is the owner's, and nobody knows it as well afterwards.
- A check that reports nothing on a clean repository is one that gets run and believed.
- It serves the skill library directly: every library skill must be shareable as it stands.

## Scope and behavioural consequences

- **Agents** writing into the mechanics or the library take values from memory at run time and
  split owner lessons as they write. A commit with a hit fails the validator.
- **The owner** sees nothing new unless a hit occurs; then the report names the file, line and
  value.
- **Any project repository** is unaffected: the rule's first bullet already applies there, and
  its own confidentiality is its own affair.

## Risks and conflicts

- **False positives** on first run. Mitigated by the skeleton-name rule and the reasoned
  exemptions file; the validation below requires zero hits on today's mechanics before the rule
  becomes active.
- **False negatives.** Pattern and term matching cannot prove absence (a paraphrased client
  story has no term to match). The first three bullets are the real control; the check is the
  backstop.
- **Owner terms that are common words.** A short owner term could match ordinary prose; terms
  under four characters are ignored, and a surname that is a common word goes in the exemptions
  only with its reason.
- Complements `PROPOSAL-skill-exchange` (whose scrub becomes this check) and
  `PROPOSAL-skill-library` (a second shareable repository). No conflict with active rules.

## Migration

Move the check's code, add the exemptions file, fix any real hit it finds, and rerun until the
mechanics report zero. Past commits are not rewritten: what is already in history stays there.

## Rollback

Revert the rule text and the validator commit; `skill_exchange.py scrub` keeps its own copy only
if the move is reverted with it.

## Validation

- Validator tests on a fictional brain: a planted owner term, email and phone in a mechanics file
  each fail; the same values in memory pass; an exempted vendor-documentation folder passes;
  a skeleton node name is not an owner term; without memory, only patterns run.
- The validator reports zero personal-data hits on the mechanics today (currently 212, all
  judged false positives above, each resolved by the skeleton-name rule or a reasoned exemption).
- `skill_exchange.py scrub` tests still pass through the moved implementation.

## Acceptance

Not yet requested. Ask one direct question that identifies
`PROPOSAL-clean-from-the-first-draft` as amendment A1 to `SMART-RULE-0008`. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record

None.
