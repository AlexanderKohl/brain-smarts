---
id: ghl-general-textbox-list-newline-join-hypothesis
title: 'REFUTED: joining Textbox List into a newline-separated string across all object types'
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: textbox_list
endpoint: PUT /contacts/:contactId, PUT /opportunities/:id, PUT /objects/business/records/:id
status: refuted
superseded_by: null
refuted_by: ghl-opportunity-monetary-textbox-list-plain
discovered: '2026-08-24'
verified: null
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/general--textbox-list--newline-joined-string-hypothesis.md
---

# REFUTED: newline-joined string for Textbox List on every object

## The hypothesis

Reproducing a real 400 on a live Business Textbox List write
(`"...must be text"`), the fix applied was: join a Textbox List field's
array value into a single **newline-separated string** on write – applied
identically at **all four** object types' write call sites (Business,
Contact, Opportunity, Custom Object).

## Why it looked plausible

The error message ("must be text") reads as "send a string, not an
array," and a joined-string workaround is a common, reasonable-looking
pattern for exactly that kind of complaint. It was applied alongside the
Monetary wrap fix under the same "platform-level DTO rule" reasoning – see
`general--monetary--currency-value-wrap-hypothesis.md`.

## What was actually true

Opportunity's Textbox List was **already correct as a plain string
array** – the join broke a working field. Contact's Textbox List needed
neither a join nor a plain array, but an **object keyed by the record's
own existing per-row UUIDs** (see
`contact--textbox-list--uuid-keyed-object-write.md`). Business/Custom
Object's real requirement wasn't a joined string at all, but **separate
per-row compound-key properties** (see
`business--textbox-list--compound-key-shape.md`). None of the four object
types actually wanted a newline-joined string.

## Do not repeat this

Do not join a Textbox List array into a delimited string for any of these
four objects. Check the object-specific entry
(`business--textbox-list--compound-key-shape.md`,
`contact--textbox-list--uuid-keyed-object-write.md`,
`opportunity--monetary-textbox-list--plain-shapes-correct.md`,
`custom_object--textbox-list--compound-key-nested-in-properties.md`) for
the real per-object shape before writing this field type anywhere.
