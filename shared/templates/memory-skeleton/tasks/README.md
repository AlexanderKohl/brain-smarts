---
id: template-tasks-readme
title: Task System
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: system
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Task System

Read `/CONTRACT.md` first.

This is the owner store: the tasks with no project reference (CONTRACT §9). A task whose project
reference names a node is kept in that node's `tasks/` folder, in memory or in the project
repository's `brain/tasks/`; task views read every store the brain can reach. `STATE.md` is
generated from the records by `tasks.py state` and is never edited by hand.

#### Folders

##### `completed/`

Contains canonical completed or cancelled task records retained for history. Preserve task history and do not return a record to active use without an explicit status change.

##### `inbox/`

Contains canonical captured tasks that have not yet been processed. Clarify ownership, outcome, references and next action before moving them onward.

##### `open/`

Contains canonical ready, in-progress, waiting, scheduled or blocked task records. Keep status, owner, dependencies and review timestamps current.

##### `private/`

Contains the owner's private companion notes, `<task id>.md`, about tasks kept in a project repository. Never task records and never drawn into a repository.

##### `recurring/`

Contains canonical recurrence definitions. Generated task instances must remain separately traceable and must not overwrite the recurrence definition.

##### `templates/`

Contains canonical templates local to the task system. Copy and complete a template when creating a task; do not treat the template itself as an active task.

## Operating principle

A task exists once, in one store, and names one project. Work for several projects is split into one task per project, each listing the others in `related_tasks`.

Use one owner. The system performs review checks using `due` and `next_review` whenever it is invoked or when an external scheduler runs.
