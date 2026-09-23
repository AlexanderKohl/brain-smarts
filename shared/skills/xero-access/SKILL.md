---
name: xero-access
description: Connect to any Xero organisation authorised through OAuth, select the active organisation, run authenticated Python code against the Xero API, and download live Xero data with provenance metadata. Use for Xero organisation connection, account, contact, invoice, bill, transaction, balance, report, attachment, or other authorised Xero API retrieval work; use write operations only when the user explicitly authorises them.
metadata:
  id: skill-xero-access
  title: Xero Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: Xero
  canonical_source: /shared/skills/xero-access
  skill_refs:
    - /shared/skills/manage-credentials
  created: 2026-08-04T03:31:56+10:00
  updated: 2026-09-23T13:47:16+10:00
---

# Xero Access

## Purpose

Connect the Portable AI Brain to any Xero organisation authorised by the user, select the intended organisation, and retrieve data through reusable authenticated code.

## Allowed operations

- Authorise a Xero organisation on `localhost:8765` with selectable scope groups; store rotating tokens in the vault.
- Select the target organisation by tenant id from the registry, or ask.
- Download live data (chart of accounts, contacts, invoices and other read endpoints) to a destination under the requesting node, with provenance.
- Create planned accounts or a planned draft invoice, and run custom authorised Python, only with explicit owner authorisation for that write.

## Data sources

- Xero Accounting API for the authorised organisation and granted scopes.
- The owner's Xero organisation registry (tenant ids and persona links), located by `/memory/skills/xero-access/NOTES.md`, and `/memory/projects/credential-management/data/credential-registry.json`.
- Vault entry `xero-oauth`; any capability snapshots the owner keeps, located by `/memory/skills/xero-access/NOTES.md`.

## Permissions

- Treat retrievals as read-only unless the user explicitly authorises a write operation.
- Confirm the target organisation and intended change before a write.
- Never store client secrets, access tokens, refresh tokens, or private certificates in the repository.
- Use `/shared/skills/manage-credentials/` to inject static credentials and store rotating tokens in the passphrase-encrypted portable vault.
- Fail closed when credentials, scopes, organisation selection, or authorisation are missing.
- Follow the current agent or execution environment's approval rules before network access, package installation, browser launch, or external writes.

## Required inputs

- The requested Xero operation and scope.
- The requesting Portable Brain node, such as `/memory/projects/example`.
- An authorised Xero organisation.
- A destination path for downloaded data.
- Explicit write authorisation for any operation that changes Xero.

## Connect an organisation

Create an Auth Code app in the Xero developer portal with this exact redirect URI:

```text
http://localhost:8765/oauth/callback
```

Store `client_id`, `client_secret`, and the OAuth JSON field in the portable vault as defined by `/memory/projects/credential-management/data/credential-registry.json`. Configure only these non-secret runtime settings:

```powershell
$env:XERO_TOKEN_STORE = "vault"
$env:XERO_VAULT_ENTRY = "xero-oauth"
$env:XERO_VAULT_FIELD = "oauth_token_json"
$env:XERO_REDIRECT_URI = "http://localhost:8765/oauth/callback"
```

Ensure the Portable Vault tray icon is present and unlocked (red; `vaultctl status` may be used to confirm). Run Xero commands with mapped-field injection via `vaultctl run` / `vault_credentials.py run`; OAuth token refresh uses that same tray-hosted broker and does not require a chat-long PowerShell session.

By design, the connector supports every current standard organisation scope, but requests them in compatible profiles. Xero may reject one combined request with `invalid_scope` when the app is not enabled for an optional product.

The default Accounting profile includes all current granular transaction, report, settings, contact, attachment and budget scopes available without extra certification. In the manager, tick one or more Accounting, identity, Payroll, Files, Assets, Projects and eInvoicing groups, then submit one combined authorization request. The manager deduplicates shared scopes.

If a combined selection returns `invalid_scope`, retry with fewer groups to isolate the unavailable product. A failed authorization does not replace or invalidate previously granted scopes.

The default deliberately excludes:

- deprecated broad accounting scopes
- Practice Manager scopes, which require a separate tenant-type authorisation
- non-tenanted scopes, which require the Client Credentials grant
- payment-services, bank-feed, Finance API and journal scopes that require additional certification or commercial approval

An organisation's subscription and the Xero app's eligibility may still limit particular APIs. Record successful grants from the token response; do not infer them from the requested set. Broad OAuth consent does not authorise the skill to perform writes: every external write still requires the user's explicit instruction and target confirmation.

Use the credential skill to inject the static fields into the connection manager:

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry xero-oauth `
  --map XERO_CLIENT_ID=client_id `
  --map XERO_CLIENT_SECRET=client_secret `
  -- python shared/skills/xero-access/scripts/xero_connect.py
```

Open the local manager at `http://localhost:8765/`:

| Action | How |
|---|---|
| Set the active organisation | Choose an existing org in the **Organisation** dropdown, then **Save selection** |
| Connect another organisation | Choose **Add Organisation…** in the same dropdown (starts OAuth with Accounting scopes; on Xero’s consent screen, tick the additional org(s)) |
| Add scope groups for the current connection | Tick groups under **Add scope groups for …**, then **Authorise selected groups for this organisation** – this is for scopes, not for adding orgs |

Treat only scopes returned in the token as granted. Xero’s consent UI may still show every organisation already linked to the app; that is expected platform behaviour.

With `XERO_TOKEN_STORE=vault`, token exchange and refresh atomically replace `oauth_token_json` inside the authenticated encrypted vault. The legacy file backend remains available only when `XERO_TOKEN_STORE=file`; it must not be used for newly configured Portable AI Brain credentials.

## Download live data

Use the downloader for arbitrary read-only Xero Accounting API resources:

```powershell
python scripts/xero_download.py --resource Invoices --query "where=Status==`"AUTHORISED`"" --output <brain-root>\memory\projects\example\data\xero-invoices.json --requesting-node /memory/projects/example
```

Use `--url` instead of `--resource` for another endpoint hosted on `api.xero.com`. Use `--tenant-id` to select a particular connected organisation. Run `python scripts/xero_download.py --help` for all options.

The downloader writes the response and an adjacent `.metadata.json` file. It refuses to overwrite either file unless `--force` is supplied.

## Create planned accounts

Use `scripts/xero_create_accounts.py` only after the user explicitly approves the target organisation and complete account plan:

```powershell
python scripts/xero_create_accounts.py `
  --plan C:\path\approved-account-plan.json `
  --result C:\path\account-creation-result.json `
  --requesting-node /memory/projects/example
```

The script validates all plan entries, selects the declared tenant, reads the current chart, and refuses every write if a code or name conflicts. It skips exact existing matches, creates missing accounts one at a time, verifies each response, reconciles uncertain results with a fresh read, and stops without retrying when an outcome cannot be proven. Preserve the result file as the write audit record.

## Run custom Python

Add the skill's `scripts` directory to the import path, then reuse the auto-refreshing client:

```python
from xero_oauth import XeroConnection

xero = XeroConnection.from_environment()
status, body, headers = xero.request(
    "GET",
    "https://api.xero.com/api.xro/2.0/Contacts",
)
```

`request()` supplies the selected `Xero-tenant-id`, refreshes expired access tokens, spaces requests, and honours Xero `429 Retry-After` responses. For custom downloads, record the same provenance fields produced by `xero_download.py`.

## Create a planned draft invoice

Use `scripts/xero_create_draft_invoice.py` only after the user approves the target tenant, contact, tax basis and complete line plan:

```powershell
python scripts/xero_create_draft_invoice.py `
  --plan C:\path\approved-draft-invoice-plan.json `
  --result C:\path\draft-invoice-result.json `
  --requesting-node /memory/projects/example
```

The writer requires `DRAFT` `ACCREC`, a stable idempotency reference and an expected total. It verifies the accounts, refuses account differences, and uses the existing exact contact. When the approved plan sets `CreateContactIfMissing` to `true`, it may create one minimal name-only contact and reconcile the result before continuing. It reconciles an existing exact invoice reference, performs at most one invoice-create request, retrieves the invoice by ID, and verifies its status, contact, line items and total. It never emails or authorises the draft.

## Outputs and repository updates

Store project-specific results under the requesting project's `data/` or `sources/` area. Record:

- source system and API URL
- retrieval time
- tenant or organisation identifier
- requesting node
- query and scope
- live, cached, complete, or partial status
- transformations
- response hash

Log material Xero writes and any resulting state change. Include the target tenant, approved plan, verified results and timestamp without credential material. Create a task when access, scope, data quality, or an uncertain write result requires human action.

## Failure behaviour

- Do not claim completeness when pagination, permissions, filters, or rate limits make coverage partial.
- Do not retry a write until checking whether the original operation succeeded.
- Stop when the selected organisation is ambiguous.
- Surface Xero and connection errors without exposing tokens or client secrets.
