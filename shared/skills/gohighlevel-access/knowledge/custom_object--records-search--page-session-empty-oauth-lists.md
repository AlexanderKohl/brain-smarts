---
id: ghl-custom_object--records-search--page-session-empty-oauth-lists
title: "Record search from the HighLevel page session lists nothing; the same search through an OAuth location token lists every record"
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: POST /objects/{schemaKey}/records/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs: []
created: 2026-09-15T12:35:00+10:00
updated: 2026-09-23T18:00:00+10:00
---
# Record search: empty from the page session, complete through an OAuth location token

## Behaviour

On Example Test (`loc_EXAMPLE_04`), `custom_objects.example_docs` with `searchableProperties`
`title`, `subject`, `kind` declared and eight records present:

- A browser-extension storage test, sending `POST /objects/custom_objects.example_docs/records/search`
  through the HighLevel page's own session (the page's last authorisation headers replayed,
  `version: 2021-07-28`, body `{locationId, page: 1, pageLimit: 20, query: ""}`), answered
  **201 with zero records**, five runs on 15 September, the last two with the properties
  already declared and a record created minutes earlier that a read by id returned intact.
- The brain's OAuth client (Company token exchanged for a location token, `Version`
  `2021-07-28`), same body with `pageLimit: 100`, answered **201 with `total: 8`** and all
  eight ids, for a bare listing, for `query: "ExampleDocs"` (7) and for a body with no `query` key
  (8). A filter `properties.kind eq "External system"` answered 0, which is unexplained
  (probe of 12:20, read-only).

Creates, reads by id, updates and deletes succeed through the page session; only search is
empty there.

## Working hypothesis

The search service scopes results by something carried in the token rather than by the
body's `locationId`: an OAuth location token names the location, a user's page token may not,
or the page token needs the app's own `channel` / `source` headers for search to be routed like
the web app's. Discriminating probes: the same search from the page session (a) with the
page's own `channel` and `source` headers replayed, (b) without `locationId` in the body,
(c) with the page's internal search host.

## Why it's non-obvious

Every write and read works from the page session, and the search answers a clean 201, so
nothing points at the token. The index and the schema were suspected for five runs.

## Evidence

Storage test reports of 15 September 2026 (10:15 and 11:45 local) and a read-only OAuth
probe at 12:20.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Confirmed 15 September 2026, 15:30

The discriminating probes were run from the page session on a test sub-account: (a) the current body and headers, (b) the page's own `channel: APP` and `source: WEB_USER`
replayed, (d) `pageLimit: 100` without the `query` key. All three answered 201 with zero records
while a record created seconds earlier read back by id, and the same body through the brain's
OAuth location token listed eight. (c) without `locationId` is refused by the test's own
guard and was not sent; (e) there is no GET listing. Headers do not matter; the token type does:
**record search needs an OAuth location token; a user's page-session token gets an empty index.**
Reads by id, creates, updates and deletes all work from the page session.

Consequence for a client that holds only a page-session token: any feature that must discover
records it did not create (records saved by another install, or written through an OAuth
client) cannot use the page session's search. Either an OAuth token reaches the client (for
example through a marketplace app), or record ids are kept discoverable without search
(for example an index record whose id the object schema's `description` carries, since the
schema is readable and one schema update is a permitted write).
