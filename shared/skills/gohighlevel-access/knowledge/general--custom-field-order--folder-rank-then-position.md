---
id: ghl-general-field-order-folder-rank
title: Field order ranks by folder first; folder rank must use first-seen array index, not position value
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /objects/:key?fetchProperties=true
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Field ordering: folder rank dominates, and must use array index

## Behaviour

Two layered facts about how HighLevel's field catalog order should be
reconstructed:

1. **Folder rank outranks in-folder position.** A field's overall display
   order is decided by which folder it's in first, then its position
   within that folder – reordering a field's position *within* its own
   folder can never move it ahead of every field in an entirely
   lower-ranked folder. (Real case: Company Name and Business Turnover
   live in different folders; no amount of reordering Business Turnover's
   own position moved it ahead of Company Name, because Company Name's
   *folder* outranked Business Turnover's folder regardless.)
2. **A folder's own rank must be its first-seen array index, not its
   lowest member position value.** HighLevel resets position numbering to
   start at 0 **independently within every folder** – so two different
   folders can each have a first field at position 0, tying naive
   "rank by lowest position" logic, and if subsequent positions also
   happen to number identically (0/50/100/150/...) the whole sort
   degrades to alphabetical-by-key, interleaving folders together instead
   of keeping each one grouped. Ranking a folder by the array index of its
   first-appearing field in the raw catalog response instead is
   collision-proof (guaranteed unique across distinct folder ids) and
   matches HighLevel's own real ordering: fields interleave folder-by-
   folder at each shared position rung, but do so in a consistent
   first-encountered order.

## Why it's non-obvious

Position-based ranking looks like the obviously-correct approach – it's
literally a field HighLevel calls "position" – and works correctly until
tested against a real account where two folders' position numbering
genuinely collides. The resulting scramble (alphabetical-looking order)
doesn't obviously point back at "folder position collision."

## Evidence

Confirmed against a real 31-field Example Test Contact catalog (Railway
logs): the "Contact" folder's first field and the "General Info" folder's
first field were both at position 0, and every subsequent slot in both
folders also collided (0/50/100/150/...), reproducing the exact reported
symptom (fields from two folders scrambled together). The array-index fix
was independently re-verified against the same real catalog end-to-end.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Any object's field catalog ordering (Contact, Opportunity, Business,
Custom Object) – the folder/position mechanism and the collision risk are
catalog-wide, not object-specific.
