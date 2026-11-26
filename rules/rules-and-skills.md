---
id: brain-rules-rules-and-skills
title: Rule pack: rules-and-skills
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-26T15:48:16+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: rules-and-skills

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: writing or changing the contract, a rule, a proposal, a governance template, a bootstrap file, a skill or its operating instructions, a host entry file or a pointer file, or anything in the mechanics or the skill library; accepting or applying such a change; numbering a rule or naming a proposal.

## 10. Skills, scripts and external systems

A skill may include:

- operating instructions
- prompts
- executable scripts
- API clients
- connectors
- data transformations
- validation logic
- automation workflows

A skill may retrieve or update data in external systems such as Xero or GoHighLevel.

### 10.1 Skill placement

Keep a skill local when it contains project-specific logic or permissions.

Place it in the skill library (`/library/skills/`) when multiple nodes can use the general capability, and in `/shared/skills/` only when the brain itself depends on it (section 3.4).

Separate:

- capability, stored in the shared skill
- project configuration, stored in the project, or for owner-wide configuration in `/memory/skills/<skill>/` (section 3.5)
- credentials, stored in a secure external mechanism
- results, stored or referenced by the requesting node

### 10.2 Skill specification

Every `SKILL.md` must define:

- purpose
- allowed operations
- required inputs
- data sources
- scripts or commands
- outputs
- permissions
- failure behaviour
- logging behaviour
- state, knowledge and task update behaviour

### 10.3 Credentials

Never store secrets, passwords, API keys, access tokens or private certificates in Markdown or committed scripts.

Reference environment variables, secret managers or approved authentication flows.

### 10.4 External data

Data retrieved through a skill must record:

- source system
- retrieval time
- relevant account, organisation or location
- query or scope
- whether the data is live, cached or partial
- any transformation applied

Do not represent retrieved data as complete when coverage is partial or uncertain.

### 10.5 External target confirmation

Before any write or other side-effecting operation against an external system that has multiple accounts, organisations, companies, locations or subaccounts:

1. Ask the owner which specific target applies for this operation, or obtain an explicit confirmation of the named target, before proceeding.
2. Identify the target at the precision the system requires (for HighLevel: company and subaccount/location; for other systems: the equivalent account or organisation scope).
3. Do not infer the target solely from recent chat context, the most recently used account, a project default, or an earlier session without a current confirmation for this operation.
4. Stop and ask when the target is missing, ambiguous or conflicts with another candidate.

Read-only discovery that lists available targets does not require prior target confirmation. Using a discovered target for a write or other side effect does.

### 13.2 Protected governance

Protected governance is rule and contract wording:

- `/CONTRACT.md`
- every active `RULES.md`, including the owner layer `/memory/RULES.md` and node rules in memory and in project repositories
- governance schemas and templates that define the wording of a rule or a proposal
- bootstrap instructions that determine how agents locate or load the contract and inherited rules
- the statement of what the repository preflight validator enforces: the *Failure behaviour* section of its skill

The validator's code, tests and fixtures, the rest of its skill, and README files are not protected governance; they change as ordinary persistent changes (section 13.1). Code that changes what the validator accepts or refuses changes the rule it enforces, so the *Failure behaviour* section changes with it, under this section.

A substantive or semantic change to protected governance must not become active until the owner explicitly accepts an identified proposal or the exact displayed diff. Acceptance covers that change, not later changes to the same file: each substantive change needs its own. One standing acceptance is allowed: an owner who turns `follow_upstream` on (`SMART-RULE-0032`) accepts each protected-governance change to the mechanics and the skill library that the upstream maintainer has already accepted on upstream `main`, for each upstream merge made while the setting is on. It covers nothing made locally, on another branch or offered upstream, and ends when the owner turns the setting off. Every change it admits is recorded in `/memory/governance/upstream-merges.md` and reported to the owner in the first reply. A change that only rewrites the `updated` stamp, line endings or the dash style is not substantive.

Before requesting acceptance, present:

1. a stable proposal ID
2. a plain-language summary of the changes (what will be different for the owner and agents), stated before or alongside the exact diffs
3. the current and proposed wording or exact diff
4. the reason for the change
5. the affected scope and expected behavioural consequences
6. risks, conflicts and migration requirements
7. a rollback method
8. the planned validation

Ask one direct acceptance question. Silence, lack of objection, approval of adjacent work, or general encouragement does not constitute acceptance. Acceptance must unambiguously identify the proposal or exact change set.

An agent may create or revise a proposal without activating it. A protected-governance change is checked for an accepted proposal where it becomes active: on `main` and in the branches that merge into it. On a `proposal/*` branch whose open proposal lists the file in `target_files`, preflight reports it as a warning, so a proposal's exact diff can be committed before the owner decides on it. Store proposals outside the inherited rule path, in the layer whose governance they change:

- a change to the contract, `/RULES.md`, shared governance schemas or templates, bootstrap files or the preflight validator: `/governance/proposals/` in the mechanics repository while it is under review, offered upstream as a pull request when it should reach everyone who uses the mechanics. The mechanics repository keeps no decision history: the owner's record of accepting and applying the change is kept in `/memory/governance/proposals/`
- a change to `/memory/RULES.md` or a node `RULES.md` in memory: `/memory/governance/proposals/`
- a change to a node `RULES.md` inside a project repository: that repository's `brain/proposals/`

A proposal that changes several layers is stored once, in the highest layer it touches, and lists every target in `target_files`.

When the change is a small additive or clarifying amendment to an existing numbered rule, keep that rule's identifier. Revise the original proposal record (or add an amendment section to it) and present that same identifier for acceptance. Give a new identifier only to a distinct new rule. Do not supersede a live rule with a new number merely because the wording grew by a sentence or a tighter constraint.

#### Rule identifiers

Every accepted rule has one identifier that names its layer and its number within that layer:

- `SMART-RULE-NNNN`: a rule whose canonical home is in the mechanics repository – this contract, `/RULES.md`, or a shared skill or template under `/shared/`. `/RULES.md` indexes every `SMART-RULE` identifier, including those whose wording lives elsewhere.
- `MEMORY-RULE-NNNN`: a rule in the owner layer, `/memory/RULES.md`.
- `<PROJECT>-RULE-NNNN`: a rule in a node's `RULES.md`, where `<PROJECT>` is the node's folder name in upper case (for example `EXAMPLE-PROJECT-RULE-0001` for `/memory/projects/example-project/RULES.md`). A rule inherited by several nodes keeps the prefix of the node that defines it.

Numbers have four digits, start at `0001` in each layer and are never reused, not even after a rule is retired. A newly accepted rule takes the next number in its layer: one more than the highest identifier already used in that layer's rule file (for the mechanics, the index in `/RULES.md`).

A proposal carries no rule number. Until the owner accepts it, it is named `PROPOSAL-<slug>`, its file is `<slug>.md` in the proposals folder of its layer, and that is its `id`. The number is assigned at acceptance and recorded in the proposal's `rule_id` field; the proposal keeps its own `id` and file name. Historical records – logs, proposal files, completed tasks, notes – keep the identifiers they were written with and are not rewritten.

After acceptance:

1. apply only the accepted change set
2. record the accepter and acceptance time
3. update `contract_version` when contract behaviour changes
4. run the repository preflight validator
5. record implementation and validation results
6. report the exact files changed, effective version, migrations and unresolved issues

If implementation reveals a material consequence not disclosed in the accepted proposal, stop and request acceptance of a revised proposal before continuing.

### 13.3 Contract versioning

Use semantic versioning for `contract_version`:

- patch: clarification with no intended behavioural change
- minor: additive or meaningfully changed behaviour that remains compatible with existing content
- major: breaking governance or repository-behaviour change requiring coordinated migration

Every accepted contract change must identify its previous and new contract versions. Do not use `schema_version` as a substitute for behavioural contract versioning.

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
