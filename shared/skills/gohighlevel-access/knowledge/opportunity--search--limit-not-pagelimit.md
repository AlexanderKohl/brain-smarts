---
id: ghl-opportunity-search-limit-not-pagelimit
title: POST /opportunities/search rejects pageLimit and pageSize; use limit, and expect a 201
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: POST /opportunities/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-02
verified: 2026-09-02
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/opportunity--search--limit-not-pagelimit.md
created: 2026-09-02T21:20:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# POST /opportunities/search takes `limit`, not `pageLimit`

## Behaviour

The three record-search endpoints do **not** share a page-size parameter:

| Endpoint | Page-size key | Success status |
|---|---|---|
| `POST /contacts/search` | `pageLimit` | 200 |
| `POST /objects/{key}/records/search` (v3) | `pageLimit` | 200 |
| **`POST /opportunities/search`** | **`limit`** | **201** |

Sending `pageLimit` to `/opportunities/search` returns:

```json
{"message":["property pageLimit should not exist"],"error":"Unprocessable Entity","statusCode":422}
```

`pageSize` is rejected identically (`property pageSize should not exist`). The rejection is
whole-request: nothing is returned, so a caller that treats the search as best-effort gets an empty
result rather than a partial one.

Everything else in the body is shared and accepted as-is: `locationId`, `page`,
`filters: [{field, operator, value}]` (including `contains_set` on `id`), and `searchAfter`. Only
the page-size key differs. Omitting a page-size key entirely also works.

The success status is **201, not 200** – a client that whitelists 200 will treat a successful search
as a failure.

## Why it's non-obvious

The 422 names the offending property clearly, but only if anyone sees it. In the case that found
this, the call sat inside a `try { … } catch {}` whose comment said labels were presentation-only
and a CRM read failure must not hide the links – correct in intent, but it swallowed a permanent,
100%-reproducible misuse of the API. Every Opportunity row in the ExampleFormsApp dashboard showed a raw
record id from the day the dashboard shipped, and it read as a display choice rather than a broken
request. Contacts and Custom Objects were unaffected, which made it look object-specific in a way
that pointed at label resolution rather than at the request body.

**Lesson: a best-effort catch around an API call needs a log line.** Without one, a permanent
failure is indistinguishable from the feature not existing.

## Evidence

Confirmed 2026-09-02 against `Example Test` (`loc_EXAMPLE_04`) with a Location token derived
from the connected agency grant. Two real opportunities (`Tobin Vale Sample Launch`,
`Mira Quill Sample Expansion3`) were listed via `GET /opportunities/search?location_id=…&limit=3`,
then their ids were used in a `contains_set` filter across six body shapes:

| Body | Result |
|---|---|
| `page` + `pageLimit` + `searchAfter` (the shape that shipped) | 422 `property pageLimit should not exist` |
| `pageSize` | 422 `property pageSize should not exist` |
| no page-size key | 201, both rows with `name` |
| `limit` | 201, both rows with `name` |
| `limit` + `page` | 201, both rows with `name` |
| `limit` + `searchAfter` | 201, both rows with `name` |

Production logs for the same period show the identical 422 repeating on every dashboard load of the
Opportunity tab.

## Applies to

The opportunity search resource specifically. Do not generalise the `limit` key to
`/contacts/search` or the v3 `/objects/{key}/records/search`, which require `pageLimit` and reject
`limit` handling in the opposite direction (untested, but they are documented with `pageLimit` and
have worked with it continuously).
