---
id: GOOGLE-OAUTH-REFRESH-INVALID-GRANT-STORED-TRAY-TOKEN
title: Tray-stored Google refresh token can return HTTP 400 invalid_grant while client_id/secret still load from the same vault entry
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: google-workspace
object_type: oauth
field_type: refresh_token
endpoint: POST https://oauth2.googleapis.com/token
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs: []
created: 2026-09-12T14:50:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Tray-stored Google refresh token rejected as invalid_grant

## Behaviour

For a vault entry `google-workspace-oauth-<alias>`, broker `get_json` on
`oauth_token_json` returns a token object with `access_token`, `refresh_token`,
`expires_at` and Calendar/Contacts scopes, with `expires_at` about five weeks in
the past. `get_fields` still returns `client_id` and `client_secret`
from the same entry.

`POST https://oauth2.googleapis.com/token` with
`grant_type=refresh_token` plus those tray fields returns:

```json
{"error": "invalid_grant", "error_description": "Bad Request"}
```

Using the stored (expired) access token against Calendar
`GET /calendar/v3/calendars/primary/events` then returns HTTP 401
`UNAUTHENTICATED` / `Invalid Credentials`.

This happens both through `GoogleConnection.refresh()` (which also maps
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` from the tray) and through
`google_tray_token.py` talking to the broker directly. Loading credentials
from the unlocked tray does not repair a Google-side revoked refresh token.

## Why it's non-obvious

An unlocked Vault Agent and a populated `oauth_token_json` look like a live
connection (`google-accounts.json` still says `connected`). The failure is
Google rejecting the refresh grant, not a missing tray/broker path. Re-running
connect/browser consent is a different operation from "use the tray vault".

## Evidence

Live probes on 2026-09-12 against one owner account alias from Cursor with the
tray agent unlocked. Confirmed independently by `google_status.py` and
`google_tray_token.py`. The owner's record, with the account alias and its sources, is kept
in their memory.

## Applies to

OAuth refresh for `google-workspace-oauth-<alias>` entries. Not a Calendar
event-shape quirk. Sibling APIs (Gmail, People, Tasks, Drive) will fail the
same way until a new refresh token is stored.
