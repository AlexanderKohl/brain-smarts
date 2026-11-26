---
id: brain-rules-node-files
title: Rule pack: node-files
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

# Rule pack: node-files

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: writing a node's `README.md`, `RULES.md`, `STATE.md`, `LOG.md` or `KNOWLEDGE.md`; creating a Markdown file, or changing front matter or a log heading; writing a checkpoint, or the context was compacted; before finishing a substantive update.

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

A change a commit made is recorded by the commit: its message says what changed and why (`SMART-RULE-0009`), and the log does not tell it again. The log holds what no commit holds: a decision and the owner's words behind it, what was ruled out and the evidence that ruled it out, a measurement, an event outside the repository such as a deployment or an approval, and a correction to what an earlier commit message said. An entry that belongs to a commit names it by its short hash.

### `KNOWLEDGE.md`

Contains durable facts, principles, definitions and established understanding owned by the node.

Do not use it for temporary instructions, current status or unverified claims.

A node whose knowledge outgrows one readable file keeps it by subject: each subject has a file under `knowledge/`, and `KNOWLEDGE.md` becomes the index – one line per subject file, saying what it holds – together with the facts that fit no subject. A subject file is knowledge like `KNOWLEDGE.md` itself: everything this section and section 11.6 say of `KNOWLEDGE.md` holds for it, and an agent reads it when its subject is the work's. `KNOWLEDGE.md` is at most 28,000 characters, so that a host shows it whole.

A claim that can change carries the date it was true as of, and may carry a date to check it by:
`(as of 2026-09-20)` or `(as of 2026-09-20; review by 2026-12-31)`. When a claim is replaced, the
old one is kept and marked, never overwritten or silently deleted:
`~~Agreed price: $500,000~~ (superseded 2026-09-20 by the line below)`, followed by the new claim
with its own date. A timeless fact needs no date. The repository preflight fails on a claim whose
review date has passed, so stale knowledge surfaces instead of being served as current
(proposal `RULE-2026-0045`).

### `tasks/`

Contains the node's task store (section 9): `inbox/`, `open/` and `completed/`, `recurring/` when needed, and a `STATE.md` the tasks skill generates from the records.

### `skills/`

Contains local capabilities, instructions and executable scripts specific to the node.

### `data/`

Contains structured or generated data owned by the node.

### `sources/`

Contains the canonical Markdown source records of the sources this node owns, and references to source material owned elsewhere. Every source record must reference its immutable raw file.

### `raw/`

Contains the immutable raw files of the sources this node owns, at `raw/YYYY/MM/<source-id>/<original-filename>` (section 11.1).

## 8. Metadata contract

Every Markdown file must begin with YAML front matter.

Exception: immutable evidence files stored in a raw store (section 11.1) – `/memory/raw/` or a node's `raw/` – are exempt. Do not add or rewrite front matter on raw files. Their companion Markdown source records in the `sources/` folder beside that raw store (and any derivatives in other nodes) carry the required metadata and must reference the raw path.

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
- Take a new timestamp from the system clock at the moment of writing – the command's or the script's own clock, never a remembered or rounded time. A timestamp is never later than the moment it was written; the repository preflight validator fails on one more than five minutes ahead of the time it runs.
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
  - /library/skills/xero-access
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
author: brain-owner
priority: normal
due: 2026-08-10
next_review: 2026-08-07
waiting_on: null
schedule: null
project_refs:
  - /memory/projects/example
related_tasks: []
```

### 8.4 Metadata simplicity

Use the smallest metadata set that supports a clear use.

Do not add fields merely because they may be useful later.

When a repeated need appears, add the field to the relevant schema and increment `schema_version`.

Prefer additive changes. Do not remove or rename a field without a migration plan.

Update the `updated` timestamp whenever substantive content or metadata changes.

## 15. Repository integrity checks

Before finishing a substantive update, verify:

- every Markdown file outside a raw store begins with valid YAML front matter
- every Markdown file outside a raw store references `/CONTRACT.md`
- immutable Markdown evidence in a raw store remains unchanged; companion source records in the `sources/` folder beside it carry metadata and `raw_source`
- each durable item has one canonical home
- task owners and statuses are clear
- waiting tasks have `next_review`
- raw source derivatives reference an existing raw path
- shared resources are linked rather than copied
- project state reflects material completed work
- significant changes are recorded: by their commit, and in the log what no commit holds (section 4)
- no credentials were stored
- every README.md lists and accurately summarises each immediate child folder
- protected governance changes have an accepted proposal
- the active `contract_version` is recorded in the repository manifest of each brain repository changed (`/repository-manifest.json`, `/library/repository-manifest.json` and `/memory/repository-manifest.json`)
- no personal data has entered the mechanics repository or the skill library (section 3.4)
- `/CORE.md`, `/CORE-RULES.md` and the rule packs under `/rules/` are current with this contract and `/RULES.md` (`core.py check`)
- the repository preflight validator passes
- every separable, validated, agent-owned durable change has been committed at the required logical checkpoint
- the final report identifies each resulting commit and push status, or gives the exact permitted reason no commit was created

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0019` | Context handoff checkpoint | this file | context is running low, a stage of work ends, a session ends with work in flight, or the context was compacted |

## SMART-RULE-0019 – Context handoff checkpoint

- Write a handoff checkpoint before context runs out, and prefer a **stage boundary** to a
  context threshold: the best moment is immediately after a validated, committed increment and
  **before** starting a new stage of work, because that is when the repository and the agent's
  understanding agree. Take the checkpoint at whichever comes first – the natural boundary, or
  the drain threshold below.
- Never begin a new stage of work when the remaining context is unlikely to carry it to a
  committed, validated state. Checkpoint and say so instead.
- **The conductor stops dispatching before its context runs out; the owner does not have to
  find the moment.** Before opening a delegation run or dispatching a packet, the conductor
  reads its context size from the host and passes it to the delegation script
  (`--context-tokens`). Up to 750 000 tokens it dispatches freely. From 750 000 it **drains**:
  no new run; the workers in flight finish, their results are merged, the checkpoint is written
  and the handover prompt given. From 900 000 no new packet either, and no new stage of its own
  work, until the checkpoint is committed. The thresholds are a guard rail, not a working
  budget: a conductor that only conducts (`SMART-RULE-0024`) rarely reaches them, and reaching
  them is itself a finding to record. The delegation script refuses a run or packet past its
  threshold; only the owner can override it, for a named run or packet, and the override and
  its reason are recorded in the run.
- **An automatic compaction of the conductor's context is a missed checkpoint.** The host hook
  marks it; dispatching stays closed until the conductor has re-read `/CORE.md`,
  `/CORE-RULES.md`, `/memory/RULES.md`, its own entry under the owning node's `## Handover` and
  every rule its work in flight falls under (`Applies when`), written the checkpoint, committed,
  and cleared the marker (`delegation.py checkpoint-done`). The conductor tells the owner in its
  next reply that a compaction happened.
- On a host that cannot report the context size, the conductor passes `--context-unknown`
  with the reason, and drains at its first compaction or after its fourth run in the thread,
  whichever comes first.
- Each run records the context size when it opens and when it closes, so the thresholds are
  tuned from measurements recorded under `/memory/projects/brain-development/`, never by feel.
- A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
  flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
  facts a later session could not re-derive cheaply – especially external-system behaviour
  established by experiment; `LOG.md` with what no commit holds (CONTRACT §4); and the task's
  store (CONTRACT §9) for anything outstanding. It does not list the commits, versions and merges
  since the last checkpoint: Git holds them, and `state.py since` prints them when they are wanted.
- Record **open questions with enough context to act on them**, not just their titles: what is
  unknown, what was already tried, and what would settle it.
- Record **negative findings**. What was ruled out, and the evidence that ruled it out, is as
  valuable as what worked and is never recoverable from code.
- Distinguish what is **verified** from what is **assumed or unverified**, and name where
  uncommitted work lives when it is outside this repository.
- A checkpoint must not present unfinished work as finished. Report the actual state, including
  failures, blocked steps and anything skipped.
- **A state file holds the position, not its history.** Under `## Handover` each live thread has one entry, and it is short: where things stand, what is in flight, what is uncommitted and where, and the next action. A new checkpoint replaces the thread's previous entry, and the entry of a thread that has ended leaves the section; what is replaced or removed moves, unchanged, to `STATE-HISTORY.md` beside the state file (`state.py history`). Detail that only the thread continuing the work needs goes in `HANDOVER-<thread>.md` beside the state file, named by a line in the entry (`state.py detail`). No bootstrap names either file: an agent reads the history only when it needs what happened earlier, and a handover file only when it continues that thread. What happened and why is in the commits and in `LOG.md`, and is not told again in the entry. A `STATE.md` is at most 28,000 characters, so that a host shows it whole: the repository preflight fails on a longer one in the memory and the mechanics, and `state.py check` names one in a project repository, whose own checks may adopt the limit.
- A checkpoint ends with **one handover prompt** for the next thread, and it is a pointer, not a summary: the bootstrap files to read, the owning node's `STATE.md` whose `## Handover` section holds the position, and the single next action. Ten lines at most; nothing in it that a file already says. Everything the successor needs – runs and workers with their packets, branches and pending results, builds and where the owner loaded them, owner steps outstanding, decisions still open, the reminder that a worker's completion notice reaches only the thread that launched it – lives in the thread's entry under `## Handover` in the owning node's `STATE.md`, or in the handover file that entry names (and, for work spanning nodes, one line per other node pointing at its own `## Handover`), written before the prompt and kept current at every checkpoint. Write the prompt under `## Handover prompt` in the same `STATE.md`. Give it in the reply when the thread is handing over to a new one: after a compaction, when the host's context warning fires, at the drain threshold, or when the owner asks. A reply after a checkpoint the thread carries on from says only that the checkpoint is written. The live conductors are named in the `## Handover` of `/memory/projects/brain-development/STATE.md`, and a new thread that finds one asks the owner which thread continues (`SMART-RULE-0048`).
- The active-conductor question is not required for at most one bounded, read-only learning or public-research worker per thread under SMART-RULE-0028, within SMART-RULE-0024’s delegation budget. Workers use no credentials, take no external side effects and write only their separate result artifacts. This exception grants no product-editing, merging or canonical-integration authority.
- Finish with the Git exit check under `SMART-RULE-0014`, so the handoff and the tree agree.
