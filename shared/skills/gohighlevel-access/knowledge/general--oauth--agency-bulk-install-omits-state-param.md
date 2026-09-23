---
id: ghl-general-oauth-agency-bulk-install-no-state
title: Agency bulk-install callbacks omit the state query param entirely, unlike single-location installs
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /api/oauth/callback
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-24'
verified: '2026-08-24'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- /memory/skills/gohighlevel-access/knowledge/general--oauth--agency-bulk-install-omits-state-param.md
---

# Agency bulk-install OAuth callback: no `state` param

## Behaviour

For a normal single-location install, HighLevel's OAuth redirect echoes
back the `state` query param the app sent. For an **agency-level bulk
install** (installing across many sub-accounts at once), HighLevel's
redirect to the callback omits the `state` query param **entirely** –
while the app's own `oauth_state` cookie from the app-initiated flow is
still genuinely present. A CSRF check that treats "cookie present, `state`
absent" the same as "cookie present, `state` mismatched" incorrectly
rejects every agency bulk install.

This has a real, non-obvious downstream consequence: HighLevel completes
the agency-level authorization **independently of the callback's outcome**
and fires one `INSTALL` webhook per sub-account regardless. Each webhook
then attempts to exchange its location token using whatever agency token
is already on file – stale, since the rejected callback never got to save
the fresh one – and every one of those per-location exchanges can fail. If
the webhook handler always returns `200` even on that internal failure (a
separate, generally-reasonable pattern to avoid HighLevel retry storms),
none of the affected sub-accounts get an automatic recovery path; they
need the install redone once the root cause is fixed.

## Why it's non-obvious

The correct fix is narrow: treat it as CSRF **only** when `state` is
actually present and doesn't match – not "we expected one and didn't get
one." A blanket "state must be present" check is the natural-looking CSRF
implementation and is exactly what breaks this path. The downstream
webhook failures also don't obviously trace back to the callback's CSRF
logic – they look like a separate token-exchange problem.

## Evidence

Confirmed via Railway production logs during a real agency bulk install
across 18 sub-accounts: cookie present, `state` param absent in the actual
redirect, callback rejected, followed by 18 webhook-side `401 Invalid JWT`
token-exchange failures in the same log window.

## Applies to

Any OAuth callback implementation for this app – not object- or
endpoint-specific. A fully-absent `oauth_state` cookie was already an
established, separately-handled legitimate case (HighLevel's
provider-initiated install path); this is the equivalent gap for a
present-cookie/absent-param combination.
