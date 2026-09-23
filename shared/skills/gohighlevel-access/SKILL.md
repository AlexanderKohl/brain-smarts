---
name: gohighlevel-access
description: Connect the brain to a HighLevel agency through a local OAuth manager, store rotating Company tokens in the encrypted portable vault, discover approved subaccounts, derive temporary Location tokens, and run scoped API requests. Use for HighLevel or GoHighLevel agency connection, subaccount discovery, contacts, opportunities, pipelines, pipeline/stage migration review, conversations, appointments, workflows, CRM downloads, or explicitly authorised CRM writes.
metadata:
  id: skill-gohighlevel-access
  title: GoHighLevel Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: HighLevel
  skill_refs:
    - /shared/skills/manage-credentials
  created: 2026-08-04T03:31:56+10:00
  updated: 2026-09-23T12:00:00+10:00
---

# GoHighLevel Access

## Purpose

Connect one authorised HighLevel agency, rotate its OAuth credentials securely, discover approved subaccounts and provide reusable authenticated API access.

## Knowledge base

`knowledge/` holds confirmed and hypothesised non-obvious HighLevel API behaviour – per-object custom-field write/read shapes, file-field quirks, OAuth/scope edge cases, and refuted wrong-shape hypotheses worth not repeating. Before diagnosing unexpected HighLevel behaviour, search it first (`Glob`/`Grep` by object type, field type, endpoint or status – see `knowledge/_CONVENTION.md`). After resolving something genuinely non-obvious, add an entry there per root `/RULES.md`.

## Allowed operations

- Authorise and rotate the agency OAuth connection on `localhost:8766`; store rotating tokens only in the vault.
- Discover approved subaccounts and derive Location tokens in memory.
- Read Company and Location resources (contacts, opportunities, pipelines, custom fields and values, workflows, calendars, phone numbers) through the reusable client.
- Create or update a sub-account, or perform any other write, only after the owner confirms the exact target for this operation (CONTRACT §10.5).
- Run the pipeline and stage migration review UI on `localhost:8769` and apply only owner-approved migrations.
- Record non-obvious API behaviour under `knowledge/` (`RULE-2026-0022`).

## Permissions

- Treat retrievals as read-only unless the user explicitly authorises a write.
- Never delete a record, a custom object or its schema without the owner's explicit permission for that object in that confirmed sub-account; project scripts that can delete keep their own, narrower permission (see "Project scripts built on this client").
- Before any write or other side-effecting HighLevel operation, always ask which subaccount is the target (name and/or location ID), or obtain an explicit confirmation of the named subaccount for this operation; also confirm the intended change.
- Do not infer the target subaccount solely from recent chat context, the most recently used location, a project default, or an earlier session without a current confirmation for this operation.
- Require a Company agency token; reject a Location-only installation as the canonical agency connection.
- Never store client secrets, access tokens, refresh tokens or authorization codes in repository files or logs.
- Keep derived Location tokens in process memory only.
- Use the encrypted portable vault through `/shared/skills/manage-credentials/`.
- Bind the callback server to localhost and fail closed on invalid browser state, credentials, scopes, account identity or token rotation.

## Required inputs

- HighLevel Marketplace app configured for an Agency target user.
- Exact redirect URL `http://localhost:8766/oauth/callback`.
- The replacement app's generated Marketplace Installation URL.
- Vault entry `ghl-agency-oauth` containing `client_id`, `client_secret` and `oauth_token_json`.
- Agency scopes `companies.readonly` and `locations.readonly` for agency identity and paginated subaccount discovery.
- Optional legacy scopes `oauth.readonly` and `oauth.write`, when the app model exposes them, for installed-location discovery and Location-token derivation.
- Resource-specific scopes for every intended subaccount operation, for example `locations.write` to create a new sub-account.
- A requesting node, target company or location and explicit write permission when applicable.

## Store credentials

With the Vault Agent unlocked (or via interactive `put-entry`). It asks for all secret values through hidden prompts and updates the encrypted entry atomically:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry ghl-agency-oauth `
  --secret client_id `
  --secret client_secret `
  --empty-json oauth_token_json
```

Do not manually paste access or refresh tokens. The connection manager owns the rotating JSON field.

## Connect the agency

In the HighLevel app Auth pane:

1. Set the target user to Agency.
2. Add `http://localhost:8766/oauth/callback` exactly.
3. Grant `companies.readonly`, `locations.readonly` and the resource scopes required by the intended workflows. Add `oauth.readonly` and `oauth.write` only when the app model exposes them.
4. Copy the replacement app's generated Marketplace Installation URL. Supply
   it in the local manager UI or through `GHL_INSTALLATION_URL`.

Run the manager with the Vault Agent unlocked:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_connect.py
```

The manager opens `http://localhost:8766/`. Paste the Installation URL, connect as an agency administrator and approve the intended current and future subaccounts. The callback exchanges the one-use code for a Company token and atomically stores the rotating token bundle in the portable vault.

The Installation URL is held only in manager memory. The local HTTP callback is for this loopback-only private workflow. If HighLevel refuses an HTTP redirect during app configuration, stop; do not substitute a third-party callback or expose the manager publicly.

Treat the encrypted `company_profile` and `location_catalog` inside
`oauth_token_json` as the reusable subaccount cache. Do not refresh that
catalogue unless the owner explicitly asks or a requested operation proves
that a cached location is stale.

## Token lifecycle

HighLevel access tokens expire after about one day. Refresh tokens rotate on use, so the client locks the complete load-refresh-save sequence and replaces the stored bundle immediately. Use only one active refresh writer for `ghl-agency-oauth` across devices.

### If an unlocked tray agent appears unavailable

HighLevel commands use the existing tray-hosted Vault Agent through
`HighLevelConnection.from_environment()`. In a restricted execution context, the command may
incorrectly report that the Vault Agent is locked, unavailable or not running because it can see
but cannot read the current Windows user's protected broker discovery file.

When the owner says the tray is unlocked, do not ask for the passphrase and do not start another
agent. Follow `/shared/skills/manage-credentials/SKILL.md`'s "Access from a sandboxed Python
process" recovery sequence: check only whether the discovery file exists and is readable (never
display it), then retry the exact HighLevel consumer command in the approved current-user context
outside the restricted sandbox. Verify `vaultctl.py status` there if needed. The normal direct
HighLevel command remains correct; do not wrap it in a second credential session merely to work
around sandbox access.

Verified example (owner's machine): a sandboxed `ghl_subaccounts.py` invocation reported the agent unavailable while
the discovery file existed but was unreadable; the identical command in the Windows user context
immediately reused the already-unlocked tray broker and loaded the cached agency/subaccount
catalogue without another unlock.

Agency tokens have `userType=Company`. Discover agency subaccounts with `GET /locations/search` and the token's `companyId`; use `GET /companies/{companyId}` to verify the agency identity. Subaccount API calls that require a Location token remain unavailable unless the app grant supports `oauth.write`. When available, `HighLevelConnection` derives that token for the explicit location ID, validates the returned company and location, and caches it only in process memory. Location-token mint (`POST` to the oauth location-token endpoint) may return **HTTP 201** as well as 200; treat both as success (the client already does).

## Run authenticated Python

Add the skill's `scripts` directory to the import path:

```python
from ghl_oauth import HighLevelConnection

ghl = HighLevelConnection.from_environment()
status, body, headers = ghl.request(
    "GET",
    "https://services.leadconnectorhq.com/opportunities/pipelines",
    location_id="LOCATION_ID",
)
```

The client accepts authenticated URLs only on `https://services.leadconnectorhq.com/`, refreshes the Company token when required, and honours HighLevel rate-limit responses. Agency endpoints may omit `location_id`; subaccount endpoints must pass it explicitly.

## List connected subaccounts

Run with the Vault Agent unlocked:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_subaccounts.py
```

Prints the connected agency name and company ID plus every cached approved subaccount (name and location ID), using the existing `location_catalog` without calling HighLevel. Add `--refresh` to rediscover subaccounts live instead of relying on the cache.

## Create a new sub-account

Requires the `locations.write` scope on the agency app grant (not part of the default scope list above) and a HighLevel Agency Pro plan; the endpoint rejects the request otherwise. Add `locations.write` in the Marketplace app's Auth pane and reconnect the agency (see "Connect the agency" above) before first use.

Run with the Vault Agent unlocked:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_create_subaccount.py --name "Sub-account name"
```

The HighLevel API only strictly requires `name` and `companyId` to create a sub-account; `companyId` is filled in automatically from the connected agency token. Optional fields (`--phone`, `--address`, `--city`, `--state`, `--country`, `--postal-code`, `--website`, `--timezone`, `--snapshot-id`, `--prospect-first-name`, `--prospect-last-name`, `--prospect-email`) may be supplied when the owner provides them; none are required by the API. The script prints the exact payload and asks for interactive confirmation (re-typing the sub-account name) before sending the request, unless `--yes` is passed. It does not retry automatically on failure. After a successful creation, refresh the cached catalogue with `ghl_subaccounts.py --refresh` so the new sub-account appears in future listings.

## Update an existing sub-account

Same `locations.write` scope requirement as creation. Identify the target with `--location-id` or `--name` (looked up against the cached, or `--refresh-catalog`-rediscovered, subaccount catalogue):

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_update_subaccount.py --name "Sub-account name" --city "City" --state "State" --country XX --postal-code 0000 --timezone Area/City
```

Only the fields you pass are sent. Prints the exact payload and asks for interactive confirmation before sending the request, unless `--yes` is passed. Does not retry automatically on failure. When the owner has not specified a location for a new or updated sub-account, use the owner's recorded default timezone in `/memory/OWNER.md` and default location in `/memory/KNOWLEDGE.md` ("Owner context") rather than leaving it blank or guessing.

## Check phone numbers across subaccounts

Run with the Vault Agent unlocked:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_phone_numbers.py
```

Reads the cached `location_catalog` and calls `GET /phone-system/numbers/location/{locationId}` per subaccount using a derived Location token, printing each number's status, provider and type. Add `--refresh-catalog` to rediscover subaccounts first, or `--out <path>` to also save the full JSON result with provenance. Stops per-location with a recorded error rather than failing the whole run when a Location token cannot be derived (for example, missing `oauth.write`).

## Review pipeline / stage migrations

Interactive review tool for occupied opportunity stages in one explicit sub-account. Fetches pipelines and opportunities, applies the owner's known source→target stage mappings from `/memory/skills/gohighlevel-access/data/opportunity-stage-mappings.json` (found through brain-root discovery; override with `--mappings-file`), serves a local review UI for unmapped stages, and can apply confirmed moves (including invalid assigned-user replacements). A missing mappings file stops the run with an error, as before; the mappings are owner data and never live in this skill.

Auth uses the existing agency connection only (`HighLevelConnection.from_environment()` + Location token for the chosen `--location-id` / `--name`). There is no `--token` flag and no Private Integration Token path. Note: `GET /opportunities/search` requires query param `location_id` (snake_case); pipelines/users still use `locationId`.

Defaults:

- Review UI: `http://127.0.0.1:8769/` (port **8769**; 8765–8768 are reserved elsewhere in this brain)
- Output: `/temp/ghl-migration-output/` under the brain root (`migration-summary.json`, `apply-results.json`); override with `--output-dir`

Require an explicit target sub-account on every run. Example only (fictional, not a default): Example Plumbing Pty Ltd (`loc_EXAMPLE123`).

Run from the brain root (the folder holding `/CONTRACT.md`; the owner's path is `brain_root` in `/memory/OWNER.md`) with the Vault Agent unlocked:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_review_pipeline_migrations.py `
  --location-id loc_EXAMPLE123
```

Or resolve by cached catalogue name:

```powershell
python shared/skills/gohighlevel-access/scripts/ghl_review_pipeline_migrations.py `
  --name "Example Plumbing Pty Ltd"
```

If the Vault Agent is not unlocked, inject static OAuth app fields for one run:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry ghl-agency-oauth `
  --map GHL_CLIENT_ID=client_id `
  --map GHL_CLIENT_SECRET=client_secret `
  -- python shared/skills/gohighlevel-access/scripts/ghl_review_pipeline_migrations.py `
  --location-id loc_EXAMPLE123
```

Leave the process running while you review and apply moves in the browser; Ctrl+C stops the local server. Applying moves is a write – confirm the target sub-account and intended mappings with the owner first.

## Project scripts built on this client

Project-specific HighLevel automation (data-plane setup for one product, writers into a project's own custom object, test runners) does not live in this shared skill. It lives with its project – in the memory layer under `/memory/projects/<project>/skills/<skill>/` or in the project's own repository – and imports this skill's `ghl_oauth` client by locating the brain root (walk up to `CONTRACT.md`) and adding `shared/skills/gohighlevel-access/scripts` to the import path. Such scripts inherit every permission rule above and add none.

## Custom object data-plane lessons (live-verified)

These lessons came from building a multi-object data plane (Custom Values, Contact custom fields, Custom Object schemas and fields, Associations, seed records and a technical user) in one orchestrated pass. They hold for any script that does the same; do not regress them:

| Lesson | Requirement |
| --- | --- |
| Custom Object fields | Custom Fields V2 `POST /custom-fields/` with Version header **`v3`**; body: `locationId`, `fieldKey` (`{schemaKey}.{slug}`), `objectKey`, `parentId` (folder id), `showInForms`, `dataType` – **no `model`** (HTTP 422) |
| Field parent | `parentId` must be a custom-fields **folder** id from `GET /custom-fields/object-key/{objectKey}` (create a "Fields" folder if none); never the schema id |
| CHECKBOX fields | Contact and object CHECKBOX creates need non-empty `options` (e.g. `["Yes"]`) |
| Schema description | Max **100** characters on create and update |
| Schema update | `PUT /objects/{key}` needs non-empty `searchableProperties` |
| Schema key | Resolve each schema's live `schemaKey` after create; HighLevel may suffix a key to keep it unique, and it always starts with `custom_objects.` |
| Record search | `POST .../records/search` requires `page` or `searchAfter` (send `page`/`pageLimit`/`query`) |
| CHECKBOX record values | Values must be option-label lists like `["Yes"]`, not booleans |
| Technical user password | `POST /users/` (CreateUserDto) needs length >12 with upper, lower, digit and a special from `!@#$%^&*`; `secrets.token_urlsafe` alone fails because `-`/`_` are not accepted as special. Never print or store it |
| Technical user role | Create with role `user` (not `admin`) and every permission toggle False |
| User `locationIds` | Reconcile with a Company-token `PUT /users/{userId}` (a Location token gets 401). HTTP 400 `The company does not have access to this feature` can occur: save what depends on the user id and have the owner assign the user to the sub-account in the HighLevel UI |
| Location token | Mint may return HTTP **201**; accept 200 and 201 |
| Custom Values folder | The Create Custom Value endpoint has no folder parameter; placing values in a folder is a **manual UI** step after API setup |

Idempotence pattern that held up: every step only adds what is missing (checked by name or key against the live sub-account first), supports `--dry-run` (prints every payload, no network call, works before the sub-account or credentials exist) and `--yes`, stops the orchestrator at the first failed step, and never deletes.

### Endpoint verification summary

Confirmed against HighLevel's marketplace developer docs (`marketplace.gohighlevel.com/docs`) and the community-maintained markdown mirror of that same source; the legacy `highlevel.stoplight.io` docs are deprecated and were not used. A live data-plane build on a test sub-account further hardened the Custom Fields V2, record-search, schema-update, CHECKBOX and user-password rows.

| Area | Endpoint(s) | Version header |
| --- | --- | --- |
| Custom Values | `GET/POST /locations/{locationId}/customValues`, `PUT/DELETE .../{id}` | `2021-07-28` |
| Contact custom fields | `GET/POST /locations/{locationId}/customFields`, `PUT/DELETE .../{id}` (`model: contact`; CHECKBOX needs non-empty `options`) | `2021-07-28` |
| Custom Object schemas | `GET /objects/` (list), `POST /objects/` (create; description ≤100 chars), `GET/PUT /objects/{key}` (`PUT` needs non-empty `searchableProperties`) | `2021-07-28` |
| Custom Object fields | `POST /custom-fields/` (Custom Fields V2: `locationId`, `objectKey`, `fieldKey`, `parentId`, `showInForms`, `dataType` – do **not** send `model`); `GET /custom-fields/object-key/{objectKey}`; `POST /custom-fields/folder` | `v3` |
| Custom Object records | `POST /objects/{schemaKey}/records`, `POST .../records/search` (**requires `page` or `searchAfter`**), `GET/PUT/DELETE .../records/{id}` | `2021-07-28` |
| Associations | `POST /associations/` (define), `POST /associations/relations` (link records), `GET /associations/objectKey/{objectKey}` | `2021-07-28` |
| Users | `POST /users/` (password: >12 chars, upper/lower/digit/special from `!@#$%^&*`), `GET /users/search`, `GET/PUT /users/{userId}` | `2021-07-28` |
| Location token mint | OAuth location-token `POST` (accept **200 or 201**) | oauth |
| Contact tasks | `POST/GET /contacts/{contactId}/tasks`, `PUT/DELETE .../{taskId}`, `PUT .../{taskId}/completed` | `2021-07-28` |
| Task search (location-wide) | `POST /locations/{locationId}/tasks/search` – the only cross-contact task read; returns **201**, `limit` up to 500, `searchAfter` pagination. Not in `openapi/contacts-v3.json`; every `/contacts/`-prefixed search path 404s. See `knowledge/task--search--location-endpoint-not-in-snapshots.md` | any |

Required `CreateCustomFieldsDTO` body (from `/shared/skills/gohighlevel-access/openapi/custom-fields-v3.json`): `locationId`, `showInForms`, `dataType`, `fieldKey`, `objectKey` (the live `custom_objects.*` key) and `parentId` (a folder id only). Verify the first live field in the HighLevel UI after a new build.

## Deleting a custom object through the API

A custom object schema is deleted by **`DELETE /objects/<objectId>`** on the services host, which is in no specification but was captured live from the HighLevel interface (`knowledge/custom_object--schema-delete--by-object-id-on-services-host.md`). The object is addressed by its id, never by its key: read the schema first and use the id only when that schema's key is the one intended. One call takes the fields and the associations with it. Records go first through `DELETE /objects/<key>/records/<id>` (in the vendored specification, sent without `locationId`). Deleting records or objects is destructive and needs the owner's explicit permission for that object in that confirmed sub-account.

## OpenAPI reference snapshots

Downloaded HighLevel Marketplace OpenAPI 3.0 snapshots used to ground request shapes live under `/shared/skills/gohighlevel-access/openapi/` (see that folder's README). They are API documentation, not live CRM exports. Prefer these files when verifying DTO required fields; keep project-specific live results under the requesting node.

## Data sources and outputs

The authoritative sources are the HighLevel OAuth and API endpoints. Store project-specific results under the requesting node and record:

- source system: HighLevel
- retrieval timestamp
- company and location identifiers
- endpoint, operation, filters and granted-scope limitations
- live, cached, complete or partial coverage
- transformations and response hash
- requesting node

Do not store token payloads in result or provenance files.

## Failure behaviour

- Stop if the callback URL differs, browser state is invalid or the authorization code is missing.
- Stop if HighLevel returns anything other than a Company token for the agency connection.
- Stop if refresh returns another company, omits the replacement refresh token or cannot be saved atomically.
- Stop if a Location token does not match the requested company and location.
- Send the brain's named integration User-Agent on every HighLevel request; HighLevel's Cloudflare policy rejects Python's default `Python-urllib` signature with Error 1010.
- Do not retry uncertain writes until the authoritative CRM record is reconciled.
- Do not claim complete subaccount coverage when scopes, installation choices, pagination or endpoint availability make it partial.
- Clear local tokens only when explicitly requested; uninstall the app in HighLevel to revoke server-side access.

## Repository updates

Log material CRM writes and resulting state changes without credential material. Update the requesting project's state when current CRM reality changes. Create a task for missing scopes, reauthorisation, suspected disclosure, token-rotation conflict, ambiguous target location or uncertain writes.

## Tests

`python -m unittest discover -s shared/skills/gohighlevel-access/scripts/tests` (no network; a fake opener answers every request).
