---
id: ghl-contact-multi-file-full-kept-set
title: Contact multi-file fields must resend the full kept set with echoed meta, and use the byte-only upload endpoint
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: file
endpoint: POST /locations/:locationId/customFields/upload, PUT /contacts/:contactId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/contact--file-fields--multi-file-full-kept-set-required.md
---

# Contact multi-file fields: resend the full kept set

## Behaviour

Two distinct confirmed facts:

1. **Write shape.** A multi-file Contact custom field is written back as
   the **full kept set** – every existing file the recipient didn't remove,
   plus any newly uploaded file – each entry with its original `meta`
   echoed through, under a **snake_case `field_value`** key. A removed file
   is simply **left out of the array** (not flagged `deleted`, unlike
   Opportunity – see
   `opportunity--file-fields--multi-file-full-array-deleted-flag.md`).
2. **Upload endpoint.** `POST /forms/upload-custom-files` (a Contact-
   specific upload endpoint) was assumed additive across repeated calls –
   confirmed live **not** to be: it silently drops every other file already
   on the field. The correct upload path is the shared byte-only uploader
   (`POST /locations/:locationId/customFields/upload`, the same one every
   other object uses), followed by this app re-fetching the record's raw
   value and reconstructing the complete field on every write.

## Why it's non-obvious

`/forms/upload-custom-files` looks Contact-specific and purpose-built, and
"upload" endpoints generally read as additive/incremental by name – the
silent data loss (rather than an error) on a second call is what makes it
dangerous.

## Evidence

Confirmed via an official `@gohighlevel/api-client` SDK example for
`contacts.updateContact` for the write shape; confirmed live that the
Contact-specific upload endpoint drops sibling files.

## Applies to

Contact multi-file fields specifically. Single-file/signature Contact
fields use a different shape entirely – see
`contact--file-fields--single-file-bare-object-shape.md`.
