---
id: ghl-business-custom-fields-objects-api
title: Business custom fields must be written through the Objects API, never the classic endpoint's customFields
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: null
endpoint: PUT /objects/business/records/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-22
verified: 2026-08-22
created: 2026-08-24T21:30:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Business custom fields: Objects API only

## Behaviour

`PUT /businesses/:businessId`'s `customFields` rejects **every** shape
tried – `422 "customFields must be an object"` – even the array-of-
`{id, fieldValue}` shape that works fine on the same field type for
Opportunity. Standard fields on that same classic endpoint are unaffected;
this is `customFields` specifically. Business custom fields must instead go
through `PUT /objects/business/records/:businessId?locationId=...`
(scope `objects/record.write`), body `{ properties: { <key>: <value> } }`,
with two further confirmed details:

- `properties` keys are the field's **short key** (`business_turnover`),
  not its full `fieldKey` (`business.business_turnover` – sending the full
  key gets a distinct `400`, "couldn't validate the mapped field", not a
  silent no-op).
- A checkbox/multiselect field rejects a plain array – `422 "We couldn't
  apply updates to <Field> due to an unexpected format"` – and needs the
  add/remove delta shape instead (see
  `general--custom-fields--checkbox-multiselect-delta-required.md`),
  diffed against a fresh `GET` of the record's current properties. Every
  other field type (text, number, date, single-value select) accepts a
  plain value directly.

## Why it's non-obvious

Business is otherwise a "classic endpoint" object (`/businesses/:id`), so
the natural assumption is that all of its fields – standard and custom –
go through that one endpoint, the way Contact and Opportunity's do. Custom
fields silently need a completely different endpoint (the Objects API
endpoint normally associated with Custom Object records).

## Evidence

Confirmed live via a raw authenticated call (`gohighlevel-access` skill +
agency token, bypassing the app): the classic write attempt reproduced the
422, the Objects API write with short key succeeded, and a follow-up `GET`
confirmed the change.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business only. `BusinessAdapter.updateRecord`/`createRecord` therefore
issue up to two requests per write: the classic PUT for standard fields
(if any changed) and this separate Objects API PUT for custom fields (if
any changed) – see `business--standard-fields--write-shape-and-key-overrides.md`
for the standard-field half.
