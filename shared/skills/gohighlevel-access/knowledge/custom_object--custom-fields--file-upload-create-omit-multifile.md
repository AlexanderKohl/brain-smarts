---
id: ghl-custom-object-custom-fields-file-upload-create-omit-multifile
title: Custom object FILE_UPLOAD create must not send isMultiFileAllowed or options
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: custom_object
field_type: file
endpoint: POST /custom-fields/
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-04
verified: 2026-09-04
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/custom_object--custom-fields--file-upload-create-omit-multifile.md
created: 2026-09-04T12:27:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Custom object FILE_UPLOAD create: omit isMultiFileAllowed and options

## Behaviour

`POST /custom-fields/` with `Version: v3` to create a `FILE_UPLOAD` field on a custom object (`objectKey` such as `custom_objects.site_visits`) succeeds when the body has `name`, `dataType`, `fieldKey`, `objectKey`, `parentId`, and optionally `acceptedFormats` / `maxFileLimit`. Sending `isMultiFileAllowed` or `options` (copied from a classic Opportunity source field) is rejected.

Choice types still need `options` on create (`RADIO`, `SINGLE_OPTIONS`, `MULTIPLE_OPTIONS`, `CHECKBOX`, `TEXTBOX_LIST`).

## Why it's non-obvious

The classic Opportunity GET payload includes `isMultiFileAllowed` and sometimes `options` on FILE_UPLOAD. Echoing that object into v3 create looks like a faithful copy and fails.

## Evidence

Live create of Site Visit `Front of Location` and `Inverter Label Photo` on `Example Co (Staging)` (`loc_EXAMPLE_01`) on 2026-09-04 after omitting those keys. `confirmed`.

## Applies to

Confirmed for custom-object field create via Custom Fields v3. Classic Opportunity FILE_UPLOAD *update* separately rejects `maxFileLimit` on PUT (`opportunity--custom-fields--classic-put-payload-by-type.md`).
