---
id: ghl-general-monetary-currency-value-wrap-hypothesis
title: 'REFUTED: wrapping Monetary as {currency,value} across all object types'
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: monetary
endpoint: PUT /contacts/:contactId, PUT /opportunities/:id
status: refuted
superseded_by: null
refuted_by: ghl-contact-monetary-bare-number
discovered: '2026-08-24'
verified: null
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# REFUTED: `{currency, value}` wrap for Monetary on every object

## The hypothesis

Reproducing real 400s on a live Business Monetary write
(`"...is missing a currency code"`), the fix applied was: wrap every
Monetary custom-field value as `{ currency: "default", value }` on write –
applied identically at **all four** object types' write call sites
(Business, Contact, Opportunity, Custom Object) – reasoning that the
error was "a platform-level DTO rule tied to the field's type, not any one
object."

## Why it looked plausible

The wrap is genuinely correct for Business/Custom Object's Objects API –
confirmed by a raw Objects API record read showing exactly that shape
live. A field-type-level rule that applies identically everywhere is also
the simpler, more elegant hypothesis than "it depends on which endpoint
this object happens to use."

## What was actually true

Contact and Opportunity's classic `customFields[].fieldValue` write wants
a **bare number**, not the wrapped object – the wrapped shape is rejected
outright (`"Invalid Custom Field Value \"{...}\" for \"<fieldId>\""`). The
real rule is endpoint-shaped, not field-type-shaped: it depends on
**which write surface** the object uses (classic `customFields` vs. Objects
API `properties`), not the field type alone. See
`contact--monetary--bare-number-required.md` for the corrected,
per-endpoint understanding.

## Do not repeat this

Do not wrap a Monetary value as `{currency, value}` for a Contact or
Opportunity classic-endpoint write, even though it is the genuinely
correct shape for Business/Custom Object on the Objects API. Check which
write surface (classic vs. Objects API) the target object actually uses
before assuming a field-type-level serialization rule generalises across
objects.

## Evidence

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.
