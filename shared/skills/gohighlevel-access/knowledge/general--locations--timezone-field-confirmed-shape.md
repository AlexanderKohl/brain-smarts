---
id: ghl-general-locations-timezone-field
title: GET /locations/:locationId returns the location's own configured timezone
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /locations/:locationId
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-25
verified: 2026-08-25
source_refs: []
created: 2026-08-25T09:45:00+10:00
updated: 2026-09-23T14:45:16+10:00
evidence:
- Live raw authenticated call (gohighlevel-access skill), 2026-08-25, against the "Example Test" sub-account (loc_EXAMPLE_04) -- returned "Australia/Brisbane"
---

# GET /locations/:locationId: the location's own timezone

## Behaviour

`GET /locations/:locationId` (scope `locations.readonly`) returns a
wrapped `{ location: { ..., timezone: "Australia/Brisbane", ... } }`
object. `location.timezone` is a plain IANA zone string – the sub-account's
own configured timezone, confirmed live against a real account.

**Not to be confused with** `GET /locations/:locationId/timezones` (see
`contact--timezone--empty-catalog-needs-locations-endpoint.md`), which
returns the *catalog of selectable timezone values* for a Contact custom
field – a completely different endpoint and a different concept
(available option values vs. this location's own actual setting).

## Why it's non-obvious

The two endpoints' names differ by one trailing `/timezones` segment and
are easy to conflate; only one of them (this one) tells you what timezone
the location itself is actually set to.

## Evidence

Confirmed live via a raw authenticated `GET` (`gohighlevel-access` skill)
against the "Example Test" sub-account: `200`, full location object,
`timezone: "Australia/Brisbane"` (also separately echoed under
`location.business.timezone`).

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

General – any feature needing "what timezone is this sub-account in,"
independent of object type. Typical use: rendering a
submission timestamp in the sub-account's timezone instead of
raw UTC. Uses the `locations.readonly` scope, already
requested by every existing install for install-time context – no
reinstall needed to start using this field.
