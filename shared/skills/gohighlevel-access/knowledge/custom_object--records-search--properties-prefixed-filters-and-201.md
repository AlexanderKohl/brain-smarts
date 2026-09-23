---
id: GHL-CUSTOM-OBJECT-RECORDS-SEARCH-FILTER-SHAPE
title: Custom-object record search returns 201 and filters on properties.<field>, not the bare field name
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: null
endpoint: POST /objects/{objectKey}/records/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-09
verified: 2026-09-09
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/custom_object--records-search--properties-prefixed-filters-and-201.md
created: 2026-09-09T11:20:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Custom-object record search: 201, `pageLimit`, and `properties.`-prefixed filters

## Behaviour

Three things about `POST /objects/{objectKey}/records/search` that a caller has
to get right together, or the search silently returns nothing useful:

**1. It answers HTTP 201, not 200.** A client that whitelists 200 treats a
successful search as a failure. (The portable brain's `ghl_oauth` client raises
`HighLevelOAuthError` unless `expected=(200, 201)` is passed.)

**2. Page size is `pageLimit`, and `page` is required.** Same as
`POST /contacts/search`; note this differs from `POST /opportunities/search`,
which takes `limit` – see
`opportunity--search--limit-not-pagelimit.md`.

**3. Filters address a property as `properties.<field>`, never the bare field
name.** The bare name is rejected outright:

```jsonc
// POST /objects/custom_objects.site_visits/records/search
{"filters": [{"field": "oid", "operator": "eq", "value": "abc123"}]}
// -> HTTP 422 {"message":"Invalid field - oid","error":"Unprocessable Entity"}

{"filters": [{"field": "properties.oid", "operator": "eq", "value": "abc123"}]}
// -> HTTP 201, matches correctly
```

Free-text `query` also matches property *values* (searching `"Test Site Visit"`
returned the record whose `project_name` was exactly that), so `query` is a
usable fallback – but it is a substring search across the record, not an exact
field match, and will over-match.

A returned record carries `id`, `locationId`, `objectId`, `objectKey`,
`createdBy`, `lastUpdatedBy`, `owners`, `followers`, `searchAfter`, `sort`,
`createdAt`, `updatedAt` and `properties`. **`properties` contains only the
fields that have values** – an unset property is absent, not null.

## Why it's non-obvious

The two failure modes look identical from the caller's side and neither
resembles its cause. Getting the filter prefix wrong is a hard 422 that a
caller wrapping search in a try/catch will swallow into "no match found";
getting the status code wrong turns a successful, correctly-filtered search into
a thrown error. Neither says anything about properties or pagination.

The prefix is also inconsistent with how the same object's fields are addressed
elsewhere: custom-field *definitions* use the flat `custom_objects.<obj>.<field>`
fieldKey, and record *writes* nest values under `properties`, but only the
search filter demands the `properties.` prefix on the field name itself.

## Evidence

Live read-only probe against `Example Co (Staging)`
(`loc_EXAMPLE_01`) on 2026-09-09 via the agency OAuth connection, against
`custom_objects.site_visits`. An empty query returned the single record; a
free-text query on a property value matched it; a nonsense query returned zero;
`filters` on `properties.oid` was accepted (201, zero matches, since no record
carried that oid); `filters` on bare `oid` returned 422 `Invalid field - oid`.
A positive control – `properties.project_name eq "Test Site Visit"` returning
the record, and `eq "Nope"` returning none – confirmed the filter genuinely
matches on property values rather than merely being accepted. `confirmed`, not
hypothesised.
