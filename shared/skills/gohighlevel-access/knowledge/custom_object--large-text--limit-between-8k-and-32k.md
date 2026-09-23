---
id: ghl-custom_object--large-text--limit-between-8k-and-32k
title: "A LARGE_TEXT custom-object property holds at most 12,000 characters"
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: large_text
endpoint: POST /objects/{schemaKey}/records
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs: []
created: 2026-09-15T11:20:00+10:00
updated: 2026-09-23T18:00:00+10:00
---
# LARGE_TEXT: 12,000 characters, exactly

## Behaviour

Writing a custom-object record whose `LARGE_TEXT` property held a JSON string:

| Characters | Answer |
| --- | --- |
| 1,129 | 201, read back byte for byte |
| 8,116 | 201, read back byte for byte |
| 11,482 | 201, read back byte for byte |
| 12,482 | **400** |
| 13,182 / 14,482 / 20,482 / 32,382 / 121,384 | **400** |

The 400 names the limit, after echoing the whole value: *"… exceeds the 12,000 character
limit for Detail."* So a `LARGE_TEXT` property holds **12,000 characters** (the field's
display name is in the message). Bisected to within 1,000 on the second run of 15
September; the message states the exact figure.

JSON survives the round trip unchanged at the sizes that are accepted: quotes, braces,
newlines inside strings, none of it is altered by the API. Pasting the same JSON into the
record editor in the HighLevel UI reportedly does not work; that is the editor, not the
field (reported from use, undiagnosed).

## Why it's non-obvious

Nothing in the custom-fields or objects API documents a length for `LARGE_TEXT`. The 400
does name it, but only after repeating the offending value, which for a 32 KB value pushes
the reason off the end of any log line that shows the message's head.

## Evidence

Two storage test runs of 15 September 2026 on Example Test through the page-session
token. Consequence for a client storing JSON there: one record per item, split across records
once the JSON passes a safe margin below the limit (12,000 characters, say).

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Custom object properties of type `LARGE_TEXT`. Whether contact or opportunity large-text
fields share the limit is untested; Example Co keeps AI JSON in one, so it is at least
above what a workflow writes there.

