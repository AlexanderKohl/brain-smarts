---
id: ghl-workflow-enrolment-internal-api-exposes-step-counts
title: The internal API does expose workflow enrolment totals and per-step contact counts
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflows/status/search/count-per-step
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--enrolment--internal-api-exposes-step-counts.md
created: 2026-09-12T16:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Enrolment is readable on the internal API

## Behaviour

Two endpoints the workflow builder calls for itself, on
`backend.leadconnectorhq.com`, with the ordinary bearer token the builder frame holds:

```text
GET /workflows/status/search/enroll-stats-cache?workflowIds[]={wf}&workflowIds[]={wf}&locationId={loc}
200 [{"workflowId": "...", "total": 20, "finished": 19},
     {"workflowId": "...", "total": 14, "finished": 12}]

GET /workflows/status/search/count-per-step?workflowId={wf}&locationId={loc}
200 [{"total": 1, "currentStepId": "<uuid-01>"}]
```

`enroll-stats-cache` is batched across workflows and gives lifetime totals with a finished
count. `count-per-step` gives **how many contacts are sitting at each step right now**,
keyed by the step id used in `workflowData.templates`.

## Why it's non-obvious

The public API's answer to the same question is a flat no, and it is emphatic: seven
endpoint shapes 404 or 422, and `/workflows/` explicitly rejects a `contactId` filter with
`422 property contactId should not exist`. That evidence is correct and is recorded in
[general--workflows--no-enrolment-read-surface](general--workflows--no-enrolment-read-surface.md).
It reads as a platform limitation, and the conclusion drawn from it – that runtime tracing
is impossible – was wrong by one word. It is impossible *on the public API*.

The naming hides it further: neither path contains "enrolment", "contacts" or "history", and
both sit under `/workflows/status/search/`, which reads like a workflow status filter rather
than a runtime query.

## Consequence

A live overlay on a rendered workflow – queue depth per step, totals per workflow – is
available to anything running in an authenticated browser session. It is not available to a
server-side integration holding a public API token. Any product decision that treated
runtime state as unreachable should be revisited against which of the two surfaces it
actually has.

## Evidence

Observed in live builder traffic against `Example Co` (`loc_EXAMPLE_01`) on
2026-09-12, captured by a browser extension's traffic recorder.
Responses quoted verbatim. Not probed deliberately – the builder issues both on opening a
workflow – so the parameter space beyond what is shown is untested.

## Applies to

`workflow` on the internal API only. Does **not** apply to
`services.leadconnectorhq.com/workflows/` or any documented public route; treat the
public-API entry as still correct for that surface.
