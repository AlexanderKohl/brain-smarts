---
id: ghl-custom-object-file-fields-delta-name
title: Custom Object file properties need the add/remove delta AND a name key, despite docs showing url only
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: file
endpoint: PUT /objects/:schemaKey/records/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/custom_object--file-fields--add-remove-delta-name-required.md
---

# Custom Object file properties: delta shape needs `name` despite docs

## Behaviour

A Custom Object file property write uses the same add/remove delta as
Business (see `business--file-fields--objects-api-add-remove-delta.md`):
`properties: { <key>: { add: [...], remove: [...] } }`. HighLevel's own
Objects API docs show each file entry in that shape as `{ "url": "..." }`
only, with no `name` field, in both Create and Update/Search schemas. That
documented shape works for a **single brand-new file**. It does **not**
work once an *existing* file (previously written with `name`) is being
merged with a newly-uploaded one – that combination, both entries reduced
to bare `{url}`, gets a real `422 "We couldn't process file updates for
<field>"`. The working shape sends `{ url, name }` on every entry,
unconditionally.

Separately, on **read**: the real filename for a Custom Object file entry
is recovered from `meta.name` on the record's raw `properties.<field>`
array items (alongside `meta.extension`/`meta.size`) – not from
`originalname`/`originalName`/`fieldname`, and not by deriving a name from
the file's own storage URL (which is a HighLevel-generated UUID, not the
original filename).

## Why it's non-obvious

The official docs' `{url}`-only shape is directly contradicted by live
behaviour, but only in the multi-file-merge case – a same-day attempt to
"align with the documented schema" by dropping `name` shipped, worked for
new single-file uploads, and only broke when a second file was added to an
already-populated field, which is easy to not test.

## Evidence

Confirmed live in both directions: dropping `name` reproduced the 422 on a
merge; restoring `{url, name}` unconditionally fixed it, matching the
state Custom Object uploads already worked in before the documentation-
aligned attempt.

## Applies to

Custom Object file property writes specifically. Not confirmed whether
Business's identical add/remove delta shares this exact `name`-required
detail – treat as a Custom-Object-confirmed fact, not yet cross-verified
for Business.
