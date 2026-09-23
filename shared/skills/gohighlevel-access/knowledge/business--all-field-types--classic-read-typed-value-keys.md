---
id: ghl-business-classic-read-typed-value-keys
title: Business classic read needs type-specific value*/valueArray fallback keys, not just value/fieldValue
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: null
endpoint: GET /businesses/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: 2026-08-24T21:30:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Business classic read: type-specific value keys required

## Behaviour

A Business `customFields` entry from `GET /businesses/:businessId` does
**not** reliably carry its current value under a generic `value` /
`fieldValue` / `field_value` key. It uses **type-specific** keys instead:
`valueString`, `valueNumber`, `valueDate`, `valueCurrency`, `valueFiles`
for ordinary field types, and `valueArray` specifically for
`MULTIPLE_OPTIONS` (checkbox/multiselect) fields. A lookup chain that only
checks the generic keys silently reads every one of these field types back
as empty/unset, even though the record genuinely holds a value.

## Why it's non-obvious

The generic `value`/`fieldValue` keys work for *some* field types and for
other objects, so a lookup chain built against those looks complete until
tested against a Business record carrying every field type. The failure is
silent (empty form field, no error), not a loud rejection.

## Evidence

Confirmed directly against real Business record raw `customFields` arrays
pulled from production Railway logs – each blank-on-load field's value was
genuinely present under its own typed key the whole time.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business classic-endpoint reads specifically. This is additive fallback
behaviour (only reached when the generic keys all miss), so it cannot
regress a field that already reads back correctly on any object type. Not
confirmed whether Contact/Opportunity's classic reads ever use these same
typed keys – their lookup chains have not needed this fallback in
practice.
