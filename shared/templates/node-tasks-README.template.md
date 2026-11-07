---
id: NODE-ID-tasks-readme
title: NODE TITLE – Tasks
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: system
status: active
parent: /PARENT
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER
---

# NODE TITLE – Tasks

Read `/CONTRACT.md` first.

This is the task store of the node NODE TITLE (CONTRACT §9). It holds every task whose first
project reference names this node, and nothing else. Every store has the same folders, record
format, statuses and rules, so the node moves between memory and its own repository unchanged.
Records are created and changed with `/shared/skills/tasks/`; every change adds an attributed
History entry `- <timestamp> – <author>: <what changed>`.

In a project repository's `brain/tasks/`, everything here can be read by everyone who can read the
repository, and no file here names a path in the owner's memory. A private task or note about the
project stays in the owner's memory (CONTRACT §16.1).

`STATE.md` is generated from the records by `tasks.py state` and is never edited by hand; a Git
conflict in it is resolved by generating it again.

#### Folders

Remove the entry for a folder the store does not have yet.

##### `completed/`

Contains completed or cancelled task records retained for history. Preserve task history and do
not return a record to active use without an explicit status change.

##### `inbox/`

Contains captured tasks that have not yet been processed. Clarify ownership, outcome, references
and next action before moving them onward.

##### `open/`

Contains ready, in-progress, waiting, scheduled or blocked task records. Each is listed in
`STATE.md` with its status word.

##### `recurring/`

Contains recurrence definitions, when the node has any. Generated task instances remain separately
traceable and never overwrite the recurrence definition.
