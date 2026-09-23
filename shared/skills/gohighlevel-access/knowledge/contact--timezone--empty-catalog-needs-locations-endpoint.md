---
id: ghl-contact-timezone-empty-catalog
title: Contact timezone field's own catalog picklist is empty; real options come from the locations timezones endpoint
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: timezone
endpoint: GET /locations/:locationId/timezones
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Contact timezone: catalog is empty, use the locations endpoint

## Behaviour

The Contact `timezone` field's own field-catalog picklist is confirmed
**empty** – no options at all – so relying only on the catalog leaves the
dropdown with nothing to show. The authoritative option list comes from
`GET /locations/:locationId/timezones` instead, whose response wraps the
array under a key that must be matched **case-insensitively**: a real
response returned it as `timeZones` (capital Z), not `timezones`.

HighLevel's real list includes legacy IANA aliases (`Etc/GMT+12`) and
deprecated zone names (`Australia/Canberra`) that
`Intl.supportedValuesOf("timeZone")` does not enumerate – a generated
"complete" fallback list still cannot match every value HighLevel actually
sends/accepts, so only HighLevel's own list is authoritative here; there
is no safe computed fallback.

Separately confirmed: the field is written as a flat top-level
`{ timezone: <value> }` key on `PUT /contacts/:contactId`, **not** wrapped
in `customFields` – no write-path change was needed once the read-side
option-source fix landed.

## Why it's non-obvious

The generic pattern for every other picklist field on this integration is
"trust the field catalog's own options" – timezone is the one field where
that pattern silently produces zero options, with no error to signal it.
The response-key casing (`timeZones` vs `timezones`) is also a one-off
that a copy-pasted "match one exact key" parser would miss without ever
erroring – it just returns zero matched results.

## Evidence

Confirmed live via `GET /locations/:locationId/timezones` returning `200`
with data under `timeZones`; confirmed the real list contains `Etc/GMT+12`
and `Australia/Canberra`, both absent from a generated `Intl` list.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Contact's `timezone` field specifically. This app caches the fetched list
in a local DB table (refreshed by a cleanup cron job) rather than
fetching live per form load, since timezones aren't location-specific data
despite the endpoint being location-scoped.

**Do not confuse this endpoint with `GET /locations/:locationId`** (no
trailing `/timezones`), which returns the location's own single configured
timezone, not a catalog of selectable values – see
`general--locations--timezone-field-confirmed-shape.md`.
