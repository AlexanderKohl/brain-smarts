---
id: schema-task
title: Task Metadata Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-10-23T08:25:27+10:00
---

# Task Metadata Schema

```yaml
---
id: TASK-<author>-YYYY-NNNN
title: Clear action or outcome
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: inbox
owner: brain-owner
author: brain-owner
priority: normal
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
due: null
next_review: null
waiting_on: null
schedule: null
project_refs: []
skill_refs: []
depends_on: []
related_tasks: []
team: null
claimed_by: null
claimed_at: null
---
```

The fields are additive: the schema stays at version 0.2, and a record without the newer fields
still parses.

## Rules

- Every task lives in exactly one task store (CONTRACT §9): the `tasks/` folder of the node its
  first project reference names (`brain/tasks/` for a project in its own repository), or
  `/memory/tasks/` for a task with no project. Every store has the folders `inbox/`, `open/`,
  `completed/` and, when needed, `recurring/`, and a `STATE.md` the tasks skill generates.
- Use one owner. A task whose owner has left a shared project is reassigned by the repository's
  maintainer, with a History entry.
- `id`: a new task is `TASK-<author>-YYYY-NNNN`, where `<author>` is the creating brain's
  `owner_short_name` in lower case (every run of other characters one hyphen) and `NNNN` the next
  number in that author's one sequence across every store. A legacy `TASK-YYYY-NNNN` keeps its
  form wherever it moves.
- `author`: the brain that created the task, as an author name. Required; set on creation and
  never changed.
- Use ISO 8601 timestamps with seconds and an explicit timezone for `created` and `updated`.
- Every change to a record sets `updated` and adds a History entry with the same timestamp:

  ```text
  - <timestamp> – <author>: <what changed>
  ```

  Lines indented two spaces below an entry belong to it (a note kept verbatim, screenshot
  links). The newest History entry therefore names who made the latest change. A record has one
  `## History` section; a record with two is read as one, and the next change merges them.
- `schedule`: when an app or the operating system runs work for the task on a schedule, one
  scalar `"<app> | <job> | <cadence>"`, else `null`. Each run is recorded as a History entry
  `run of `<job>`: <outcome>` (`tasks.py note --run <job>`).
- `project_refs`: the first reference names the node that holds the record. In a repository
  record it is `<repository>:brain`, where `<repository>` is the remote's name, followed by other
  `<repository>:<path>` references; a repository record never names a `/memory/` path. Every
  reference in memory is inside a node; a task in `/memory/tasks/` has no project reference. Work
  for several projects is split into one task per project.
- `related_tasks`: the identifiers of the other parts of a split; `[]` otherwise.
- Do not create a separate follow-up owner.
- Use `next_review` when the system should surface a waiting or scheduled task.
- Use a real due date only when a deadline exists.
- Describe completion criteria in the body.
- `team`, `claimed_by` and `claimed_at` are optional and let several conductor threads (teams)
  pull cards from one board:
  - `team` is a short lowercase label naming the team thread that works the card; the boards
    draw it as a lane colour. A card with no team is anyone's.
  - `claimed_by` is the session name of the thread holding the card; `claimed_at` is when it
    took it (ISO 8601 with seconds and an explicit timezone, from the clock).
  - `claimed_by` and `claimed_at` are set together when the card enters `in_progress`
    (`tasks.py claim`) and cleared together when it leaves (`tasks.py release`, `done`).

## The companion file

An owner-private note about a task kept in a repository lives in
`/memory/tasks/private/<task id>.md`. It is not a task record and is never loaded as one:

```yaml
---
id: <task id>-private
title: Private notes – <task id>
type: task_private_note
schema_version: 0.2
contract: /CONTRACT.md
status: active
owner: brain-owner
task: <task id>
store: <repository>:brain/tasks
memory_refs: []
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---
```

Its body holds `## Notes`, with entries in the History format.
