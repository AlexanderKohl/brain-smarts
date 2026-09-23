---
id: ghl-general-type-scoped-parsing
title: File-value parsing must be scoped to file/signature field types, or it corrupts plain string values
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: null
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# File-shape parsing must be type-scoped, not run on every value

## Behaviour

This is a client-side lesson about handling HighLevel's raw field values,
not a HighLevel API behaviour itself – recorded here because the trigger
was a HighLevel data shape (a plain string value containing `/`, e.g. a
timezone `"Etc/GMT+12"`) and it's a trap any future integration against
this same catalog will hit again.

Running every field's raw value through generic "is this a file value?"
parsing (a bare-string branch that treats any non-empty string as a
potential single-file URL) mis-fires on ordinary text values that merely
*contain a `/`* – a value like `"Etc/GMT+12"` gets its URL-path fallback
applied, which splits on `/` and keeps only the last segment, truncating it
to `"GMT+12"` and wrapping it as a one-element file array. For most fields
this is invisible (a one-element array like `["Ada"]` stringifies
identically to `"Ada"` wherever downstream code just renders it), but two
things break visibly: an exact-match select field's value becomes an array
instead of a string and so never matches any option, and *any* value
containing a literal `/` gets silently truncated, not just timezone-shaped
ones.

## Why it's non-obvious

The corruption only shows up for values that are (a) not actually file
values and (b) contain `/` – a narrow, easy-to-miss intersection. It was
found via a Contact timezone field showing empty on reload despite being
saved correctly, which reads like a save-side bug, not a display-parsing
one.

## Evidence

Confirmed live: a Contact timezone always showed empty on form reload
despite the dropdown having the correct options and the value being saved
correctly; traced to the generic file-parsing branch firing on the plain
string value.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Any field-value normalisation layer reading raw HighLevel field values –
scope file-shape parsing (`filesFromValue`-style logic) strictly to fields
whose catalog-declared type is actually file or signature.
