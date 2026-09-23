---
id: ghl-general-email-templates-delete-route-needs-location-id-segment
title: Email template hard delete works at DELETE /emails/builder/{locationId}/{templateId}; the shorter /emails/builder/{id} form 404s
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: DELETE /emails/builder/{locationId}/{templateId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--email-templates--delete-route-needs-location-id-segment.md
  - /shared/skills/gohighlevel-access/knowledge/general--email-templates--requires-version-v3-header.md
created: 2026-09-15T14:20:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Email template hard delete needs the location ID as a path segment

## Behaviour

```
DELETE /emails/builder/{locationId}/{templateId}
  headers: Location OAuth token, default Version (2021-07-28) – no Version: v3 needed
  -> 200 {"ok": true, "traceId": "..."}
```

This is a **hard delete**. Immediately afterwards:

- `GET /emails/locations/{locationId}/templates/{templateId}` (`Version: v3`) returns
  `404 {"message":"Template Not Found","code":5005,"messageKey":"emails.builder.error.templateNotFound"}`.
- The template appears in neither the active listing nor `?archived=true` on either path
  family (`/emails/locations/{locationId}/templates` and `/emails/builder`).

The shorter form `DELETE /emails/builder/{templateId}` (with or without `locationId` as a query
string or body field) is a routing-level `404 Cannot DELETE ...` and was the reason the earlier
entry concluded no DELETE existed.

Related: `GET /emails/locations/{locationId}/templates` rejects `limit` above 50 with
`422 ["limit must not be greater than 50"]`; page with `limit=50&offset=N`.

## Why it's non-obvious

Every other route in this resource family takes the location either in the path prefix
(`/emails/locations/{locationId}/...`) or as `locationId` in the query/body
(`/emails/builder?locationId=`). DELETE alone takes it as a bare second path segment under
`/emails/builder/`, so the "obvious" `/emails/builder/{id}` guess, which works for PATCH, 404s
for DELETE in a way indistinguishable from the route not existing.

## Evidence

Confirmed live 2026-09-15 in `Example Co Master` (`loc_EXAMPLE_02`), owner-directed
deletion of one template named `DELETE Default - Invoice received`
(`000000000000000000000001`). DELETE returned `200 {"ok":true}`; a fresh `GET` by id returned
the 404 above; both active and archived listings on both path families no longer contained the
id. Listing cross-check before the delete: documented list and builder alias both returned the
same five active ids.

## Applies to

Email Builder v2 templates via a Location OAuth token derived from the connected agency grant.
`PATCH {"archived": true}` remains the soft alternative when the record should stay
recoverable. Not tested for SMS templates or the separate `/locations/{locationId}/templates`
store.
