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
- Convert an informal open item tracked only in a project's `STATE.md` (such as an "Active priorities" or "Active work" entry) into a formal task record in the `open/` folder of its store (CONTRACT §9) once it represents real outstanding work, so every open item is discoverable from one place; keep the source note and the task record in sync rather than tracking the same open item in two places.
- Each store's `STATE.md` enumerates every record under its `open/` folder: one entry per task carrying
  its ID and the status word from its front matter. It is generated from the records by the tasks
  skill whenever a record changes and is never edited by hand; a task absent from it, or listed
  with a different status word than its record, is a defect to fix in the same turn by generating
  it again, and a Git conflict in it is resolved the same way.
- Link tasks to all relevant projects.
- Move completed and cancelled tasks to the `completed/` folder of their store.
- Update related project state when completion changes current reality.
- In every store, every change to a record sets `updated` and adds a History entry
  `- <timestamp> – <author>: <what changed>`, with the same timestamp, so the newest History
  entry always names who made the latest change. The record's `author` names the brain that
  created it and never changes. A Git conflict in a record is resolved by hand before anything
  else is committed: keep the History entries of both sides in time order, decide each
  conflicting field (ask the task's `owner` when the right value is not clear), add a History
  entry naming the resolver, and generate `STATE.md` again.
