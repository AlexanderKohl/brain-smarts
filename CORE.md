---
id: brain-core
title: Brain Core
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-10-01T12:10:36+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Brain Core

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is the
first of the two files a writing session reads first (CONTRACT §1): the contract sections that
always apply, verbatim. Then read `/CORE-RULES.md`.

## Contract sections that always apply

## 1. Authority and bootstrap

This file is the canonical operating contract for the entire brain: the mechanics repository that holds this file, the skill library checked out beneath it at `/library/`, the owner's memory repository checked out beneath it at `/memory/`, and every external project repository the memory points to (section 16).

Every AI agent, script or person working anywhere in the brain must:

1. Locate the brain root by moving upwards from the supplied path until `CONTRACT.md` is found. A path inside `/memory/` finds the contract one level above the memory checkout.
2. Treat a bootstrap reference to a repository directory as an instruction to locate the `CONTRACT.md` inside that directory and bootstrap from it.
3. Treat an absolute bootstrap path as a location hint, not repository authority. Verify that the path exists and contains this contract.
4. Choose a bootstrap tier for the current turn, before reading further:
   - **Scoped bootstrap** (allowed only for answer-only / read-only fact retrieval with no durable writes): read what the answer needs – injected host context, a file already read in this session, or targeted reads of known paths – and nothing else.
   - **Full bootstrap** (required before the first creation, change or deletion of brain content, a governance change, use of a skill with side effects, or when applicable policy is unclear): read `/CORE.md` and `/CORE-RULES.md`, then the owner profile `/memory/OWNER.md` and the owner-layer rules `/memory/RULES.md`, then inherited node `RULES.md` files down to the active node, then the active node's `README.md`, `STATE.md` and relevant dependencies before acting. The two files are generated from this contract and `/RULES.md`: `/CORE.md` holds, verbatim, the sections of this contract that always apply; `/CORE-RULES.md` holds the tables that say when every other section and rule applies, and, verbatim, the rules that always apply. Each is short enough for a host to show whole; read them, and every bootstrap file, with the host's file-reading tool (for example Read), not a shell command such as `cat`: a shell may show only the start of a long file.
   - **Read by situation.** Before acting in a situation named under `Applies when` in those tables, read that section of this contract, or that rule in its canonical home, in full. When it is unclear whether a row applies, read it.
   - **Escalation.** A turn that began scoped escalates to full bootstrap the moment it is about to write, take a side effect, use a credential or meet policy doubt: before that first action, never after it. A write to a brain repository begins with `session.py start` (`SMART-RULE-0038`), which prints the full-bootstrap reading list, so every agent in every host meets the escalation at the same step.
5. Stop and report the problem if the contract cannot be found or read, or if competing location hints identify different contracts.
6. When `/memory/` is absent, work only on the mechanics layer and say so; do not create owner content anywhere else to compensate. A fresh memory is set up from `/shared/templates/memory-skeleton/`.

Every Markdown file must contain YAML front matter with:

```yaml
contract: /CONTRACT.md
```

This reference means: if the bootstrap of the tier the work needs (item 4 above) has not been done in the current working session, do it before using the file.

Local rules may add constraints. They may not override this contract.

`contract_version` identifies the active behavioural contract. `schema_version` identifies the metadata structure used by this file. They are independent.

Rules inherit in this order, each level adding constraints and none overriding an earlier one:

```text
/CONTRACT.md  ->  /RULES.md  ->  /memory/RULES.md  ->  node RULES.md files down to the active node
```

`/RULES.md` holds generic rules any owner could adopt. `/memory/RULES.md` is the owner layer: always read, it applies to the whole brain, including the mechanics layer and external project repositories, and holds the owner's own standing preferences.

## 2. Purpose

The brain is a portable, file-based operating context that can be used by different AI systems without depending on one platform.

It must:

- preserve durable knowledge
- describe current state
- maintain a traceable activity history
- manage outstanding tasks and responsibility
- provide reusable skills and executable scripts
- preserve raw source files
- create accessible Markdown representations of source files
- route information to its correct canonical home
- remain understandable and maintainable by people

### 3.4 The four layers

The brain is made of four layers, each with its own repository and its own audience.

1. **Mechanics (this repository).** The contract, generic rules, bootstrap and onboarding files, the core skills the brain itself depends on (a skill a `SMART-RULE` or this contract requires, or that another core skill calls), templates, schemas, the raw-file system node and governance proposals about the mechanics. It holds **no personal data**: no owner name, client, contact, company, account, location or tenant identifier, email address, phone number, machine path or owner project name. Anyone could adopt it unchanged.
2. **Skill library (`/library/`).** Every other reusable skill: access to an outside system, or a way of working an owner may choose. Instructions, scripts, tests and generic external-API knowledge, under the same no-personal-data condition as the mechanics. An owner uses the skills listed in `active_skills` in `/memory/OWNER.md`, and may merge skills from other libraries into their own.
3. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, tasks, in-brain projects, contacts, raw files, sources, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.
4. **Project repositories.** Bodies of work with their own lifecycle, each in its own repository, checked out as siblings of the brain root (section 16). The memory keeps only a small pointer node for each.

When an item could sit in memory or in a shareable layer (the mechanics or the skill library), it belongs in memory unless it is free of every owner specific listed above and useful to another owner as it stands. A mechanism learnt from an owner incident goes to the mechanics layer in generalised form, and the original incident, with its real identifiers, stays in memory at the node that owns it.

### 3.5 Runtime layout and the `/memory/` path rule

One working tree holds three repositories:

```text
<brain_root>/                  mechanics repository; the brain root "/"; CONTRACT.md lives here
<brain_root>/library/          skill library repository; listed in the mechanics repository's .gitignore
<brain_root>/memory/           memory repository; listed in the mechanics repository's .gitignore
<project_repos_root>/<repo>/   each external project repository, a sibling checkout
```

- A repository-root path such as `/CONTRACT.md`, `/RULES.md` or `/shared/...` names a file in the mechanics repository.
- A library skill is addressed as `/library/skills/<skill>/`. A core skill stays `/shared/skills/<skill>/`. Owner configuration, data and notes for either live at `/memory/skills/<skill>/`. A script that needs another skill finds it from the brain root, never by a path relative to its own folder, so a skill works whichever repository holds it.
- Everything owned by memory is addressed as `/memory/...`: for example `/memory/tasks/open/`, `/memory/projects/<node>/`, `/memory/raw/YYYY/MM/<source-id>/`, `/memory/sources/<source-id>.md`, `/memory/outbox/`, `/memory/boards/`, `/memory/STATE.md`.
- **Path rule:** an item that belongs to memory keeps the path it would have in a single tree, prefixed with `/memory/`: `/X` becomes `/memory/X`. Moving content into memory applies this rule mechanically and does not rename the rest of the path.
- Owner-specific configuration, data and notes for a shared or library skill live at `/memory/skills/<skill>/`, using the same inner layout as the skill (`config/`, `data/`, `knowledge/` and so on). A shared script finds them by locating the brain root (moving upwards to `CONTRACT.md`) and joining `memory/skills/<skill>/`, or by a path the owner profile names. It never hard-codes a machine path.
- A system node in the mechanics, `/systems/<system>/`, holds the mechanism: its rules, its procedure and the state of the mechanism itself. The owner's records for that system – its log of use, the owner's state, decisions and configuration – live in memory at `/memory/systems/<system>/`, a node of the same name. An owner fact about a system is written there, never in the mechanics node.
- `/temp/` is local scratch in the brain root working tree, ignored by every brain repository. Nothing durable belongs there.
- The mechanics repository never commits anything under `/memory/` or `/library/`; the memory repository never carries a copy of a mechanics or library file; the library never carries a copy of a mechanics file. A file that must change in both layers is changed in each repository and committed in each.

### 3.6 The owner profile

The owner of the brain is described in `/memory/OWNER.md`, whose front matter carries at least:

```yaml
owner_name: Full name
owner_short_name: Name the agents use in conversation
timezone: IANA zone (UTC offset)
brain_root: absolute local path of the brain root
github_account: account that owns the brain repositories
project_repos_root: absolute local folder where project repositories are checked out
default_host: the host and tool the owner usually works in
```

In mechanics files, the metadata value `owner: brain-owner` means the person named in `/memory/OWNER.md`, and prose says "the owner". Where a concrete value is needed (a local path, a timezone, an account), mechanics text says "see `/memory/OWNER.md`" instead of repeating it. Memory files may name the owner directly.

## 5. Input classification

Every user input must be classified into one or more of the following categories before repository updates are made.

### 5.1 Temporary instruction

An action to perform now.

Examples:

- draft a document
- analyse a file
- retrieve Xero information
- update a plan

After completion, the instruction itself may be forgotten unless it creates a task, changes state, produces knowledge or warrants a log entry.

### 5.2 Durable knowledge

A fact, principle, preference, definition or established relationship expected to remain useful.

Store it in the `KNOWLEDGE.md` file or dedicated knowledge node that owns the subject.

Place knowledge according to subject ownership, not the project active when it was mentioned.

### 5.3 State change

Something currently true that has changed or may change later.

Update the relevant `STATE.md`.

Create a `LOG.md` entry when the change is significant, explains a decision or is needed for traceability.

### 5.4 Task

An outstanding action that must remain visible after the current interaction.

Create or update a canonical task record under `/memory/tasks/`.

### 5.5 Mixed input

One statement may contain several categories.

Example:

> Send the revised contract to Cameron. Nick has approved the figures. The agreed price is $500,000.

Possible handling:

- perform or create the sending task
- update project state to record Nick's approval
- log the approval
- store the agreed price as durable project knowledge if verified

### 5.6 Durable operating rule

A forward-looking instruction that changes how agents must behave in future sessions.

Signals include phrases such as "in the future", "from now on", "going forward", "always", "never again", or equivalent language that clearly intends ongoing behaviour rather than a one-off action.

When such an instruction is identified:

1. Do not treat it as a temporary chat preference.
2. Identify the correct governance level: this contract, root `/RULES.md` (a mechanism any owner could adopt), the owner layer `/memory/RULES.md` (this owner's own preference), a node `RULES.md`, or a skill's permissions and operating instructions.
3. Draft or update the rule at that level. If the target is protected governance under section 13.2, follow the proposal-and-acceptance process before applying it.
4. Record the decision in the relevant log when the rule becomes active.

Until the rule is active in the governing file, do not claim the instruction is durable repository policy.

## 6. Routing information

For each persistent item, determine:

1. What subject owns this information?
2. Is it local to one node, part of an enduring domain or reusable across nodes?
3. Does a canonical item already exist?
4. Is this knowledge, state, history, a task, a skill, data or a source?
5. Which nodes need references to it?
6. Which layer holds it: mechanics, memory or a project repository (sections 3.4 and 7.1)?

Information mentioned during one project may belong elsewhere.

Do not store information in the active node merely because that is where it was mentioned.

## 13. Change protocol

### 13.1 Ordinary persistent changes

Before modifying persistent files:

1. identify the canonical file
2. read applicable rules
3. assess whether the change affects knowledge, state, tasks, logs, metadata or dependencies
4. avoid duplicate records
5. preserve raw evidence
6. update `updated`
7. append relevant log entries
8. validate links and metadata

When facts conflict:

- do not silently choose one
- preserve evidence and provenance
- mark the conflict
- create a review task when resolution matters

When uncertain:

- label the item as unverified, provisional or incomplete
- do not store inference as immutable knowledge

### 13.2 Protected governance

Protected governance files are:

- `/CONTRACT.md`
- every active `RULES.md`, including the owner layer `/memory/RULES.md` and node rules in memory and in project repositories
- governance schemas and templates
- bootstrap instructions that determine how agents locate or load the contract and inherited rules
- the repository preflight skill and validator that enforce this protocol

A substantive or semantic change to protected governance must not become active until the owner explicitly accepts an identified proposal or the exact displayed diff.

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

## 14. Session operating loop

When an agent starts work:

1. choose the bootstrap tier; for full bootstrap read `/CORE.md` and `/CORE-RULES.md` (section 1)
2. read `/memory/OWNER.md` when memory is present
3. establish the active node
4. read inherited rules (`/memory/RULES.md`, then node rules; a section of this contract or a `/RULES.md` rule when its `Applies when` fits the work) and active state
5. inspect relevant open tasks
6. inspect declared dependencies
7. classify the user's input
8. perform immediate instructions
9. persist knowledge, state changes, tasks and source records
10. update logs
11. check that created or changed Markdown files have valid metadata
12. before pausing or reporting completion, execute the applicable inherited Git checkpoint rule for every repository modified during the task: the mechanics repository, the memory repository and each project repository are separate repositories with separate commits
13. report completed work, unresolved issues, created tasks, commit hashes and push status; when no commit was created despite durable changes, report the exact blocking reason

An agent must not claim autonomous future follow-up unless an external scheduler or automation capability is actually configured.

Next: read `/CORE-RULES.md`, with the file-reading tool.
