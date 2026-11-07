---
id: template-tasks-private-readme
title: Private Task Notes
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Private Task Notes

Read `/CONTRACT.md` first.

The owner's private notes about tasks kept in a project repository's `brain/tasks/` (CONTRACT §9,
§16.1). Whatever a repository's `brain/` holds can be read by everyone who can read the
repository, so a note the owner keeps private, and any `/memory/` reference a repository task
needs, is kept here instead and never drawn into the repository.

One companion file per task, named `<task id>.md`. Its front matter carries `id: <task id>-private`,
`type: task_private_note`, `task` (the task's identifier), `store` (the label of the store that
holds the task, such as `<repository>:brain/tasks`) and `memory_refs` (a list), with the required
fields. Its body is a `## Notes` section of History-format entries
`- <timestamp> – <author>: <note>`. `tasks.py note --private` writes it.

A companion file is not a task record: it is never loaded as a task, listed in a `STATE.md` or
drawn on a shared board.

#### Folders

No immediate child folders exist. Companion files are stored directly in this directory.
