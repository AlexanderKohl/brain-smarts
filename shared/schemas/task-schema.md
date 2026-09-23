---
id: schema-task
title: Task Metadata Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
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
---
```

## Rules

- Use one owner. Task records are owner content and live in `/memory/tasks/` (CONTRACT §9).
- Use ISO 8601 timestamps with seconds and an explicit timezone for `created` and `updated`.
- Do not create a separate follow-up owner.
- Use `next_review` when the system should surface a waiting or scheduled task.
- Use a real due date only when a deadline exists.
- Describe completion criteria in the body.

