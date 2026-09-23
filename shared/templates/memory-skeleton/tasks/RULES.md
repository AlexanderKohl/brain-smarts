---
id: template-tasks-rules
title: Task System Rules
type: rules
schema_version: 0.2
contract: /CONTRACT.md
scope: /memory/tasks
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---

# Task Rules

Read `/CONTRACT.md` first.

- Use one canonical task record.
- Use one owner.
- Do not store a separate follow-up owner.
- Use `waiting_on` to identify the external dependency.
- Use `next_review` to tell the system when to surface waiting or scheduled work.
- Do not create a task for work completed immediately.
- Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record under `/memory/tasks/open/` once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
- `/memory/tasks/STATE.md` enumerates every record under `/memory/tasks/open/`: one entry per task carrying
  its ID and the status word from its front matter. Update the entry when the record changes
  and remove it when the record moves to `/memory/tasks/completed/`. A task absent from the file, or
  listed with a different status word than its record, is a defect to fix in the same turn.
- Link tasks to all relevant projects.
- Move completed and cancelled tasks to `/memory/tasks/completed/`.
- Update related project state when completion changes current reality.
