---
id: schema-task
title: Task Metadata Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-10-01T22:38:06+10:00
---

# Task Metadata Schema

```yaml
---
id: TASK-YYYY-NNNN
title: Clear action or outcome
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: inbox
owner: brain-owner
priority: normal
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
due: null
next_review: null
waiting_on: null
project_refs: []
skill_refs: []
depends_on: []
team: null
claimed_by: null
claimed_at: null
---
```

## Rules

- Use one owner. Task records are owner content and live in `/memory/tasks/` (CONTRACT §9).
- Use ISO 8601 timestamps with seconds and an explicit timezone for `created` and `updated`.
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

