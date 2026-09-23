---
id: ghl-contact-textbox-list-uuid-keyed
title: Contact Textbox List fields must be edited by reusing the record's own existing per-row UUID keys
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: textbox_list
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

# Contact Textbox List: reuse the record's own UUID keys

## Behaviour

A Contact Textbox List custom field is stored as an **object keyed by
stable per-row UUIDs that HighLevel itself assigned** when the field was
first populated. Editing an existing value only works by **reusing the
record's own current UUID keys**, positionally matched to row order, with
new text. A plain array, a freshly self-generated UUID, and an
option-key-keyed object were all tried live and **silently accepted (HTTP
200) but had zero effect on the stored value** – no error, no persisted
change.

Separately: a field that has **never** been given a value before (no
existing keys to reuse) does not appear to accept *any* shape tried via
this endpoint – a confirmed, currently unresolved limitation for
first-time initialization, not just an unconfirmed gap. A caller must
fetch the record's current raw value first (when a Textbox List field is
among the changed fields) and reuse those keys; when there is nothing to
reuse, the best available fallback is a plain array (documented as
known-not-to-work for true first-time init, kept only because it's no
worse than any other untested shape).

## Why it's non-obvious

The write returns `200 OK` in every tried shape, including the ones that
have no effect – there is no error signal distinguishing "this worked"
from "this was silently ignored." This is a different shape from every
other object's Textbox List (Business/Custom Object's compound-key rows,
Opportunity's plain array/string – see the sibling entries), so nothing
about those confirms or informs this one.

## Evidence

Confirmed via a real write+read round-trip against a live Contact record
(`gohighlevel-access` skill): the record's own current keys, reused,
persisted the new text; every other shape tried round-tripped back to the
unchanged prior value with a `200` response and no error.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Contact only. Do not assume this UUID-keyed shape for Opportunity (plain
array – confirmed different, see
`opportunity--monetary-textbox-list--plain-shapes-correct.md`) or for
Business/Custom Object (compound-key rows – see
`business--textbox-list--compound-key-shape.md`).
