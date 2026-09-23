---
id: ghl-custom_object--records-delete--no-locationid-anywhere
title: Custom object record delete refuses locationId in the query string
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: DELETE /objects/{schemaKey}/records/{id}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/custom_object--records-delete--no-locationid-anywhere.md
created: 2026-09-15T11:20:00+10:00
updated: 2026-09-23T12:00:00+10:00
---
# Record delete: no `locationId`, unlike update

## Behaviour

`DELETE /objects/custom_objects.example_docs/records/{id}?locationId=<loc>` answered
**422 `property locationId should not exist`** on 15 September 2026 (Example Test,
`loc_EXAMPLE_04`, page-session token from the extension). The same query-string
placement is the one `PUT` on the same resource *requires* (see
`custom_object--records-write--locationid-body-on-create-query-on-update.md`).

**Confirmed on the second run the same day:** `DELETE /objects/custom_objects.example_docs/records/{id}`
with no query string and no body answered **200** for two records. The record id is enough.

## Why it's non-obvious

Three verbs on one resource, three placements: body on create, query on update, nowhere
on delete. The 422 wording is the NestJS whitelist message and reads as though it were
about the body, which the request did not have.

## Evidence

One live 422 with `locationId` in the query, then two live 200s with the bare path, both
on 15 September 2026 from the extension's storage test on Example Test (project `LOG.md`).

