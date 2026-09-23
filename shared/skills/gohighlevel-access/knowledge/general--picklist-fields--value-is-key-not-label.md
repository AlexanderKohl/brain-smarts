---
id: ghl-general-picklist-value-is-key
title: Picklist option values are opt.key, not opt.label – the two only sometimes match
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: picklist
endpoint: GET /objects/:key?fetchProperties=true
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/general--picklist-fields--value-is-key-not-label.md
---

# Picklist options: use opt.key, never opt.label

## Behaviour

HighLevel's field catalog rows for RADIO/SINGLE_OPTIONS/CHECKBOX options
are shaped `{ key, label }` – for example `{key: "full_time", label: "Full
Time"}` or `{key: "yes", label: "Yes"}`. The field's actual stored/written
**value is `opt.key`**, never `opt.label`. This is easy to get away with
undetected: it's only visibly broken when a field's key and label happen to
differ, which is the normal case, but is silently masked whenever they
happen to be identical strings (e.g. a field whose option key genuinely is
`"Yes"`).

Using the label instead of the key produces two distinct failure modes
depending on write path:

- On an Objects-API checkbox/multiselect field: the record's real stored
  key (e.g. `"yes"`) plus the label-derived wrong value (e.g. `"Yes"`) get
  sent together, and HighLevel rejects the whole write –
  `"We couldn't apply updates to <Field> due to an unexpected format"`.
- On a classic single-value select field: the write is **silently
  accepted** (HighLevel tolerates arbitrary text for a single-value
  field), but the stored canonical key never matches the label-derived
  option value on the next read, so the field never appears pre-selected.

## Why it's non-obvious

A field whose key and label coincidentally match (common for short,
already-lowercase-friendly option sets) hides the bug entirely in casual
testing; it only surfaces once a field has options where key and label
genuinely diverge.

## Evidence

Confirmed live: reproduced both failure modes against real fields – a
Custom Object checkbox field (`employment_status`, `use_example_template`)
for the rejected-write case, and a Contact checkbox field that
coincidentally had `key:"Yes"/label:"Yes"` for why it had gone unnoticed.

## Applies to

Any RADIO/SINGLE_OPTIONS/CHECKBOX/multiselect field on any object type –
this is a field-catalog-parsing rule, not object- or endpoint-specific.
