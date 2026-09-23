---
id: ghl-business-file-fields-add-remove-delta
title: Business file fields write through the Objects API add/remove delta, not a full replace
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: file
endpoint: PUT /objects/business/records/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-24'
source_refs: []
created: 2026-08-24T21:30:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Business file fields: Objects API add/remove delta

## Behaviour

A Business file property is updated through the Objects API as
`properties: { <key>: { add: [{ url, ... }], remove: [{ url, ... }] } }` –
a **delta**, not by resending the field's full final file list. Sending
the whole list including an already-present unchanged file previously
produced a `422 "We couldn't process file updates"`.

A direct consequence, confirmed live in production: on a field capped at
one file, sending only `add` for a replacement upload – without including
the field's existing file in `remove` – gets rejected: `400 "Too many
files for <Field>. Maximum allowed: 1."`, because the API is computing
`existing ∪ add`, not `add` in place of existing. The caller must always
compute and send `remove` for anything being displaced, not just for an
explicit deletion.

## Why it's non-obvious

"Resend the field's intended final state" is the natural mental model
coming from how most of this object's other fields are written (a plain
value replaces the old one). File fields specifically want a diff against
current state, and the error message for a full-file-list resend ("process
file updates") doesn't obviously point at "you sent the whole list instead
of a delta."

## Evidence

Delta shape confirmed via an official `@gohighlevel/api-client` SDK example
for `objects.updateObjectRecord`. The max-1-field rejection was
independently confirmed live against a real production record already
holding one file.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business and Custom Object (both go through the Objects API for file
fields – see `custom_object--file-fields--add-remove-delta-name-required.md`
for the Custom Object write, which additionally needs a `name` key this
entry's endpoint does not require). Contact and Opportunity file writes use
different shapes entirely – see the `contact--file-fields--*` and
`opportunity--file-fields--*` entries.
