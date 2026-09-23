---
id: ghl-general--session-token--user-id-in-sourceid-claim
title: The app session token names the user in sourceId, not user_id
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: general
field_type: null
endpoint: null
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--session-token--user-id-in-sourceid-claim.md
created: 2026-09-15T12:10:00+10:00
updated: 2026-09-23T18:00:00+10:00
---
# The session token's claims

## Behaviour

The bearer token the HighLevel web app attaches to its own API requests (the one a
client can recognise by its `authClass` claim) carries exactly these
claims, read live from a logged-in session on 15 September 2026:

```text
authClass  channel  source  authClassId  primaryAuthClassId  sourceId  iat  exp  jti
```

There is no `user_id`, `sub` or `email`. Working hypothesis, from the names and from the
known values of `source` (`WEB_USER`) and `authClass` (`Location` / `Agency`): `sourceId`
is the user's id when `source` is `WEB_USER`; `authClassId` is the sub-account (or agency)
the token is scoped to; `primaryAuthClassId` is the agency. **Confirmed the same day:**
looking `sourceId` up in `GET /users/?locationId=…` returned the logged-in user's own name
and email.

## Why it's non-obvious

Every other JWT one meets names the subject in `sub` or `user_id`. Guessing those, the
first run reported the writer as unknown; only listing the claim names showed where the
user actually is.

## Evidence

Claim names as reported by a browser-extension storage test, 15 September 2026. Values not recorded; the token never leaves the page realm.
