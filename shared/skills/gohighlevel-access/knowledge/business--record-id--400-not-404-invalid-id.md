---
id: ghl-business-record-id-400-not-404
title: Business record GET 400s on a bad id instead of 404ing like every other object
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: null
endpoint: GET /businesses/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-22
verified: 2026-08-22
created: 2026-08-24T21:30:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Business record GET 400s on a bad id instead of 404ing

## Behaviour

`GET /businesses/:businessId` with a non-`ObjectId`-shaped id returns
**HTTP 400** ("not a valid ObjectId"), not the 404 every other object
(Contact, Opportunity, Custom Object) returns for an unresolvable record id.

## Why it's non-obvious

Generic client error-status mapping naturally treats "record not found" as
404-shaped. A 400 gets mapped to a generic API-error type instead of a
not-found type, so any not-found-triggered fallback logic (for example, a
name-based lookup fallback) silently never engages – the request just fails
outright with no fallback attempt.

## Evidence

Confirmed live via Railway production logs: a workflow mapped a Business
"Company Name" merge field into the Record ID input (the documented
workaround, since Business has no Company ID merge field) and the whole
form-generation action failed with a 502 instead of falling back to a
name lookup.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business only, confirmed. Not verified whether Custom Object exhibits the
same 400-vs-404 split for a malformed (non-standard-shaped) id – Custom
Object ids observed so far have always been well-formed in testing.
Client code must re-map this specific 400 to a not-found condition before
any not-found fallback (e.g. the Company Name search fallback – see
`business--search--name-query-no-field-prefix.md`) can run.
