---
id: ghl-workflow-steps-advance-canvas-meta-disabled
title: A workflow step can be disabled in place, and the flag is a nested object most readers will miss
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
discovered: 2026-09-14
verified: 2026-09-14
source_refs: []
created: 2026-09-14T21:00:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# A disabled step is still in the graph

## Behaviour

A step inside `workflowData.templates` may carry:

```json
{
  "id": "...",
  "type": "internal_update_opportunity",
  "name": "Update opportunity to Send Bill Upload",
  "parent": "...", "next": [...], "attributes": { ... },
  "advanceCanvasMeta": { "isDisabled": true }
}
```

The step keeps its `parent`, `next` and `attributes` exactly as an enabled step does.
Nothing else about it changes. It is present in the graph, wired into the flow, and it
does not run.

Both values occur: in the reference account's 924 steps, 4 carry
`{"isDisabled": true}` and 5 carry `{"isDisabled": false}`. **The key is absent
entirely on the other 915.** So the test is
`step.advanceCanvasMeta?.isDisabled === true`, not the presence of `advanceCanvasMeta`
and not a falsy check on a key that usually does not exist.

The flag is step-level only. No workflow-level `advanceCanvasMeta` was found.

`GET /workflow/{loc}/{wf}` returns it, so it is available to a headless read and not
only to an observed save.

## Why it's non-obvious

The name suggests presentation – "canvas meta" reads like a layout or rendering hint,
alongside the coordinates and collapse states that builders usually keep in such
objects. It is not: it is the step's operational state.

It is also easy to have and not notice. Four disabled steps in a 924-step corpus is
under half a percent, and a reader sampling a workflow will almost never meet one.

## Consequence

Any analysis that treats `templates` as the set of things a workflow does will count
disabled steps as live. In the reference account that produces at least one concretely
wrong edge: a disabled `internal_update_opportunity` step named "Update opportunity to
Send Bill Upload" is a *writer* of an opportunity field, and field-usage or impact
analysis that counts it will report a dependency that cannot fire.

The other three are an `add_notes` and two `internal_notification` steps – less
damaging, still counted.

Disabled steps should be kept in the captured document, not filtered out. They are
real configuration, a reader wants to see them, and a step that is disabled today is
often one that ran last month. The distinction belongs in the analysis, not the
capture.

## Evidence

Found by direct inspection of 45 committed workflow captures from `Example Co`
(`loc_EXAMPLE_01`) on 2026-09-14: 9 steps carry `advanceCanvasMeta`, 4 of them
`isDisabled: true`. Three of the captures carrying it were taken through the headless
`GET`, which is what confirms the field is served by the read rather than only present
in a save payload.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

`workflowData.templates` entries on `workflow`. Not tested: whether trigger objects
carry an equivalent, or whether any other HighLevel collection uses
`advanceCanvasMeta` for operational state.
