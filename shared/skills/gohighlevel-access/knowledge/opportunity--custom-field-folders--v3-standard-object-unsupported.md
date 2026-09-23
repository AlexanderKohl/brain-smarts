---
id: gohighlevel-opportunity-custom-field-folders-v3-standard-object-unsupported
title: Custom Fields v3 cannot create folders for Opportunity or Contact
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: POST /custom-fields/folder
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-26
verified: 2026-08-26
source_refs: []
created: 2026-08-26T11:45:20+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Custom Fields v3 cannot create Opportunity or Contact folders

## Behaviour

`POST /custom-fields/folder` with Version `v3` and an otherwise valid body
for an Opportunity folder is rejected:

```json
{
  "locationId": "<location-id>",
  "objectKey": "opportunity",
  "name": "Site Visit"
}
```

The API returns HTTP 400:

```json
{
  "message": "Api does not support objectKey of type contact or opportunity",
  "error": "Bad Request",
  "statusCode": 400
}
```

Use the HighLevel interface to create or organise Contact and Opportunity
custom-field folders. The classic `locations/{locationId}/customFields`
endpoint can still create Opportunity fields, but it does not provide the
equivalent supported folder-creation operation.

## Why it's non-obvious

Custom Fields v3 accepts an `objectKey`, and `opportunity` is a recognised
standard-object key, but the folder operation is deliberately restricted.
The same v3 surface works for supported custom objects and Business, which can
make it look suitable for Opportunity folder creation until the live request
is attempted.

## Evidence

Confirmed on 2026-08-26 by a live write probe against authorised `Example Co
(Staging)` (`loc_EXAMPLE_01`). The request failed before creating a
folder. This matches the official endpoint note that the operation supports
Custom Objects and Company (Business), not standard Contact or Opportunity
objects.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for Opportunity with `objectKey: "opportunity"`. The exact error also
states that Contact is unsupported. Custom Objects and Business are different:
their v3 field-folder endpoints are supported.
