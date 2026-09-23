---
id: ghl-opportunity--search--custom-field-values-omitted
title: Opportunity search returns an empty customFields array; values need one GET per opportunity
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
discovered: 2026-09-22
verified: 2026-09-22
source_refs: []
created: 2026-09-22T12:10:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Search gives you opportunities without their custom field values

## Behaviour

`GET /opportunities/search?location_id=...` returns each opportunity with a
`customFields` key that is present and **empty**. Fetching the same opportunity by id
returns the values:

```text
GET /opportunities/search?location_id=loc_EXAMPLE_01&limit=100
  -> 200, 11 opportunities, 0 non-empty customField values in total

GET /opportunities/{id}   (same records)
  -> 200, customFields populated: 8, 32, 25 and 25 values respectively
```

There is no opt-in. The search endpoint validates its query string strictly and
rejects the obvious guesses:

```text
GET /opportunities/search?...&getCustomFields=true
  -> 422 {"message":["property getCustomFields should not exist"],
          "error":"Unprocessable Entity","statusCode":422}
```

`includeCustomFields` and `getCustomField` were not reached in that run because the
first variant aborts the batch, but the 422 text shows the endpoint rejects any
unknown property rather than ignoring it, so a working spelling would have to be
documented rather than guessed.

The system timestamps (`createdAt`, `updatedAt`, `lastStageChangeAt`,
`lastStatusChangeAt`) **are** returned by search on every row.

## Why it is non-obvious

Contact search returns custom field values inline, so the symmetrical expectation for
opportunities is reasonable and wrong. The empty array is worse than a missing key: a
caller that iterates `customFields` finds it present, iterates zero entries and
concludes the records are unpopulated, which on a staging sub-account full of test
data is a believable conclusion.

## Cost this imposes

Anything computing per-opportunity values - funnel step timestamps, a field-fill
census, reporting on custom data - costs **1 + N requests**, not 1. Against the
budget in
[`general--rate-limits--hundred-per-ten-seconds-and-daily-cap`](general--rate-limits--hundred-per-ten-seconds-and-daily-cap.md)
(100 requests per 10 seconds per app per location), 500 opportunities is about 50
seconds of wall clock for one sub-account, before any other caller is considered.

A dashboard therefore cannot compute these figures on page load. It needs an
incremental store fed in the background, keyed on the `updatedAt` that search does
return, so only changed opportunities are re-fetched.

## Evidence

Live read-only probe against Example Co (Staging) `loc_EXAMPLE_01` on
22 September 2026 through `/shared/skills/gohighlevel-access`. All 11 opportunities
were read both ways in the same session. `confirmed`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Every opportunity read where custom field values matter. Search remains correct and
cheap for ids, names, stages, status, assignment and the four system timestamps.
