---
id: ghl-opportunity-monetary-textbox-list-plain
title: Opportunity Monetary and Textbox List already use plain shapes; wrapping/joining them is a regression
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: monetary
endpoint: PUT /opportunities/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Opportunity Monetary/Textbox List: already plain, don't touch

## Behaviour

On Opportunity's classic `customFields` write, Monetary is a **bare
number** (same as Contact – see
`contact--monetary--bare-number-required.md`) and Textbox List is a
**plain string array** – both already correct with no serialization at
all. Wrapping Monetary as `{currency, value}` or joining Textbox List into
a newline-separated string (a fix that reasoned from Business's genuinely
different, Objects-API-only shapes) was a pure regression on Opportunity:
these plain shapes already worked before that change and just needed to be
left alone.

Separately confirmed on **read**: a real Opportunity record's Textbox List
value can also appear stored as an object **keyed by the option's label**
(not Contact's UUID-keying – see
`contact--textbox-list--uuid-keyed-object-write.md`), confirmed on a second
real record. A plain-array write from this app was confirmed to correctly
convert/persist over that label-keyed shape too – unlike Contact's known
silent-no-op quirk for non-reused keys.

## Why it's non-obvious

Business's Objects API genuinely does need the wrapped/joined shapes for
the identical field types (see `business--textbox-list--compound-key-shape.md`),
which makes "apply the same fix to every object" a natural but wrong
generalisation – Opportunity's classic endpoint was never broken for these
two field types.

## Evidence

Confirmed via a systematic live-API investigation: a raw read of real
stored Opportunity data showed Monetary as a bare number and Textbox List
as a plain string array – exactly what this app sent before the incorrect
fix; a live write+read round-trip confirmed both persist correctly in
plain form.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Opportunity classic `customFields` writes only. Do not apply Business's
wrapped/compound-key shapes here, and do not apply Contact's UUID-reuse
requirement here – Opportunity's own shapes are simpler than either.
