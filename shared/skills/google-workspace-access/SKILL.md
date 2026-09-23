---
name: google-workspace-access
description: Connect named Google accounts through vault-backed OAuth and run portable Gmail, Calendar, Tasks, Drive and Contacts operations. Integrates with Personal CRM personas and contact files. Draft-first email; send only after explicit owner approval of a specific draft. Use instead of Cursor marketplace/MCP Google connectors for portable work.
metadata:
  id: skill-google-workspace-access
  title: Google Workspace Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: Google Workspace
  canonical_source: /shared/skills/google-workspace-access
  skill_refs:
    - /shared/skills/manage-credentials
  project_refs:
    - /memory/projects/credential-management
  owner_config: /memory/skills/google-workspace-access/config/
  created: 2026-08-06T09:37:00+10:00
  updated: 2026-09-23T16:53:00+10:00
---

# Google Workspace Access

## Purpose

Provide a portable, vault-backed Google Workspace skill covering Gmail, Calendar, Tasks, Drive and Contacts for any AI working in this brain. Multi-account from day one. Integrate with the owner's Personal CRM node (`<crm-node>/`, see *Owner configuration*) so side effects resolve contact → persona → `google_account_alias` before writing.

This skill does **not** use Cursor marketplace or MCP Google connectors.

## Allowed operations

- Authorise one or more Google accounts on `localhost:8767` and keep rotating tokens in the vault, one entry per account alias.
- Gmail: search, read (decoded), create and update drafts; send only a draft the owner approved by id; optional local SQLite sync for routine reads.
- Calendar: list and create events. Tasks: list, create and update, with an optional local mirror.
- Drive: search, read and download; write only files this app created (`drive.file`).
- Contacts: list and sync into Personal CRM files; field writes only with `--i-approve-write` and `--confirm-target`.
- Resolve contact, persona and account alias before any side effect (CONTRACT §10.5).

## Data sources

- Google APIs for Gmail, Calendar, Tasks, Drive and People under the scopes listed below.
- `<crm-node>/data/google-accounts.json` (account aliases), `<crm-node>/personas/` and `<crm-node>/contacts/` for resolution.
- The encrypted vault entries `google-workspace-oauth-<alias>`, and the optional local SQLite index outside the repository.
- `/memory/projects/credential-management/data/credential-registry.json` (non-secret registry).

## Permissions

- Treat retrievals as read-only unless the user explicitly authorises a write.
- Before any write or other side-effecting Google operation (CONTRACT §10.5):
  1. Resolve the Personal CRM contact file when the operation is person-linked.
  2. Load the persona (`preferred_reply_persona` or ask).
  3. Resolve `google_account_alias` from the persona (or ask).
  4. Confirm the named account alias for this operation; do not silently default.
- Email is draft-first. Create or update a Gmail draft only until the owner explicitly approves sending that specific draft id.
- Never store client secrets, access tokens or refresh tokens in the repository.
- Use `/shared/skills/manage-credentials/` and the encrypted portable vault.
- No delete/trash helpers in this first cut. Google Contacts field writes require the `contacts` scope and `--i-approve-write` / `--confirm-target`.
- Fail closed when credentials, account alias, scopes or CRM confirmation are missing.

## Required inputs

- A Google Cloud OAuth client (Web application) with redirect URI `http://localhost:8767/oauth/callback`.
- Vault entry per account alias (see registry), containing `client_id`, `client_secret` and rotating `oauth_token_json`.
- Account alias from `<crm-node>/data/google-accounts.json` (or env `GOOGLE_ACCOUNT_ALIAS`).
- For person-linked side effects: CRM contact and/or persona confirmation.
- Explicit write/send approval flags where scripts require them.

## Owner configuration

Everything specific to the owner lives in `/memory/`, never in this skill:

| Item | Where |
|---|---|
| Personal CRM node (`<crm-node>` below) | `crm_root` in `/memory/skills/google-workspace-access/config/crm.json`, a brain-root path such as `"/memory/projects/<crm-node>"`; env `GOOGLE_CRM_ROOT` overrides with an absolute path |
| Account registry | `accounts_registry` in the same file; defaults to `<crm-node>/data/google-accounts.json`; env `GOOGLE_ACCOUNTS_REGISTRY` overrides |
| Seeded accounts (alias, Google login, vault entry, primary from address) | the account registry, summarised in `/memory/skills/google-workspace-access/NOTES.md` |
| Calendar default `--timezone` | `timezone` in `/memory/OWNER.md`, else UTC |
| Defaults for `google_tray_token.py apply-event-location` | `/memory/skills/google-workspace-access/config/tray-token.json` |

The scripts find these by walking up from the script to the brain root (the folder holding
`CONTRACT.md`) and joining `memory/skills/google-workspace-access/config/`. Without `crm_root`
every CRM-dependent command fails closed with a message naming the file to create.

The examples below use the fictional alias `example-gmail` (persona `personal`, vault entry
`google-workspace-oauth-example-gmail`, primary from `owner@example.com`). Substitute an alias
from the registry.

## Scopes requested (first cut)

```text
openid
email
profile
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/drive.readonly
https://www.googleapis.com/auth/drive.file
https://www.googleapis.com/auth/contacts
```

Notes:

- `gmail.modify` can send at the API layer; this skill still gates send behind explicit draft approval flags.
- Drive writes use `drive.file` (files created by this app). Broader Drive write scopes are out of first cut.
- `contacts` is read/write (do not also request `contacts.readonly`). Contact field writes still need an explicit owner-authorised command; CRM files remain the relationship-memory source of truth.

## Store credentials

With the Vault Agent unlocked (or via interactive `put-entry`):

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry google-workspace-oauth-example-gmail `
  --secret client_id `
  --secret client_secret `
  --empty-json oauth_token_json
```

Do not paste access or refresh tokens manually. The connection manager owns `oauth_token_json`.

Configure non-secret runtime settings in the shell that launches Google commands:

```powershell
$env:GOOGLE_TOKEN_STORE = "vault"
$env:GOOGLE_ACCOUNT_ALIAS = "example-gmail"
$env:GOOGLE_VAULT_ENTRY = "google-workspace-oauth-example-gmail"
$env:GOOGLE_VAULT_FIELD = "oauth_token_json"
$env:GOOGLE_REDIRECT_URI = "http://localhost:8767/oauth/callback"
```

`GOOGLE_VAULT_ENTRY` may be omitted when the alias exists in `google-accounts.json`.

## Connect an account

1. In Google Cloud Console, create (or reuse) an OAuth client of type **Web application**.
2. Add authorised redirect URI exactly: `http://localhost:8767/oauth/callback`.
3. Enable APIs: Gmail, Google Calendar, Tasks, Google Drive, People (Contacts).
4. Put `client_id` / `client_secret` in the account vault entry (above).
5. With the Vault Agent unlocked:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-example-gmail `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_connect.py --account example-gmail
```

Open `http://localhost:8767/`, connect, and approve scopes while signed into the intended Google login (the `email` recorded for that alias in the registry).

Check status:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-example-gmail `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_status.py --account example-gmail
```

List registry aliases without calling Google:

```powershell
python shared/skills/google-workspace-access/scripts/google_status.py --list-accounts
```

After a successful connect, set the registry account `status` to `connected` in `<crm-node>/data/google-accounts.json`.

## CRM resolution before side effects

```powershell
python shared/skills/google-workspace-access/scripts/google_crm_resolve.py `
  --contact-email someone@example.com
```

Or with persona only:

```powershell
python shared/skills/google-workspace-access/scripts/google_crm_resolve.py `
  --persona personal `
  --allow-missing-contact
```

Side-effect CLIs require `--confirm-target` after the owner confirms the resolved persona/account. When multiple contacts match, present candidates and ask; never guess.

## Gmail

### Auto-create CRM + Newsletter / CRM read depth

**Rule – auto-create on new contact:** When the From address (or another newly observed remote party) has no CRM contact, create one from `<crm-node>/contacts/_TEMPLATE.md` in the same session. Deduplicate by email/name (one contact per real person/org; marketing blasts may be newsletter contacts). Never store secrets in CRM files. Do not invent `preferred_reply_persona` for newsletters (leave null).

**First encounter:** For a brand-new email contact, call `gmail read` for the **full decoded body** (not subject/snippet alone). Extract identifiers and context into the CRM file and use the body to decide `contact_kind` / newsletter flags. After the contact is classified as a newsletter, subsequent processing honours `newsletter_read_detail`.

Before calling full `gmail read` or fetching images for an **already classified** contact:

1. Resolve the Personal CRM contact from the From address (`google_crm_resolve.py` or read `contacts/`).
2. If the contact is a newsletter (`contact_kind: newsletter` or `newsletter: true`), honour `newsletter_read_detail`:
   - `subject` (default) – use subject / metadata only; do not pull the full body unless the owner asks
   - `body` – include detailed text body; still skip images
   - `body_and_images` – text body plus image fetch/description when needed
3. Text-first: never invent image content; fetch images only when the flag allows or the owner explicitly requests them.
4. Do not invent `preferred_reply_persona` for newsletters (leave null; no default reply draft).

Governance note: the auto-create / first-encounter full-body / Google Contacts merge rules are governed by the CRM node's own `<crm-node>/RULES.md`.

Search / read:

**Rule – Gmail search pagination:** Always continue pulling matching messages with `pageToken` until none remain. Do **not** stop silently after one page (e.g. 100). Default page size is 100 (`--page-size`; Gmail API max 500). Hard ask-the-owner threshold: **1000 messages**. If search hits 1000 and `nextPageToken` / `more_remain` is still true, stop, surface `needs_owner_approval_to_continue`, and **ask the owner** before continuing. Never auto-fetch past 1000 without explicit owner approval via `--i-approve-more-than-1000` (optionally `--max-total N` with N>1000 after that approval).

```powershell
# Default: paginate until exhausted (stops at 1000 and asks owner if more remain)
python shared/skills/google-workspace-access/scripts/google_gmail.py search --account example-gmail --query "is:unread"
python shared/skills/google-workspace-access/scripts/google_gmail.py search --account example-gmail --query "newer_than:7d"
# Optional sample cap (still paginates pages until this total)
python shared/skills/google-workspace-access/scripts/google_gmail.py search --account example-gmail --query "is:unread" --max-total 50
# Only after owner approves continuing past 1000:
python shared/skills/google-workspace-access/scripts/google_gmail.py search --account example-gmail --query "is:unread" --i-approve-more-than-1000
python shared/skills/google-workspace-access/scripts/google_gmail.py search --account example-gmail --query "is:unread" --i-approve-more-than-1000 --max-total 2500
# Default read: decoded JSON (id, headers, labelIds, snippet, text). Prefer text/plain; HTML-only messages are tag-stripped.
python shared/skills/google-workspace-access/scripts/google_gmail.py read --account example-gmail --message-id MESSAGE_ID
python shared/skills/google-workspace-access/scripts/google_gmail.py read --account example-gmail --message-id MESSAGE_ID --include-html
python shared/skills/google-workspace-access/scripts/google_gmail.py read --account example-gmail --message-id MESSAGE_ID --format raw
python shared/skills/google-workspace-access/scripts/google_gmail.py list-drafts --account example-gmail
```

Search JSON includes `count`, `complete`, `more_remain`, `resultSizeEstimate`, `nextPageToken`, `stopped_at_owner_threshold`, `needs_owner_approval_to_continue`, and `note`. Treat `complete: false` as partial coverage.

Create draft (CRM + confirmation):

```powershell
python shared/skills/google-workspace-access/scripts/google_gmail.py create-draft `
  --account example-gmail `
  --persona personal `
  --to someone@example.com `
  --subject "Subject" `
  --body "Body text" `
  --from-address owner@example.com `
  --confirm-target
```

Send only after the owner approves a specific draft id:

```powershell
python shared/skills/google-workspace-access/scripts/google_gmail.py send-draft `
  --account example-gmail `
  --persona personal `
  --draft-id DRAFT_ID `
  --approve-draft-id DRAFT_ID `
  --i-approve-send `
  --confirm-target
```

## Calendar

```powershell
python shared/skills/google-workspace-access/scripts/google_calendar.py list-calendars --account example-gmail
python shared/skills/google-workspace-access/scripts/google_calendar.py list-events --account example-gmail --query "standup"
python shared/skills/google-workspace-access/scripts/google_calendar.py create-event `
  --account example-gmail `
  --persona personal `
  --summary "Meeting" `
  --start 2026-08-07T10:00:00+10:00 `
  --end 2026-08-07T10:30:00+10:00 `
  --timezone Australia/Brisbane `
  --confirm-target
```

## Tasks

```powershell
python shared/skills/google-workspace-access/scripts/google_tasks.py list-lists --account example-gmail
python shared/skills/google-workspace-access/scripts/google_tasks.py list-tasks --account example-gmail
python shared/skills/google-workspace-access/scripts/google_tasks.py create-task `
  --account example-gmail `
  --persona personal `
  --title "Follow up" `
  --confirm-target
```

## Drive

```powershell
python shared/skills/google-workspace-access/scripts/google_drive.py search --account example-gmail --query "name contains 'brief' and trashed = false"
python shared/skills/google-workspace-access/scripts/google_drive.py get --account example-gmail --file-id FILE_ID
python shared/skills/google-workspace-access/scripts/google_drive.py download --account example-gmail --file-id FILE_ID --output C:\path\out.bin
```

Explicit writes only:

```powershell
python shared/skills/google-workspace-access/scripts/google_drive.py upload `
  --account example-gmail `
  --path C:\path\file.pdf `
  --i-approve-write
```

Drive files into the brain:

1. Given a URL or file ID, read its metadata directly; otherwise search with short, specific
   title terms. When several files remain plausible, show them and let the owner choose before
   treating one as canonical.
2. Fetch only what the request needs, cite the Drive title and URL, and do not keep a file
   merely because it was read.
3. For durable knowledge, keep a reproducible snapshot: record the file ID, URL, MIME type and
   modification time; export a native Google file to an open format, or download a stored file
   unchanged; ingest it through `/shared/skills/raw-file-ingestion/`; note any export fidelity
   limits; add source references, and only then promote verified facts to `KNOWLEDGE.md`.

## Contacts → Personal CRM

```powershell
# Paginate all My Contacts (People API connections.list)
python shared/skills/google-workspace-access/scripts/google_contacts.py list --account example-gmail
python shared/skills/google-workspace-access/scripts/google_contacts.py search --account example-gmail --query "Jane"
python shared/skills/google-workspace-access/scripts/google_contacts.py get --account example-gmail --resource-name people/cXXXX
# Merge one person
python shared/skills/google-workspace-access/scripts/google_contacts.py sync-to-crm `
  --account example-gmail `
  --resource-name people/cXXXX `
  --create-contact-id jane-doe `
  --i-approve-write
# Merge all listed Google Contacts into CRM (create missing; merge identifiers on match)
python shared/skills/google-workspace-access/scripts/google_contacts.py sync-all-to-crm `
  --account example-gmail `
  --i-approve-write
```

Merge identifiers (emails, phones, organisations, `google_contact_refs`) into CRM; create files for Google people not yet present. Do **not** overwrite relationship notes, reply guidance, or open loops from Google automatically. Deduplicate against email-seeded contacts by email/name so the CRM stays one coherent set.

`personFields` / `readMask` must use People API paths only (`names,emailAddresses,phoneNumbers,organizations,metadata`). Do not include `resourceName` in the mask (API returns it automatically; including it causes HTTP 400).

People API `personFields` / `readMask` must be field paths only (e.g. `names,emailAddresses,phoneNumbers,organizations,metadata`). Do **not** include `resourceName` – it is a top-level Person property returned automatically; putting it in the mask returns `HttpError 400 Invalid personFields mask path`.

## Stored tray-token access

When the tray Vault Agent is unlocked, `google_tray_token.py` loads `oauth_token_json` plus `client_id`/`client_secret` from that account vault entry through the broker. It uses the stored access token when still valid, or refreshes silently with the stored refresh token. It does **not** open a browser or run `google_connect.py`. Never print access or refresh tokens. If Google returns `invalid_grant`, the stored refresh token has been revoked; do not start a connect/browser flow unless the owner asks.

```powershell
python shared/skills/google-workspace-access/scripts/google_tray_token.py token-meta --account example-gmail
python shared/skills/google-workspace-access/scripts/google_tray_token.py calendar-search --account example-gmail --query "Exampletown"
python shared/skills/google-workspace-access/scripts/google_tray_token.py apply-event-location `
  --account example-gmail `
  --contact-id contact-jane-example `
  --query "Exampletown|Jane Example" `
  --person "Jane,Example" `
  --location-contains "Exampletown" `
  --confirm-target `
  --i-approve-write
```

`--query`, `--person` and `--location-contains` fall back to `apply_event_location` in `/memory/skills/google-workspace-access/config/tray-token.json`; with neither, the command stops and names the missing option.

Never print the access or refresh token. If Google returns HTTP 401, the stored access token has expired; do not start a connect/browser flow unless the owner asks.

## Local Gmail / Google Tasks sync

Google remains the external system of record. Normal reads should use the **local SQLite index** so agents and CLIs do not wait on live Google calls.

Architecture: Google APIs → background worker → local DB → `google_local_email.py` / `google_local_tasks.py`.

- DB default: `%LOCALAPPDATA%\PortableAIBrain\google-local-sync\sync.db` (override `GOOGLE_LOCAL_SYNC_DB`)
- Package: `scripts/google_sync/`
- Control: `google_sync_ctl.py` (`migrate`, `ensure-connection`, `backfill`, `worker`, `status`)
- Local email reads: `google_local_email.py` (`list-recent`, `search`, `get`, `thread`, `body`, `attachments`, `sync-status`, `refresh`)
- Operational tasks (not Markdown `/memory/tasks/`): `google_local_tasks.py` (`list`, `get`, `search`, `create`, `update`, `complete`, `sync-status`, `refresh`)
- Gmail push: `users.watch` + **Pub/Sub pull** in the worker (no public HTTPS webhook)
- Tasks: dedicated list title `Portable AI Brain` (configurable); outbox create/complete; poll with `updatedMin`
- Feature flags default **off** – enable explicitly; never auto-import the full mailbox at startup

### Enable and run

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
pip install -r shared/skills/google-workspace-access/requirements.txt

$env:GMAIL_LOCAL_SYNC_ENABLED = "true"
$env:GOOGLE_TASKS_SYNC_ENABLED = "true"
# Optional Pub/Sub (watch + pull). Topic must allow gmail-api-push@system.gserviceaccount.com to publish.
$env:GMAIL_PUBSUB_TOPIC = "projects/YOUR_PROJECT/topics/gmail-push"
$env:GMAIL_PUBSUB_SUBSCRIPTION = "projects/YOUR_PROJECT/subscriptions/gmail-pull"

python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-example-gmail `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_sync_ctl.py migrate

python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-example-gmail `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_sync_ctl.py backfill --account example-gmail

# Leave running while using local email/tasks
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-example-gmail `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_sync_ctl.py worker
```

Main config env vars: `GMAIL_LOCAL_SYNC_ENABLED`, `GMAIL_INITIAL_SYNC_QUERY` (default `newer_than:1y`), `GMAIL_IMPORT_IMPORTANT_HISTORY`, `GMAIL_RECONCILIATION_INTERVAL`, `GMAIL_WATCH_RENEWAL_INTERVAL`, `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_SUBSCRIPTION`, `GMAIL_STALE_THRESHOLD_SECONDS`, `GOOGLE_TASKS_SYNC_ENABLED`, `GOOGLE_TASKS_LIST_NAME`, `GOOGLE_TASKS_POLL_INTERVAL`, `GOOGLE_TASKS_UPDATED_MIN_OVERLAP`, `GOOGLE_LOCAL_SYNC_DB`.

### Tests

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python -m unittest discover -s shared/skills/google-workspace-access/scripts/google_sync/tests -v
```

Live `google_gmail.py` / `google_tasks.py` CLIs remain available; prefer local CLIs for routine list/search once sync is enabled and backfilled.

## Python reuse

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("shared/skills/google-workspace-access/scripts")))
from google_oauth import GoogleConnection

google = GoogleConnection.from_environment("example-gmail")
gmail = google.build_service("gmail", "v1")
```

## Dependencies

```powershell
pip install -r shared/skills/google-workspace-access/requirements.txt
```

## Outputs and repository updates

- Store project-specific results under the requesting node (`data/` / `sources/`).
- Record provenance: source system, time, account alias, query/scope, live/partial, transformations.
- When durable, append contact notes with message/event/task ids and account alias.
- Log material Google writes without credential material.
- Create a task when access, scope or an uncertain write needs human action.

## Failure behaviour

- Stop when the Google account alias or CRM persona/contact target is missing or ambiguous.
- Do not send mail without `--i-approve-send` and matching `--approve-draft-id`.
- Do not retry a write until checking whether the original operation succeeded.
- Surface Google errors without exposing tokens or client secrets.
- Do not claim completeness when pagination, permissions or rate limits make coverage partial.
- For Gmail `search`, if `needs_owner_approval_to_continue` is true (1000-message owner threshold), ask the owner before re-running with `--i-approve-more-than-1000`.

## Deliberate non-goals (first cut)

- delete/trash operations
- silent multi-account defaulting
- Cursor plugin/MCP Google backends
- automatic sync that overwrites CRM notes from Google
