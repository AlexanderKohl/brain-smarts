---
id: ghl-business-standard-fields-write-shape
title: Business standard-field writes need a schema-aware body, a postalCode key override, and no locationId on PUT
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: null
endpoint: GET, PUT /businesses/:businessId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-24'
source_refs: []
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Business standard-field write/read mechanics

## Behaviour

Two distinct, easy-to-miss facts about `/businesses/:businessId`:

1. **`postalCode` key mismatch.** HighLevel's field catalog reports this
   field's key as `business.postalcode` – no underscore, unlike every other
   compound-word field key. A generic snake_case→camelCase key deriver
   cannot produce `postalCode` from that. The classic `PUT` body needs an
   explicit `postalcode` → `postalCode` override to write it, and the
   classic `GET` response echoes the value back under the camelCase key
   `postalCode`, which a generic alias generator also never derives – the
   read side needs the identical override, independently.
2. **The write body must be schema-aware.** A naive "flat-map every changed
   field onto the body" write (unlike Contact/Opportunity, which already
   used a schema-aware `bodyFromChanges`) sends **every** changed field –
   standard and custom – as a top-level property and always attaches
   `locationId`. All three are wrong: `PUT` rejects a top-level
   `locationId` outright (`"property locationId should not exist"`);
   custom fields must go under a separate write, not top-level (see
   `business--custom-fields--objects-api-required.md`); and any top-level
   key that isn't a real standard-field key on this endpoint 422s the
   **entire** request, so no field in that submission gets saved – not just
   the offending one.

## Why it's non-obvious

The failure mode is not "the odd field is dropped" but "the whole write
422s and nothing is saved," so a legitimately-changed, correctly-keyed
field (e.g. `phone`) can look unsaved/unverified purely because a sibling
field in the same request broke the body.

## Evidence

Confirmed live via Railway production logs: a real submission 422'd with
`"property postalcode should not exist"`, `"property businessTurnover
should not exist"`, and `"property locationId should not exist"` in the
same response.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Business only for the `locationId`-on-PUT and schema-aware-body facts.
The `postalcode`/`postalCode` key-casing mismatch is confirmed specific to
this one Business field – do not assume other Business fields need a
similar override without checking the catalog key directly. `locationId`
is still required (and sent) on `POST` (create).
