---
id: ghl-opportunity-file-record-id-uuid-experiment
title: 'REFUTED: uploading Opportunity files under the record id instead of the field id'
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: file
endpoint: POST /locations/:locationId/customFields/upload
status: refuted
superseded_by: null
refuted_by: ghl-opportunity-single-file-needs-array-shape
discovered: '2026-08-22'
verified: null
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# REFUTED: `id = record id` + `{fieldId}_{uuid}` upload for Opportunity

## The hypothesis

HighLevel's docs describe the legacy upload endpoint's `id` parameter
ambiguously as "Contact Id / Opportunity Id / Custom Field Id." Modeled on
a separately confirmed working fix for Contact uploads, this experiment
sent the **Opportunity's own record id** (never tried before – the app had
always sent the custom field's id) as `id`, naming the multipart part
`{fieldId}_{uuid}` instead of the filename, and skipped the follow-up
`setFileField` write for a plain multi-file add.

## Why it looked plausible

It was a structural parallel to a fix that had genuinely just worked for
Contact, applied to the one other object still broken for multi-file
uploads, against HighLevel's own ambiguous documentation of the same
parameter.

## What was actually true

A real record read after this shipped showed the field's stored
`meta.name` as a bare storage-path UUID
(`d78a47d8-....pdf`, matching the upload URL's own generated filename
segment exactly) instead of the real uploaded filename – HighLevel
silently discards the original filename under this `id = record id`
reading, unlike the `id = field id` reading. It also **regressed the
previously-working single-file case** live. The eventual real fix was
unrelated to the upload `id`/multipart-naming question entirely: the
actual missing piece was the **write shape** (the array-of-`{url, deleted,
meta}` form), not the upload call – see
`opportunity--file-fields--single-file-needs-multifile-array-shape.md` and
`opportunity--file-fields--multi-file-full-array-deleted-flag.md`.

## Do not repeat this

Do not send an Opportunity's record id (instead of the custom field's id)
to the legacy `customFields/upload` endpoint, and do not name the
multipart part `{fieldId}_{uuid}` for Opportunity uploads – this was tried
live, shipped, and reverted after confirmed real-world regression. The
Contact fix that motivated this experiment does not generalise to
Opportunity.

## Evidence

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.
