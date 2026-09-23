---
id: template-tasks-state
title: Task System Current State
type: state
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Current State

Read `/CONTRACT.md` first.

## Operating rule

This file enumerates every record under `/memory/tasks/open/`: one row per task with the status
word from its front matter. A row changes when the record changes and leaves when the record
moves to `/memory/tasks/completed/` (`SMART-RULE-0025`).

## Open tasks (0, ordered by task number ascending)

| Task | Status | Priority | Review / waiting on | Title |
|---|---|---|---|---|

`tasks.py new` adds a row here and keeps the count in the heading; for the next free number run
`tasks.py next-id`, which reads it from the records (`/shared/skills/tasks/SKILL.md`).
