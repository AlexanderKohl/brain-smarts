---
name: manage-credentials
description: Create and operate the Portable AI Brain's self-contained passphrase-encrypted credential vault via a per-login Vault Agent broker, inject selected static secrets into authorised child processes without exporting the master passphrase, and provide reusable authenticated JSON storage for rotating OAuth tokens. Use when Codex needs to initialise, retrieve, pass, rotate, audit, or troubleshoot passwords, API keys, client secrets, access tokens, refresh tokens, OAuth state, or other integration credentials without Windows Credential Manager, LastPass, or committed secrets.
metadata:
  id: skill-manage-credentials
  title: Credential Management
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  project_ref: /memory/projects/credential-management
  created: 2026-08-04T16:11:53+10:00
  updated: 2026-10-01T12:01:44+10:00
---

# Credential Management

## Purpose

Operate one portable encrypted credential vault without an external secret service. The recovery passphrase is the only unlock factor and must never be stored in the repository, vault, scripts, command arguments, logs, persistent environment configuration, or child-process environments.

Runtime unlock is held by the **per-login Vault Agent**. Applications receive scoped results through the local broker (normally mapped static fields or OAuth JSON load/save). Closing PowerShell does not revoke OAuth grants; those remain encrypted in the vault.

## Allowed operations and permissions

Read `/memory/projects/credential-management/RULES.md` before changing credential storage.

- Initialise and authenticate the approved vault.
- Start, unlock and lock the Vault Agent.
- Add or replace fields through hidden input or standard input from an authorised producer.
- Inject selected text fields only into an authorised child process (never the master passphrase).
- Read and atomically replace rotating JSON credentials through `BrokerOAuthStore` / `PortableVaultJsonStore` via the agent.
- Change the vault passphrase after authenticating with the current passphrase.
- Log aliases and results only; never expose values or decrypted payloads.

## Required inputs

- The recovery passphrase, entered interactively by the owner through a hidden prompt; never as an argument, a file or an environment variable.
- The vault path: `/memory/projects/credential-management/data/credentials.vault` by default (the scripts find the brain root by walking up to `CONTRACT.md`), or `--vault` / `PORTABLE_VAULT_PATH`.
- For each operation: the entry name and field names from the credential registry, and for consumers the `--map ENV=field` list and the command to run.
- The `cryptography` Python package.

## Data sources

- The encrypted vault file, the only store of secret values, excluded from Git.
- `/memory/projects/credential-management/data/credential-registry.json` for non-secret entry and field names.
- The per-login Vault Agent broker for unlocked reads and rotating-JSON writes.

## Cryptographic design

`scripts/portable_vault.py` derives a 256-bit key from the recovery passphrase using scrypt with `N=2^17`, `r=8`, and `p=1`. It encrypts and authenticates every complete vault snapshot with AES-256-GCM, using a fresh 16-byte salt and 12-byte nonce for every write. The header is authenticated as associated data, and writes use an atomic same-directory replacement. On Windows, best-effort user ACLs are applied after write.

Install Python dependencies on each device:

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python -m pip install -r shared/skills/manage-credentials/requirements.txt
```

## Initialise the vault

Run this yourself. Enter a unique recovery passphrase of at least 20 characters twice and store it securely outside this repository.

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python shared/skills/manage-credentials/scripts/vault_credentials.py init
```

The default file is `/memory/projects/credential-management/data/credentials.vault`. It is explicitly excluded from Git. To use another location, add `--vault "D:\secure\credentials.vault"` or set `PORTABLE_VAULT_PATH`.

Verify the passphrase and authenticated vault:

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python shared/skills/manage-credentials/scripts/vault_credentials.py check
```

There is no password reset or recovery bypass. Loss of the passphrase means loss of vault contents.

## Start and unlock the Vault Agent

The Vault Agent runs as the tray app with no PowerShell window. Grey icon = locked; red icon = unlocked. At startup it asks whether to unlock.

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python -m pip install -r shared/skills/manage-credentials/requirements.txt
powershell -NoProfile -File shared/skills/manage-credentials/scripts/install_vault_agent_login.ps1
pythonw shared\skills\manage-credentials\scripts\vault_tray.py
```

Tray menu: Unlock… / Lock / Status… / Quit. After reboot/login the scheduled task starts the tray app automatically.

Before prompting for the recovery passphrase, check the tray colour or run `python shared/skills/manage-credentials/scripts/vaultctl.py status`. If already unlocked, reuse that same tray agent and do not prompt again.

### Access from a sandboxed Python process

The tray broker publishes its discovery record at `%LOCALAPPDATA%\PortableAIBrain\vault-agent\agent-state.json`. The file contains broker authentication material, is restricted to the current Windows user, and must never be displayed, copied into the repository, or logged.

A restricted or sandboxed process may be able to see this file while being unable to read it. In that case, `vaultctl status`, `BrokerOAuthStore`, or an integration client may misleadingly report that the Vault Agent is not running even when the tray icon is red and unlocked.

A process started by a packaged Windows app (MSIX), such as the Claude desktop app, sees the app's
own copy of `%LOCALAPPDATA%`: what it writes there goes to
`%LOCALAPPDATA%\Packages\<app>\LocalCache\Local\...`, and that copy hides the real file from it
afterwards. So never start the tray or `vault_agent.py serve` from such a session: its state file
lands in the app's copy, outlives the process, and later sessions there read its key instead of the
running tray's. The client refuses a state file whose process has ended rather than connect with a
dead agent's key, and the agent survives a client with a wrong key. If a session reports that the
state names a process that has ended while the tray is running, the owner removes the app's copy
(`%LOCALAPPDATA%\Packages\<app>\LocalCache\Local\PortableAIBrain\vault-agent\`, only those two
runtime files) and the session sees the real one again.

Use this recovery sequence:

1. Keep using the existing tray agent and do not ask for the passphrase again.
2. Confirm only that `agent-state.json` exists and whether it is readable; never print its contents.
3. Retry the exact Python consumer command in the approved current-user execution context outside the restricted sandbox. This is access to the already-authorised local broker, not permission to broaden the consumer's external operations.
4. Run `python shared/skills/manage-credentials/scripts/vaultctl.py status` in that same context. Continue only when it reports the existing agent as unlocked.
5. If the discovery file is genuinely absent or the broker remains unreachable in the current-user context, have the owner quit the tray, restart it, and unlock once. Do not attempt to reconstruct the broker auth key or connect to the named pipe without the broker client.

Python integrations should use their established client, which will select `BrokerOAuthStore` automatically. For example, the HighLevel client in `/library/skills/gohighlevel-access/` uses `HighLevelConnection.from_environment()`. Connector code that needs the rotating JSON store directly may use:

```python
from portable_vault import PortableVaultJsonStore

store = PortableVaultJsonStore(
    entry="ghl-agency-oauth",
    field="oauth_token_json",
)
record = store.load()
```

Keep decrypted records in process memory only. Never print the record, tokens, broker state, or child environment. For a safe connectivity test, report only success, the credential alias, and non-secret structural facts such as whether the result is a JSON object.

## Store credentials

Use the canonical entry and fields from `/memory/projects/credential-management/data/credential-registry.json`:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry xero-oauth `
  --secret client_id `
  --secret client_secret `
  --empty-json oauth_token_json
```

With an unlocked agent, `put` / `vaultctl secret-put` can store fields without a second passphrase prompt. Use `--empty-json` for rotating OAuth records that an authorised connector will populate.

Delete an obsolete complete entry only after the owner explicitly requests it:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py delete-entry `
  --entry obsolete-entry
```

## Run an authorised consumer

Prefer the unlocked agent. Mapped fields are injected; the master passphrase is never exported:

```powershell
$env:XERO_TOKEN_STORE = "vault"
$env:XERO_VAULT_ENTRY = "xero-oauth"
$env:XERO_VAULT_FIELD = "oauth_token_json"

python shared/skills/manage-credentials/scripts/vaultctl.py run `
  --entry xero-oauth `
  --map XERO_CLIENT_ID=client_id `
  --map XERO_CLIENT_SECRET=client_secret `
  -- python library/skills/xero-access/scripts/xero_connect.py
```

Equivalent: `vault_credentials.py run` (also prefers the agent; interactive passphrase only for one-shot mapped-field injection when the agent is unavailable).

## Deprecated session command

`vault_credentials.py session` is emergency compatibility only. It opens a mapped-field shell with `-NoProfile` on Windows and does **not** export `PORTABLE_VAULT_PASSPHRASE`. OAuth refresh requires the Vault Agent.

## Use rotating JSON storage

```python
from portable_vault import PortableVaultJsonStore  # prefers BrokerOAuthStore

store = PortableVaultJsonStore(entry="xero-oauth", field="oauth_token_json")
with store.rotation_lock():
    current = store.load()
    store.save(updated_token_record)
```

Library consumers do not prompt. They require an unlocked Vault Agent (or an emergency in-process passphrase that must not be placed in child environments). `rotation_lock()` protects the complete local read-refresh-write sequence.

## Change the recovery passphrase

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py change-passphrase
```

This authenticates with the current passphrase, then re-encrypts the vault with a fresh salt and the new passphrase. Historical copies remain decryptable with the old passphrase until destroyed; rotate provider credentials after suspected disclosure.

## Portability and recovery

- Copy or synchronise `credentials.vault` separately from Git, only while no process is using it.
- Keep one verified offline backup of the encrypted file and store the passphrase separately.
- Use one active OAuth refresh writer for each credential set across all devices.
- Do not merge vault files. If two devices write independently, choose the authoritative complete copy.
- Per-login interactive unlock into the Vault Agent is the approved workstation model. Unattended unlock after reboot requires a separately accepted design.
- The vault file data lock is short-lived around each read/write; it is not a session lease. Agent singleton state lives under `%LOCALAPPDATA%\PortableAIBrain\vault-agent\`.

## Outputs

- one authenticated encrypted vault file
- temporary environment variables for mapped static fields only
- non-secret success or failure messages
- no plaintext repository output

## Failure and repository behaviour

- Fail closed on a missing vault, wrong passphrase, altered ciphertext, unsupported parameters, malformed fields, unavailable cryptography dependency, or locked/unavailable agent when broker access is required.
- Do not fall back to a plaintext file or another provider automatically.
- Do not retry an uncertain OAuth write without reconciling the authoritative vault copy.
- Update the non-secret credential registry and project state only when aliases or lifecycle status change.
- Append significant policy, recovery, rotation, or integrity events to the project log without secret material.
- Create a task for reauthorisation, suspected disclosure, lost passphrase, corrupted vault, or rotation conflict.
