---
id: ghl-general-invoices-tax-list-endpoint-500-use-invoice-line-items
title: GET /invoices/tax returns HTTP 500; scrape tax IDs from invoice and template line items
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /invoices/tax
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-09-02'
verified: '2026-09-02'
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--invoices-tax--list-endpoint-500-use-invoice-line-items.md
created: 2026-09-02T10:50:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Invoice tax catalogue list is unusable; tax IDs live on line items

## Behaviour

`GET https://services.leadconnectorhq.com/invoices/tax` with
`altId=<locationId>&altType=location` returns HTTP 500
`{"statusCode":500,"message":"Internal server error"}` even when
`limit`/`offset` are sent as strings, with or without `search=`, and with
`Version` `2021-07-28` or `v3`. This happened on a location that already
had `invoices.readonly` / `invoices.write` and that had live invoices with
tax objects attached.

`GET /payments/tax?locationId=<locationId>` returns HTTP 401
"token is not authorized for this scope" unless the install includes
`payments/taxesSettings.readonly`. `invoices.readonly` is not sufficient.

Working read path: `GET /invoices/?altId=<locationId>&altType=location`
with `limit` and `offset` as **strings** (numeric query values 422). Each
invoice line's `invoiceItems[].taxes[]` carries:

```json
{
  "_id": "<taxId>",
  "name": "GST",
  "rate": 10,
  "calculation": "exclusive",
  "description": "GST on Income"
}
```

`GET /invoices/template?altId=...&altType=location&limit=20&offset=0`
returns `{ "data": [ ... ] }` and the same `taxes[]` shape on template
line items. `GET /invoices/settings` does not include tax catalogue IDs.
`GET /invoices/estimate` returned HTTP 500 on the same location.

This scrape only finds taxes that are already attached to an invoice or
template. Unused catalogue rates would be invisible while `/invoices/tax`
500s.

## Why it's non-obvious

HighLevel documents a dedicated tax list under Invoices. A 200 list of
`{ _id, name, rate }` is the obvious first call. The live list endpoint
fails with a generic 500, and the Payments tax-settings sibling is gated
on a different scope, so the durable IDs are only on document line items.

## Evidence

Confirmed 2026-09-02 with a live agency-OAuth location-token pull against
`Example Co (Staging)` (`loc_EXAMPLE_01`). Regenerable probe
artefacts under a local run folder.

## Applies to

Invoice tax catalogue listing (`GET /invoices/tax`) and Payments tax
settings (`GET /payments/tax`) as of 2026-09-02. Does not claim that
creating or updating a tax via `POST/PUT /invoices/tax` is broken – those
were not tried (read-only pull). Do not assume Contact/Opportunity custom
fields hold these IDs; they did not.
