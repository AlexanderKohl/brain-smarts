---
id: ghl-opportunity-multi-file-deleted-flag
title: Opportunity multi-file fields resend the complete history with deleted flags, not a trimmed array
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: file
endpoint: PUT /opportunities/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/opportunity--file-fields--multi-file-full-array-deleted-flag.md
---

# Opportunity multi-file: resend everything, flag deletions

## Behaviour

An Opportunity multi-file custom field is written back as the **complete
array of every file that has ever existed on the field**, with removed
files flagged `deleted: true` (their `meta` left intact) rather than
omitted from the array entirely. Sending a trimmed array (only the
currently-kept files) causes corruption/loss, not a clean "removed files
are gone" result.

## Why it's non-obvious

"Send the array you want the field to end up holding" is the natural
mental model for a REST-style PUT; this endpoint instead wants a full,
append-only history with in-place deletion flags, closer to an event log
than a snapshot.

## Evidence

Confirmed via an official `@gohighlevel/api-client` SDK example for
`opportunities.updateOpportunity`.

## Applies to

Opportunity multi-file fields. The single-file write path was later
unified onto this same array shape – see
`opportunity--file-fields--single-file-needs-multifile-array-shape.md`.
Contact's own multi-file shape is different in one respect: Contact
**omits** a removed file rather than flagging it `deleted` – see
`contact--file-fields--multi-file-full-kept-set-required.md`. Do not
assume the two objects' multi-file conventions match.
