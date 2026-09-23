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

This is the canonical cross-project task store.

#### Folders

##### `completed/`

Contains canonical completed or cancelled task records retained for history. Preserve task history and do not return a record to active use without an explicit status change.

##### `inbox/`

Contains canonical captured tasks that have not yet been processed. Clarify ownership, outcome, references and next action before moving them onward.

##### `open/`

Contains canonical ready, in-progress, waiting, scheduled or blocked task records. Keep status, owner, dependencies and review timestamps current.

##### `recurring/`

Contains canonical recurrence definitions. Generated task instances must remain separately traceable and must not overwrite the recurrence definition.

##### `templates/`

Contains canonical templates local to the task system. Copy and complete a template when creating a task; do not treat the template itself as an active task.

## Operating principle

A task exists once and references every relevant project.

Use one owner. The system performs review checks using `due` and `next_review` whenever it is invoked or when an external scheduler runs.
