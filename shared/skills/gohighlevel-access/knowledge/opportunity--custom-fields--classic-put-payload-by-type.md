---
id: ghl-opportunity-custom-fields-classic-put-payload-by-type
title: Classic Opportunity custom-field PUT needs JSON Content-Type and type-specific bodies; FILE_UPLOAD rejects maxFileLimit
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: PUT /locations/{locationId}/customFields/{fieldId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-04
verified: 2026-09-04
source_refs: []
created: 2026-09-04T12:27:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Classic Opportunity field PUT: JSON body and type-specific allowed keys

## Behaviour

`PUT /locations/{locationId}/customFields/{fieldId}` to rename an Opportunity field:

1. Requires `Content-Type: application/json`. A body with only `{ "name": "..." }` and no JSON content type returns HTTP 422.
2. **RADIO** (and other choice types) must send `options` as the live string list (for example `["Yes", "No"]`). Sending `picklistOptions` with `options`, or omitting `options` when the field is RADIO, returns 422 or 400.
3. **FILE_UPLOAD** rename must send `name` and `dataType` only. Including `maxFileLimit`, `acceptedFormats`, or `options` is rejected (`maxFileLimit should not exist` observed live).

Merge `fieldKey` is unchanged by a display-name rename.

## Why it's non-obvious

The OpenAPI custom-fields schema lists `maxFileLimit` / `acceptedFormats` as FILE_UPLOAD properties and `picklistOptions` on choice fields, so echoing the GET payload into PUT looks correct and fails. A name-only PUT also looks sufficient and fails without the JSON content type.

## Evidence

Live writes against `Example Co (Staging)` (`loc_EXAMPLE_01`) on 2026-09-04 while prefixing Opportunity names with `DELETE `. RADIO Yes/No fields succeeded with `options`; FILE_UPLOAD `Front of Location` (`id_EXAMPLE_01`) failed until `maxFileLimit` / `acceptedFormats` / `options` were omitted. `confirmed`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for classic Opportunity field updates. Custom-object field *create* is a different surface (`POST /custom-fields/` v3); FILE_UPLOAD create there has its own omit-`isMultiFileAllowed` quirk.
