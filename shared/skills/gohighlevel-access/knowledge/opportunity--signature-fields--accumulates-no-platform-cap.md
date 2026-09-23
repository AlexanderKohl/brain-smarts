---
id: ghl-opportunity-signature-accumulates
title: Opportunity signature fields have no platform-enforced single-value cap and accumulate indefinitely
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: signature
endpoint: PUT /opportunities/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-24
verified: 2026-08-25
source_refs: []
created: 2026-08-25T09:15:00+10:00
updated: 2026-09-23T14:45:16+10:00
evidence:
- Production Railway logs, 2026-08-24T20:24-20:26+00:00 (two real submissions two minutes apart, on the same Opportunity/field)
---

# Opportunity signature fields: no platform cap, accumulate by design

## Behaviour

HighLevel does **not** enforce a single-value cap on a signature-type
field at the write/platform level – it accepts and stores as many entries
as are written to it, the same as any ordinary multi-file field. This app
special-cases Contact signature fields (`isSignature`, see
`contact--signature-fields--replace-not-accumulate.md`) to always discard
the kept set on a new signing so the field only ever holds one value – but
that is a purely **client-side convention**, not something HighLevel
requires or enforces itself, and Opportunity has no equivalent guard.

Confirmed live: on an Opportunity signature field configured
`file_upload_mode: add`, two real submissions two minutes apart each
appended a new signature without removing any prior one (array grew from 4
entries to 5, every entry `deleted: false`) – matching ordinary Opportunity
multi-file behaviour (`opportunity--file-fields--multi-file-full-array-deleted-flag.md`)
exactly, because that's genuinely the same write path.

This had a real downstream bug: the Form Submitted trigger's signature-URL
lookup read array index `[0]` – the oldest surviving entry – instead of the most
recently added one, so it returned the *first-ever* signature on every
submission regardless of how many newer ones had since been added. Fixed
by reading the last entry instead (kept entries are
always written before newly-added ones – `fileWriteEntries([...kept,
...added])` – so the last array element is reliably the newest, as long as
this write pattern holds).

## Why it's non-obvious

It's easy to assume a "signature" field type carries single-value
semantics as a platform guarantee, the way this app's own Contact handling
makes it look. HighLevel treats it as an ordinary file field with no such
guarantee – any code reading "the current signature" for any object must
not assume array position `[0]` (or any fixed position) is the current
one; it must explicitly reason about kept/added write order, exactly as
for any other accumulating multi-file field.

## Evidence

Confirmed directly from real production Railway logs: two `PUT
/opportunities/:id` writes for the same field two minutes apart, each
appending one new entry with no prior entry ever marked `deleted`, and the
Form Submitted trigger payload showing the identical oldest URL both
times before the fix.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Opportunity signature fields specifically. Whether Business or Custom
Object signature fields behave the same way is not yet tested – see
`contact--signature-fields--replace-not-accumulate.md`'s "Applies to" for
the still-open status on those two.
