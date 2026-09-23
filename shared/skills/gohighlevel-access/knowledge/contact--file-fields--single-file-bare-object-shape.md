---
id: ghl-contact-single-file-bare-object
title: Contact single-file/signature fields need a bare {url,meta} object, not a one-element array
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: file
endpoint: PUT /contacts/:contactId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Contact single-file fields: bare object, not an array

## Behaviour

For a non-multiple Contact custom field (every signature field, and any
single-file Contact field), `field_value` must be a **bare `{ url, meta }`
object**, not a one-element array. HighLevel accepts the one-element-array
form without erroring, but silently stores a shape that doesn't match what
a real signature/single-file value looks like on subsequent reads.

## Why it's non-obvious

Multi-file Contact fields genuinely do use an array (see
`contact--file-fields--multi-file-full-kept-set-required.md`), so
generalising "file field values are arrays" from that case is a reasonable
but wrong inference for the single-file/signature case – and the wrong
shape doesn't error, it just silently misrenders.

## Evidence

Confirmed live: a single-element array wrote without error but did not
read back as a normal signature/file value.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Non-multiple Contact fields (signature fields always; any Contact file
field explicitly configured single-file). Multi-file Contact fields use
the array shape – see the sibling entry.
