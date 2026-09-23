---
id: gohighlevel-workflow-contact-tag-trigger-tag-by-name-rename-propagates
title: Contact Tag triggers and tag steps reference a tag by name only; a tag rename is rewritten into them server-side
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflow/{locationId}/trigger?workflowId= (backend host); PUT /locations/{locationId}/tags/{tagId} (services host)
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--contact-tag-trigger--tag-by-name-rename-propagates.md
created: 2026-09-15T12:55:31+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Contact Tag triggers and tag steps reference a tag by name only; a tag rename is rewritten into them server-side

## Behaviour

A workflow trigger of type `contact_tag` stores the tag it fires on as the tag's **name**, in
its condition value. The internal trigger resource returns:

```json
{"type": "contact_tag", "conditions": [{"operator": "index-of-true", "field": "tagsAdded",
  "value": "trigger tag new name", "title": "Tag added", "type": "select", "id": "tag-added"}]}
```

`field` is `tagsAdded` or `tagsRemoved` (title `Tag added` / `Tag removed`). The builder saves
the trigger with the same shape (`PUT /workflow/{loc}/trigger/{triggerId}`, body `conditions[]`
as above). Workflow steps `add_contact_tag` and `remove_contact_tag` carry
`attributes.tags: ["<name>", ...]`. The tag's id (`id_EXAMPLE_01` in the probe) appears
only on the tag endpoints and never in a trigger or step payload.

Renaming the tag (`PUT /locations/{loc}/tags/{id}` with `{"name": "<new>"}`) is followed, with
no further save by the user, by the trigger resource and the workflow definition both returning
the **new** name in the trigger condition and in the `remove_contact_tag` step. HighLevel's
rename dialog says so ("Update workflow triggers and actions with the new name") and warns that
filters and smart lists are *not* updated.

## Why it's non-obvious

Every other trigger condition on a record field carries the field's id (`opportunity.<fieldId>`)
and is stable across renames. Tags are the exception: the name is the identity inside workflows,
so a graph keyed on tag names stays correct across a rename only because HighLevel rewrites the
workflows, and a filter or smart list keyed on the old name silently stops matching.

## Evidence

Traffic recordings (full-body mode) `traffic-2026-09-15-12-33-00.json` and
`traffic-2026-09-15-12-39-06.json` and the sweep `assets-loc_EXAMPLE_04.json`, all kept
in the owner's local raw captures (memory layer, gitignored), taken on sub-account
Example Test (`loc_EXAMPLE_04`) with workflow `<uuid-01>`:
tag created as `trigger tag`, trigger saved with that value, tag renamed to
`trigger tag new name` at seq `1789439899671331`; the next trigger read and workflow read (no
user save in between - the only writes after the rename were contact search, analytics, Firestore
and a token refresh) carry the new name, as does the 12:42 sweep. Confirmed, not pending.

## Applies to

`contact_tag` triggers (`tagsAdded` and `tagsRemoved`) and the `add_contact_tag` /
`remove_contact_tag` step types, on the internal builder endpoints. Not checked: tag conditions
inside `if_else` branches, smart lists and filters (the dialog says those are *not* renamed), and
the public API's `contact_tag` representation.

**A trigger saved without choosing a tag is stored with `conditions: []`** – no `tagsAdded` /
`tagsRemoved` condition at all (second probe on Example Test, sweep of 2026-09-15T13:37:59+10:00,
trigger `id_EXAMPLE_02`, `active: true`). HighLevel accepts the save; what the runtime
then treats as its event (any tag added or removed) was not exercised live.

Still open: the fourteen `contact_tag` triggers in Example Co's draft `001-WF-*` / `011-WF-*`
workflows carry `{field: "tagsAdded", value: ""}` – a filter present but blank, which is not the
shape the builder writes today for "no tag chosen". Most likely a filter whose tag was deleted,
or an older builder's output; not established, so do not model it as "any tag".
