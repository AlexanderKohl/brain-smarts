---
id: ghl-custom-object-textbox-list-nested-properties
title: Custom Object Textbox List compound-key rows are nested one level deeper than Business's
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: textbox_list
endpoint: GET /objects/:schemaKey/records/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Custom Object Textbox List: nested under `record.properties`

## Behaviour

Custom Object shares Business's per-row compound-key Textbox List
convention (`"${shortKey}.${optionKey}"`, see
`business--textbox-list--compound-key-shape.md`), but the rows live at a
different nesting depth: Business's classic-endpoint echo happens to put
them in a **top-level `customFields` array**, while a Custom Object record
(read via the Objects API) nests the same per-row keys **one level deeper,
under `record.properties`**.

## Why it's non-obvious

Both objects use the identical key convention, so code that correctly
reassembles the rows for Business can look complete while silently missing
Custom Object's records entirely – the bug is a location/depth mismatch,
not a key-format mismatch, so a naive "does it recognise the key pattern"
check passes even when the actual field is never found.

## Evidence

Confirmed directly against a real Custom Object record's raw response: the
Sample Reference Notes field showed only placeholder text on the form
(reassembly found nothing) while the compound-key rows were genuinely
present under `record.properties`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Custom Object reads specifically. The write side is unaffected – Custom
Object's Textbox List write already goes through the same `properties`
map, flat, as any other Objects API write (see
`business--custom-fields--objects-api-required.md`'s Objects API pattern).
