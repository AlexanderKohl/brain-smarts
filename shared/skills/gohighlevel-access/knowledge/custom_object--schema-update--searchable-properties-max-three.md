---
id: ghl-custom_object--schema-update--searchable-properties-max-three
title: A custom object may declare at most three searchable properties
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: PUT /objects/{key}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs: []
created: 2026-09-15T14:30:00+10:00
updated: 2026-09-23T14:45:16+10:00
---
# At most three searchable properties

## Behaviour

`PUT /objects/custom_objects.example_docs` with `searchableProperties` of four field keys answered
**400 "Too many searchable properties. Maximum allowed is 3, but received 4."** The DTO
requires at least one; the ceiling is three. Objects made in the HighLevel UI show the same
bound (`business` declares two).

## Why it's non-obvious

The OpenAPI description of `searchableProperties` gives an example of three and states no
maximum; the minimum of one is enforced by the DTO, the maximum only by the server.

## Evidence

Live, 15 September 2026, from a browser-extension storage test on Example Test
(`loc_EXAMPLE_04`) through the page-session token.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Also confirmed 15 September 2026, 17:20

`PUT /objects/{key}` from a page-session token also accepts `description` (under 100 characters) alongside `searchableProperties`; a client can use it to name an index record (for example `Example index <recordId>`), which keeps records discoverable without search.
