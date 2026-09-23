---
id: ghl-workflow-triggers-separate-resource-own-endpoint
title: Workflow triggers are a separate resource with their own endpoint; the workflow read never includes them
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflow/{locationId}/trigger?workflowId={workflowId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--triggers--separate-resource-own-endpoint.md
created: 2026-09-12T16:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Workflow triggers are a separate resource

## Behaviour

`GET https://backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}` returns the
complete workflow object – `workflowData.templates` with the whole step graph – and **no
triggers at all**. There is no `newTriggers` key in the response.

Triggers live at their own address:

```text
GET https://backend.leadconnectorhq.com/workflow/{locationId}/trigger?workflowId={workflowId}
200 []                      # this workflow has no triggers
```

The workflow object points at them indirectly, through a Firebase Storage path with no
signed URL beside it:

```json
"filePath":         "location/{loc}/workflows/{wf}/34",
"fileUrl":          "https://firebasestorage.googleapis.com/...?alt=media&token=...",
"triggersFilePath": "location/{loc}/workflow-triggers/{wf}/32",
"isTriggerBucketMigrated": true
```

The two version numbers differ: the triggers file is versioned independently of the
workflow file.

The trigger objects are snake_case where the workflow object is camelCase – `date_added`,
`belongs_to`, `location_id`, `origin_id`, `workflow_id` – alongside a camelCase
`masterType`:

```json
{"id": "...", "belongs_to": "workflow", "workflow_id": "...", "masterType": "highlevel",
 "type": "form_submission", "active": true, "conditions": [...], "actions": [...]}
```

## Why it's non-obvious

The builder shows triggers as part of the workflow, and the workflow object carries
`triggersFilePath`, so the natural reading is that a workflow read returns everything and
the file path is an implementation detail. It does not. A capture built on the workflow
read alone looks complete – full step graph, correct version, correct name – and is
silently missing every trigger, which then reads as "this workflow has no entry point".

The path shape is its own trap. `/workflow/{loc}/trigger` has the same two-segment shape as
`/workflow/{loc}/{workflowId}`, so a classifier that does not reserve `trigger` files the
trigger response under a workflow whose id is the literal string `trigger`.

## Consequence

Distinguish "not fetched" from "fetched, none exist". An empty array from this endpoint is
a positive answer; never having called it is not. A rule that reports "workflow has no
trigger" must know which it is looking at, or it fires on every headlessly captured
workflow.

Two paths carry triggers inline, and neither is a GET: the `PUT` save request body and the
`POST .../validate-workflows` request body both include `newTriggers`. Observing the builder
therefore yields triggers for free; querying the API does not.

## Evidence

Recorded from live builder traffic against `Example Co` (`loc_EXAMPLE_01`) on
2026-09-12 with a browser extension's traffic recorder. The endpoint
was observed being called by the builder itself, returning `200 []` for a workflow whose
`newTriggers` in the same page's `validate-workflows` request body was also `[]` –
consistent, but the non-empty response shape has **not** yet been observed directly.

## Applies to

Confirmed for `workflow` on `backend.leadconnectorhq.com`. Untested: whether omitting
`workflowId` returns every trigger in the location. A third-party export tool's output
carries location-wide trigger rows each stamped with a `workflow_id`, which suggests it
does, but that is inference from another tool's output, not an observation.
