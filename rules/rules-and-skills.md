---
id: brain-rules-rules-and-skills
title: Rule pack: rules-and-skills
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-24T18:28:13+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: rules-and-skills

Generated from `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim, the rules of one
situation, so that they are read together. Each rule's canonical home stays `/RULES.md`.

Read the whole file before: writing or changing a rule, a proposal, a skill's operating instructions, a host entry file or a pointer file, or anything in the mechanics or the skill library.

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0002` | Protected governance | this file; `/CONTRACT.md` §13.2 | proposing, amending or applying a change to protected governance |
| `SMART-RULE-0007` | Portable behavioural rules only | this file | writing a rule, a skill's operating instructions, a host entry file or a pointer file |
| `SMART-RULE-0008` | No real data in sample data or shareable repositories | this file; `/shared/skills/repository-preflight/` | writing sample, seed or fixture data, or anything in the mechanics or the skill library |
| `SMART-RULE-0031` | Show the text of every new or changed rule | this file | proposing, amending, accepting or applying a rule at any level |

## SMART-RULE-0002 / CONTRACT §13.2 – Protected governance

- CONTRACT §13.2 governs every change to protected governance. The report of an accepted change names its proposal ID, the exact files changed, the effective contract version and the validation result.

## SMART-RULE-0007 – Portable behavioural rules only

- Durable behavioural rules live only in portable governance: `/CONTRACT.md`, root and node `RULES.md` files, and skill operating instructions. A host entry file only points agents to the portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`, `/AGENTS.md`); no host-specific file restates, extends or carries behavioural policy of its own.
- **One text per rule.** A rule's wording lives only in its canonical home. Anywhere else it is referred to by its identifier and section, never restated in other words; a list that can be generated from its sources is generated. The repository preflight fails when a pointer file carries rule identifiers or runs past a pointer's length. The worker brief (`/shared/skills/delegate-work/templates/worker-brief.template.md`) is the one permitted digest: each of its items names the rule or contract section it digests, and a change to a digested rule changes the brief in the same commit.
- **A host's own memory is not a home.** Where a host keeps notes of its own between sessions (a memory folder, saved memories, custom instructions), an agent stores no behavioural rule, owner preference, project fact or learning there, even when the host tells it to save one. It routes the item under CONTRACT §5 and §6 – an owner preference to the owner layer through a proposal, a fact to the node that owns it, a tool's quirk to its learning or API record – and says where it went. A host's memory holds at most a pointer to the brain and facts about that one installation which no other host could use. An entry found there that belongs in the brain is moved, not copied.

## SMART-RULE-0008 – No real data in sample data or shareable repositories

- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data - including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
- **Shareable repositories are written clean, not cleaned.** Everything written into a shareable repository – the mechanics and the skill library: rules, skills, scripts, tests, templates, proposals and commit messages – is free of personal data from its first draft (CONTRACT §3.4). Say "the owner". Read concrete values – names, paths, accounts, identifiers, locations, project and client names – at run time from `/memory/OWNER.md` or `/memory/skills/<skill>/config/`, never inline. Write examples with fictional values: `example.com` addresses, numbers reserved for fiction, invented names.
- **Split a lesson as you write it.** When a rule or skill comes out of the owner's own incident, write the generalised mechanism in the shareable repository and the incident, with its real identifiers, in memory at the node that owns it, in the same piece of work. Never write one file to be split later.
- **The check confirms; it does not clean.** The validator runs the personal-data check on every shareable repository before each commit, and a hit fails it. Fix a hit at its source. Exempt a value only when it is genuinely public or generic – a vendor's published documentation, a documented default – and give the reason beside the exemption. When a writing habit or a template invited the hit, record it as a learning (`SMART-RULE-0028`).
- **Fixture numbers are chosen to pass from the start.** A run of nine or more digits, such as a ten-digit epoch-second timestamp, reads as a telephone number. In fixtures, choose such values so their digits contain the run reserved for fiction, `55501` (for example `1755501000`), when the fixture is first written, and derive every expected result from them. A hit found later is fixed by whoever wrote the tests, keeping their ordering and range assertions true, never by a blanket swap of values.
- **A memory node is not named after a library skill.** The check reads the folder name of every memory project node as an owner term. Give a new memory project node a name that no skill in the library has, or the skill's own name becomes a hit in the library and its commit is refused.

## SMART-RULE-0031 – Show the text of every new or changed rule

- Whenever an agent proposes, amends, accepts or applies a rule at any level (the contract,
  `/RULES.md`, `/memory/RULES.md`, a node's `RULES.md` or a skill's operating rules), the reply
  to the owner quotes the rule's full text – its heading and every bullet, or the exact
  before-and-after for an amendment – before the file path. A summary may accompany the text but
  never replaces it.
