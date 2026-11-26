---
id: brain-rules-nodes
title: Rule pack: nodes
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

# Rule pack: nodes

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: creating a node, moving one into its own repository, or deciding where an item belongs; creating a durable item, or copying one; declaring a dependency, or configuring a shared skill for a node.

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
knowledge/
tasks/
skills/
data/
sources/
raw/
```

Empty folders are optional until required. The five core Markdown files are required for project, domain and system nodes. A project node has this one layout wherever it lives – in memory at `/memory/projects/<node>/`, or in its own repository's `brain/` folder (section 16.2) – so it moves between the two unchanged.

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

The owner may lay out a structure ahead of its content – for example one node for each part of a business – before three strong reasons apply. Each such node says so at the top of its `STATE.md` (`Placeholder: laid out ahead of its content on <date>.`), and one task with `next_review` covers the structure. At that review, a placeholder that still holds no content of its own is filled, folded into its parent, or kept to a new review date, as the owner decides.

Before creating a node:

1. search for an existing suitable node
2. choose the canonical parent
3. select a node type
4. create the five core Markdown files from templates
5. define concise metadata
6. record dependencies
7. move or create its tasks in its own `tasks/` folder
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
2. after the owner has cleared what will become visible to anyone who can read the repository, move the node's own files – its core files and its `tasks/`, `sources/`, `raw/`, `data/` and `skills/` – unchanged into the repository's `brain/` folder (section 16.2), keeping task identifiers, History and authorship
3. replace the node in memory with a pointer node (section 16.1), which receives, in folders of the same names, whatever the owner keeps private
4. update references to the moved files across memory
5. log the move in the node's new `brain/LOG.md` and in the memory parent node

## 12. Shared resources and dependencies

Store schemas, templates and core skills under `/shared/`, and every other reusable skill in the skill library.

A node declares dependencies in `README.md` using repository-root paths.

Example:

```yaml
knowledge_refs:
  - /memory/domains/finance
skill_refs:
  - /library/skills/xero-access
source_refs:
  - /memory/sources/source-id.md
```

Do not copy shared skills or knowledge into each project.

A project may store configuration for a shared skill, but the general skill remains canonical under `/shared/skills/` or `/library/skills/`. Owner-wide configuration, data and notes for a shared skill live in `/memory/skills/<skill>/` (section 3.5); a mechanics skill never carries them.
