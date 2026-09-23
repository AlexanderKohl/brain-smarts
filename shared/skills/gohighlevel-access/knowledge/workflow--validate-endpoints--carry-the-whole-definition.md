---
id: ghl-workflow-validate-endpoints-carry-the-whole-definition
title: The builder's two validate calls carry the whole workflow definition on every change; auto-save fires only while it is a draft
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: POST /workflow/{locationId}/validate-assets and POST /workflow/{locationId}/{workflowId}/validate-workflows
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-16
verified: 2026-09-16
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--validate-endpoints--carry-the-whole-definition.md
created: 2026-09-16T09:48:08+10:00
updated: 2026-09-23T12:00:00+10:00
---

# The validate calls are where the live definition is

## Behaviour

The workflow builder validates as you edit. Two calls do it, and both send the definition
rather than a reference to it.

`POST /workflow/{loc}/validate-assets` - the whole definition and nothing else:

```json
{ "templates": [ /* every step, with its full attributes */ ],
  "triggers":  [ /* every trigger */ ],
  "companyId": "..." }
```

```json
{ "errors": [], "warnings": [] }
```

`POST /workflow/{loc}/{wf}/validate-workflows` - the whole workflow object, the shape
`GET /workflow/{loc}/{wf}` returns, plus four keys the read never carries:

```text
workflowData.templates    every step, full attributes, parent/next/parentKey/order
newTriggers, oldTriggers  the triggers, which the workflow read omits entirely
createdSteps              NOT what the name says - see below
modifiedSteps             NOT what the name says - see below
deletedSteps              NOT what the name says - see below
status                    "draft" or "published", of the definition being validated
```

```json
{ "valid": true, "message": "Validation successful", "assetWarnings": [] }
```

`PUT /workflow/{loc}/{wf}/auto-save` sends the same object again with `isAutoSave: true` and
an `autoSaveSession: {workflowId, id, userId, version, inProgress}`. **It fires only while the
workflow is a draft.** In a scripted session of 16 September 2026 both auto-saves carried
`status: draft`, and after the workflow was published not one more fired through two further
action saves. It is the draft editor's own persistence, not a change notification.

**Which call witnesses which change.** Measured across four recordings by hashing `templates`
on every `/workflow/` write and counting the distinct definitions each endpoint saw:

| Recording | Distinct definitions | `validate-workflows` | `validate-assets` | `auto-save` |
| --- | --- | --- | --- | --- |
| 15 Sep, 12:33 | 4 | 4 | 3 | 2 |
| 15 Sep, 12:39 | 5 | 5 | 4 | 2 |
| 14 Sep, 19:28 | 4 | 3 | 2 | 1 |
| 16 Sep, 10:05 (scripted) | 4 | 4 | 4 | 2 |
| 16 Sep, 10:33 (the same session, continued through a delete) | 5 | 5 | 4 | 2 |

Neither validate call sees everything on its own. **Their union saw every definition in all
five recordings**, and the delete says why rather than leaving it to luck:

**`validate-assets` does not fire on a delete.** Deleting an action produced
`validate-workflows` alone, 3.7 seconds before the workflow was saved, with nothing else on the
wire in that window. Add and edit fire both calls; delete fires one. So the two calls cover
different edits and a listener needs both.

**A delete can return the definition to a hash already seen.** Deleting the action that had just
been added restored the definition byte-for-byte to its pre-add state, so a listener that
remembers *every* hash it has seen will decide nothing changed and miss the delete. Compare
against the **last** definition acted on, not against a set.

The two fire within about a second of each other, in no fixed order, one pair per deliberate
action save, and `validate-workflows` also fires on opening the builder and again after a
deliberate save - so a listener must expect the same definition more than once and decide on
content, not on arrival.

**`createdSteps` / `modifiedSteps` / `deletedSteps` do not name what just changed.** They are
the builder's own dirty-tracking as it stands when the request goes out, and they are empty at
the moment of a change and filled at the moment of a persist:

| 16 Sep | Request | steps | `createdSteps` | `modifiedSteps` |
| --- | --- | --- | --- | --- |
| 67.9s | `validate-assets`, an action just added | 2 | key absent | key absent |
| 68.9s | `validate-workflows` | 2 | `[]` | `[]` |
| 82.1s | `validate-assets`, a field just added to it | 2 | key absent | key absent |
| 83.1s | `validate-workflows` | 2 | `[]` | `[]` |
| 89.2s | `PUT`, the workflow saved | 2 | one id | the same id |

The same step id appears in both lists at 89.2s. Do not use these keys to decide what changed;
diff two definitions instead.

**`version` does not mark persisted from on-screen. Hypothesis refuted 16 September.** It had
looked as though the number rose by one on each persisting write, with the following
`validate-workflows` carrying the next one. The delete session refutes it: the save sent
`version: 4` and the `validate-workflows` 0.2 seconds later also sent `4`, and two of the five
persisting writes in that session do not bump at all. Whatever the field tracks, it is not a
usable marker of what is persisted.

## Why it's non-obvious

Both read as helper calls. They answer `200` and change nothing, which is exactly why the
extension's save detector suppresses them by name (`HELPER_CALL` in
`src/highlevel/save-detect.ts`): reporting them as saves would put four entries in the
blind-spot banner for every workflow opened. The suppression is right about what they are and
hides what they carry.

`validate-assets` also carries no workflow id - only the location - so the workflow it
describes has to come from the issuing frame's own URL
(`.../v2/location/{loc}/automation/workflow/{wf}`).

## Consequence

These bodies are the only place the definition of an unsaved workflow exists outside the
builder's memory; the read does not serve it (see
[`workflow--builder-draft--get-does-not-serve-unsaved-edits`](workflow--builder-draft--get-does-not-serve-unsaved-edits.md)).
Per-item work is therefore possible, but its unit of change has to be derived by diffing
successive definitions, not taken from the change lists.

`assetWarnings`, `errors` and `warnings` are HighLevel's own validation channel, presented in
its own builder. Anything drawn in that page from another source is a second, differently
sourced set of findings and should not be made to look like HighLevel's.

## Evidence

Four `full`-mode traffic recordings from the extension's traffic recorder: 14 September 2026
19:28 (extension 0.3.0), 15 September 2026 12:33 and 12:39 (0.4.1), and 16 September 2026
10:05 (0.45.0), against two live sub-accounts. Every non-GET `/workflow/` request was parsed
and its `templates` hashed; the tables above are counts of distinct hashes per endpoint.
Recordings hold live account data and are not committed.

The 16 September recording is a **scripted** session made to test this behaviour rather than a
walk through the UI: an action added and then edited while the workflow was a draft, the
workflow published, then an action added and saved on its own, edited and saved on its own
again, and only then the workflow saved. It is what confirms the draft-only auto-save, the
one-pair-per-action-save shape, and the change lists not meaning what they say - the earlier
reading of them, that they name the item just edited, was **wrong** and is corrected here.

The 16 September 10:33 recording continues that session through a **delete** of the action and
a workflow save. It is what established the `validate-assets` asymmetry, the hash-returns-to-a-
previous-state case, and `deletedSteps` populated (on the save, not on the validate that
witnessed the delete).

## Applies to

Confirmed for `workflow` on `backend.leadconnectorhq.com`, issued from
`client-app-automation-workflows.leadconnectorhq.com`. Not tested for any other builder: the
form, calendar and AI agent editors have their own validate calls, and nothing here says they
carry their definitions the same way.
