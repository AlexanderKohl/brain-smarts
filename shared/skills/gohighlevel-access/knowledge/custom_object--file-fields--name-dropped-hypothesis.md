---
id: ghl-custom-object-file-name-dropped-hypothesis
title: 'REFUTED: dropping name from Custom Object file-property writes to match the documented schema'
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: file
endpoint: PUT /objects/:schemaKey/records/:id
status: refuted
superseded_by: null
refuted_by: ghl-custom-object-file-fields-delta-name
discovered: '2026-08-22'
verified: null
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# REFUTED: `{url}`-only Custom Object file writes, matching the docs

## The hypothesis

HighLevel's Objects API docs show a FILE_UPLOAD property as
`{ "my_files": [{ "url": "..." }] }` in both Create and Update/Search
schemas – no `name` key at all. Since the real recovered filename on read
comes from HighLevel's own upload-time `meta.name`, not from anything this
app writes into `properties`, a `name` sent on write looked like inert
padding. The fix dropped `name` from the write entirely, "aligning with
the documented schema" – a low-risk-looking simplification, not a guess at
fixing something broken, since the change shipped on top of already-working
uploads.

## Why it looked plausible

It matched the official documentation exactly, and a first test (a single
brand-new file) worked fine – an API silently ignoring an extra
undocumented field is normal behaviour, so removing one looked safe by
construction.

## What was actually true

The documented `{url}`-only shape breaks specifically when **merging** an
existing file (previously written with `name`) with a newly uploaded one –
both entries reduced to bare `{url}` produced a real
`422 "We couldn't process file updates for <field>"`. The working shape
sends `{ url, name }` unconditionally, on every entry, regardless of
whether the file is new or already existed. See
`custom_object--file-fields--add-remove-delta-name-required.md`.

## Do not repeat this

Do not drop `name` from a Custom Object file-property write entry just
because HighLevel's own docs show it without one – the documented shape is
verified incomplete for the multi-file-merge case, which is easy to miss
if testing only covers a single brand-new upload.

## Evidence

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.
