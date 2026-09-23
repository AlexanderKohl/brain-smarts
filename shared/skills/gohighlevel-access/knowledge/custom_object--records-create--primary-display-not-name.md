---
id: ghl-custom-object-records-create-primary-display-not-name
title: Custom object create requires the primary display property key, not `name`
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: text
endpoint: POST /objects/:key/records
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-09-10'
verified: '2026-09-10'
source_refs: []
created: 2026-09-10T14:25:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Custom object create requires the primary display property, not `name`

## Behaviour

`POST /objects/:key/records` validates `requiredProperties` from the object
schema. For `custom_objects.site_visits` on Example Co (Staging)
(`loc_EXAMPLE_01`) that list is only:

```text
custom_objects.site_visits.project_name
```

which is also `primaryDisplayProperty`. Sending `properties.name` with the
opportunity title is accepted, then rejected:

```text
Missing required properties to create Site Visit - project_name
{"errorCode":"required_property_missing","fieldKey":"custom_objects.site_visits.project_name"}
```

The create body must use the short property key (`project_name`), matching
`oid` / `cid`. `name` does not alias to the primary display field.

## Why it's non-obvious

Standard CRM objects use `name`. Custom object records look like they have a
name too, and HighLevel still accepts a `name` property, so the request looks
successful until required-property validation. The live display title is a
custom field chosen at schema create (`primaryDisplayPropertyDetails.key`).

## Evidence

Confirmed live 2026-09-10: workflow `4.5` webhook request
`<uuid-01>` against opportunity `id_EXAMPLE_01`.
`GET /objects/custom_objects.site_visits?locationId=...` returned
`primaryDisplayProperty` and `requiredProperties` both equal to
`custom_objects.site_visits.project_name`. The field catalogue entry is TEXT
`Project Name` (`id_EXAMPLE_02`).

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for `custom_objects.site_visits` create. Other custom objects will
use whatever key is in that object's `requiredProperties` /
`primaryDisplayProperty`, which is not necessarily `name` or `project_name`.
Contact and Opportunity creates still use their own `/contacts` and
`/opportunities` APIs.
