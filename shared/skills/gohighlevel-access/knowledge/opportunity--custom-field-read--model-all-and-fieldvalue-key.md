---
id: GHL-OPPORTUNITY-CUSTOM-FIELD-READ-SHAPE
title: Reading opportunity custom fields needs ?model=all on the catalogue and the fieldValue key on the record
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: GET /locations/{locationId}/customFields
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-01
verified: 2026-09-01
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/opportunity--custom-field-read--model-all-and-fieldvalue-key.md
created: 2026-09-01T11:13:57+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Opportunity custom fields: catalogue needs `?model=all`, record uses `fieldValue`

## Behaviour

Two independent traps combine to make opportunity custom fields read back as
empty.

**1. The catalogue endpoint silently filters to contact.**
`GET /locations/{locationId}/customFields` with no query string returns *only*
`model: contact` fields – 78 in `Example Co (Staging)`. There is no error, no
warning, and no indication the response is partial. Adding `?model=all` returns
269 (`opportunity: 185`, `contact: 78`, `custom_objects.installers: 6`);
`?model=opportunity` returns the 185. Every opportunity field id is absent from
the unqualified response, so an id→key map built from it resolves nothing.

**2. The record uses `fieldValue`, not `value`.**
`GET /opportunities/{id}` returns custom fields as:

```json
{"id": "id_EXAMPLE_01", "fieldValue": "Metal Tin"}
```

Contacts use `value` in the equivalent position. Code that reads `value` on an
opportunity gets `None` for every field.

~~Note also that `GET /opportunities/search` omits custom fields altogether – the
per-id `GET /opportunities/{id}` is required to see them.~~ **Corrected
2026-09-09:** search *does* return custom fields, under the type-scoped keys
`fieldValueString` / `fieldValueNumber` rather than `fieldValue`, which is why
they read as absent. See
`opportunity--search--returns-custom-fields-type-scoped.md`. The rest of this
entry was re-confirmed by the same probe and stands.

## Why it's non-obvious

Both failures are silent and produce the same symptom – every field reads empty
– which looks exactly like "the automation did not populate the opportunity".
During the Example Co end-to-end test this nearly produced a false FAIL on the
mandated Roof Type and Number of Phases checks, when the data was in fact
present and correct. Nothing in the response distinguishes "field not set" from
"you asked the wrong way", and the unqualified catalogue call looks complete
because it returns a large, plausible list.

## Evidence

Live probe against `Example Co (Staging)` (`loc_EXAMPLE_01`) on
2026-09-01. Seven populated custom fields on opportunity
`id_EXAMPLE_02` resolved to zero known keys against the unqualified
catalogue and all seven against `?model=all`; values were `None` under `value`
and correct under `fieldValue`. `confirmed` – both halves observed directly.

## Correct usage

Build the id→key map from `GET /locations/{locationId}/customFields?model=all`
(or `?model=opportunity`), read the record with `GET /opportunities/{id}`, and
take values from `fieldValue`. Do not rely on `GET /opportunities/search` for
custom-field content.
