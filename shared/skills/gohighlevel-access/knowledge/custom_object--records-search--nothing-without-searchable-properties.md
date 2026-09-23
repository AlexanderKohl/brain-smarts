---
id: ghl-custom_object--records-search--nothing-without-searchable-properties
title: "Record search answers nothing for a custom object created without searchableProperties"
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: POST /objects/{schemaKey}/records/search
status: refuted
superseded_by: null
refuted_by: ghl-custom_object--records-search--page-session-empty-oauth-lists
discovered: 2026-09-15
verified: null
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/custom_object--records-search--nothing-without-searchable-properties.md
created: 2026-09-15T11:20:00+10:00
updated: 2026-09-23T18:00:00+10:00
---
# Record search: nothing at all until the schema declares searchable properties

## Behaviour

For a custom object created by `POST /objects/` with no `searchableProperties`,
`POST /objects/{key}/records/search` answered **201 with an empty list to everything** –
an `eq` filter on a text property, an `eq` filter on a single-token hash property, an `eq`
filter on an option property, a free-text `query`, and a bare listing (`query: ""`, page
1, pageLimit 100) – while three records existed in the object and each was read by id
(200, intact). Three runs on 15 September 2026, up to fourteen hours after the writes.

The earlier readings – an index lagging the write, then an analyser splitting the value on
braces – are both **refuted** by the listing returning nothing: they would not stop a bare
list.

Working hypothesis: the records search is served from an index built on the schema's
`searchableProperties`, and a schema that declares none indexes nothing. `PUT /objects/{key}`
with `{locationId, searchableProperties: [...]}` (UpdateCustomObjectSchemaDTO, where the
list is required and must be non-empty) should switch it on. Objects created in the
HighLevel UI carry `searchableProperties` from the start – `business` declares
`business.name` and `business.email` – which is why the 9 September search on
`custom_objects.site_visits` worked.

The storage test was then changed to read the schema and declare searchable properties when
they are missing before running its lookups; see the refutation below.

## Why it's non-obvious

A create through the API does not require `searchableProperties`, succeeds without them,
and nothing in the search's answer says the object is unindexed – it is a clean 201 with
`records: []`, indistinguishable from "no match".

## Evidence

Storage test runs of 15 September 2026 on Example Test.

## Refuted 15 September 2026, 12:35

With `title`, `subject` and `kind` declared searchable (confirmed by `GET /objects/custom_objects.example_docs`),
a browser extension's page-session listing still answered 201 with no records while eight records
existed, and a bare listing through the brain's OAuth location token listed all eight
(`total: 8`). The searchable-properties declaration was not the cause; the transport is. See
`custom_object--records-search--page-session-empty-oauth-lists.md`.
