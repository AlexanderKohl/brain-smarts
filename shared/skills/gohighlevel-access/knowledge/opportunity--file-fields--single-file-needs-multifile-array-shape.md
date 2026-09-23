---
id: ghl-opportunity-single-file-needs-array-shape
title: Opportunity single-file writes must use the multi-file array shape to preserve the real filename
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: file
endpoint: PUT /opportunities/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Opportunity single-file writes: use the array shape

## Behaviour

Opportunity's classic single-file custom-field write endpoint only ever
echoes a real filename back for the **array-of-`{url, deleted, meta}`**
shape – the same one confirmed for multi-file writes (see
`opportunity--file-fields--multi-file-full-array-deleted-flag.md`). A bare
`fieldValue` string is **accepted without error** but round-trips
nameless: the file's name falls back to the storage URL's own randomly
generated path segment.

Also confirmed: **HighLevel does not enforce the field catalog's own
"single file" cap at this write endpoint at all.** Sending the array shape
to a field whose catalog says "single file" is accepted fine by the
underlying write – only this app's own client/server checks enforce a
single-file cap. There is therefore no API-side reason to special-case
single- vs multi-file Opportunity writes; both can go through the same
array-shape write path, with a removed file marked `deleted: true` and
kept in the array (matching multi-file behaviour) rather than dropped –
invisible on read, since filename/file-listing logic already filters out
deleted entries.

## Why it's non-obvious

The bare-string write never errors, so "it works" was true by the only
signal available (no 4xx/5xx) even though it silently lost user-facing
data (the real filename) that only shows up on a later read, not at write
time.

## Evidence

Confirmed live against a real Opportunity: sending the array shape to a
single-file-configured field succeeded and preserved the real filename on
the next read; the bare-string shape had previously round-tripped nameless
on the same kind of field.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Opportunity file fields, both single- and multi-file – after this fix,
both types share one write path. Does not apply to Contact (which
genuinely does need a bare object, not an array, for its own single-file
case – see `contact--file-fields--single-file-bare-object-shape.md`; the
two objects are not analogous here).
