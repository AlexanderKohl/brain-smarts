---
id: GHL-OPPORTUNITY-SEARCH-CUSTOM-FIELDS-TYPE-SCOPED
title: GET /opportunities/search does return custom fields, but keyed fieldValueString/Number, not fieldValue
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: GET /opportunities/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-09
verified: 2026-09-09
source_refs: []
created: 2026-09-09T09:40:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Opportunity search returns custom fields under type-scoped value keys

## Behaviour

`GET /opportunities/search` **does** populate `customFields` on every returned
opportunity. It does not use the uniform `fieldValue` key that
`GET /opportunities/{id}` uses; it uses the type-scoped keys, plus an explicit
`type` discriminator:

```jsonc
// GET /opportunities/search?location_id=...&limit=10
{"fieldValueString": "test",   "id": "id_EXAMPLE_01", "type": "string"}
{"fieldValueString": "Residential", "id": "id_EXAMPLE_02", "type": "string"}
{"id": "id_EXAMPLE_03", "fieldValueNumber": 3, "type": "number"}

// GET /opportunities/{id} – same three fields, same values
{"id": "id_EXAMPLE_01", "fieldValue": "test"}
{"id": "id_EXAMPLE_02", "fieldValue": "Residential"}
{"id": "id_EXAMPLE_03", "fieldValue": 3}
```

Coverage is complete, not a subset: on `id_EXAMPLE_04` the search
returned 33 custom fields and the per-id detail returned the same 33.

The practical consequence is that **the per-id read is not required merely to
see custom-field values.** A caller that needs values for many opportunities on
one contact can take them from the single search response instead of issuing
one `GET /opportunities/{id}` per opportunity – provided it reads the
type-scoped keys.

## Why it's non-obvious

Reading `fieldValue` on a search result returns `undefined` for every field,
which is indistinguishable from the field being absent. That is exactly how the
earlier conclusion was reached: the note in
`opportunity--custom-field-read--model-all-and-fieldvalue-key.md` that "GET
/opportunities/search omits custom fields altogether" describes the symptom of
reading the wrong key, not the API. That note is superseded by this entry; the
rest of that entry (`?model=all` on the catalogue, `fieldValue` on the per-id
read) remains correct and was re-confirmed by the same probe.

The same type-scoped value shape is already documented for other objects in
`general--field-values--type-scoped-parsing-required.md` and
`business--all-field-types--classic-read-typed-value-keys.md`. Opportunity
search follows that family; the per-id opportunity read is the odd one out.

Note also that `source` is a **standard** opportunity property, present on both
the search result and the detail record (observed value `'Internal Request
Form'`). It is not a custom field, and no `opportunity.source` custom field
exists in `Example Co (Staging)`. `{{opportunity.source}}` resolves to the
standard property, written as top-level `source` in a create/update payload.

## Evidence

Live read-only probe against `Example Co (Staging)`
(`loc_EXAMPLE_01`) on 2026-09-09, via the agency OAuth connection:
`GET /opportunities/search?location_id=…&limit=10` followed by
`GET /opportunities/{id}` on the same record, comparing both shapes and counts.
Ten of ten search results carried a populated `customFields` array (lengths 1 to
33). `confirmed`, not hypothesised.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

