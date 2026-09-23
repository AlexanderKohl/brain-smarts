---
id: brain-contract
title: Portable AI Brain Contract
type: contract
status: active
schema_version: 0.2
contract_version: 1.1.0
contract: /CONTRACT.md
canonical: true
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T20:00:00+10:00
owner: brain-owner
---

# Portable AI Brain Contract

## 1. Authority and bootstrap

This file is the canonical operating contract for the entire brain: the mechanics repository that holds this file, the owner's memory repository checked out beneath it at `/memory/`, and every external project repository the memory points to (section 16).

Every AI agent, script or person working anywhere in the brain must:

1. Locate the brain root by moving upwards from the supplied path until `CONTRACT.md` is found. A path inside `/memory/` finds the contract one level above the memory checkout.
2. Treat a bootstrap reference to a repository directory as an instruction to read the `CONTRACT.md` inside that directory.
3. Treat an absolute bootstrap path as a location hint, not repository authority. Verify that the path exists and contains this contract.
4. Choose a bootstrap tier for the current turn:
   - **Full bootstrap** (required when creating, changing or deleting brain content, changing governance, using a skill with side effects, or when applicable policy is unclear): read the discovered `/CONTRACT.md`, then `/RULES.md`, then the owner profile `/memory/OWNER.md` and the owner-layer rules `/memory/RULES.md`, then inherited node `RULES.md` files down to the active node, then the active node's `README.md`, `STATE.md` and relevant dependencies before acting.
   - **Scoped bootstrap** (allowed only for answer-only / read-only fact retrieval with no durable writes): if the needed fact is already available from injected host context, a file already read in this session, or one targeted read of a known path, do not re-read the full contract tree. Escalate immediately to full bootstrap when a durable write, governance change, credential/side-effecting skill use, or policy uncertainty appears.
5. Stop and report the problem if the contract cannot be found or read, or if competing location hints identify different contracts.
6. When `/memory/` is absent, work only on the mechanics layer and say so; do not create owner content anywhere else to compensate. A fresh memory is set up from `/shared/templates/memory-skeleton/`.

Every Markdown file must contain YAML front matter with:

```yaml
contract: /CONTRACT.md
```

This reference means: if the contract has not been read in the current working session, read it before using the file.

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

## 3. Core concepts

### 3.1 Node

A node is a meaningful unit of ownership and context within the repository.

A node may represent:

- a project
- a domain
- an operating system
- an organisation
- a person
- another substantial area with an independent lifecycle or context

A complete node normally contains:

```text
README.md
RULES.md
STATE.md
LOG.md
KNOWLEDGE.md
skills/
data/
sources/
```

Empty folders are optional until required. The five core Markdown files are required for project, domain and system nodes.

### 3.2 Hierarchy and network

The folder hierarchy defines ownership, scope and inherited rules.

Cross-references define relationships, dependencies and shared use.

Use folders to answer:

- Where does this belong?
- Who owns it?
- Which rules apply?
- What is its parent context?

Use links and metadata references to answer:

- Which projects use it?
- Which knowledge does it depend on?
- Which skills can act on it?
- Which people or organisations are involved?

Do not force every relationship into the folder tree.

### 3.3 Canonical home

Each durable item must have one canonical home.

Other nodes reference the canonical item. They do not maintain independent copies unless a deliberate derivative is required.

When a derivative is required, its metadata must identify the canonical source.

### 3.4 The three layers

The brain is made of three layers, each with its own repository and its own audience.

1. **Mechanics (this repository).** The contract, generic rules, bootstrap and onboarding files, shared skills (instructions, scripts, tests and generic external-API knowledge), templates, schemas, the raw-file system node and governance proposals about the mechanics. It holds **no personal data**: no owner name, client, contact, company, account, location or tenant identifier, email address, phone number, machine path or owner project name. Anyone could adopt it unchanged.
2. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, tasks, in-brain projects, contacts, raw files, sources, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.
3. **Project repositories.** Bodies of work with their own lifecycle, each in its own repository, checked out as siblings of the brain root (section 16). The memory keeps only a small pointer node for each.

When an item could sit in either of the first two layers, it belongs in memory unless it is free of every owner specific listed above and useful to another owner as it stands. A mechanism learnt from an owner incident goes to the mechanics layer in generalised form, and the original incident, with its real identifiers, stays in memory at the node that owns it.

### 3.5 Runtime layout and the `/memory/` path rule

One working tree holds two repositories:

```text
<brain_root>/                  mechanics repository; the brain root "/"; CONTRACT.md lives here
<brain_root>/memory/           memory repository; listed in the mechanics repository's .gitignore
<project_repos_root>/<repo>/   each external project repository, a sibling checkout
```

- A repository-root path such as `/CONTRACT.md`, `/RULES.md` or `/shared/...` names a file in the mechanics repository.
- Everything owned by memory is addressed as `/memory/...`: for example `/memory/tasks/open/`, `/memory/projects/<node>/`, `/memory/raw/YYYY/MM/<source-id>/`, `/memory/sources/<source-id>.md`, `/memory/outbox/`, `/memory/boards/`, `/memory/STATE.md`.
- **Path rule:** an item that belongs to memory keeps the path it would have in a single tree, prefixed with `/memory/`: `/X` becomes `/memory/X`. Moving content into memory applies this rule mechanically and does not rename the rest of the path.
- Owner-specific configuration, data and notes for a shared skill `/shared/skills/<skill>/` live at `/memory/skills/<skill>/`, using the same inner layout as the skill (`config/`, `data/`, `knowledge/` and so on). A shared script finds them by locating the brain root (moving upwards to `CONTRACT.md`) and joining `memory/skills/<skill>/`, or by a path the owner profile names. It never hard-codes a machine path.
- `/temp/` is local scratch in the brain root working tree, ignored by both repositories. Nothing durable belongs there.
- The mechanics repository never commits anything under `/memory/`, and the memory repository never carries a copy of a mechanics file. A file that must change in both layers is changed in each repository and committed in each.

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

## 4. Standard node files

### `README.md`

Every `README.md` must include a summary of each immediate child folder beneath that node.

The folder summary must:

* name every immediate child folder  
* explain what the folder contains  
* explain what belongs there  
* identify whether it is local, shared, generated, canonical or derived  
* identify any important access, update or preservation rules  
* remain current when folders are added, removed, renamed or repurposed

Use a standard section:

#### Folders

##### \`skills/\`

Contains skills, scripts and procedures specific to this node.

##### \`data/\`

Contains structured and generated data owned by this node.

##### \`sources/\`

Contains source references and project-local derivatives linked to canonical raw files.

##### \`subproject-name/\`

Contains the node for the named subproject, including its own rules, state, knowledge and tasks.

Only immediate child folders must be summarised. Nested folders are documented in the `README.md` of their parent node.

A folder must not be created without updating the parent node's `README.md`.


### `RULES.md`

Defines local operating rules. It inherits this contract and all ancestor rules.

### `STATE.md`

Describes what is currently true and may change.

Keep it current. Replace superseded state rather than accumulating history.

### `LOG.md`

Records significant events, actions and decisions in chronological order.

Begin each event group with an ISO 8601 timestamp heading. Append new entries. Do not rewrite historical entries except to correct an identified error, and record the correction.

### `KNOWLEDGE.md`

Contains durable facts, principles, definitions and established understanding owned by the node.

Do not use it for temporary instructions, current status or unverified claims.

### `skills/`

Contains local capabilities, instructions and executable scripts specific to the node.

### `data/`

Contains structured or generated data owned by the node.

### `sources/`

Contains Markdown source records or project-local references to source material. Every source record must reference its immutable raw file.

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

## 7. Creating and structuring nodes

Create a new node only when it has enough independent structure to justify one.

Strong reasons include:

- an independent purpose or outcome
- state that changes over time
- substantial knowledge or source material
- distinct rules, permissions or confidentiality
- specialised skills or data
- multiple contributors or dependencies
- a need to be referenced by several other nodes
- a lifecycle independent of its parent

Do not create a node for:

- one small task
- one temporary conversation
- a minor topic
- a document with no independent lifecycle
- filing convenience alone

A new node is usually justified when at least three strong reasons apply.

Before creating a node:

1. search for an existing suitable node
2. choose the canonical parent
3. select a node type
4. create the five core Markdown files from templates
5. define concise metadata
6. record dependencies
7. create or link relevant tasks
8. log the creation in the parent node

### 7.1 In memory or in its own repository

This decision rule lives in the contract, beside node creation, because it decides which repository a new node's files are committed to.

Start a body of work as a node inside memory, under `/memory/projects/`, by default. Give it its own repository (section 16) when **any** of these tests is true:

1. **Code.** It has, or is expected within weeks to have, code that is built, run or deployed.
2. **Other people.** Someone other than the owner will work on it, or needs to see it.
3. **Own lifecycle.** It needs its own versioning, releases or continuous integration.
4. **Size.** It will outgrow a few hundred files, or holds large binary files.
5. **Confidentiality.** Its confidentiality differs from the rest of the memory, in either direction.
6. **Independent value.** It would be useful to share, publish or sell on its own.

Keep it in memory when none of these is true: the work is mostly notes, state and tasks for the owner alone.

Each test is answered yes or no and recorded, with one line of evidence, in the node's `LOG.md` entry that creates the node or moves it. When the answer is unclear, keep the work in memory and create a task with `next_review` to test the question again.

Moving a node out of memory later is an extraction, not a copy:

1. extract the node's folder into a new repository with its history
2. move the node's own files into the repository's `brain/` folder (section 16.2)
3. replace the node in memory with a pointer node (section 16.1)
4. update references to the moved files across memory
5. log the move in the node's new `brain/LOG.md` and in the memory parent node

## 8. Metadata contract

Every Markdown file must begin with YAML front matter.

Exception: immutable evidence files stored under `/memory/raw/` are exempt. Do not add or rewrite front matter on raw files. Their companion Markdown source records under `/memory/sources/` (and any project-local derivatives) carry the required metadata and must reference the raw path.

### 8.1 Required fields

```yaml
---
id: unique-stable-id
title: Human-readable title
type: document-type
schema_version: 0.2
contract: /CONTRACT.md
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---
```

`id` must remain stable when a file is renamed or moved.

`type` must describe the file's function, such as:

- contract
- node_readme
- rules
- state
- log
- knowledge
- task
- skill
- source_document
- source_reference
- schema
- template

### 8.2 Timestamp format

Use ISO 8601 timestamps with second precision and an explicit timezone designator for `created`, `updated`, and log entry headings.

Valid forms include:

```text
2026-08-04T15:40:17+10:00
2026-08-04T05:40:17Z
```

Do not use a date without a time for these fields or entries.

- Keep `created` unchanged after the item is created.
- Set `updated` to the time of the latest substantive content or metadata change.
- Use the timezone of the event when known; otherwise use UTC.
- Do not invent precision for migrated legacy records. Use the most reliable available filesystem, source-system or provenance timestamp and record the migration decision in the relevant log.

### 8.3 Type-specific fields

Add only fields that improve discovery, routing, responsibility, automation or traceability.

Common examples:

```yaml
status: active
owner: brain-owner
parent: /memory/projects/example
node_type: project
project_refs:
  - /memory/projects/example
skill_refs:
  - /shared/skills/xero-access
tags:
  - accounting
```

Source-specific examples:

```yaml
raw_source: /memory/raw/2026/08/source-id/original.pdf
raw_sha256: full-hash
canonical_source_md: /memory/sources/source-id.md
conversion_status: complete
conversion_skill: /shared/skills/raw-file-ingestion
```

Task-specific examples:

```yaml
status: ready
owner: brain-owner
priority: normal
due: 2026-08-10
next_review: 2026-08-07
waiting_on: null
project_refs:
  - /memory/projects/example
```

### 8.4 Metadata simplicity

Use the smallest metadata set that supports a clear use.

Do not add fields merely because they may be useful later.

When a repeated need appears, add the field to the relevant schema and increment `schema_version`.

Prefer additive changes. Do not remove or rename a field without a migration plan.

Update the `updated` timestamp whenever substantive content or metadata changes.

## 9. Tasks

Tasks are a cross-cutting operating system, not an ordinary project.

The canonical task store is `/memory/tasks/`. Tasks are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

A task exists once and references every relevant project, person, organisation, skill or dependency.

### 9.1 Responsibility

Use one `owner` field.

The owner is accountable for the next action or outcome.

Do not store a separate follow-up owner. The system performs follow-up checks whenever an agent is invoked, a task view is requested or an external scheduler runs the task-review skill.

For delegated or waiting work, use:

```yaml
owner: brain-owner
waiting_on: External accountant
next_review: 2026-08-07
```

The owner remains accountable. The system surfaces the task at `next_review`.

### 9.2 Status values

Use:

- `inbox`
- `ready`
- `in_progress`
- `waiting`
- `scheduled`
- `blocked`
- `completed`
- `cancelled`

Meanings:

- `inbox`: captured but not processed
- `ready`: actionable now
- `in_progress`: actively being worked on
- `waiting`: another person, event or dependency is expected to move it
- `scheduled`: intentionally deferred until a date
- `blocked`: cannot proceed without intervention
- `completed`: completion criteria are met
- `cancelled`: no longer required

### 9.3 Required task behaviour

When processing tasks:

1. capture implied outstanding work
2. avoid creating a task when the instruction is completed immediately
3. assign one owner
4. define a clear outcome or next action
5. add relevant project references
6. add `due` only when a real deadline exists
7. add `next_review` for waiting, scheduled or delegated work
8. update related node state when task completion changes reality
9. move completed records to `/memory/tasks/completed/`
10. preserve task history in the task body and task log

### 9.4 Task versus project

A task is one directly completable action or outcome.

A project requires coordination of multiple tasks over time.

Promote a task into a project when it gains several dependent actions, multiple contributors, meaningful risks, substantial state or its own knowledge.

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

Place it in `/shared/skills/` when multiple nodes can use the general capability.

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

## 11. Raw files and Markdown derivatives

### 11.1 Immutable raw store

All uploaded or imported source files must be preserved in `/memory/raw/`. Raw files are owner evidence and never enter the mechanics repository.

The raw file is immutable source evidence.

Do not edit, overwrite, normalise or delete it as part of ordinary work.

Store raw files using a stable source ID:

```text
/memory/raw/YYYY/MM/<source-id>/<original-filename>
```

Record a SHA-256 hash at ingestion.

If the same file is uploaded again, detect it by hash and reuse the existing canonical raw record.

### 11.2 Automatic Markdown conversion

When a raw file enters the repository:

1. preserve the original under `/memory/raw/`
2. compute and record its SHA-256 hash
3. create a canonical Markdown representation under `/memory/sources/`
4. create project-local source references or derivatives where needed
5. link every derivative back to the raw file
6. record conversion method, time and limitations
7. update the relevant node log
8. create a task if conversion is incomplete or requires review

The Markdown representation exists for accessibility, search and AI use. It does not replace the raw file.

### 11.3 Source metadata

Every Markdown conversion or source reference must include:

```yaml
type: source_document
raw_source: /memory/raw/YYYY/MM/<source-id>/<original-filename>
raw_sha256: full-sha256
conversion_status: complete
conversion_skill: /shared/skills/raw-file-ingestion
```

A project-local derivative should also include:

```yaml
canonical_source_md: /memory/sources/<source-id>.md
project_refs:
  - /memory/projects/example
```

### 11.4 Fidelity

Preserve:

- headings and document order
- tables where practical
- page, slide, sheet or section references where available
- dates, names, quantities and identifiers
- uncertainty and illegible content markers

Do not silently invent missing text.

Mark incomplete extraction, OCR uncertainty, unsupported formats or lost formatting.

### 11.5 Multi-project use

The raw file and canonical source Markdown are globally accessible.

Projects should reference them.

Create a project-local derivative only when the project needs annotations, excerpts, mappings or a specialised representation.

Every local derivative must retain the raw source reference.

## 12. Shared resources and dependencies

Store reusable capabilities and schemas under `/shared/`.

A node declares dependencies in `README.md` using repository-root paths.

Example:

```yaml
knowledge_refs:
  - /memory/domains/finance
skill_refs:
  - /shared/skills/xero-access
source_refs:
  - /memory/sources/source-id.md
```

Do not copy shared skills or knowledge into each project.

A project may store configuration for a shared skill, but the general skill remains canonical under `/shared/skills/`. Owner-wide configuration, data and notes for a shared skill live in `/memory/skills/<skill>/` (section 3.5); a mechanics skill never carries them.

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

An agent may create or revise a proposal without activating it. Store proposals outside the inherited rule path, in the layer whose governance they change:

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

1. read this contract
2. read `/memory/OWNER.md` when memory is present
3. establish the active node
4. read inherited rules (`/RULES.md`, `/memory/RULES.md`, then node rules) and active state
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

## 15. Repository integrity checks

Before finishing a substantive update, verify:

- every Markdown file outside `/memory/raw/` begins with valid YAML front matter
- every Markdown file outside `/memory/raw/` references `/CONTRACT.md`
- immutable `/memory/raw/` Markdown evidence remains unchanged; companion source records under `/memory/sources/` carry metadata and `raw_source`
- each durable item has one canonical home
- task owners and statuses are clear
- waiting tasks have `next_review`
- raw source derivatives reference an existing raw path
- shared resources are linked rather than copied
- project state reflects material completed work
- significant changes are logged
- no credentials were stored
- every README.md lists and accurately summarises each immediate child folder
- protected governance changes have an accepted proposal
- the active `contract_version` is recorded in the repository manifest of each brain repository changed (`/repository-manifest.json` and `/memory/repository-manifest.json`)
- no personal data has entered the mechanics repository (section 3.4)
- the repository preflight validator passes
- every separable, validated, agent-owned durable change has been committed at the required logical checkpoint
- the final report identifies each resulting commit and push status, or gives the exact permitted reason no commit was created

## 16. External project repositories

A body of work that passes a test in section 7.1 lives in its own repository, checked out as a sibling of the brain root under the owner's `project_repos_root` (see `/memory/OWNER.md`). It stays part of the brain: this contract governs it, and an agent working inside it bootstraps from the brain root.

### 16.1 Pointer node in memory

Memory keeps one small pointer node per project repository, at `/memory/projects/<node>/`. Its `README.md` carries, in front matter or a short table:

- `repo_url`: the repository's remote URL
- `local_path`: the checkout path, relative to `project_repos_root` or absolute
- `default_branch`: the branch that holds released or agreed work
- what lives where: which of the project's records are in the repository's `brain/` folder, which are in memory, and which external systems hold the rest

The pointer node may also hold owner-private notes that must not be visible to the project's collaborators, in its own `KNOWLEDGE.md`, `STATE.md` or `LOG.md`. It holds nothing else: no copy of the project's state, rules or knowledge.

Tasks about the project remain canonical in `/memory/tasks/` and reference the pointer node in `project_refs`. A project with collaborators may also run its own issue tracker; an owner task then links the issue instead of copying it.

### 16.2 The project's own node files

The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and any `sources/` or `data/` it owns – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules.

References from a project repository's `brain/` files to its own files use paths relative to the repository root, prefixed with the repository name and a colon when a reader outside the repository needs them (for example `example-repo:brain/STATE.md`). References into the brain use repository-root paths such as `/shared/skills/<skill>/`. A project repository never references `/memory/` paths, because a collaborator cannot resolve them.

### 16.3 Validation and commits

The repository preflight validator validates the mechanics repository and, when present, `/memory/`. A project repository runs its own checks; its `brain/` folder follows section 15 where it applies. Commits and pushes in a project repository follow the inherited Git rules and are reported separately from the brain's own repositories.
