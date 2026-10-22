---
id: PROPOSAL-shared-project-tasks-in-the-repository
title: One structure for every project node, with its own tasks, sources and facts
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-10-22T15:46:11+10:00
updated: 2026-10-22T16:16:15+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.7.0
new_contract_version: 3.0.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /shared/templates/memory-skeleton/tasks/RULES.md
  - /memory/tasks/RULES.md
  - /shared/skills/repository-preflight/SKILL.md
---

# One structure for every project node, with its own tasks, sources and facts

## Summary

Today a project's tasks, sources and many of its facts sit in brain-wide folders of the owner's
memory (`/memory/tasks/`, `/memory/raw/`, `/memory/sources/`, `/memory/KNOWLEDGE.md`), while its
state, log and knowledge sit in the project's node. A collaborator who clones a project repository
sees the node but not the project's tasks.

This proposal gives every project node one structure, wherever it lives: in memory at
`/memory/projects/<node>/`, or in its own repository's `brain/` folder. Each node holds its own
`tasks/` (`inbox/`, `open/`, `completed/`, a generated `STATE.md`), `sources/`, `raw/`, `data/`,
`STATE.md`, `LOG.md` and `KNOWLEDGE.md`. A node therefore moves into its own repository unchanged,
and a project in a repository is ready for collaborators at any moment. CONTRACT §7.1 still decides
when a node needs a repository. `/memory/tasks/` keeps only tasks with no project.

What will be different for the owner and agents:

- **Where a task lives.** A task lives in the `tasks/` folder of the node its first project
  reference names. Task views read every store: the review, the boards and the scheduled review.
- **Privacy is a place.** Whatever a repository's `brain/` holds is visible to everyone who can
  read the repository. What the owner keeps private about a repository project sits in its
  pointer node, in the same layout: private tasks in `tasks/`, private sources in `sources/` and
  `raw/`, and private notes in its `KNOWLEDGE.md`, `STATE.md` or `LOG.md`. A private note about a
  task in a repository goes to `/memory/tasks/private/<task id>.md`.
- **Editing and attribution.** Any brain working on a project may edit its task records. Each
  record keeps `author`, and every change adds a History entry naming who changed what. Git
  conflicts are resolved by hand, and the preflight refuses a half-merged record.
- **Identifiers.** A new task's identifier names its author, `TASK-<author>-YYYY-NNNN`, in every
  store. Existing tasks keep their identifiers.
- **Sources and facts.** A source that one node owns is kept in that node, and so is a fact about
  one project.
- **Scheduled runs.** A task that an app runs on a schedule names the job in a `schedule` field
  and records each run in its History.
- **Migration.** Every task with a project moves into its node, open and completed alike, and so
  do the project sources and project facts. Anything bound for a repository moves only after the
  owner has cleared that repository's list.

The proposal introduces no new rule number. It amends `SMART-RULE-0011`, `SMART-RULE-0019`,
`SMART-RULE-0024`, `SMART-RULE-0025` and `SMART-RULE-0043` in place and keeps their identifiers,
so `rule_id` stays `null`.

## Decisions

The owner's answers to the first design questions, 22 October 2026, in question order:

1. Shared tasks live in `brain/tasks/` in the project repository, in today's task format, not in
   enriched cards.
2. A new task whose first project is a shared project is shared, unless it is marked private.
3. Any brain may edit a shared task record, and Git conflicts are resolved by hand. The record
   keeps `author`. An edit is attributed by a History line naming who changed what. There is no
   single writer and no separate note file.
4. A new shared task's identifier is `TASK-<author>-YYYY-NNNN`. A moved task keeps its identifier.
5. `contract_version` becomes 3.0.0, and each shared project's joining manifest is raised to it.
6. The owner clears each repository's move list, with possibly-private lines flagged, before
   anything is written into that repository.
7. Completed tasks about a shared project move too, into `brain/tasks/completed/`.
8. A task whose owner has left the project is reassigned by the repository's maintainer, recorded
   in History.

## Amendment of 22 Oct

**What was accepted.** The owner accepted texts P1 to P12 of the earlier draft on 22 October 2026.
Those texts covered shared project repositories only, and the record of that acceptance is in the
owner's memory. They were not applied.

**What the owner then asked.** The owner said yes to adding project sources, project facts and
notes of app-scheduled runs to the build. He then widened the request: "treat all projects with
the same structure, instead of having two structures … any project is ready for collaborators at
any moment".

**What the conductor agreed, and the owner did not contradict.** One structure for every project
node, in memory or in its own repository. Each node holds its own `tasks/`, `sources/`, `data/`,
`STATE.md`, `LOG.md` and `KNOWLEDGE.md` in the same layout. The §7.1 tests still decide when a
node needs its own repository. `/memory/tasks/` keeps only tasks with no project. Private notes
keep their private place. Task views read every store.

**What this amendment changes.** The texts below replace the accepted P1 to P12 and need a new
acceptance (CONTRACT §13.2: acceptance covers the change that was shown). The accepted texts map
to the new ones as follows, in the order of the accepted numbers:

- Old P1 (§3.4) becomes P2. It now also covers item 4 and sources.
- Old P2 (§5.4) becomes P5. It now names the node store.
- Old P3 (§9) becomes P10. It now holds the node stores, the identifiers and the pointer node as
  the private place, and drops `private: true` in `/memory/tasks/`.
- Old P4 (§9.3) becomes P11. It gains item 11, the scheduled runs.
- Old P5 (§16.1) becomes P17. It now covers the second paragraph as well.
- Old P6 (§16.2) becomes P18. It now covers every repository project, not only shared ones.
- Old P7 to P10 (`/RULES.md`) become P19 to P22. P22 now names every node's `tasks/`.
- Old P11 (tasks `RULES.md`) becomes P23. Attribution and generated `STATE.md` now apply in every
  store.
- Old P12 (preflight) becomes P25. It now covers every store and drops the memory warning about
  `private: true`.

New texts cover the node layout (P1, P3), project facts (P4), node creation and extraction (P6,
P7), raw evidence in node stores (P8, P13 to P16, P24), task fields (P9) and promotion (P12).

**Choices this draft makes, which the owner has not yet answered.** These are open questions in
the plan, and the draft shows the recommended answer of each:

- A task naming several nodes goes to the node of its first reference.
- Every new task in every store takes `TASK-<author>-YYYY-NNNN`.
- Attribution and generated `STATE.md` apply in every store.
- A raw source about a repository project is private, in the pointer node, unless the owner
  chooses the repository.
- A scheduled job is named in a `schedule` field, and each run adds a History entry.
- The task schema stays at version 0.2 and gains its fields additively.

## Current problem

**Tasks.** CONTRACT §9 makes `/memory/tasks/` the one task store, and §16.2 keeps every owner's
tasks about a project out of its repository. As a result:

- A collaborator sees a card's title and a task identifier, and nothing about the task itself.
- A node that moves into its own repository leaves its tasks behind, so a project has one shape in
  memory and another in a repository.

**Sources and facts.** §11 sends every raw file to `/memory/raw/` and every source record to
`/memory/sources/`. A project's evidence and facts therefore also live outside the project. The
owner wants one structure, so that any project can take a collaborator at any moment.

## Current wording

Each protected text this proposal changes, quoted in full, in file order. The proposed text of each
follows under the same number in the next section.

**C1. CONTRACT §3.1, the node layout.**

> A complete node normally contains:
>
> ```text
> README.md
> RULES.md
> STATE.md
> LOG.md
> KNOWLEDGE.md
> skills/
> data/
> sources/
> ```
>
> Empty folders are optional until required. The five core Markdown files are required for project, domain and system nodes.

**C2. CONTRACT §3.4, items 3 and 4.**

> 3. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, tasks, in-brain projects, contacts, raw files, sources, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.
> 4. **Project repositories.** Bodies of work with their own lifecycle, each in its own repository, checked out as siblings of the brain root (section 16). The memory keeps only a small pointer node for each.

**C3. CONTRACT §4, `### sources/`.**

> ### `sources/`
>
> Contains Markdown source records or project-local references to source material. Every source record must reference its immutable raw file.

**C4. CONTRACT §5.2.**

> A fact, principle, preference, definition or established relationship expected to remain useful.
>
> Store it in the `KNOWLEDGE.md` file or dedicated knowledge node that owns the subject.
>
> Place knowledge according to subject ownership, not the project active when it was mentioned.

**C5. CONTRACT §5.4.**

> An outstanding action that must remain visible after the current interaction.
>
> Create or update a canonical task record under `/memory/tasks/`.

**C6. CONTRACT §7, "Before creating a node".**

> Before creating a node:
>
> 1. search for an existing suitable node
> 2. choose the canonical parent
> 3. select a node type
> 4. create the five core Markdown files from templates
> 5. define concise metadata
> 6. record dependencies
> 7. create or link relevant tasks
> 8. log the creation in the parent node

**C7. CONTRACT §7.1, the extraction steps.**

> Moving a node out of memory later is an extraction, not a copy:
>
> 1. extract the node's folder into a new repository with its history
> 2. move the node's own files into the repository's `brain/` folder (section 16.2)
> 3. replace the node in memory with a pointer node (section 16.1)
> 4. update references to the moved files across memory
> 5. log the move in the node's new `brain/LOG.md` and in the memory parent node

**C8. CONTRACT §8, the raw-file exception.**

> Exception: immutable evidence files stored under `/memory/raw/` are exempt. Do not add or rewrite front matter on raw files. Their companion Markdown source records under `/memory/sources/` (and any project-local derivatives) carry the required metadata and must reference the raw path.

**C9. CONTRACT §8.3, task-specific examples.**

> Task-specific examples:
>
> ```yaml
> status: ready
> owner: brain-owner
> priority: normal
> due: 2026-08-10
> next_review: 2026-08-07
> waiting_on: null
> project_refs:
>   - /memory/projects/example
> ```

**C10. CONTRACT §9, second paragraph.**

> The canonical task store is `/memory/tasks/`. Tasks are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

**C11. CONTRACT §9.3, items 9 and 10.**

> 9. move completed records to `/memory/tasks/completed/`
> 10. preserve task history in the task body and task log

**C12. CONTRACT §9.4, last paragraph.**

> Promote a task into a project when it gains several dependent actions, multiple contributors, meaningful risks, substantial state or its own knowledge.

**C13. CONTRACT §11.1, the first paragraph, the path and the reuse sentence.**

> All uploaded or imported source files must be preserved in `/memory/raw/`. Raw files are owner evidence and never enter the mechanics repository.
>
> ```text
> /memory/raw/YYYY/MM/<source-id>/<original-filename>
> ```
>
> If the same file is uploaded again, detect it by hash and reuse the existing canonical raw record.

**C14. CONTRACT §11.2, items 1, 3 and 4.**

> 1. preserve the original under `/memory/raw/`
> 3. create a canonical Markdown representation under `/memory/sources/`
> 4. create project-local source references or derivatives where needed

**C15. CONTRACT §11.5, first two paragraphs.**

> The raw file and canonical source Markdown are globally accessible.
>
> Projects should reference them.

**C16. CONTRACT §15, the first three bullets.**

> - every Markdown file outside `/memory/raw/` begins with valid YAML front matter
> - every Markdown file outside `/memory/raw/` references `/CONTRACT.md`
> - immutable `/memory/raw/` Markdown evidence remains unchanged; companion source records under `/memory/sources/` carry metadata and `raw_source`

**C17. CONTRACT §16.1, second and third paragraphs.**

> The pointer node may also hold owner-private notes that must not be visible to the project's collaborators, in its own `KNOWLEDGE.md`, `STATE.md` or `LOG.md`. It holds nothing else: no copy of the project's state, rules or knowledge.
>
> Tasks about the project remain canonical in `/memory/tasks/` and reference the pointer node in `project_refs`. A project with collaborators may also run its own issue tracker; an owner task then links the issue instead of copying it.

**C18. CONTRACT §16.2, first paragraph.**

> The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and any `sources/` or `data/` it owns – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules. A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more than one brain works on it. A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the repository, the working branch, the contract and skill versions it assumes, its shared boards, the vault entries each person creates for themselves (names only) and the records to read first; a brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying another brain's memory. Every such brain is a peer: its records carry its author and are rewritten by no other author, its generated pages are not committed, and each owner's tasks about the project stay in that owner's `/memory/tasks/`, drawn only in that owner's memory, never into the repository.

**C19. `/RULES.md`, `SMART-RULE-0019`, the bullet "A checkpoint updates".**

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what happened and why; and `/memory/tasks/` for anything
>   outstanding.

**C20. `/RULES.md`, `SMART-RULE-0024`, the bullet "Delegate through".**

> - Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
>   files rather than copying prose, and a result record the worker writes back. Packets and
>   results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
>   must outlive the session is an ordinary `/memory/tasks/` record with `waiting_on` and `next_review`.

**C21. `/RULES.md`, `SMART-RULE-0043`, the bullet "A card".**

> - A **card** is a task record under `/memory/tasks/` with a `team`. A team thread takes a card
>   by setting `claimed_by` to its session name, `claimed_at` from the clock and
>   `status: in_progress`, and committing that record on its own (`tasks.py claim`); a conflict
>   on that commit means another thread took it first, and the loser moves on. A card leaving
>   `in_progress` loses its claim (`tasks.py release`, or completion). The task record stays the
>   only record: who holds a card lives nowhere else.

**C22. `/RULES.md`, *Contract restatements*, one line.**

> - Treat `/memory/tasks/` as the canonical task system. (CONTRACT §9)

**C23. `/shared/templates/memory-skeleton/tasks/RULES.md` and `/memory/tasks/RULES.md` (identical bodies), three bullets.**

> - Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record under `/memory/tasks/open/` once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
> - `/memory/tasks/STATE.md` enumerates every record under `/memory/tasks/open/`: one entry per task carrying
>   its ID and the status word from its front matter. Update the entry when the record changes
>   and remove it when the record moves to `/memory/tasks/completed/`. A task absent from the file, or
>   listed with a different status word than its record, is a defect to fix in the same turn.
> - Move completed and cancelled tasks to `/memory/tasks/completed/`.

**C24. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, the raw bullet.**

> - skip immutable `/memory/raw/` (and `/raw/` in a brain without a separate memory) Markdown evidence (companion source records remain validated)

**C25. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*.** No current bullet
covers task stores other than `/memory/tasks/`. The new bullet goes after the bullet that begins
"**timestamps ahead of the clock (CONTRACT §8.2):**".

## Proposed wording or exact diff

**P1. CONTRACT §3.1, the node layout.**

> A complete node normally contains:
>
> ```text
> README.md
> RULES.md
> STATE.md
> LOG.md
> KNOWLEDGE.md
> tasks/
> skills/
> data/
> sources/
> raw/
> ```
>
> Empty folders are optional until required. The five core Markdown files are required for project, domain and system nodes. A project node has this one layout wherever it lives – in memory at `/memory/projects/<node>/`, or in its own repository's `brain/` folder (section 16.2) – so it moves between the two unchanged.

**P2. CONTRACT §3.4, items 3 and 4.**

> 3. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, the tasks that belong to no project, in-brain projects with their own tasks, sources and knowledge, contacts, the raw files and sources that belong to no single node, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.
> 4. **Project repositories.** Bodies of work with their own lifecycle, each in its own repository, checked out as siblings of the brain root (section 16). Each holds its project node, tasks and sources included, in its `brain/` folder. The memory keeps a small pointer node for each, holding only what the owner keeps private about the project.

**P3. CONTRACT §4, `### sources/` replaced, and `### tasks/` and `### raw/` added.** `### tasks/`
goes before `### skills/`; `### raw/` goes after `### sources/`, as the last folder.

> ### `tasks/`
>
> Contains the node's task store (section 9): `inbox/`, `open/` and `completed/`, `recurring/` when needed, and a `STATE.md` the tasks skill generates from the records.

> ### `sources/`
>
> Contains the canonical Markdown source records of the sources this node owns, and references to source material owned elsewhere. Every source record must reference its immutable raw file.

> ### `raw/`
>
> Contains the immutable raw files of the sources this node owns, at `raw/YYYY/MM/<source-id>/<original-filename>` (section 11.1).

**P4. CONTRACT §5.2.**

> A fact, principle, preference, definition or established relationship expected to remain useful.
>
> Store it in the `KNOWLEDGE.md` file or dedicated knowledge node that owns the subject.
>
> Place knowledge according to subject ownership, not the project active when it was mentioned. A fact about one project belongs in that project node's `KNOWLEDGE.md` – in its repository when it has one – and not in `/memory/KNOWLEDGE.md` or another node, unless the owner keeps it private, when it goes to the project's pointer node (section 16.1).

**P5. CONTRACT §5.4.**

> An outstanding action that must remain visible after the current interaction.
>
> Create or update a canonical task record in its task store (section 9): the `tasks/` folder of the node its first project reference names, or `/memory/tasks/` for a task with no project.

**P6. CONTRACT §7, "Before creating a node".**

> Before creating a node:
>
> 1. search for an existing suitable node
> 2. choose the canonical parent
> 3. select a node type
> 4. create the five core Markdown files from templates
> 5. define concise metadata
> 6. record dependencies
> 7. move or create its tasks in its own `tasks/` folder
> 8. log the creation in the parent node

**P7. CONTRACT §7.1, the extraction steps.**

> Moving a node out of memory later is an extraction, not a copy:
>
> 1. extract the node's folder into a new repository with its history
> 2. after the owner has cleared what will become visible to anyone who can read the repository, move the node's own files – its core files and its `tasks/`, `sources/`, `raw/`, `data/` and `skills/` – unchanged into the repository's `brain/` folder (section 16.2), keeping task identifiers, History and authorship
> 3. replace the node in memory with a pointer node (section 16.1), which receives, in folders of the same names, whatever the owner keeps private
> 4. update references to the moved files across memory
> 5. log the move in the node's new `brain/LOG.md` and in the memory parent node

**P8. CONTRACT §8, the raw-file exception.**

> Exception: immutable evidence files stored in a raw store (section 11.1) – `/memory/raw/` or a node's `raw/` – are exempt. Do not add or rewrite front matter on raw files. Their companion Markdown source records in the `sources/` folder beside that raw store (and any derivatives in other nodes) carry the required metadata and must reference the raw path.

**P9. CONTRACT §8.3, task-specific examples.**

> Task-specific examples:
>
> ```yaml
> status: ready
> owner: brain-owner
> author: brain-owner
> priority: normal
> due: 2026-08-10
> next_review: 2026-08-07
> waiting_on: null
> schedule: null
> project_refs:
>   - /memory/projects/example
> ```

**P10. CONTRACT §9, second paragraph, replaced by four paragraphs and a list.**

> Every task lives in exactly one task store, and that record is canonical:
>
> - the `tasks/` folder of a node (section 3.1) holds every task whose first project reference names that node: `/memory/projects/<node>/tasks/` for a node in memory, and `brain/tasks/` for a project in its own repository (section 16.2); a reference names the deepest node it is in, and a reference to a pointer node names its repository;
> - `/memory/tasks/` holds the tasks with no project reference.
>
> Every store has the same folders, record format, statuses and rules, and a `STATE.md` generated from its records, so a node moves between memory and its own repository unchanged. Task views – the task review, the boards, the scheduled review – read every store the brain can reach.
>
> Every task record carries `author`, the brain that created it, which never changes. A new task takes an identifier that names its author, `TASK-<author>-YYYY-NNNN`, where `<author>` is the creating brain's `owner_short_name` in lower case and the number is the next in that author's one sequence across every store, so two brains never number two tasks alike. An existing task keeps its identifier wherever it moves.
>
> Privacy is a place, not a flag. Whatever a repository's `brain/` holds can be read by everyone who can read the repository, now or once a collaborator joins. An owner-private task about a project in its own repository is kept in the pointer node's `tasks/` folder (section 16.1), and an owner-private note about a task in a repository is kept in `/memory/tasks/private/<task id>.md`, which names the task. Neither is ever drawn into the repository.
>
> Tasks in memory are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

**P11. CONTRACT §9.3, items 9 to 11.**

> 9. move completed records to the `completed/` folder of their store
> 10. preserve task history in the task body and task log
> 11. when an app or the operating system runs work for the task on a schedule, name the job in the task's `schedule` field (the app, the job's name and its cadence), and record the outcome of each run as a History entry

**P12. CONTRACT §9.4, last paragraph.**

> Promote a task into a project when it gains several dependent actions, multiple contributors, meaningful risks, substantial state or its own knowledge. The task then moves into the new node's `tasks/` folder.

**P13. CONTRACT §11.1, the first paragraph, the path and the reuse sentence.**

> All uploaded or imported source files must be preserved in a raw store. Raw files are owner or project evidence and never enter the mechanics repository. A source owned by one node in memory goes to that node's `raw/`. A source about a project in its own repository goes to the pointer node's `raw/`, unless the owner chooses the repository's `brain/raw/`, because raw evidence often holds other people's data. Any other source goes to `/memory/raw/`.
>
> ```text
> <raw store>/YYYY/MM/<source-id>/<original-filename>
> ```
>
> If the same file is uploaded again, detect it by hash across every raw store the brain can reach and reuse the existing canonical raw record.

**P14. CONTRACT §11.2, items 1, 3 and 4.**

> 1. preserve the original in its raw store (section 11.1)
> 3. create a canonical Markdown representation in the `sources/` folder beside that raw store
> 4. create source references or derivatives in other nodes where needed

**P15. CONTRACT §11.5, first two paragraphs.**

> The raw file and canonical source Markdown are accessible to every node that can resolve their path.
>
> Other nodes should reference them. A node in a project repository cannot resolve a `/memory/` path (section 16.2), so a source it needs belongs in its own `raw/` and `sources/`.

**P16. CONTRACT §15, the first three bullets.**

> - every Markdown file outside a raw store begins with valid YAML front matter
> - every Markdown file outside a raw store references `/CONTRACT.md`
> - immutable Markdown evidence in a raw store remains unchanged; companion source records in the `sources/` folder beside it carry metadata and `raw_source`

**P17. CONTRACT §16.1, second and third paragraphs.**

> The pointer node may also hold what the owner keeps private about the project, in the layout of section 3.1: notes in its own `KNOWLEDGE.md`, `STATE.md` or `LOG.md`, private tasks in `tasks/`, and private sources in `sources/` and `raw/`. It holds nothing else: no copy of the project's state, rules, knowledge, tasks or sources.
>
> Tasks about the project, open and completed alike, are kept in the repository's `brain/tasks/` (sections 9 and 16.2), except the owner's private tasks and private notes about it. A project with collaborators may also run its own issue tracker; a task then links the issue instead of copying it.

**P18. CONTRACT §16.2, first paragraph.**

> The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and its `tasks/`, `sources/`, `raw/` and `data/` in the layout of section 3.1 – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules. A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more than one brain works on it. A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the repository, the working branch, the contract and skill versions it assumes, its shared boards, the vault entries each person creates for themselves (names only) and the records to read first; a brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying another brain's memory. Every such brain is a peer: its records carry its author and are rewritten by no other author, a task record excepted as below, and its generated pages are not committed. Any brain that works on the project may change a task record in `brain/tasks/`; every change adds a History entry `- <timestamp> – <author>: <what changed>`, so each edit names the brain that made it, and a Git conflict in a record is resolved by hand, keeping the History entries of both sides in time order. A task whose `owner` has left the project is reassigned by the repository's maintainer, with a History entry. Each owner's private tasks, notes and sources about the project stay in that owner's memory (section 16.1) and are never drawn into the repository.

**P19. `/RULES.md`, `SMART-RULE-0019`.**

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what happened and why; and the task's store
>   (CONTRACT §9) for anything outstanding.

**P20. `/RULES.md`, `SMART-RULE-0024`.**

> - Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
>   files rather than copying prose, and a result record the worker writes back. Packets and
>   results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
>   must outlive the session is an ordinary task record (CONTRACT §9) with `waiting_on` and
>   `next_review`.

**P21. `/RULES.md`, `SMART-RULE-0043`.**

> - A **card** is a task record in a task store (CONTRACT §9) with a `team`. A team thread takes a
>   card by setting `claimed_by` to its session name, `claimed_at` from the clock and
>   `status: in_progress`, and committing that record on its own, in the repository that holds it
>   (`tasks.py claim`); a conflict on that commit means another thread took it first, and the
>   loser moves on. A card leaving `in_progress` loses its claim (`tasks.py release`, or
>   completion). The task record stays the only record: who holds a card lives nowhere else.

**P22. `/RULES.md`, *Contract restatements*.**

> - Treat the task stores of CONTRACT §9 – every node's `tasks/` and `/memory/tasks/` – as the canonical task system. (CONTRACT §9)

**P23. `/shared/templates/memory-skeleton/tasks/RULES.md` and `/memory/tasks/RULES.md`.** The three
bullets become the first three below, and one bullet is added after them, last. The `scope`
front-matter value of the template stays `/memory/tasks` because the same rules govern every store
by CONTRACT §9:

> - Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record in the `open/` folder of its store (CONTRACT §9) once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
> - Each store's `STATE.md` enumerates every record under its `open/` folder: one entry per task carrying
>   its ID and the status word from its front matter. It is generated from the records by the tasks
>   skill whenever a record changes and is never edited by hand; a task absent from it, or listed
>   with a different status word than its record, is a defect to fix in the same turn by generating
>   it again, and a Git conflict in it is resolved the same way.
> - Move completed and cancelled tasks to the `completed/` folder of their store.
> - In every store, every change to a record sets `updated` and adds a History entry
>   `- <timestamp> – <author>: <what changed>`, with the same timestamp, so the newest History
>   entry always names who made the latest change. The record's `author` names the brain that
>   created it and never changes. A Git conflict in a record is resolved by hand before anything
>   else is committed: keep the History entries of both sides in time order, decide each
>   conflicting field (ask the task's `owner` when the right value is not clear), add a History
>   entry naming the resolver, and generate `STATE.md` again.

**P24. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, the raw bullet.**

> - skip immutable Markdown evidence in every raw store – `/memory/raw/` and the `raw/` folder of every memory node (and `/raw/` in a brain without a separate memory) – while companion source records remain validated

**P25. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, new bullet.**

> - **task stores (CONTRACT §9):** check `/memory/tasks/`, the `tasks/` folder of every node under `/memory/projects/`, and the `brain/tasks/` of every pointer node's repository that is checked out – with `--project <repository>`, that repository's store alone. Fail on a record with missing required metadata or no `author`, an invalid status or one its folder does not hold, an identifier used twice across the stores checked, a record whose first project reference does not name the node that holds it (or, in `/memory/tasks/`, any project reference), a `/memory/` path anywhere in a repository's `brain/tasks/`, a Git conflict marker (a line beginning `<<<<<<< ` or `>>>>>>> `) in a store or a path in one that Git reports as unmerged, a record whose `updated` is later than its newest History entry of the form `- <timestamp> – <author>: <what changed>` (an edit nobody is named for), or a store's `STATE.md` that differs from the one the tasks skill generates. Run from the brain root, a failure in a repository's store is reported as a warning, because that repository runs its own check

`contract_version` 2.7.0 becomes 3.0.0: the canonical home of whole classes of existing records
moves, and existing content needs a coordinated migration (CONTRACT §13.3, major). The manifests
`/repository-manifest.json`, `/library/repository-manifest.json` and
`/memory/repository-manifest.json` record 3.0.0. Each project repository with a `brain/JOINING.md`
raises `minimum_contract_version` to 3.0.0, so a peer brain that does not yet know node task stores
is told so when it joins or syncs.

## Reason

The owner's instructions:

- All task-related details of a shared task belong in the shared project.
- Every project has the same structure, so that any project is ready for collaborators at any
  moment.
- Project sources, project facts and notes of scheduled runs belong in the build.

Two structures cost twice. A project in memory and a project in a repository are read by
different code paths. An extraction rewrites every task's reference and leaves the tasks behind.
A collaborator added later finds the project's working memory missing.

With one layout:

- Extraction is a move.
- The boards and the review read one shape from several roots.
- The §16.2 privacy guarantee is kept by placing private content in the pointer node, not by
  keeping every task out of the repository.

**Why a task store in each node, not enriched cards.** A card and a task are different records:

- A card is one owner request travelling to a verdict, retired by a verdict or a release.
- A task is an outcome with one accountable owner, statuses, a review date and a history,
  completed by its criteria.

A store in the existing format reuses the one parser (`task_records.load_tasks`), the one set of
commands and the one board routing, with more roots (`SMART-RULE-0018`).

**Why any brain may edit, with every edit named.** The owner chose this (Decisions, 3). The fetch
before every write keeps conflicts rare, and the preflight refuses a record left half-merged.
Attribution lives in the record: `author` says who created it, and History says who changed what.

**Why `TASK-<author>-YYYY-NNNN` in every store, recommended over keeping `TASK-YYYY-NNNN` in
memory.**

- A node in memory can be shared at any moment. Its new tasks then need no renaming.
- One identifier pattern means no rule depends on where a task lives.
- The author's one sequence still gives each task a short number for conversation.
- The cost is a longer identifier for the owner's own tasks.

**Why sources of a repository project default to the pointer node.** Raw evidence (bills,
contracts, exports) often carries third parties' personal data, and a line pushed to a repository
cannot be recalled. Facts and tasks are written by the owner's agents and can be screened as they
are written. Raw files are not written by the owner's agents, so they are private until the owner
says otherwise.

## Scope and behavioural consequences

- **Scope.** Every node a task's first project reference names, in memory or in a repository.
  `/memory/tasks/` keeps tasks with no project. A domain or system node that a task names holds
  that task too, by the same rule.
- **Which store a new task goes to.** `tasks.py new` looks at the first `--project`:
  - It writes to the `tasks/` of the deepest node that reference is in.
  - For a pointer node, it writes to its repository's `brain/tasks/`, or with `--private` to the
    pointer node's own `tasks/`.
  - In a repository, `project_refs` name `<repository>:brain` and other repository references. The
    task's `/memory/` references are kept in the owner's companion file
    `/memory/tasks/private/<task id>.md`.
- **Finding the stores.** One function in the tasks skill lists them: `/memory/tasks/`, every
  memory node's `tasks/`, and the `brain/tasks/` of every pointer node whose `local_path` resolves
  to a checkout. Every reader calls it: review, `check`, `next-id`, the scheduled review, the
  boards, the card detail, the join report and the preflight. No second registry is kept.
- **Writing.**
  - Before writing to a repository's store, `tasks.py` fetches. It refuses when the checkout is
    behind its upstream.
  - Every changing command (`done`, `do-now`, `note`, `claim`, `release`, a new `edit`) sets
    `updated`, adds the attributed History entry and regenerates the store's `STATE.md`.
  - A record with conflict markers is refused.
  - `note --private` writes to the companion file.
  - Commits and pushes follow each repository's Git rules (CONTRACT §16.3).
- **Scheduled runs.** A task carries `schedule` (app, job, cadence). `tasks.py note --run <job>`,
  called by the job or by the agent after it, adds the run's History entry.
- **Reading.** `tasks.py review` lists this brain's tasks from every store. `--all` adds tasks
  owned by others.
- **Boards.**
  - A task routes to the board of the node that holds it, or an ancestor's, as the deepest match
    today. Otherwise it goes to the personal board.
  - A shared board's page draws its repository's tasks and still refuses any `/memory/` path. The
    owner's page for that board draws the pointer node's private tasks.
  - Every open task is drawn once.
- **Sources and facts.** The raw-file-ingestion skill writes a new source to the raw store P13
  names. A fact about one project goes to that node's `KNOWLEDGE.md` (P4).
- **Joining.** `brain/JOINING.md` lists `brain/tasks/STATE.md` in `read_first` after
  `brain/STATE.md#Handover`. `join.py` reports the store and the joining person's tasks.
- **Extraction.** Extraction moves `tasks/`, `sources/` and `raw/` with the node (P7).

## Risks and conflicts

Ordered by severity, worst first.

1. **Private content leaking into a repository.** A pushed line cannot be recalled from a clone.
   Mitigations:
   - Privacy is a place.
   - Raw evidence of a repository project is private by default (P13).
   - The migration and every extraction show the owner each repository-bound task, source and
     fact, with possibly-private lines flagged (a `/memory/` path, an amount, a contact detail, a
     personal-data pattern, an owner term). Nothing moves until the owner clears it.
   - `tasks.py` refuses a `/memory/` path in a repository record.
   - The preflight's project mode fails on one, and runs in each repository's pre-commit hook.
   - A public repository makes its tasks public, and `tasks.py new` says so once.
2. **Two brains editing one record.** The second push meets a Git conflict. Mitigations:
   - `tasks.py` fetches before every write and refuses a checkout that is behind.
   - The resolution is fixed by P23.
   - `tasks.py` refuses a conflicted record.
   - The preflight fails on conflict markers or an unmerged path.
   - A task record is hand-written, so the conflict is never auto-resolved.
   - Claims keep `SMART-RULE-0043`'s rule that the second commit loses.
   - Each `STATE.md` is generated, so a conflict there is resolved by generating it again
     (`SMART-RULE-0034`).
3. **An edit nobody is named for.** Every `tasks.py` change writes the History entry. The
   preflight fails a record whose `updated` is later than its newest attributed entry. In memory
   this also catches hand edits by the owner; the fix is one History line.
4. **Many stores, more places to look.** 15 task stores replace one (see the plan). Every reader
   goes through one store list. The preflight fails on a task in the wrong store and on a
   duplicate identifier. A store the brain cannot reach (a repository not checked out) is not
   read, and the review says so.
5. **Identifier sequence across stores.** An author's next number is taken across every store the
   brain can reach and the claims folder. A repository not checked out could hold a higher number
   of the same author; the preflight's duplicate check catches the clash.
6. **Large raw files in repositories.** A source the owner moves into `brain/raw/` adds binary
   weight. CONTRACT §7.1 test 4 still applies, and the default keeps raw files in memory.
7. **Version skew.** A peer brain on contract 2.7.0 keeps tasks in its own memory.
   `minimum_contract_version: 3.0.0` makes `join.py` and `sync.py` report it.
8. **Conflicts with existing texts.** These are skill text, not protected, and change in the
   build:
   - the owner-board paragraph *What never enters the repository*
   - its failure sentence about a task on a shared page
   - the tasks and raw-file-ingestion skill paths
   - the node and pointer README templates

   The worker brief digests none of the amended bullets (`SMART-RULE-0007`). A pointer node with
   in-memory child nodes beneath it (seen in one owner's memory) is unaffected: each child is a
   node with its own `tasks/`.

## Migration

Runs after the owner accepts this amended proposal and the build is merged and tested. Each step
names what it reads and writes, and memory and each repository are committed separately.

1. **Memory nodes first.** No privacy review is needed, because nothing leaves memory.
   `tasks.py migrate --node <node> --dry-run`, then without `--dry-run`, moves every task (inbox,
   open, recurring, completed) whose first project reference names the node into
   `<node>/tasks/<same folder>/`. Each move:
   - keeps the identifier and file name;
   - adds `author: <owner short name>`;
   - sets `updated`;
   - adds `- <timestamp> – <owner short name>: moved into the node's tasks/
     (PROPOSAL-shared-project-tasks-in-the-repository)`.

   The command then generates both `STATE.md` files.
2. **Repository nodes, one at a time, smallest first.**
   - **Prepare.** Create `brain/tasks/` and add it to `brain/README.md`. Where `brain/JOINING.md`
     exists, add `brain/tasks/STATE.md` to `read_first` and raise `minimum_contract_version`. Add
     `preflight.py --project` to the pre-commit hook.
   - **Inventory.** `migrate --repo <repository> --dry-run` lists the open, then the completed
     tasks, with possibly-private lines flagged.
   - **Owner clears.** The owner clears the list. Tasks kept private go to the pointer node's
     `tasks/`, and private lines go to `/memory/tasks/private/<task id>.md`. Silence moves nothing.
   - **Move.** Then the move as in step 1, with `project_refs` rewritten to repository
     references.
3. **Sources.** Each record in `/memory/sources/` whose `project_refs` name one node moves with
   its raw folder into that node's `sources/` and `raw/`. For a repository project, it moves into
   the pointer node by default, and into `brain/` only for sources the owner names. Hashes are
   re-verified after the move. References across memory are updated, and repository records
   reference repository paths only.
4. **Facts.** A worker lists claims in `/memory/KNOWLEDGE.md` and in pointer nodes'
   `KNOWLEDGE.md` that concern one project. The owner clears the repository-bound ones. Each
   moves with its date and source line (CONTRACT §4) to the node's `KNOWLEDGE.md`, and the old
   line is marked superseded with a pointer.
5. **Record.**
   - Removed memory files go to `/memory/governance/removed-files.md`.
   - Add one entry each in `/memory/tasks/LOG.md`, each node's `LOG.md` and each repository's
     `brain/LOG.md`.
   - Update each pointer node's *what lives where* line.
6. **Show them again.**
   - Rebuild the boards.
   - Run `task_board.py check` (each open task once).
   - `tasks.py review` lists every moved task.
   - Card task links resolve.
   - Pull before pushing (CONTRACT §16.3).

Tasks that name several nodes go with their first reference and keep the others as references.

## Rollback

- **Before migration:** revert the governance and build commits.
- **After migration:** `tasks.py migrate --reverse` (per node or repository), and the same for
  sources and facts. It moves each record back to its former home with every History entry
  others added and restores `/memory/` references from the companion file. Tasks other brains
  created in a repository are listed for the owner and left there. Then revert the governance and
  build commits.
- **What cannot be undone:** content pushed to a repository stays in its Git history and in every
  clone, which is why the owner clears every repository-bound list before any write.

## Validation

1. **Unit tests**, fictional data only (`SMART-RULE-0008`), authors `sam` and `bob`:
   - **tasks:** store discovery; routing of `new` by the deepest node and by pointer node; author
     identifiers across stores; refusal when behind; attributed History on every change; refusal
     of conflicted records; `--private`; generated `STATE.md` per store; `schedule` and
     `note --run`; refusal of `/memory/` paths in a repository.
   - **owner-board:** routing from stores; each open task once; the shared page draws repository
     tasks and refuses memory content; card task links.
   - **join-project.**
   - **raw-file-ingestion:** the raw store chosen per P13, and the hash reused across stores.
   - **repository-preflight:** each P25 failure, the P24 skip, and warning versus failure from the
     brain root.
2. **An extraction test.** A fictional memory node with tasks, sources and a fact is extracted to
   a repository. The node's files arrive unchanged, the preflight passes in both places, and the
   boards show the same tasks before and after.
3. **A two-brain join test.**
   - `bob` joins, sees and completes `sam`'s task (History names `bob`) and creates
     `TASK-bob-2026-0001`.
   - `sam`'s private note and private task are in no repository file.
   - A deliberate conflict fails the preflight until it is resolved per P23.
4. **The board build:** `build_status.py --all`, `task_board.py route` and `task_board.py check`.
5. **The repository preflight:** `preflight.py` on the mechanics, library and memory, and
   `preflight.py --project <repository>` on each repository after its migration.
6. **Migration counts, per node and folder:** before equals after. Every identifier is found
   exactly once. No repository `brain/` file contains `/memory/`. Every moved raw file's hash
   matches its record.

## Acceptance

The owner accepted P1 to P12 of the earlier draft on 22 October 2026 (record in the owner's
memory); they were never applied. This amended set has not yet been presented. Ask one direct
question that identifies this proposal and its amendment of 22 October. Do not treat the earlier
acceptance, silence, adjacent approval or general agreement as acceptance of the amended set.

## Implementation record

None. Nothing in this proposal is active.

### Build, after acceptance

Code changes in the core skills, listed for a later build. Each package names the files it
writes. The build touches stored data and several modules, so it starts from an approved plan
(`SMART-RULE-0024`).

- **tasks** (`/shared/skills/tasks/`):
  - a new `task_stores.py`: the one store list, covering memory nodes, pointer repositories and
    `/memory/tasks/`;
  - `task_records.Task` gains its store;
  - `tasks.py`: routing of `new` by node, `--private`, author identifiers in `next-id`, the
    attributed History entry on every change, `edit`, `note --run`, refusal of conflicted
    records, fetch-before-write, a generated `STATE.md` per store, `review --all`, and `migrate`
    (`--node`, `--repo`, `--dry-run`, `--reverse`);
  - `scheduled_review.py` reads every store;
  - the task template gains `author` and `schedule`;
  - `SKILL.md` and tests.
- **owner-board** (`/shared/skills/owner-board/`):
  - `task_board.py` loads every store and routes by store node;
  - `build_status.py` draws a shared page's tasks and keeps the refusal of memory content;
  - `card_detail.py` links records in any store;
  - `task_actions.py` and `apply_events.py` apply actions through the tasks skill, attributed;
  - `reconcile.py` check 10 reads the store of the board's node;
  - `SKILL.md` and tests.
- **join-project** (`/shared/skills/join-project/`): `joining.py` and `join.py` report the store;
  the two-brain test; `SKILL.md`.
- **raw-file-ingestion** (`/shared/skills/raw-file-ingestion/`): choose the raw store per P13,
  deduplicate by hash across stores, and add a `migrate` command for sources; `SKILL.md` and
  tests.
- **repository-preflight** (`/shared/skills/repository-preflight/`): the `--project` mode, the
  P25 checks and the P24 skip; *Failure behaviour* (P24, P25, protected); tests.
- **templates** (`/shared/templates/`):
  - `node-README.template.md` names `tasks/` and `raw/`;
  - the pointer README template names its private `tasks/`, `sources/` and `raw/`;
  - the memory skeleton gains `tasks/private/`;
  - a `tasks/README.md` template for a node store.
