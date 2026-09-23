---
id: ghl-general-ai-employees-action-targets-separate-search
title: AI employee action targets need a separate search call; the agent record carries only opaque ids
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /ai-employees/actions/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: 2026-09-14
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--ai-employees--action-targets-need-separate-search.md
created: 2026-09-14T10:12:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# AI employee action targets need a separate search call

## Behaviour

Both `GET services.leadconnectorhq.com/ai-employees/employees/search?locationId=` and the
per-employee endpoint return an `actions` array of bare references:

```json
"actions": [{"type": "triggerWorkflow", "id": "id_EXAMPLE_01"},
            {"type": "appointmentBooking", "id": "id_EXAMPLE_02"}]
```

Those ids are **action records**, not targets. They match no workflow id, calendar id, field id
or bot id anywhere in the account. The targets live behind:

```
GET services.leadconnectorhq.com/ai-employees/actions/search?employeeId={id}&skip=0&limit=20&query=
```

which returns `{data: [{type, actions: [...], count}], success, traceId}` grouped by action type.
Each type carries different target keys:

| `type` | target keys |
| --- | --- |
| `triggerWorkflow` | `workflowIds[]` – real workflow ids |
| `appointmentBooking` | `calendarIds[{id, triggerCondition}]` |
| `updateContactField` | `contactFieldId`, `contactFieldKey`, `contactFieldDataType` |
| `humanHandOver` | `assignToUserId`, `createTask`, `tags[]`, `handoverType` |
| `transferBot` | `transferToBot` (`"PRIMARY"` or a bot id), `transferBotType` |
| `stopBot` | `stopBotDetectionType`, `stopBotExamples[]`, `finalMessage` |
| `advancedFollowup` | `followupSequence[{id, followupTime, workflowId, triggerWorkflow}]` |

Every action also carries `enabled`, which is independent of the agent's own `mode`.

## Why it's non-obvious

The agent record looks complete – it has an `actions` array with ids in it, and nothing signals
that the ids address a different collection. A cross-reference of all 36 action ids in the
reference account against every id in an 81-endpoint sweep returned no matches at all, which
reads as "these targets were deleted" rather than "you are holding the wrong ids".

`limit=20` is the default the UI sends. An agent with more than 20 actions will silently
truncate.

## What to do

Call the search endpoint once per employee id and raise `limit`. Until then an AI agent is a
node with no edges: its workflow triggers, calendar bookings, field writes and user assignments
are all invisible, which makes a workflow started only by a bot look like a workflow with no
entry point.

## Related

- `/shared/skills/gohighlevel-access/knowledge/general--folder-lists--top-level-returns-folders-not-records.md`
