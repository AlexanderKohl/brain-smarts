---
id: ghl-general-checkbox-multiselect-delta
title: Objects API checkbox/multiselect properties need an add/remove delta, not a plain array
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: checkbox_multiselect
endpoint: PUT /objects/:schemaKey/records/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Objects API checkbox/multiselect: add/remove delta required

## Behaviour

On any object written through the Objects API (`PUT
/objects/:schemaKey/records/:id`, i.e. Business or Custom Object), a
`CHECKBOX`/multiselect property rejects a plain array value –
`422 "We couldn't apply updates to <Field> due to an unexpected format"` –
**even though HighLevel's own read response returns that exact array shape
back.** It needs the same add/remove delta shape file fields use instead
(`{ <key>: { add: [...], remove: [...] } }`), computed by diffing the
submitted value against a fresh raw read of the field's current value.
Single-value fields on the same endpoint (RADIO/SINGLE_OPTIONS, text,
number, date) are unaffected and accept a plain value directly – only
checkbox/multiselect fields need this extra current-value lookup.

## Why it's non-obvious

The read/write asymmetry is the trap: HighLevel echoes the value back as a
plain array on `GET`, which looks like confirmation that a plain array is
the correct shape to send back on `PUT`. It is not – read shape and write
shape differ for this one field type.

## Evidence

Confirmed live, in complete isolation (a single-field request, nothing
else present): `PUT /objects/custom_objects.employment/records/:id` with
`{"include_fair_work_note":["yes"]}` reproduced the exact 422 against a
real record whose own `GET` response returns that identical array shape.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Any checkbox/multiselect field on any object written through the Objects
API – confirmed for Custom Object and Business. Does not apply to
Contact/Opportunity's classic `customFields` write path, which has not
shown this same requirement.
