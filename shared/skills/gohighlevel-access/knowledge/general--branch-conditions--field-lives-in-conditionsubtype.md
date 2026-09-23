---
id: gohighlevel-branch-condition-field-in-conditionsubtype
title: A workflow branch condition names its field in conditionSubType, not in any field key
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /workflow/:locationId/:workflowId
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: 2026-09-14
source_refs: []
created: 2026-09-14T09:40:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# A branch condition names its field in `conditionSubType`

## Behaviour

An `if_else` step's branch conditions live at
`workflowData.templates[].attributes.branches[].segments[].conditions[]`. A condition carries:

```json
{
  "conditionType": "contact_detail",
  "conditionSubType": "tags",
  "conditionOperator": "index-of-true",
  "conditionValue": ["ai off"],
  "__customFieldType__": "standard",
  "__conditionId": "37b825fe-…",
  "ifElseNodeId": "",
  "isWait": false,
  "nestedDropdownTypes": [...],
  "allowIsOperatorTypes": [...]
}
```

There is **no `field` key and no `__customFieldKey__` key** – across 218 conditions in a
45-workflow account, neither appeared once.

The field is assembled from two keys:

- `conditionType` names the object – `contact_detail` → contact, `opportunities` → opportunity,
  `custom_values` → a custom value, `contact_reply` → the inbound message.
- `conditionSubType` names the attribute – either a standard name (`state`, `tags`, `type`,
  `phone`, `pipelineId`, `pipelineStageId`), a **24-character custom-field id**, or an already
  qualified key (`message.body`), or a merge token
  (`{{custom_values.serviceable_postcodes}}`).

`conditionSubType: "trigger"` is not a field: the branch is tied to *which trigger fired*, and
its `conditionValue` is a trigger id.

`__customFieldType__` reads `"standard"` even when `conditionSubType` is a custom-field id, so it
does not distinguish custom from standard and must not be used to decide how to resolve the key.

## Why it's non-obvious

A *trigger* condition in the same payload does carry `field` (`contact.xyz`, `form.id`), so code
written against triggers looks correct and then silently resolves nothing for branches. The
failure is quiet: conditions parse, the branch structure is right, only the field is blank – so a
simulator matching a chosen state against branch conditions finds no match anywhere and reports
"that state does not narrow any path here", which reads like a property of the account rather
than a parser bug.

## Evidence

Confirmed 14 September 2026 against 45 captured workflows from the Example Co location: 218 raw
branch conditions, zero carrying `field` or `__customFieldKey__`; after reading
`conditionSubType`, 123 of 168 modelled conditions resolve to a field and the remaining 45 are
all `conditionType: trigger`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for `if_else` branch conditions in the workflow payload. Trigger conditions are a
**different** shape in the same payload and do use `field` – do not unify the two readers without
handling both.
