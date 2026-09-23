---
id: ghl-contact-signature-replace-not-accumulate
title: Signature fields need their own meta shape and must replace, never accumulate, on each signing
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: signature
endpoint: PUT /contacts/:contactId
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-25'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:45:16+10:00
---

# Signature fields: own meta shape, always replace

## Behaviour

Two confirmed, related facts about signature fields (a Contact field type):

1. **Meta shape.** A signature entry's `meta` is a different shape from a
   regular uploaded file's echoed-through meta: `fieldname` (the custom
   field's own id, **not** the uploaded filename), `originalname`
   (`sign-timestamp-<epoch>.png`), `encoding` (`"7bit"`), `mimetype`,
   `size`, `isSignature: true`, and `timestamp`. Deliberately no
   `uuid`/`documentId` – this app's own upload response never returns
   either, so fabricating them risks colliding with values HighLevel
   expects to own itself.
2. **Replace, don't accumulate.** A signature field's write path must
   **discard** whatever is already on the field and hold only the newest
   signature. A signature field never shows its existing value on the
   public form (always renders blank by design) and has no file-count cap,
   so nothing client-side stops a recipient from signing repeatedly across
   sessions – if the write path merges instead of replacing (the same
   "keep existing + add new" logic multi-file fields correctly use), the
   field silently accumulates a growing array that HighLevel's own
   signature UI apparently cannot render. A real field was observed to
   reach three accumulated entries this way in testing.

## Why it's non-obvious

The multi-file "keep existing, add new" merge pattern is correct and
necessary for genuine multi-file fields (see
`contact--file-fields--multi-file-full-kept-set-required.md`) – applying
that same pattern to a signature field is the natural-looking mistake,
since a signature field is implemented as a file-shaped custom field
underneath.

## Evidence

Confirmed live: a real field accumulated a 3-entry array across three
separate signings before this was caught; a fresh signing that discards
the kept set was verified to leave exactly one current entry.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Signature fields on **Contact** – the only object this app gives
signature fields any special-cased handling for at all. Confirmed
directly in code (`ContactAdapter.setFileField`'s `options.isSignature`
path, and its own type declaration explicitly documents this as
"Contact only"). Not a general file-field rule; ordinary multi-file
fields must continue to merge, not replace.

**Opportunity is now confirmed, and it does NOT need this replace guard**
(a deliberate design choice) – see
`opportunity--signature-fields--accumulates-no-platform-cap.md`.
Opportunity signature fields go through the ordinary file-field write path
(`opportunity-adapter.ts`) with no `isSignature` meta shape and no
replace-not-accumulate guard, and genuinely accumulate every signing
indefinitely; HighLevel does not enforce a single-value cap at the
platform level for either object. Only the meta-shape half of this entry
is Contact-specific – the replace-not-accumulate half is a Contact-only
*design choice*, not something every object needs.

**Business and Custom Object remain untested, not confirmed-absent.** If
a signature field is ever configured on either, this app's shared
`live-adapter.ts` `setFileField` path would treat it as an ordinary file
field the same way Opportunity's does – confirm live against the specific
object before assuming that's correct or that it needs the Contact
treatment.
