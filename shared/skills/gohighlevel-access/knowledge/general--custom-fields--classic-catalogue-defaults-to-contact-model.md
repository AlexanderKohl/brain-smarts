---
id: ghl-general--custom-fields--classic-catalogue-defaults-to-contact-model
title: GET /locations/{id}/customFields returns only contact fields unless model is passed
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /locations/{locationId}/customFields
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-22
verified: 2026-09-22
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--custom-fields--classic-catalogue-defaults-to-contact-model.md
created: 2026-09-22T12:05:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# The classic catalogue silently answers for contacts only

## Behaviour

`GET /locations/{locationId}/customFields` with no query string returns **contact
fields only**, with no flag in the response saying so. The `model` parameter selects
the rest:

```text
GET /locations/loc_EXAMPLE_01/customFields                       -> 200, 86 fields
GET /locations/loc_EXAMPLE_01/customFields?model=contact         -> 200, 86 fields
GET /locations/loc_EXAMPLE_01/customFields?model=opportunity     -> 200, 233 fields
GET /locations/loc_EXAMPLE_01/customFields?model=all             -> 200, 346 fields
```

`model=all` also returns custom-object fields, which neither of the other two do. On
Example Co (Staging) the 346 break down as 233 `opportunity`, 86 `contact`,
14 `custom_objects.installers` and 13 `custom_objects.example_docs`.

Each row carries `model`, so a caller that fetched `model=all` can partition locally
and never needs the per-model calls.

## Why it is non-obvious

The bare call succeeds, returns a large plausible list, and names itself after the
location rather than the object. Nothing in the response marks it as a subset. A
caller checking "is `opportunity.datetime_bill_uploaded` in the catalogue?" gets a
clean 200 and a confident, wrong "no" - the failure looks like a missing field in
HighLevel rather than a missing query parameter.

This repository had already recorded the Staging catalogue as "225 fields" while
treating it as the whole catalogue. That figure was the opportunity model alone; the
true total at the time would have been roughly 90 higher.

## Evidence

Live read-only probe against Example Co (Staging) `loc_EXAMPLE_01`
(company `comp_EXAMPLE_01`) on 22 September 2026 through
`/shared/skills/gohighlevel-access`, using an agency-derived Location token. All four
calls above were made in the same session, seconds apart. `confirmed`, not inferred.

## Applies to

Every field-catalogue read on a sub-account. Pass `model=all` and partition on the
returned `model` key unless only one object is wanted.

Related: [`general--picklist-fields--value-is-key-not-label`](general--picklist-fields--value-is-key-not-label.md),
[`opportunity--picklist-fields--classic-catalogue-returns-bare-strings`](opportunity--picklist-fields--classic-catalogue-returns-bare-strings.md).
