---
name: abr-access
description: Look up Australian Business Numbers (ABN), Australian Company Numbers (ACN), and entity names via the free ABR ABN Lookup JSON web services using a vault-stored authentication GUID. Use whenever an ABN must be validated or found by name (e.g. Example Plumbing Pty Ltd), or when integrating ABR data into brain workflows.
metadata:
  id: skill-abr-access
  title: ABR ABN Lookup Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: Australian Business Register (ABN Lookup)
  canonical_source: /shared/skills/abr-access
  docs_url: https://abr.business.gov.au/Tools/WebServices
  skill_refs:
    - /shared/skills/manage-credentials
    - /shared/skills/google-workspace-access
  project_refs:
    - /memory/projects/credential-management
  created: 2026-08-06T13:20:00+10:00
  updated: 2026-09-23T12:00:00+10:00
---

# ABR ABN Lookup Access

## Purpose

Call the Australian Business Register (ABR) **ABN Lookup web services** to validate ABNs, resolve ACNs, and search by entity/business name. Authentication is a free registration **GUID** emailed by ABR after accepting the web services agreement at [ABN Lookup Web Services](https://abr.business.gov.au/Tools/WebServices).

This skill uses the limited JSON endpoints documented at https://abr.business.gov.au/json/ (JSONP). SOAP/WSDL remains available from ABR but is not required for name/ABN/ACN lookups in this first cut.

## Allowed operations

- Look up an ABN, resolve an ACN to its ABN record, and search entities by name against the ABR ABN Lookup JSON endpoints listed under "JSON endpoints used".
- Store or import the registration GUID into the encrypted vault through `/shared/skills/manage-credentials/`.
- Write lookup results only to the requesting node or `/temp/abr-access/`. Nothing is ever written to ABR.

## Permissions

- Read-only against ABR Lookup (no update APIs exist on these services).
- Never commit the authentication GUID, paste it into governance docs, or print the full value in logs.
- Store the GUID only in the encrypted portable vault via `/shared/skills/manage-credentials/`.
- Fail closed when the GUID is missing, malformed, or rejected by ABR.
- Prefer vault injection (`vault_credentials.py run`) over ambient environment variables left in a shell after the chat ends.

## Required inputs

| Item | Value |
|---|---|
| Vault entry | `abr-webservices-guid` |
| Vault field | `authentication_guid` |
| Env (injected) | `ABR_AUTHENTICATION_GUID` |
| Optional env | `ABR_VAULT_ENTRY`, `ABR_VAULT_FIELD` |
| Docs | https://abr.business.gov.au/Tools/WebServices |
| JSON samples | https://abr.business.gov.au/json/ |

Registry (non-secret): `/memory/projects/credential-management/data/credential-registry.json`.

## Store the GUID

With the Vault Agent unlocked (owner unlocks once, then enters the GUID via hidden prompt):

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry abr-webservices-guid `
  --secret authentication_guid
```

Do **not** put the GUID on the command line. For confirmation only, agents may show the **last 4 characters** of the GUID to the owner.

### Import from Gmail (owner bootstrap)

If the GUID was emailed years ago (typical ABR registration mail), search the owner's Gmail account and store without printing the full value. The owner's account alias, search queries and mailbox noise pattern are owner configuration at `/memory/skills/abr-access/config/gmail_import.json` (fields `default_account`, `default_queries`, `focused_queries`, `noise_subject_pattern`); the script finds it through brain-root discovery and otherwise uses generic queries and requires `--account`:

```powershell
# Prefer the helper under temp/abr-access or launch via Start-Process so the owner can enter the passphrase.
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-<account-alias> `
  --map GOOGLE_CLIENT_ID=client_id `
  --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/abr-access/scripts/abr_import_guid_from_gmail.py --account <account-alias>
```

Set non-secret Google runtime env (`GOOGLE_TOKEN_STORE=vault`, `GOOGLE_ACCOUNT_ALIAS=<account-alias>`, etc.) as in `/shared/skills/google-workspace-access/SKILL.md`. Prefer an unlocked Vault Agent so the import script writes `abr-webservices-guid#authentication_guid` through the broker. Result JSON under `/temp/abr-access/` records only subjects, message ids, and GUID tails.

## Run lookups

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry abr-webservices-guid `
  --map ABR_AUTHENTICATION_GUID=authentication_guid `
  -- python shared/skills/abr-access/scripts/abr_search_name.py `
       --name "Example Plumbing Pty Ltd" --max-results 20

python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry abr-webservices-guid `
  --map ABR_AUTHENTICATION_GUID=authentication_guid `
  -- python shared/skills/abr-access/scripts/abr_lookup.py --abn <11-digit ABN>

python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry abr-webservices-guid `
  --map ABR_AUTHENTICATION_GUID=authentication_guid `
  -- python shared/skills/abr-access/scripts/abr_lookup.py --acn <9-digit ACN>
```

## JSON endpoints used

| Operation | Path |
|---|---|
| ABN | `https://abr.business.gov.au/json/AbnDetails.aspx?abn=…&callback=callback&guid=…` |
| ACN | `https://abr.business.gov.au/json/AcnDetails.aspx?acn=…&callback=callback&guid=…` |
| Name | `https://abr.business.gov.au/json/MatchingNames.aspx?name=…&maxResults=…&callback=callback&guid=…` |

Responses are JSONP (`callback({…})`); scripts strip the wrapper and emit plain JSON on stdout.

## Scripts

| Script | Role |
|---|---|
| `scripts/abr_client.py` | Shared client: resolve GUID, HTTP GET, JSONP parse, fail closed |
| `scripts/abr_lookup.py` | CLI: `--abn` or `--acn` |
| `scripts/abr_search_name.py` | CLI: `--name` / `--max-results` |
| `scripts/abr_import_guid_from_gmail.py` | One-time/bootstrap: find GUID in Gmail, store in vault |

## Outputs

- JSON on stdout for lookup/search (entity names, ABN/ACN, status, addresses as returned by ABR).
- Non-secret import result under `/temp/abr-access/` (gitignored via `/temp/`).
- No plaintext GUID in repository files.

## Failure behaviour

- Missing/malformed GUID → exit non-zero; do not call ABR with a placeholder.
- ABR message such as “GUID entered is not recognised as a Registered Party” → surface in JSON; do not invent a replacement GUID.
- If Gmail import finds zero or multiple distinct GUIDs, stop and ask the owner (unless `--store-first` was explicitly requested for a single chosen candidate). Prefer `--focused` or rely on ranking that boosts `ABNLookup.Support` / ServiceNow registration subjects and demotes the subjects the owner's `noise_subject_pattern` names. The owner's confirmed GUID (tail only) and its source are recorded in `/memory/skills/abr-access/NOTES.md`.

## Repository updates

When this skill is added or the vault alias changes: update `/ONBOARDING_AGENT.md`, `/shared/skills/README.md`, and the credential registry. Append a non-secret note to `/memory/projects/credential-management/LOG.md` when the entry is first stored. Record verified ABNs (never the GUID) in the relevant memory-layer project `KNOWLEDGE.md` / persona files.
