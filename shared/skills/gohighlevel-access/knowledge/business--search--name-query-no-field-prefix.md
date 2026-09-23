---
id: ghl-business-search-name-query-no-prefix
title: 'Business Object Records Search ignores documented name: field-prefix syntax'
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: business
field_type: null
endpoint: POST /objects/business/records/search
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/business--search--name-query-no-field-prefix.md
---

# Business Object Records Search: no field-prefix, substring match only

## Behaviour

`POST /objects/business/records/search` (body `{ locationId, page, pageLimit,
query, searchAfter }`) – HighLevel's documented `name:<value>` query-prefix
syntax returns `total: 0` **every time**, for every prefix variant tried
(`name:`, `business.name:`, full name and fragments, against two different
real businesses in the same location). The identical value sent as **plain
text with no field prefix at all** matches correctly. The match is a
**substring** match, not exact – `query: "Acme"` also returns "Acme
Roofing" and "Best Acme Co".

## Why it's non-obvious

The documented `field:value` query syntax is the natural thing to try first
and looks like it should work; it silently returns zero results instead of
erroring, which reads as "no match" rather than "wrong syntax."

## Evidence

Confirmed live via a raw authenticated call (`gohighlevel-access` skill +
agency token, bypassing the app) against a real location, tried against two
distinct real businesses.

## Applies to

Business only, confirmed. Because the match is substring-not-exact, any
caller using this as a "look up the one record with this exact name"
lookup (as this app does, for the Company Name → Record ID fallback
described in `business--record-id--400-not-404-invalid-id.md`) must still
apply its own exact (trimmed, case-insensitive) match check over the
results – do not treat a fragment hit as *the* match. Response envelope
shape beyond `{ records, total, traceId }` is not independently confirmed;
defensive parsing should accept either a flat `{ id, name }` row or an
Objects-API `{ id, properties: { name } }` row.
