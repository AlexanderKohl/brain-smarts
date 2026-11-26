---
id: brain-rules-tasks
title: Rule pack: tasks
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

# Rule pack: tasks

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: creating, changing or closing a task; a project without a board gains its fifth open task or a third active branch.

## 9. Tasks

Tasks are a cross-cutting operating system, not an ordinary project.

Every task lives in exactly one task store, and that record is canonical:

- the `tasks/` folder of a node (section 3.1) holds every task whose project reference names that node: `/memory/projects/<node>/tasks/` for a node in memory, and `brain/tasks/` for a project in its own repository (section 16.2); a reference names the deepest node it is in, and a reference to a pointer node names its repository;
- `/memory/tasks/` holds the tasks with no project reference.

A task names one project. Work that concerns several projects is split into one task per project, each in the store of its own node, and each lists the identifiers of the others in its `related_tasks` field; every part records the split in a History entry. A completed record that already names several projects is not split, and is kept in the store of its first project reference.

Every store has the same folders, record format, statuses and rules, and a `STATE.md` generated from its records, so a node moves between memory and its own repository unchanged. Task views – the task review, the boards, the scheduled review – read every store the brain can reach.

Every task record carries `author`, the brain that created it, which never changes. A new task takes an identifier that names its author, `TASK-<author>-YYYY-NNNN`, where `<author>` is the creating brain's `owner_short_name` in lower case and the number is the next in that author's one sequence across every store, so two brains never number two tasks alike. An existing task keeps its identifier wherever it moves.

Privacy is a place, not a flag. Whatever a repository's `brain/` holds can be read by everyone who can read the repository, now or once a collaborator joins. An owner-private task about a project in its own repository is kept in the pointer node's `tasks/` folder (section 16.1), and an owner-private note about a task in a repository is kept in `/memory/tasks/private/<task id>.md`, which names the task. Neither is ever drawn into the repository.

Tasks in memory are owner content; the mechanics of the task system (its rules and templates) are kept for new owners in `/shared/templates/memory-skeleton/tasks/`.

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
9. move completed records to the `completed/` folder of their store
10. preserve task history in the task body and task log
11. when an app or the operating system runs work for the task on a schedule, name the job in the task's `schedule` field (the app, the job's name and its cadence), and record the outcome of each run as a History entry

### 9.4 Task versus project

A task is one directly completable action or outcome.

A project requires coordination of multiple tasks over time.

Promote a task into a project when it gains several dependent actions, multiple contributors, meaningful risks, substantial state or its own knowledge. The task then moves into the new node's `tasks/` folder.

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0035` | Offer a board when a project outgrows the personal board | this file; `/shared/skills/owner-board/` | a project without a board gains its fifth open task or a third active branch |

## SMART-RULE-0035 – Offer a board when a project outgrows the personal board

- When a project with no board of its own gains its fifth open task, or its work runs on three or more branches at once, the agent asks the owner once whether to give it a board. The question names the project, counts its open tasks, and suggests an answer.
- The board build (`build_boards.py`) prints the same suggestion for any project over that threshold, so the check does not rely on memory.
- A "no" is recorded in the board configuration (`board_declined`) and the agent does not ask again unless the owner raises it.
- A board is created only after a "yes": the agent registers it in `boards.json`, rebuilds the boards and gives the owner the link.
