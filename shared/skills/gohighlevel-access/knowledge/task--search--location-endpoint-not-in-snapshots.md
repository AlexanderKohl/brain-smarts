---
id: ghl-task-search-location-endpoint
title: Location-wide task search lives at POST /locations/{locationId}/tasks/search – undocumented in the snapshots, 201, limit 500
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: task
field_type: null
endpoint: POST /locations/{locationId}/tasks/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-03
verified: 2026-09-03
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/task--search--location-endpoint-not-in-snapshots.md
created: 2026-09-03T11:15:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Tasks are searchable location-wide, but only at the `/locations/` path

## Behaviour

`POST /locations/{locationId}/tasks/search` returns every task in a
sub-account, filterable by assignee, in one call. It is the only
location-wide task read; everything else HighLevel exposes is per-contact.

```jsonc
// POST /locations/loc_EXAMPLE_03/tasks/search
{ "assignedTo": ["id_EXAMPLE_01"], "limit": 500 }

// -> HTTP 201
{ "tasks": [ { "_id": "...", "searchAfter": [1788329940000, "..."], ... } ] }
```

Confirmed details:

- **Success status is 201, not 200.** A client whitelisting `(200,)` – as
  `HighLevelConnection.request()` does by default – raises on a successful
  search. Same trap as `POST /opportunities/search`; see
  [`opportunity--search--limit-not-pagelimit`](opportunity--search--limit-not-pagelimit.md).
- **`limit` accepts 500** and returns a full 500 rows. Page with the
  *last row's* `searchAfter` array echoed back as a top-level `searchAfter`
  key. 909 tasks came back in **2 calls**.
- **No `total` in the response.** Stop when a page returns fewer rows than
  `limit`, not on a count.
- **`assignedTo` is an array of user IDs**, not a single string.
- The `Version` header is irrelevant here – absent, `2021-07-28` and `v3`
  all behave identically.
- The row shape is **richer than the per-contact endpoint**: `_id` (not
  `id`), `status` / `statusGroup` (`to_do` | `completed`), `deleted`,
  `dateAdded` / `dateUpdated`, `assignedToUserDetails` and
  `contactDetails`. Compare `GET /contacts/{contactId}/tasks`, which
  returns only `{id, title, body, assignedTo, dueDate, completed, contactId}`.
  `contactDetails.firstName` / `.lastName` are frequently `null` even when
  the contact has a name – join to `POST /contacts/search` output for
  reliable names.

Every path a caller would guess first fails:

| Attempt | Result |
| --- | --- |
| `POST /contacts/tasks/search` | 404 `Cannot POST /contacts/tasks/search` |
| `POST /tasks/search`, `POST /tasks/`, `GET /tasks/?locationId=` | bare 404 |
| `GET /contacts/tasks?locationId=` | 400 `Contact with id tasks not found` |
| `POST /contacts/search` with `filters:[{field:"tasks.assignedTo"...}]` | 400 `Invalid field tasks.assignedTo` |

## Why it's non-obvious

The task endpoints sit under the **Contacts** product area in the docs and
under `/contacts/` on the wire (`GET|POST /contacts/{contactId}/tasks`),
so the natural search path is a `/contacts/`-prefixed one – and all of
those 404. The working endpoint is filed under **Locations** instead,
against a path prefix otherwise used for sub-account configuration
(custom values, custom fields), not for record search.

This skill's OpenAPI snapshot `openapi/contacts-v3.json` contains only the
five per-contact task operations, and `SKILL.md`'s endpoint-verification
table lists the same five. Nothing in either points at the location path,
so a caller grounding request shapes in the local snapshots – as the
skill instructs – concludes no location-wide task read exists and falls
back to iterating contacts. On Example Plumbing Pty Ltd that fallback is
**4,763 requests instead of 2**.

The `GET /contacts/tasks?locationId=` 400 is the same masking behaviour
already recorded in
[`contact--delete--search-index-lag-and-400-not-found`](contact--delete--search-index-lag-and-400-not-found.md)
and [`business--record-id--400-not-404-invalid-id`](business--record-id--400-not-404-invalid-id.md):
the literal segment `tasks` is parsed as a contact ID and reported as a
missing record, which reads like a data problem rather than a wrong path.

## Evidence

Live probes against Example Plumbing Pty Ltd (`loc_EXAMPLE_03`,
company `comp_EXAMPLE_01`) on 2026-09-03, retrieving the 909 tasks
assigned to user `id_EXAMPLE_01`; logged at
the owner's project log (memory layer).
Endpoint supplied by the owner from
`marketplace.gohighlevel.com/docs/ghl/locations/task-search/` after the
contact-iteration fallback had already been run.

Cross-checked both ways: iterating `GET /contacts/{contactId}/tasks` over
all 4,763 contacts (0 errors) found **907** tasks for that user; the
location search found **909**. The two-task gap is unexplained and small –
most likely tasks on contacts created during the ~13-minute scan. Treat
the location search as the more complete of the two, not as exactly
reconciled.

## Applies to

Task reads in any sub-account. Writes remain per-contact
(`POST /contacts/{contactId}/tasks`, `PUT .../{taskId}`,
`PUT .../{taskId}/completed`) – this endpoint is search only, and there is
no location-wide task write.

The filter set beyond `assignedTo`, `limit` and `searchAfter` was not
probed; `completed`, `contactId` and date-range filters are plausible but
**unverified here**. Filtering client-side on the returned rows is
confirmed to work.
