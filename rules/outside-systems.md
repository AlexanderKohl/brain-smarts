---
id: brain-rules-outside-systems
title: Rule pack: outside-systems
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-26T14:35:03+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: outside-systems

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: looking up a fact or identifier; reading from or writing to an external system or its API; using a credential; using a host plugin skill or its connector.

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

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0005` | Internal-first then external lookup | this file | looking up a fact or identifier |
| `SMART-RULE-0013` | Per-API quirk knowledge base | this file | external-API behaviour is unexpected, undocumented or newly explained |
| `SMART-RULE-0017` | Surface external-system configuration mismatches before coding around them | this file | an external system's configuration disagrees with what the task needs |
| `SMART-RULE-0045` | Host plugin skills act under the brain | this file | using a skill installed in the host rather than the brain (a host plugin skill), or its connector |

## SMART-RULE-0005 – Internal-first then external lookup

- When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge, and other already-known canonical homes) with a **targeted** search. Do not run exhaustive repository grep theatre to prove absence.
- If the fact is absent or still uncertain after that internal check, use the authoritative external shared skill when one exists or is mandated (for example ABR Web Services for Australian Business Numbers and GST registration). After a verified external result, update the relevant durable brain record when the fact belongs in the repository.
- Do not delegate work to explore/repo-only subagents when the answer requires vault credentials, Gmail, or an external API. Match agent capabilities to the job, or do the lookup in-session.
- When the owner redirects to a different path (skill, external system, email), abandon or stop parallel searches that the redirect made obsolete; do not finish a doomed explore pass "for completeness."

## SMART-RULE-0013 – Per-API quirk knowledge base

- Every `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, holding one small file per confirmed or hypothesised piece of non-obvious external-API behaviour for that system. Scaffold it (empty, plus one `_CONVENTION.md` copied from `/shared/templates/api-knowledge-convention.template.md`) whenever a new `<system>-access` skill is created. If a quirk worth logging is found for a system with no shared skill yet, create the minimal skill folder and its `knowledge/` scaffold first rather than leaving the finding without a canonical home.
- Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external API, search that system's `knowledge/` folder first, by filename and by front matter as its `_CONVENTION.md` shows, before re-investigating from scratch. Treat a `refuted` entry as a warning against repeating that exact hypothesis; treat a `deprecated` entry as a pointer to its `superseded_by` replacement, not as current fact.
- After a fix or investigation resolves genuinely unexpected or undocumented external-API behaviour, write one entry under that system's `knowledge/` folder, copied from `/shared/templates/api-knowledge-entry.template.md` and named as the convention says, with `system`, `object_type`, `field_type`, `endpoint`, `status` and `source_refs` set. Routine work that reveals nothing unexpected about the external API gets no entry: the store holds quirks and workarounds, not a changelog.
- Set a new entry's `status` to `pending` when the fix it documents relies on a hypothesis not yet independently confirmed; set `confirmed` only once a live probe or observed real subsequent use corroborates it. When later evidence contradicts a `pending` or `confirmed` entry, do not delete it: set `status: refuted` for a wrong hypothesis or `status: deprecated` for behaviour that has genuinely changed, add a one-line note of what changed and when, and set `superseded_by` or leave it for the correcting entry to backlink via `refuted_by` once one exists.
- Promote, refute or deprecate an existing entry opportunistically - the next time work touches that same quirk and turns up corroborating or contradicting evidence - rather than deferring it to a scheduled review that does not otherwise exist in this repository.

## SMART-RULE-0017 – Surface external-system configuration mismatches before coding around them

- When work against an external system reveals that its configuration is inconsistent with what
  the task needs – mismatched option sets, a missing or wrongly-typed field, a naming collision, a
  value that cannot be represented in the target – stop and put the finding to the owner before
  writing code that bridges it. State precisely what disagrees, what a fix in that system would
  be, and what the code workaround would otherwise cost.
- This overrides the "prefer a reversible default and proceed" guidance in `SMART-RULE-0010` for
  configuration mismatches specifically. The reason is not risk but economy: a change in the
  external system's own interface is frequently far cheaper than a translation layer, and the
  layer outlives the mismatch it was written for.
- This does not apply to genuine API behaviour that cannot be configured away – an endpoint's
  response shape, a required header, a status code. Absorb those in code and record them under
  `SMART-RULE-0013`.

## SMART-RULE-0045 – Host plugin skills act under the brain

- A host plugin skill is a skill installed in one AI host rather than in the brain (for example a
  host's engineering, marketing, design or legal plugins). It may be used as a tool inside brain
  work. `/CONTRACT.md`, this file, `/memory/RULES.md` and the active node's rules govern it: where a
  plugin's own instructions differ – output style, list order, record formats, sending messages,
  external writes, commits – the brain's rule applies.
- Work done with a plugin follows the brain skill it serves: engineering work stays inside the
  product-development process (`SMART-RULE-0016`) with its gates, versions and checkpoint commits;
  user-interface work inside the brain's UI skills; marketing and legal work inside the owning
  project's node. The owner's mapping of enabled plugins to brain skills is kept in
  `/memory/ONBOARDING_OWNER.md` § Host plugins and updated whenever a plugin is enabled or disabled.
- Output lands in its canonical home in house style: a draft in the owning node or
  `/memory/outbox/`, a decision in the node's `STATE.md` or `KNOWLEDGE.md`, a task in
  `/memory/tasks/`. Messages are drafted, never sent without the owner's approval, and a plugin
  connector's write to an outside system needs the confirmed target of CONTRACT §10.5 like any
  other.
- **Learnings flow into the brain.** Using a plugin skill is ordinary evidence under `SMART-RULE-0028`: what the plugin produced that proved useful or wrong, the owner's corrections to its output and the preference behind them, durable decisions it helped reach, and failures or limits met. Each record names the host and plugin skill that produced the output.
- A plugin pattern that proves useful more than once is a candidate brain skill, suggested for
  promotion under `SMART-RULE-0032`, so the capability becomes portable to hosts that lack the
  plugin.
- A plugin connector's account is recorded in the owner's credential registry as
  `managed_by: host` when it is first used for real work; its credentials stay with the host,
  never in the brain.
