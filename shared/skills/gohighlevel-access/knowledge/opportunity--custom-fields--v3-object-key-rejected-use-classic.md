---
id: ghl-opportunity-custom-fields-v3-object-key-rejected-use-classic
title: Opportunity field catalogue and definition writes must use classic locations/customFields, not v3 object-key/opportunity
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: GET /objects/object-key/opportunity; GET/PUT /locations/{locationId}/customFields
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-04
verified: 2026-09-04
source_refs: []
created: 2026-09-04T12:27:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Opportunity field definitions: v3 object-key rejected, use classic catalogue

## Behaviour

`GET` (and related v3 custom-field routes) for `object-key/opportunity` return HTTP 400. Opportunity custom-field *definitions* are listed and updated on the classic location catalogue:

- List: `GET /locations/{locationId}/customFields?model=opportunity`
- Rename/update: `PUT /locations/{locationId}/customFields/{fieldId}` with `Content-Type: application/json`

Custom *object* fields (for example `custom_objects.site_visits`) still use Custom Fields v3 (`POST /custom-fields/` with `Version: v3` and `objectKey`).

## Why it's non-obvious

Custom Fields v3 accepts an `objectKey`, and `opportunity` is a recognised standard-object key elsewhere, so it looks like the same surface as Site Visit / Business. Folder creation already documents that v3 rejects Contact/Opportunity `objectKey`; field list/create for Opportunity fails the same way and must fall back to the classic `locations/.../customFields` routes.

## Evidence

Live probe against `Example Co (Staging)` (`loc_EXAMPLE_01`) on 2026-09-04 while copying Opportunity fields onto Site Visit. The v3 object-key route returned HTTP 400; `?model=opportunity` returned the 190-field catalogue used for the writes. `confirmed`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for Opportunity field catalogue/definition access. Custom objects and Business remain on the v3 custom-fields surface. Reading *values* on an opportunity record is a separate quirk (`opportunity--custom-field-read--model-all-and-fieldvalue-key.md`).
