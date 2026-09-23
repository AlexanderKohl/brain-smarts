---
id: ghl-custom-object-schema-create-page-session-token-accepted
title: The app's own session token creates custom object schemas and fields through the public-API DTOs
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: POST /objects/ and POST /custom-fields/ on services.leadconnectorhq.com
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/custom_object--schema-create--page-session-token-accepted.md
created: 2026-09-15T09:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---
# The app's session token creates schemas and fields with the public-API bodies

## Behaviour

A request sent from inside the HighLevel web app, carrying the Authorization header the
app itself last sent (the `authClass` JWT, not the Firebase token) plus `channel: APP`
and `source: WEB_USER`, is accepted by the public-API routes on
`services.leadconnectorhq.com` for schema and field creation, with the public
`CreateCustomObjectSchemaDTO` and `CreateCustomFieldsDTO` bodies unchanged:

| Request | Version header | Answer |
| --- | --- | --- |
| `GET /objects/custom_objects.example_docs/?locationId=…` (before) | page default `2021-04-15` | 404 |
| `POST /objects/` `{locationId, key: "custom_objects.example_docs", labels, description, primaryDisplayPropertyDetails}` | `2021-07-28` | 201, `object.key` = `custom_objects.example_docs` |
| `GET backend…/custom-fields/object-key/custom_objects.example_docs?locationId=…` | page default | 200 – one field (the primary) and **a folder already created with the schema** |
| `POST /custom-fields/` `{locationId, name, dataType, showInForms, objectKey, fieldKey, parentId, options?}` × 11 | `v3` | 201 each: TEXT, LARGE_TEXT, NUMERICAL, DATE, SINGLE_OPTIONS, RADIO |

No OAuth app, private integration token or scope grant was involved. The permission is
the logged-in user's own.

## Why it's non-obvious

The public API is documented for OAuth and private-integration tokens, and the internal
routes the app uses for the same actions differ (the app edits a schema by
`PUT /objects/{objectId}`, by id rather than key). It was not known whether the session
token would be accepted by the public-shaped routes at all, nor whether creating a schema
also creates the fields folder – it does, so `POST /custom-fields/folder` was not needed.

## Evidence

Live run by the owner, 15 September 2026, from the `example-docs-extension`
extension's storage test (commit `b3dd4a9`) on sub-account `Example Test`
(`loc_EXAMPLE_04`): fifteen requests, every one 2xx, all twelve fields read back.
Report in that project's `LOG.md` under the same date.

## Applies to

Schema and field creation from the page realm. Record create/update/search through the
same token is untested as of this entry.
