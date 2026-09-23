---
id: ghl-business-textbox-list-compound-key
title: Business Textbox List fields read/write as separate per-row compound-key properties, not one array/string
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: textbox_list
endpoint: GET /businesses/:businessId, PUT /objects/business/records/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Business Textbox List: compound-key row properties, not an array

## Behaviour

A Business Textbox List field (e.g. `sample_reference_notes`) is **not**
stored as one property holding an array or a joined string. It is stored as
**separate properties, one per row**, each keyed
`"${shortKey}.${optionKey}"` (e.g. `sample_reference_notes.reference_one`,
`sample_reference_notes.reference_two`), each a plain string. This is true
both on the classic `GET /businesses/:businessId` echo (top-level
`customFields` array entries with these compound keys) and on the Objects
API write (`properties` map).

This caused a second, more severe bug: the classic-endpoint read's
compound-key rows were not recognised as belonging to the real Textbox List
field, so the unmatched-`customFields` fallback invented **bogus synthetic
TEXT fields** per row (e.g. "Reference one"/"Reference two"). Submitting
the form then sent those invented keys straight to HighLevel, which
rejected them (`422 "property sample_reference_notes.reference_one should
not exist"`) and aborted the **entire** submission – including the real
field's own write – before it was ever attempted.

## Why it's non-obvious

Every other object's Textbox List shape is a single field holding an array
or delimited string (see `opportunity--monetary-textbox-list--plain-shapes-correct.md`,
`contact--textbox-list--uuid-keyed-object-write.md`). Business/Custom
Object's per-row compound-key echo looks, on first read, like multiple
unrelated fields rather than one Textbox List field's rows.

## Evidence

Confirmed via a systematic live-API investigation (raw authenticated
read/write round-trips, `gohighlevel-access` skill, four object types) –
a raw Custom Object record read showed the identical compound-key
convention (see `custom_object--textbox-list--compound-key-nested-in-properties.md`),
confirming this is an Objects-API-wide Textbox List convention, not
Business-specific, that also happens to surface through Business's classic
read.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business (classic read echo and Objects API write) and Custom Object
(Objects API read/write, one level deeper – see the Custom Object entry).
Does **not** apply to Contact (UUID-keyed object) or Opportunity (plain
array/string) – do not generalise this shape to those two objects.
