---
id: highlevel-custom-object-records-write-locationid-placement
title: Custom object record create takes locationId in the body; update takes it in the query string
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: POST /objects/:key/records and PUT /objects/:key/records/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-09
verified: 2026-09-09
source_refs: []
created: 2026-09-09T18:40:00+10:00
updated: 2026-09-23T18:00:00+10:00
---

# locationId placement is inverted between custom object create and update

## Behaviour

The two write verbs on the same resource disagree about where `locationId`
belongs, and each rejects the other's placement.

**Create – `locationId` in the body, never in the query string:**

```http
POST /objects/custom_objects.site_visits/records
{ "locationId": "<loc>", "properties": { "number_of_phases": "2" } }
→ 201 Created
```

| `locationId` placement | Result |
|---|---|
| query string only | `422 {"message":["property locationId should not exist"]}` |
| **body only** | **201 Created** |
| query string + body | `422 {"message":["property locationId should not exist"]}` |
| neither | `400 {"message":"LocationId is not specified"}` |

**Update – `locationId` in the query string, never in the body:**

```http
PUT /objects/custom_objects.site_visits/records/<id>?locationId=<loc>
{ "properties": { "number_of_phases": "2" } }
→ 200 OK
```

| `locationId` placement | Result |
|---|---|
| **query string only** | **200 OK** |
| body only | `422 {"message":["locationId must be a string","locationId should not be empty"]}` |
| query string + body | `422 {"message":["property locationId should not exist"]}` |
| neither | `404 {"message":"Custom Object (<key>) not found"}` |

`GET /objects/:key/records/:id?locationId=<loc>` follows the update
convention (200).

`owner` and `followers` are rejected on **both** verbs even though the
documented create body lists them – `422 "property owner should not
exist"`, and on PUT additionally `"followers must be an object"`. Send
neither; `locationId` + `properties` is the whole accepted body on create.

## Why it's non-obvious

The error text is NestJS whitelist-validation wording, so the query-string
rejection reads as though it were about the request body – the message
`property locationId should not exist` is returned for a request whose
body contains no `locationId` at all. That misdirects the obvious first
fix (strip it from the body) into a no-op.

Nothing signals that two verbs on one resource would disagree, so a client
that handles `locationId` uniformly across create/read/update looks
correct and passes for every read and update. Only create fails, which
delays discovery until the first record is created through that path
rather than updated.

The `400 LocationId is not specified` on create-with-neither confirms the
parameter is genuinely required, ruling out "this endpoint simply stopped
wanting it".

## Evidence

Live probe 2026-09-09 against `custom_objects.site_visits` in the
`Example Co (Staging)` subaccount (`loc_EXAMPLE_01`) via
`gohighlevel-access`, sending every combination above with resource
version header `2021-07-28`. Successful writes were read back to confirm
the properties persisted rather than being silently dropped.

Originally surfaced as a real recipient-facing failure: a form
submission that creates a record 422'd and reached the recipient as a
generic "could not be saved" message (production deploy logs,
`ghl_api_error`). `status: confirmed`.

Rationale: an earlier change moved `locationId` out of the write body
for *both* verbs on the strength of a single 422 on update. That was
correct for PUT and is what broke POST; the fix changed only the create
call.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for custom objects (`custom_objects.*`) on the Objects API.

Do **not** generalise the create half to other object types from this
entry alone. Business is known to behave differently in a related way:
`business--standard-fields--write-shape-and-key-overrides.md` records that
a top-level `locationId` is rejected on the Business `PUT` while still
being required and accepted on the Business `POST` – the same inversion,
but expressed through a different pair of endpoints. Whether Contact and
Opportunity follow either pattern is untested.
