---
id: gohighlevel-contact-full-address-system-merge-field
title: Some standard contact merge fields work but appear in no field catalogue (full_address, timezone)
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: standard
endpoint: GET /locations/:locationId/customFields
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/contact--full-address--system-merge-field-absent-from-custom-fields.md
created: 2026-09-12T18:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# `contact.full_address` is a system merge field absent from every field list

## Behaviour

`{{contact.full_address}}` resolves at send time in workflow actions, task bodies and message
templates. It appears in no field catalogue: not in `GET /locations/:locationId/customFields`,
and not in the custom-field picker in the builder UI.

Any tool that validates merge tokens against the custom-fields response will therefore report
a correct, working reference as an unknown field.

## Why it's non-obvious

The usual test for "is this token real?" is membership of the custom-fields list, and for every
*custom* field that test is correct. HighLevel also exposes a set of standard contact merge
fields that the same endpoint does not enumerate, and `full_address` is one that does not appear
in the builder's picker either – so neither the API nor the UI advertises it. It is only
discoverable from configuration that already uses it, or from someone who knows.

`full_address` is a composed value (the address parts joined), which is also why nothing in a
workflow ever writes it: it has no writer to find, and a "read but never written" rule will fire
on it forever unless standard fields are excluded from that rule.

## Evidence

The owner confirmed on 12 September 2026 while reviewing ExampleDocs findings against the Example
Co location: the field is in use and correct, and ExampleDocs was wrong to flag it. The account's
own hand-maintained field-usage catalogue classifies fields it cannot match to a custom-field id
as `Kind: standard`, which covers most such fields but not this one – `contact.full_address` is
absent from that catalogue too.

`contact.timezone` was confirmed the same day and is a second instance: it behaves as a real
contact field – see `contact--timezone--empty-catalog-needs-locations-endpoint.md`, which
documents its picklist coming from `GET /locations/:locationId/timezones` – yet it too is
missing from the location's custom-field list and from the account's field-usage catalogue.

Not established: the full set of undocumented standard merge fields. `mailgun.event` and
`message.direction` are a **different** shape and remain open – they are event-payload
attributes rather than fields on any object, so "is it a system field?" is the wrong question
for them.

## Applies to

Confirmed for `contact` on this location. Do not assume the equivalent for `opportunity` or
custom objects without checking: the composed-address case is specific to contacts, and which
standard fields each object exposes has not been enumerated.
