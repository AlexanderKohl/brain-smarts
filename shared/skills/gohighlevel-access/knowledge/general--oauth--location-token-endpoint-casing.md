---
id: ghl-general-oauth-location-token-casing
title: Use camelCase /oauth/locationToken – the kebab-case v3-docs path 404s
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: POST /oauth/locationToken
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-15'
verified: '2026-08-15'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# Location token exchange: camelCase path, not v3's kebab-case

## Behaviour

HighLevel's documentation is internally inconsistent about this endpoint's
path casing: the "v3 New" docs page shows kebab-case
(`POST /oauth/location-token`), while the OAuth walkthrough curl example
and the scopes table both use camelCase (`POST /oauth/locationToken`). Only
the **camelCase** path actually works – the kebab-case v3 path returns a
plain `404`. The same casing split exists for the installed-locations
listing endpoint (camelCase `/oauth/installedLocations` vs kebab-case
`/oauth/installed-locations`); try camelCase first.

## Why it's non-obvious

Both spellings appear in HighLevel's own official documentation,
attributed to different doc pages of the same version – there's no
in-docs signal that one of the two documented paths simply doesn't exist.
A 404 on the "newer-looking" v3 kebab-case path reads as a plausible
implementation bug on the caller's side, not confirmation that the
documented path is wrong.

## Evidence

Documented in the app's own maintained API reference (`GHL_API_NOTES.md`/
`GHL_SCOPES.md`, last verified 2026-08-15) after direct confirmation that
the kebab-case path 404s and the camelCase path succeeds.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

The location-token exchange and installed-locations listing calls in the
OAuth/agency-install flow – not object- or endpoint-specific beyond those
two OAuth-adjacent calls. Client code should try camelCase first and treat
a 404 there (not the kebab-case fallback) as the real failure signal.
