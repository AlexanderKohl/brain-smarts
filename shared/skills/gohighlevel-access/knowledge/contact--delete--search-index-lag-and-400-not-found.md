---
id: GHL-CONTACT-DELETE-SEARCH-INDEX-LAG
title: Deleted contacts keep returning from POST /contacts/search for a short window; authoritative check is GET /contacts/{id}, which answers 400 not 404
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: contact
field_type: null
endpoint: DELETE /contacts/{contactId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-01
verified: 2026-09-01
source_refs: []
created: 2026-09-01T08:27:41+10:00
updated: 2026-09-23T14:45:16+10:00
---

# Contact deletion: stale search index, and 400 for a missing contact

## Behaviour

`DELETE /contacts/{contactId}` returns HTTP 200 and the contact is genuinely
gone. For a short window afterwards, `POST /contacts/search` still returns the
deleted contact with its original `id`, `email` and `phone` – a full row, not a
tombstone. Immediately after five deletes, all five still came back from search
for every one of their ten identifiers.

The authoritative read disagrees with the index. `GET /contacts/{deletedId}`
returns:

```json
{"message":"Contact not found for id:id_EXAMPLE_01","error":"Bad Request","statusCode":400}
```

Note the status is **400**, not 404, and the string is `Contact not found for
id:{id}` with no space after the colon. This mirrors
[[business--record-id--400-not-404-invalid-id]], which records the same
400-instead-of-404 convention for business records; it applies to contacts too.

A re-check a short time later showed the index caught up: the same ten
identifier searches returned zero rows.

## Why it's non-obvious

A delete that returns 200 followed by a search that still finds the record reads
exactly like a failed delete. Any procedure whose gate is "delete, then re-run
the search and require zero matches" will report a false failure and can drive
an agent into re-deleting, escalating, or wrongly reporting that cleanup did not
work. A test runner's pre-test cleanup gate is commonly
this shape.

The 400-not-404 half compounds it: code that treats only 404 as "absent" will
raise on the very call that proves the delete succeeded.

## Evidence

Live probe against `Example Co (Staging)` (`loc_EXAMPLE_01`) on
2026-09-01 during the Example Co end-to-end test pre-cleanup. Five contacts
deleted (HTTP 200 each); immediate `POST /contacts/search` returned all five
across ten identifiers; `GET /contacts/{id}` returned HTTP 400 `Contact not
found` for all five; a later repeat of the same ten searches returned zero.
`confirmed`, not hypothesised – both halves were observed directly.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Correct usage

Verify contact deletion with `GET /contacts/{id}` and treat HTTP 400 carrying
`Contact not found` as proof of absence. Use `POST /contacts/search` to *find*
candidates, never to prove they are gone. When a zero-match gate is required,
either poll the search until it clears or gate on the per-id `GET` instead.

Note that the shared client raises `HighLevelOAuthError` on any 4xx regardless
of the `expected=` tuple, so the `GET` probe must be wrapped in a try/except
that inspects the message.
