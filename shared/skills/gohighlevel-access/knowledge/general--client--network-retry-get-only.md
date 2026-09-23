---
id: ghl-general-network-retry-get-only
title: Retry a dropped connection once for GET only – a write may have already reached HighLevel
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
discovered: '2026-08-18'
verified: '2026-08-18'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/general--client--network-retry-get-only.md
---

# Network-level retry: GET only, never a write

## Behaviour

A network-level failure (the HTTP client itself throwing before any
response – e.g. `ECONNRESET`/`aborted` – as opposed to an HTTP error status
code) is worth one automatic retry, but **only for `GET`**. `POST`/`PUT`/
`DELETE` must fail immediately instead: a dropped connection after a write
request may have already reached and been applied by HighLevel, so a blind
retry risks a duplicate write with no way to detect it happened.

## Why it's non-obvious

A generic "retry on transient failure" instinct naturally covers every
verb; the asymmetry (safe to retry a read, unsafe to retry a write) only
matters for this specific failure mode – a dropped connection with no
response at all, not a 5xx or 429 the client already has explicit
backoff/retry handling for.

## Evidence

Confirmed in production: a single transient connection reset on a plain
`GET /objects/` call silently degraded the Marketplace Object dropdown to
only the three standard objects, with no visible error beyond a
`marketplace_objects_location_unavailable` warning in the logs – the retry
fix directly addresses that failure mode.

## Applies to

Any HTTP call to HighLevel's API, regardless of object type – this is a
transport-layer rule, not tied to a specific endpoint.
