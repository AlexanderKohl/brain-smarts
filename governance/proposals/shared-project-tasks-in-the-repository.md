---
id: PROPOSAL-shared-project-tasks-in-the-repository
title: Shared project tasks live in the project repository
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-10-22T15:46:11+10:00
updated: 2026-10-22T15:57:59+10:00
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

# Shared project tasks live in the project repository

## Summary

Today every task is kept in the owner's own memory, `/memory/tasks/`, including the tasks about a
project that a collaborator's brain also works on. The project repository's shared board carries
only a card's title and the task's identifier, so a collaborator never sees a task's outcome,
position, next action, history or review date.

This proposal moves those tasks into the project. A project repository that more than one brain
works on gains a task store, `brain/tasks/`, with the same folders, record format, statuses and
rules as `/memory/tasks/`. A task whose first project is that project lives there by default, so
every brain that clones the repository reads the whole task. What stays private stays in memory:
an owner-private task about the project stays in `/memory/tasks/` marked `private: true`, and an
owner-private note about a shared task goes to `/memory/tasks/private/<task id>.md`. Privacy is a
place, not a flag: nothing in the repository is private.

What will be different for the owner and agents:

- `tasks.py new` on a shared project writes the record into the repository, and the agent commits
  and pushes it there after pulling. `--private` keeps it in memory.
- Any brain that works on the project may change a shared task record. The record keeps its
  `author` (the brain that created it), and every change adds a History line naming the brain
  that made it and what it changed. Two brains changing one record before either pulls is a Git
  conflict, resolved by hand; the preflight refuses a record left with conflict markers.
- A new shared task takes an identifier that names its author, `TASK-<author>-YYYY-NNNN`; a task
  moved in from memory keeps the identifier it has.
- The task review, the boards, the card detail and the join command read both stores. The shared
  board page shows the project's tasks to every brain; the owner's own page for that board shows
  only the owner's private tasks about it.
- The open and completed tasks of each shared project are moved once, keeping their identifiers,
  history and authorship, after the owner has cleared each repository's move list.

No rule number is new. The proposal amends `SMART-RULE-0019`, `SMART-RULE-0024`,
`SMART-RULE-0025` and `SMART-RULE-0043` in place and keeps their identifiers, so `rule_id` stays
`null`.

## Decisions

The owner's answers to the design questions, 22 October 2026, which this draft follows (ordered
by question number):

1. Shared tasks live in `brain/tasks/` in the project repository, in today's task format, not in
   enriched cards.
2. A new task whose first project is a shared project is shared unless it is marked private.
3. Any brain may edit a shared task record; Git conflicts are resolved by hand. The record keeps
   `author`, and an edit is attributed by a History line naming who changed what. There is no
   single writer and no separate note file.
4. A new shared task's identifier is `TASK-<author>-YYYY-NNNN`; a moved task keeps its identifier.
5. `contract_version` 3.0.0, and each shared project's joining manifest is raised to it.
6. The owner clears each repository's move list, with possibly-private lines flagged, before
   anything is written into that repository.
7. Completed tasks about a shared project move too, into `brain/tasks/completed/`.
8. A task whose owner has left the project is reassigned by the repository's maintainer, recorded
   in History.

## Current problem

CONTRACT §16.2 ends: "each owner's tasks about the project stay in that owner's `/memory/tasks/`,
drawn only in that owner's memory, never into the repository", and §16.1 keeps tasks about a
project canonical in `/memory/tasks/`. The owner-board skill enforces this: a shared page that
would carry a task is refused, and a card's detail on a repository board says that the task record
is kept in the owner's own brain. The result is that the person a project is shared with can see
that work exists, but not what it is for, where it stands, what happens next or when it comes back.
The owner has asked that all the details of a shared task be kept in the shared project.

## Current wording

Each protected text this proposal changes, quoted in full, in file order. The proposed text of
each follows under the same number in the next section.

**C1. CONTRACT §3.4, item 3.**

> 3. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, tasks, in-brain projects, contacts, raw files, sources, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.

**C2. CONTRACT §5.4.**

> An outstanding action that must remain visible after the current interaction.
>
> Create or update a canonical task record under `/memory/tasks/`.

**C3. CONTRACT §9, second paragraph.**

> The canonical task store is `/memory/tasks/`. Tasks are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

**C4. CONTRACT §9.3, item 9.**

> 9. move completed records to `/memory/tasks/completed/`

**C5. CONTRACT §16.1, third paragraph.**

> Tasks about the project remain canonical in `/memory/tasks/` and reference the pointer node in `project_refs`. A project with collaborators may also run its own issue tracker; an owner task then links the issue instead of copying it.

**C6. CONTRACT §16.2, first paragraph.**

> The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and any `sources/` or `data/` it owns – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules. A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more than one brain works on it. A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the repository, the working branch, the contract and skill versions it assumes, its shared boards, the vault entries each person creates for themselves (names only) and the records to read first; a brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying another brain's memory. Every such brain is a peer: its records carry its author and are rewritten by no other author, its generated pages are not committed, and each owner's tasks about the project stay in that owner's `/memory/tasks/`, drawn only in that owner's memory, never into the repository.

**C7. `/RULES.md`, `SMART-RULE-0019`, the bullet "A checkpoint updates".**

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what happened and why; and `/memory/tasks/` for anything
>   outstanding.

**C8. `/RULES.md`, `SMART-RULE-0024`, the bullet "Delegate through".**

> - Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
>   files rather than copying prose, and a result record the worker writes back. Packets and
>   results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
>   must outlive the session is an ordinary `/memory/tasks/` record with `waiting_on` and `next_review`.

**C9. `/RULES.md`, `SMART-RULE-0043`, the bullet "A card".**

> - A **card** is a task record under `/memory/tasks/` with a `team`. A team thread takes a card
>   by setting `claimed_by` to its session name, `claimed_at` from the clock and
>   `status: in_progress`, and committing that record on its own (`tasks.py claim`); a conflict
>   on that commit means another thread took it first, and the loser moves on. A card leaving
>   `in_progress` loses its claim (`tasks.py release`, or completion). The task record stays the
>   only record: who holds a card lives nowhere else.

**C10. `/RULES.md`, *Contract restatements*, one line.**

> - Treat `/memory/tasks/` as the canonical task system. (CONTRACT §9)

**C11. `/shared/templates/memory-skeleton/tasks/RULES.md` and `/memory/tasks/RULES.md` (identical bodies), three bullets.**

> - Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record under `/memory/tasks/open/` once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
> - `/memory/tasks/STATE.md` enumerates every record under `/memory/tasks/open/`: one entry per task carrying
>   its ID and the status word from its front matter. Update the entry when the record changes
>   and remove it when the record moves to `/memory/tasks/completed/`. A task absent from the file, or
>   listed with a different status word than its record, is a defect to fix in the same turn.
> - Move completed and cancelled tasks to `/memory/tasks/completed/`.

**C12. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*.** No current bullet
covers a task store in a project repository. The new bullet goes after the bullet that begins
"**timestamps ahead of the clock (CONTRACT §8.2):**".

## Proposed wording or exact diff

**P1. CONTRACT §3.4, item 3.**

> 3. **Memory (`/memory/`).** Everything specific to one owner: the owner profile, owner-layer rules, tasks other than the shared tasks a project repository keeps (section 16.2), in-brain projects, contacts, raw files, sources, outbox, boards, the brain-wide `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, per-skill owner configuration and notes, and pointer nodes for projects that live in their own repositories.

**P2. CONTRACT §5.4.**

> An outstanding action that must remain visible after the current interaction.
>
> Create or update a canonical task record in its task store (section 9): `/memory/tasks/`, or the `brain/tasks/` folder of a shared project repository (section 16.2).

**P3. CONTRACT §9, second paragraph, replaced by three paragraphs and a list.**

> There are two kinds of task store, with the same folders, record format, statuses and rules:
>
> - `/memory/tasks/`, the owner's own store, holds every task that is not a shared task;
> - `brain/tasks/` in a project repository that more than one brain works on (section 16.2) holds that project's **shared tasks**: every task whose first project reference is the project's pointer node itself, unless the owner marks the task private. A task whose first reference is an in-memory node beneath the pointer node stays in `/memory/tasks/`.
>
> A task lives in exactly one store, and that record is canonical. Privacy is a place, not a flag: whatever a shared task record holds can be read by everyone who can read the repository. An owner-private task about a shared project stays in `/memory/tasks/` with `private: true`; an owner-private note about a shared task is kept in `/memory/tasks/private/<task id>.md`, which names the task and is never drawn into the repository.
>
> Tasks in `/memory/tasks/` are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

**P4. CONTRACT §9.3, item 9.**

> 9. move completed records to the `completed/` folder of their store

**P5. CONTRACT §16.1, third paragraph.**

> Tasks about a project that no other brain works on remain canonical in `/memory/tasks/` and reference the pointer node in `project_refs`. Tasks about a project shared between brains, open and completed alike, are kept in the repository (section 16.2), except the owner's private tasks and private notes about it, which stay in `/memory/tasks/` (section 9). A project with collaborators may also run its own issue tracker; a task then links the issue instead of copying it.

**P6. CONTRACT §16.2, first paragraph.** Identical to C6 up to and including "Every such brain is a
peer: its records carry its author and are rewritten by no other author, its generated pages are not
committed", into which "a shared task record excepted as below" is inserted, because any brain
may edit a shared task; the rest of the sentence is replaced. The whole proposed paragraph:

> The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and any `sources/` or `data/` it owns – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules. A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more than one brain works on it. A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the repository, the working branch, the contract and skill versions it assumes, its shared boards, the vault entries each person creates for themselves (names only) and the records to read first; a brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying another brain's memory. Every such brain is a peer: its records carry its author and are rewritten by no other author, a shared task record excepted as below, and its generated pages are not committed. The project's shared tasks, open and completed, live in `brain/tasks/` (section 9), in the layout of `/memory/tasks/`, each record carrying the `author` that created it. Any brain that works on the project may change a shared task record; every change adds a History entry `- <timestamp> – <author>: <what changed>`, so each edit names the brain that made it, and a Git conflict in a record is resolved by hand, keeping the History entries of both sides in time order. `brain/tasks/STATE.md` is generated from the records, never edited by hand. A task whose `owner` has left the project is reassigned by the repository's maintainer, with a History entry. A new shared task takes an identifier that names its author, `TASK-<author>-YYYY-NNNN`, so two brains never number two tasks alike; a task moved in from memory keeps its identifier. Each owner's private tasks and private notes about the project stay in that owner's `/memory/tasks/` and are never drawn into the repository.

**P7. `/RULES.md`, `SMART-RULE-0019`.**

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what happened and why; and the task's store
>   (CONTRACT §9) for anything outstanding.

**P8. `/RULES.md`, `SMART-RULE-0024`.**

> - Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
>   files rather than copying prose, and a result record the worker writes back. Packets and
>   results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
>   must outlive the session is an ordinary task record (CONTRACT §9) with `waiting_on` and
>   `next_review`.

**P9. `/RULES.md`, `SMART-RULE-0043`.**

> - A **card** is a task record in a task store (CONTRACT §9) with a `team`. A team thread takes a
>   card by setting `claimed_by` to its session name, `claimed_at` from the clock and
>   `status: in_progress`, and committing that record on its own, in the repository that holds it
>   (`tasks.py claim`); a conflict on that commit means another thread took it first, and the
>   loser moves on. A card leaving `in_progress` loses its claim (`tasks.py release`, or
>   completion). The task record stays the only record: who holds a card lives nowhere else.

**P10. `/RULES.md`, *Contract restatements*.**

> - Treat the task stores of CONTRACT §9 – `/memory/tasks/` and a shared project's `brain/tasks/` – as the canonical task system. (CONTRACT §9)

**P11. `/shared/templates/memory-skeleton/tasks/RULES.md` and `/memory/tasks/RULES.md`.** The three
bullets become the first three below, and one bullet is added after them, last. The `scope`
front-matter value of the template stays `/memory/tasks` because the same rules govern every store
by CONTRACT §9:

> - Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record in the `open/` folder of its store (CONTRACT §9) once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
> - Each store's `STATE.md` enumerates every record under its `open/` folder: one entry per task carrying
>   its ID and the status word from its front matter. Update the entry when the record changes
>   and remove it when the record moves to the store's `completed/` folder. A task absent from the file, or
>   listed with a different status word than its record, is a defect to fix in the same turn. In a
>   shared project repository, `brain/tasks/STATE.md` is generated from the records by the tasks
>   skill and is never edited by hand; a conflict in it is resolved by taking either side and
>   generating it again.
> - Move completed and cancelled tasks to the `completed/` folder of their store.
> - In a shared project repository's store, any brain that works on the project may change a
>   record. Every change sets `updated` and adds a History entry
>   `- <timestamp> – <author>: <what changed>`, with the same timestamp, so the newest History
>   entry always names who made the latest change. The record's `author` names the brain that
>   created it and never changes. A Git conflict in a record is resolved by hand before anything
>   else is committed: keep the History entries of both sides in time order, decide each
>   conflicting field (ask the task's `owner` when the right value is not clear), add a History
>   entry naming the resolver, and generate `STATE.md` again.

**P12. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, new bullet.**

> - **shared task stores (CONTRACT §9, §16.2):** with `--project <repository>`, fail on a record under the repository's `brain/tasks/` with missing required metadata or no `author`, an invalid status or one its folder does not hold, an identifier used twice in that store, a `/memory/` path anywhere under `brain/tasks/`, a Git conflict marker (a line beginning `<<<<<<< ` or `>>>>>>> `) in any file there or a path there that Git reports as unmerged, a record whose `updated` is later than its newest History entry of the form `- <timestamp> – <author>: <what changed>` (an edit nobody is named for), or a `brain/tasks/STATE.md` that differs from the one the tasks skill generates from the records. Run from the brain root without `--project`, make the same checks for the repository of every pointer node under `/memory/projects/` that is checked out and holds `brain/tasks/`, as warnings, adding an error for an identifier used both there and in `/memory/tasks/`; and warn on an open task in `/memory/tasks/` whose first project reference is such a pointer node itself and that is not marked `private: true`

`contract_version` 2.7.0 becomes 3.0.0: the canonical home of a class of existing records moves,
and existing content needs a coordinated migration (CONTRACT §13.3, major). The manifests
`/repository-manifest.json`, `/library/repository-manifest.json` and
`/memory/repository-manifest.json` record 3.0.0, and each shared project's `brain/JOINING.md`
raises `minimum_contract_version` to 3.0.0 so a peer brain that does not yet know `brain/tasks/`
is told so when it joins or syncs.

## Reason

The owner's instruction: all task-related details of a shared task belong in the shared project.
A collaborator's brain cannot act on a task it cannot read, and today it reads only a title. The
§16.2 rule that kept tasks out of the repository protected owner-private content; this proposal
keeps that protection by keeping private content in a place the repository never sees, instead of
keeping every task out.

**Why a task store in `brain/tasks/`, not enriched cards.** A card and a task are different
records: a card is one owner request travelling to a verdict, retired by a verdict or a release,
and its body is written only by its author; a task is an outcome with one accountable owner,
statuses, a review date and a history, completed by its criteria. Making a card the task record
would merge two lifecycles into one file and give a task two ways to close. A store in the
existing format reuses the one parser (`task_records.load_tasks`), the one set of commands and the
one board routing, with a second root (`SMART-RULE-0018`): no new record kind, no translation
layer, and a card goes on naming its task by identifier as it does now.

**Why any brain may edit, with every edit named.** The owner chose this (Decisions, 3): the people
on a shared project should be able to move each other's tasks forward, and one record is simpler
to read than a record plus note files. The cost is that two brains can change one record before
either pulls, which Git reports as a conflict to resolve by hand; the fetch before every write
makes that rare, and the preflight refuses a record left half-merged. Attribution moves from the
file name, as on cards, into the record: `author` says who created it, and the History entry each
change adds says who changed what and when, so no edit is anonymous.

**Why author-named identifiers.** Each brain numbers its own tasks; two brains writing into one
store would produce the same `TASK-YYYY-NNNN`. Naming the author in the identifier, as cards and
events already do, makes a clash impossible without coordination. The number comes from the
author's one sequence across memory and every shared store, so the owner never has a memory task
and a shared task with the same number.

## Scope and behavioural consequences

- **Scope:** project repositories that more than one brain works on (those that carry
  `brain/JOINING.md`). A project worked by the owner alone keeps its tasks in `/memory/tasks/`
  unchanged. A shared project's completed tasks move with its open ones (Decisions, 7).
- **Which store a new task goes to.** `tasks.py new` looks at the first `--project` only. When it
  names a pointer node exactly, and that node's repository carries `brain/JOINING.md` and is
  checked out, the record is written to its `brain/tasks/` unless `--private` is given. A reference
  to an in-memory node beneath a pointer node is not the shared project: a pointer node may sit
  above nodes of the owner's own, and their tasks stay private. Its `project_refs` there name the repository's node
  (`<repository>:brain`) and any other project-repository references; references to `/memory/`
  are kept in the owner's companion file `/memory/tasks/private/<task id>.md`, never in the record.
- **Finding the stores.** One function in the tasks skill lists the stores: `/memory/tasks/`, then
  the `brain/tasks/` of every pointer node whose `local_path` resolves to a checkout holding it, by
  pointer-node path. Every reader calls it: the review, `check`, `next-id`, the scheduled review,
  the boards, the card detail, the join report and the preflight. No second registry is kept.
- **Writing.** Before writing a shared record, `tasks.py` fetches and refuses when the checkout is
  behind its upstream ("pull first"), then writes, regenerates `brain/tasks/STATE.md`, and leaves
  the commit and push to the agent under the project's Git rules (CONTRACT §16.3). Every command
  that changes a shared record (`done`, `do-now`, `note`, `claim`, `release`, and a new `edit` for
  the other fields) works for any brain, sets `updated` and adds the History entry naming this
  brain's `owner_short_name` and the change. `note --private` writes to the owner's companion file
  instead. A record found with conflict markers is refused until it is resolved.
- **Reading.** `tasks.py review` lists this brain's own tasks from every store (its memory tasks,
  and shared tasks it owns), with `--all` adding shared tasks owned by others.
- **Boards.** A shared board's `status.html` draws a *Tasks* section from its repository's
  `brain/tasks/`, the same for every brain, with links relative to the repository; it still
  refuses any `/memory/` path and any record from `/memory/tasks/`. The owner's page for that board,
  `/memory/boards/projects/<board id>.html`, draws only the owner's private tasks about the project,
  and marks a shared task that has private notes. Every open task is still drawn on exactly one
  board; the directory counts both kinds. Task actions saved from a shared page are applied through
  the tasks skill like any other, attributed to the brain that applies them.
- **Card detail.** A card's task link resolves to the shared record when the task is shared; the
  sentence "the task record is kept in the owner's own brain" remains only for a private task.
- **Joining.** `brain/JOINING.md` lists `brain/tasks/STATE.md` in `read_first` after
  `brain/STATE.md#Handover`; `join.py` reports the store, its open-task count and the tasks the
  joining person owns. Nothing is copied into the joining brain's memory.
- **Collaborator without the brain** reads `brain/tasks/STATE.md` and the records in the repository.

## Risks and conflicts

Ordered by severity, worst first.

1. **Private content leaking into the repository.** Once pushed, a line cannot be taken back from
   a clone. Mitigations: privacy is a place, so there is no flag to forget; the migration shows the
   owner, before anything is written into a repository, every task to be moved and every line
   flagged as possibly private (a `/memory/` path, an amount, a contact detail, a name the
   personal-data patterns recognise, an owner term), and moves nothing the owner has not cleared;
   `tasks.py` refuses to write a `/memory/` path into a shared record; the preflight's project mode
   fails on one; and the project repository runs `preflight.py --project` in its pre-commit hook.
   A public repository makes its tasks public: `tasks.py new` says so once for a public remote.
2. **Two brains editing one record.** Both change a record before either pulls; the second push
   meets a Git conflict in that file. Mitigations: `tasks.py` fetches before every write and
   refuses a checkout that is behind, which shrinks the window to the time between a write and its
   push; the resolution is fixed by P11 (keep both sides' History entries in time order, decide
   each field, ask the task's `owner` when unclear, add a History entry naming the resolver,
   regenerate `STATE.md`); `tasks.py` refuses a record that still has conflict markers; and the
   preflight's project mode fails on conflict markers or an unmerged path, so a half-merged record
   cannot be committed in the repository's hook. A project repository's merge routine is its own
   (`SMART-RULE-0034`); this conflict is never auto-resolved because a task record is hand-written.
   Claims keep `SMART-RULE-0043`'s rule that the second commit loses. `brain/tasks/STATE.md` is
   written by every brain and is generated, so a conflict in it is resolved by generating it again
   (`SMART-RULE-0034`, generated files). Cards are unchanged.
3. **An edit nobody is named for.** A person or tool edits a record by hand and adds no History
   entry. Mitigation: every `tasks.py` change writes the entry; the preflight fails a record whose
   `updated` is later than its newest attributed History entry. Git's own commit author remains a
   second record. A task whose owner has left the project is reassigned by the repository's
   maintainer, with a History entry (Decisions, 8).
4. **Owner-only tasks about a shared project.** They stay in `/memory/tasks/` with `private: true`,
   drawn on the owner's own page for the board. A memory task about a shared project without the
   mark is reported by the preflight as a warning, so drift is seen. Because any brain may edit a
   shared task, nothing owner-private may be written into one; a private remark goes to the
   companion file.
5. **Identifier clash between stores.** The preflight fails on an identifier used in a shared store
   and in `/memory/tasks/`; author-named identifiers prevent new ones.
6. **Version skew.** A peer brain on contract 2.7.0 would keep creating shared tasks in its own
   memory. `minimum_contract_version: 3.0.0` in each joining manifest makes `join.py` and the
   `sync.py` nudge report it.
7. **Conflicts with existing rules.** The owner-board skill's paragraph *What never enters the
   repository* and its failure sentence about a task on a shared page are skill text, not
   protected governance, and change in the build. The worker brief digests none of the amended
   bullets (`SMART-RULE-0007`), so it does not change. `SMART-RULE-0035` (offer a board) counts
   tasks on the personal board and is unaffected.

## Migration

Runs only after the build below is merged and tested, and after the owner has accepted this
proposal. One project repository at a time; each step names what it reads and writes.

1. **Prepare the repository.** Create `brain/tasks/` with `inbox/`, `open/`, `completed/` and a
   `README.md`; add `tasks/` to `brain/README.md` under *Folders*; add `brain/tasks/STATE.md` to
   `read_first` and raise `minimum_contract_version` in `brain/JOINING.md`; add
   `preflight.py --project` to the repository's pre-commit hook.
2. **Inventory (read only).** `tasks.py migrate-shared --repo <repository> --dry-run` lists each
   inbox, open and completed task in `/memory/tasks/` whose first project reference is the
   repository's pointer node, and for each: the lines flagged as possibly private, the `/memory/`
   references to be kept in the companion file, and any second shared project it names. Completed
   tasks are listed apart, after the open ones, because their History is longer and older.
3. **Owner review.** The owner clears each repository's list: the tasks to keep private (they gain
   `private: true` and stay) and the flagged lines to keep private (they go to the companion file).
   Silence moves nothing, and nothing is written into the repository before the list is cleared.
4. **Move.** For each cleared task, the command writes the record into `brain/tasks/<same
   folder>/` (`inbox/`, `open/` or `completed/`) with the same file name and identifier, its front
   matter unchanged except `author: <owner short name>` added, `project_refs` rewritten to
   repository references and `updated` set to the move time, its body unchanged except cleared
   private lines, and one History entry `- <timestamp> – <owner short name>: moved from the owner's
   memory (PROPOSAL-shared-project-tasks-in-the-repository)`. Private lines and `/memory/`
   references go to `/memory/tasks/private/<task id>.md`. The memory record is removed in the same
   memory commit, with its row in `/memory/tasks/STATE.md` and the open-task count where it was
   open, and an entry in `/memory/governance/removed-files.md` naming where each record went. Its
   earlier history stays in the memory repository's Git history; authorship stays in its `owner`,
   `author` and History.
5. **Two shared projects on one task.** The task moves to the repository of its first shared
   project and names the other as `<other repository>:brain`.
6. **Record.** One entry in `/memory/tasks/LOG.md`, in the pointer node's `LOG.md` (with its *what
   lives where* line updated to name `brain/tasks/`), and in the repository's `brain/LOG.md`.
7. **Show them again.** Rebuild the boards; `task_board.py check` shows each moved task once, on
   the shared board; `tasks.py review` lists them; card task links resolve to the shared records.
8. Commit memory and the project repository separately, pull before pushing (CONTRACT §16.3).

## Rollback

- Before migration: revert the governance commits in the mechanics and memory repositories and the
  build commits; nothing else has changed.
- After migration: `tasks.py migrate-shared --repo <repository> --reverse` moves each moved record
  back into `/memory/tasks/` with every History entry other brains added, restores `/memory/`
  references from the companion file, and adds a History entry; tasks created in the repository by
  another brain are listed for the owner and left there; then
  `brain/tasks/` is removed from the repository by a commit, and the governance and build commits
  are reverted. Content already pushed to the repository stays in its Git history and in every
  clone: rollback cannot make a shared line private again, which is why step 3 of the migration
  comes before any write.

## Validation

1. Unit tests, fictional data only (`SMART-RULE-0008`), authors `sam` and `bob`:
   tasks (store discovery, routing of `new`, author-named identifiers, refusal to write when behind,
   the attributed History entry on every change, refusal of a record with conflict markers,
   `--private` placement, generated `STATE.md`, refusal of a `/memory/` path); owner-board (a shared
   page draws the repository's tasks and still refuses memory tasks and paths, each open task once
   across stores, card task links, task actions attributed to the applying brain); join-project;
   repository-preflight (each new project-mode failure, including conflict markers, an unmerged
   path and an unattributed edit, and the memory warning).
2. A join test with a second fictional brain: two brains and one project repository in a temporary
   folder. `sam` creates a shared task and a private note; `bob` joins with `join.py`, sees the task
   in its review and on its board page, completes it (History names `bob`) and creates
   `TASK-bob-2026-0001`; `sam` pulls and sees both; the private note is in no file of the
   repository. Then both change one record without pulling: the second push conflicts, the
   preflight fails on the markers, and the resolution of P11 passes it.
3. The board build: `build_status.py --all`, `task_board.py route` and `task_board.py check`.
4. The repository preflight: `preflight.py` on the mechanics, library and memory, and
   `preflight.py --project <repository>` on each shared repository after its migration.
5. Migration counts, per folder (inbox, open, completed): tasks before equal memory tasks plus
   shared tasks after; every
   moved identifier is found exactly once; no file under any `brain/tasks/` contains `/memory/`.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record

None. Nothing in this proposal is active.

### Build, after acceptance

Code changes in the core skills, listed for a later build; each package names the files it writes.
The build touches stored data and more than one module, so it starts from an approved plan
(`SMART-RULE-0024`).

- **tasks** (`/shared/skills/tasks/`): a new `task_stores.py` (the one store list, by pointer node);
  `task_records.Task` gains its store; `tasks.py` `new` routing, `--private`, author-named ids in
  `next-id`, the attributed History entry on every change and an `edit` command, the refusal of a
  record with conflict markers, the fetch-before-write refusal, `STATE.md` generation for a shared
  store, `review --all`, `migrate-shared` (inbox, open and completed) with `--dry-run` and `--reverse`;
  `scheduled_review.py` reads every store; `SKILL.md`; tests.
- **owner-board** (`/shared/skills/owner-board/`): `task_board.py` loads every store and routes a
  shared task to its repository's board; `build_status.py` draws the shared *Tasks* section and
  keeps the refusal for memory content; `card_detail.py` links shared records; `task_actions.py`
  and `apply_events.py` apply actions to shared records through the tasks skill, attributed;
  `reconcile.py` check 10 covers shared tracks;
  `SKILL.md` (*Tasks on the boards*, *What never enters the repository*, *Failure behaviour*);
  tests.
- **join-project** (`/shared/skills/join-project/`): `joining.py` reads the store; `join.py`
  reports it and the joining person's tasks; the two-brain test; `SKILL.md`.
- **repository-preflight** (`/shared/skills/repository-preflight/`): the `--project` mode and the
  checks of P12; `SKILL.md` *Failure behaviour* (P12, protected); tests.
- **templates** (`/shared/templates/`): the memory skeleton gains `tasks/private/`; the pointer
  README template's *what lives where* names `brain/tasks/`; a `brain/tasks/README.md` template.
