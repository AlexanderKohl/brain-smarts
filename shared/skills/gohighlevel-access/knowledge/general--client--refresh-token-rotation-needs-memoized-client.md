---
id: ghl-general-refresh-token-rotation-memoized-client
title: OAuth refresh tokens rotate every use, so a fresh client per call can retry with an already-invalid token
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: POST /oauth/token
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-22'
verified: '2026-08-22'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/general--client--refresh-token-rotation-needs-memoized-client.md
---

# Refresh-token rotation requires a memoized client, not a fresh one per call

## Behaviour

HighLevel refresh tokens are **single-use**: every refresh rotates in a
**new** refresh token, which must be persisted. This has a real
correctness consequence for client code, not just a "remember to save it"
note: if a fresh API client instance is constructed on every call rather
than memoized per adapter/installation, a successful in-memory token
refresh on one call is invisible to the next call's fresh instance, which
starts over from the stale, already-superseded installation record. A
single logical request that needs 2+ HighLevel calls while straddling the
access token's near-expiry window can then have its second call attempt a
refresh using an already-rotated, now-invalid refresh token and fail
outright.

## Why it's non-obvious

The bug is intermittent and load/timing-dependent (it only manifests when
a request happens to straddle the token's near-expiry window with multiple
calls), so it doesn't reproduce reliably in casual testing – it looks like
a client that "usually works" with occasional unexplained auth failures.

## Evidence

Identified via code review confirming the mechanism (client construction
site, and that `refresh()` mutates only its own instance's copy of the
installation record) rather than a captured live failure – the fix
(memoize the client per adapter instance) removes the race by construction.

## Applies to

Any HighLevel API client implementation using OAuth refresh tokens –
general to the auth/transport layer, not tied to a specific object or
endpoint beyond the token endpoint itself.
