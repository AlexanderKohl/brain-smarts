---
name: railway-access
description: Fetch Railway project, deployment, and log data via the public GraphQL API using a vault-stored account or workspace API token. Use when agents need current deployment IDs, timeframe-bounded deploy/build/HTTP logs, or Railway log filters without per-project authentication.
metadata:
  id: skill-railway-access
  title: Railway Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: Railway
  canonical_source: /shared/skills/railway-access
  docs_url: https://docs.railway.com/integrations/api
  skill_refs:
    - /shared/skills/manage-credentials
  project_refs:
    - /memory/projects/credential-management
  created: 2026-08-22T09:47:41+10:00
  updated: 2026-09-23T13:47:16+10:00
---

# Railway Access

## Purpose

Call Railway’s public GraphQL API to list projects/services/environments, resolve the current (or latest) deployment ID, and fetch point-in-time deploy, build, or HTTP logs for a deployment with optional timeframe and Railway filter syntax.

Credentials live only in the encrypted portable vault and are injected into authorised child processes through the tray Vault Agent.

## Auth model (owner choice)

| Mechanism | Scope | Brain recommendation |
|---|---|---|
| **Account token** | All resources you can access across workspaces | **Preferred for this skill** – one vault entry covers every project |
| **Workspace token** | All projects in one workspace | Prefer when work is confined to one team workspace |
| **Project token** | One environment in one project | Avoid for brain-wide log access; would need one vault entry per project/environment |
| **OAuth (“Login with Railway”)** | Only workspaces/projects the user selects at consent | Possible for third-party apps, **not** automatic all-project access; requires registering an OAuth app and rotating refresh tokens |

You do **not** need to authenticate per project if you store one account token (or one workspace token for that workspace). OAuth does not give “all projects by default”; consent is selective.

Create an account or workspace token at https://railway.com/account/tokens (account token = select “No workspace”).

## Usage guidance

- Before querying, resolve which project/service/environment/deployment and time window actually match what the owner is asking about – do not default to "whatever session is most recent in this conversation" when it could be ambiguous (multiple recent test sessions, multiple subaccounts/locations, an unstated time window). If it isn't clear, ask the owner rather than guessing and presenting a confidently-wrong answer built on the wrong session's logs.
- Record a project's Railway project/service/environment IDs in that project's `STATE.md` once resolved (a short table of project, service and environment ids per environment is the pattern) so a later session doesn't have to re-run `railway_projects.py` to rediscover them. Deployment IDs churn on every deploy and are not worth persisting the same way – re-resolve those live with `--latest`.

## Allowed operations

- List projects, services, environments and deployments; resolve the current or latest deployment id.
- Fetch deploy, build and HTTP logs for a deployment with timeframe and filter syntax.
- Store the API token in the vault through `/shared/skills/manage-credentials/`.
- No mutations: no deploy, restart, rollback, variable or domain changes in this first cut.

## Data sources

- Railway public GraphQL API at `https://backboard.railway.com/graphql/v2`.
- Vault entry `railway-api` (token) and `/memory/projects/credential-management/data/credential-registry.json` (non-secret registry).
- Outputs under `/temp/railway-access/` or the requesting node, with retrieval time and scope.

## Permissions

- Read-only GraphQL queries for projects, deployments, and logs in this first cut (no deploy/restart/rollback mutations).
- Never commit the API token, paste it into governance docs, or print the full value in logs.
- Store the token only via `/shared/skills/manage-credentials/`.
- Fail closed when the token is missing or Railway returns auth errors.
- Prefer vault injection (`vault_credentials.py run` / `vaultctl.py run`) over ambient shell env left after the chat ends.
- Do not place `PORTABLE_VAULT_PASSPHRASE` in child environments.

## Required inputs

| Item | Value |
|---|---|
| Vault entry | `railway-api` |
| Vault field | `api_token` |
| Env (injected) | `RAILWAY_API_TOKEN` |
| Optional env | `RAILWAY_VAULT_ENTRY`, `RAILWAY_VAULT_FIELD` |
| API endpoint | `https://backboard.railway.com/graphql/v2` |
| Docs | https://docs.railway.com/integrations/api |

Registry (non-secret): `/memory/projects/credential-management/data/credential-registry.json`.

## Store the token

With the tray Vault Agent unlocked (grey→red; owner unlocks once), from the brain root (the folder holding `/CONTRACT.md`; the owner's path is `brain_root` in `/memory/OWNER.md`):

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry railway-api `
  --secret api_token
```

Do **not** put the token on the command line. Agents may show only the **last 4 characters** for confirmation.

## Run (authorised consumers)

From the brain root:

```powershell
# List projects (loads via workspaces – top-level Railway `projects` is empty)
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry railway-api `
  --map RAILWAY_API_TOKEN=api_token `
  -- python shared/skills/railway-access/scripts/railway_projects.py --include-details

# Optional: list workspaces only
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry railway-api `
  --map RAILWAY_API_TOKEN=api_token `
  -- python shared/skills/railway-access/scripts/railway_projects.py --list-workspaces

# Resolve current / recent deployments for a service
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry railway-api `
  --map RAILWAY_API_TOKEN=api_token `
  -- python shared/skills/railway-access/scripts/railway_deployments.py `
       --project-id <PROJECT_ID> `
       --service-id <SERVICE_ID> `
       --environment-id <ENVIRONMENT_ID> `
       --limit 5

# Fetch deploy logs for a deployment (timeframe + filter)
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry railway-api `
  --map RAILWAY_API_TOKEN=api_token `
  -- python shared/skills/railway-access/scripts/railway_logs.py `
       --deployment-id <DEPLOYMENT_ID> `
       --since 1h `
       --filter "@level:error" `
       --limit 200
```

IDs: in the Railway dashboard press `Ctrl+K` and copy Project / Service / Environment / Deployment ID.

## Scripts

| Script | Role |
|---|---|
| `scripts/railway_client.py` | Resolve token, GraphQL POST, fail closed |
| `scripts/railway_projects.py` | List projects (and nested services/environments when requested) |
| `scripts/railway_deployments.py` | List recent deployments; optionally emit the latest successful ID |
| `scripts/railway_logs.py` | Point-in-time deploy / build / HTTP logs with `--since` / `--until` / `--filter` / `--limit` |

## Log CLI options

| Flag | Meaning |
|---|---|
| `--deployment-id` | Required deployment UUID (or use `--latest` with project/service/environment IDs) |
| `--latest` | Resolve the most recent successful deployment for the given service/environment, then fetch logs |
| `--project-id` / `--service-id` / `--environment-id` | Required with `--latest` |
| `--kind` | `deploy` (default), `build`, or `http` |
| `--since` / `--until` | Relative (`30s`, `5m`, `2h`, `1d`, `1w`) or ISO-8601. For `deploy`/`build` these become `startDate`/`endDate`; for `http` they become `afterDate`/`beforeDate`, because `httpLogs`'s own `startDate`/`endDate` are deprecated no-ops |
| `--filter` | Railway filter syntax (e.g. `@level:error`, `"rate limit"`, `AND` / `OR` / `-`) |
| `--limit` | Max log lines (API `limit`) |

This skill fetches **historical / point-in-time** logs over HTTP. Live WebSocket streaming is out of scope for the first cut.

**`--kind http` currently returns nothing.** When last probed (the knowledge entry records the date), a correctly
formed, authorised `httpLogs` query returned an empty list for every service on the account tested,
including a live production site – no error, just `count: 0`. Do not read that emptiness as "the service received
no requests"; use `--kind deploy` to reason about traffic. See
`knowledge/general--http-logs--empty-for-account.md` for the probes and the open question.

## Log shape (`deploy`/`build`)

Each row is `{ timestamp, message, severity, attributes }`. `attributes` is Railway's structured
log metadata as `[{ key, value }]` – for an app that logs structured events (e.g. a request/
response line where `message` is just the event name, like `api_response`), the actual
payload lives in `attributes`, not `message`. Confirmed live: a consuming app's own JSON payload
can itself be **double-JSON-encoded** inside one attribute's `value` (a JSON string containing
another JSON string) – `json.loads()` it twice, not once, before reading further. Without
`attributes`, structured app logs are close to useless (every row reads as an opaque event name
with no data). `httpLogs` already returned a richer shape natively and is unaffected.

## Outputs

- JSON on stdout (projects, deployments, or `{ query, logs }` – `logs` includes `attributes` for
  `deploy`/`build`).
- No plaintext token in repository files or governance logs.
- Optional non-secret temp copies under `/temp/railway-access/` only when a caller explicitly writes them there.

## Failure behaviour

- Missing/empty `RAILWAY_API_TOKEN` → exit non-zero; do not call Railway.
- HTTP 401/403 or GraphQL auth errors → fail closed; do not invent a replacement token.
- Ambiguous `--latest` (no deployments) → exit non-zero with a clear JSON error.
- Rate limits → surface Railway’s error/headers; do not busy-loop.

## Repository updates

When this skill is added or the vault alias changes: update `/ONBOARDING_AGENT.md`, `/shared/skills/README.md`, and the credential registry. Append a non-secret note to `/memory/projects/credential-management/LOG.md` when the entry is first stored.
