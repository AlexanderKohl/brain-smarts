---
id: ghl-workflow-builder-draft-get-does-not-serve-unsaved-edits
title: The workflow builder holds an edited definition in memory; GET returns the last persisted version, not what is on screen
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflow/{locationId}/{workflowId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-16
verified: 2026-09-16
source_refs: []
created: 2026-09-16T09:48:08+10:00
updated: 2026-09-23T14:45:16+10:00
---

# An edited workflow is not readable until it is saved

## Behaviour

While the workflow builder is open, each edit changes a definition the builder holds in
memory. Nothing persists it until one of two writes goes out:

```text
PUT  /workflow/{loc}/{wf}/auto-save     # the editor's own draft write - DRAFT ONLY
PUT  /workflow/{loc}/{wf}               # the deliberate Save, carries status: published
```

Between an edit and one of those, `GET /workflow/{loc}/{wf}` answers the **last persisted**
definition. Observed on 15 September 2026 in one editing session against a live account:

| Elapsed | Request | `workflowData.templates` |
| --- | --- | --- |
| 134.5s | `PUT /workflow/{loc}/{wf}` | 1 |
| 139.8s | `GET /workflow/{loc}/{wf}` | 1 |
| 157.8s | `POST /workflow/{loc}/{wf}/validate-workflows` | **2** |
| 180.3s | `POST /workflow/{loc}/{wf}/validate-workflows` | **3** |
| 183.0s | `PUT /workflow/{loc}/{wf}` | 3 |
| 188.1s | `GET /workflow/{loc}/{wf}` | 3 |

At 157.8s and 180.3s the account's builder was showing two and then three actions. No write
carried them, and a read at either moment would have answered one action.

**`auto-save` does not close the gap, and once the workflow is published it does not exist.**
A scripted session on 16 September 2026 settled this. Two action saves while the workflow was a
draft each produced an `auto-save` carrying `status: draft`. The workflow was then published,
and two further action saves produced **no persisting write of any kind**:

| Elapsed (16 Sep) | What the person did | Writes that went out |
| --- | --- | --- |
| 24.9 – 26.0s | add an action (draft) | `validate-assets`, **`auto-save`**, `validate-workflows` |
| 43.3 – 44.3s | edit that action (draft) | `validate-assets`, **`auto-save`**, `validate-workflows` |
| 54.2s | publish | `PUT /workflow/{loc}/{wf}` |
| 67.9 – 68.9s | add an action, save the action | `validate-assets`, `validate-workflows` |
| 82.1 – 83.1s | edit it, save the action | `validate-assets`, `validate-workflows` |
| 89.2s | save the workflow | `PUT /workflow/{loc}/{wf}` |

For the 35 seconds between 54.2s and 89.2s the server held a one-action workflow while the
person was looking at a two-action one. So for a **published** workflow it is not that a read
is stale: nothing has been written for it to be stale against.

The earlier reading of `auto-save` as an intermittent change notification was wrong. It is the
draft editor's own persistence, and its absence after publishing is a rule, not a gap.

## Why it's non-obvious

Every other HighLevel surface a capture tool reads is readable the moment it changes, which is
the premise the whole refresh-after-save path rests on: observe the write, re-read the item,
never reconstruct it from the payload. A workflow under edit breaks that premise, and it
breaks it silently - the read succeeds, answers 200, and returns a coherent workflow that is
simply not the one on screen.

The `auto-save` write makes it look closable, and in draft mode it half is. That is the trap:
a design tested only on a draft workflow appears to work, and then stops working the moment the
workflow is published - which is exactly when its findings start to matter.

## Consequence

Anything that must reflect the workflow as it is being edited has to read the definition out
of a **request body**, because no read surface carries it. The bodies that do are
`POST /workflow/{loc}/validate-assets` (`{templates, triggers, companyId}`) and
`POST /workflow/{loc}/{wf}/validate-workflows` (the whole workflow object) - see
[`workflow--validate-endpoints--carry-the-whole-definition`](workflow--validate-endpoints--carry-the-whole-definition.md).

A definition taken that way is a draft that may never be saved, so it must not be merged into
a capture as though it were persisted configuration.

## Evidence

Four `full`-mode traffic recordings made with a browser extension's
traffic recorder: 14 September 2026, two on 15 September in which one
workflow was created and edited from empty to three actions, and 16 September 10:05.
Request and response bodies of every `/workflow/` call were compared by step count and by a
hash of `templates`. The recordings hold live account data and are not committed.

The 16 September recording is a **scripted** session, made to test this behaviour:
add an action and edit it while the workflow is a draft, publish, then add an action and save
the action alone, edit it and save the action alone again, and only then save the workflow. The
draft/published table above is that session, and it is what turns this entry from "a read can be
stale" into "for a published workflow nothing is written at all".

Not observed: a step deleted in the builder.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for `workflow` on `backend.leadconnectorhq.com`. The funnel page builder writes
`POST /funnels/builder/autosave/{id}` continuously while a page is typed into, which is a
different behaviour and not this one. Untested: whether forms, calendars or the AI agent
builders hold unsaved state the same way.
