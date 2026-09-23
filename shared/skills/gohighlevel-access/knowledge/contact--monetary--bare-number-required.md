---
id: ghl-contact-monetary-bare-number
title: Contact/Opportunity classic Monetary custom fields are a bare number, not a currency object
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: monetary
endpoint: PUT /contacts/:contactId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Contact/Opportunity classic Monetary: bare number

## Behaviour

On Contact and Opportunity's classic `customFields[].fieldValue` write, a
Monetary field's value is a **bare number**. Wrapping it as
`{ currency: "default", value }` – the shape Business/Custom Object's
Objects API genuinely wants (see
`business--custom-fields--objects-api-required.md` for that context) – is
rejected outright: `"Invalid Custom Field Value \"{...}\" for \"<fieldId>\""`.

An earlier fix wrapped Monetary as `{currency, value}` **across all four
object types**, reasoning from Business's genuinely-correct shape. That was
wrong specifically for Contact/Opportunity – see
`general--monetary--currency-value-wrap-hypothesis.md` for the full story
of that mistake and why it looked plausible.

## Why it's non-obvious

Business and Custom Object's Objects API really does want the wrapped
`{currency, value}` object for the identical field type – the wrong
generalisation is one hop away from a fact that's actually true for two of
the four object types.

## Evidence

Confirmed via a live write+read round-trip (`gohighlevel-access` skill,
raw authenticated calls) against a real Contact record: the bare number
write succeeded and round-tripped; the wrapped-object write was rejected.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Contact and Opportunity classic `customFields` writes. Does **not** apply
to Business or Custom Object (Objects API `properties` writes), which
genuinely need the wrapped `{currency, value}` shape – do not generalise
either direction across the classic/Objects-API split.
