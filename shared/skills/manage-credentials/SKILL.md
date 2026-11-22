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
  updated: 2026-11-21T14:31:20+10:00
---

# Credential Management

## Purpose

Operate one portable encrypted credential vault without an external secret service. The recovery passphrase is the only unlock factor and must never be stored in the repository, vault, scripts, command arguments, logs, persistent environment configuration, or child-process environments.

Runtime unlock is held by the **per-login Vault Agent**. Applications receive scoped results through the local broker (normally mapped static fields or OAuth JSON load/save). Closing PowerShell does not revoke OAuth grants; those remain encrypted in the vault.

## Credential policy

The rules every use of this skill follows (moved here from an owner's node rules on 9 November 2026, PROPOSAL-promote-owner-rules-2).

### Storage policy

- Use the vault file named under *Required inputs* as the canonical encrypted store for future credentials unless a credential set explicitly declares another approved provider.
- Store no plaintext password, API key, client secret, access token, refresh token, private key or recovery passphrase in the brain.
- Permit only the approved authenticated encrypted `credentials.vault` container in the project data directory; exclude it from Git.
- Store only non-secret aliases, provider names, field names, ownership, consumers and lifecycle metadata in the repository.
- Do not duplicate connector-managed credentials into the portable vault when the connector keeps them opaque and local code does not require them.
- Do not use Windows Credential Manager or an external password manager as the default backend.
- Do not place secrets in command-line arguments, Markdown, committed JSON, `.env` files, shell history, logs or task records.
- Accept new secret values through a hidden prompt or standard input.
- Collect all fields for a new credential entry after one vault unlock and commit them together only after every required input validates.
- Inject static credentials only into the environment of an authorised short-lived child process when that process cannot use the Vault Agent broker, and do not persist that environment. Do not place the vault recovery passphrase or vault encryption key in any child environment.
- Prefer the per-login Vault Agent as the runtime unlock holder: the owner unlocks once after Windows login (or after agent restart / explicit lock) through a hidden prompt; the agent retains the derived vault key in its own memory only; authorised consumers obtain scoped results (normally short-lived OAuth access tokens or explicitly mapped static fields) through the local broker without a chat-long credential-aware shell.
- Treat `vault_credentials.py session` as deprecated emergency compatibility only. Do not use it as the default operating model for new work or agentic shells.

### Vault structure

- Use stable lowercase entry aliases such as `xero-oauth`.
- Use lowercase snake-case field names.
- Store static values in separate fields, such as `client_id`, `client_secret` or `api_key`.
- Store a provider's complete rotating OAuth record as one JSON field so token pairs are updated together.
- Initialise OAuth JSON fields with `{}` through the credential skill; never paste live tokens into repository files.
- Fail when an entry or field is missing or malformed.

### Passphrase and encryption

- Use a unique recovery passphrase of at least 20 characters.
- Never supply the recovery passphrase in chat, command arguments, Markdown, scripts, logs, shell profiles, `.env` files, persistent environment variables, or child-process environments. Enter it only through the skill's hidden unlock prompt into the Vault Agent (or an emergency interactive vault CLI that does not export the passphrase to children). Store the recovery copy separately from the encrypted vault.
- Derive the encryption key with the fixed approved scrypt parameters and protect the complete vault with AES-256-GCM.
- Use fresh salt and nonce values for every vault write.
- Treat authentication failure as either a wrong passphrase or possible alteration; do not attempt partial recovery.

### OAuth lifecycle

- Request only required scopes.
- Replace the stored token bundle immediately after a successful refresh.
- Allow only one active refresh writer for a credential set across all devices, unless the
  entry is listed in the token relay's configuration. Brains that share a relayed entry refresh
  only while holding the relay's lease, take the newest token from the relay before refreshing,
  and write the new token back at once.
- Pass tenant or organisation context explicitly; do not infer it from an unrelated process.
- Reauthorise when refresh credentials expire, are revoked or cannot be reconciled safely.

### Portability and concurrency

- Copy or synchronise the encrypted vault only while it is closed.
- Keep a verified offline backup of the encrypted vault and keep its passphrase separately.
- Do not commit the vault, merge divergent copies, or assume file synchronisation provides
  locking. The token relay's record is not the vault: it is one rotating token bundle, encrypted
  with the relay key, and may be committed only to the private store named in the relay's
  configuration.
- Use one active writer for each rotating OAuth credential set across devices, or the token
  relay for an entry several brains share.
- The relay store holds ciphertext only. The relay key and the provider's client secret live in
  each brain's vault and reach another person only through a password manager, never through
  chat, e-mail or a repository. When the relay cannot be reached and the local token is about
  to expire, a brain refuses to refresh.
- Do not enable unattended vault unlock after reboot without a separately accepted runtime design (for example a future TPM/device-bound key slot). Per-login interactive unlock into the Vault Agent is the approved workstation model.
- Do not substitute a plaintext `.env` passphrase for interactive unlock.
- Before prompting for the recovery passphrase, check whether the Vault Agent is already unlocked for this Windows login. If it is unlocked, reuse it for further credential operations; do not prompt again and do not start a second agent instance.
- Keep the vault file data lock short-lived around each authenticated read or write. Do not treat `credentials.vault.lock` as a session lease. Use a distinct agent singleton / session lease so only one Vault Agent instance holds the unlock key, while OAuth token refresh can still serialise per entry without blocking unrelated vault maintenance incorrectly.
- Do not create parallel unlocked agents or parallel processes that each hold the recovery passphrase.

### Logging and failure

- Log credential aliases and operation results only.
- Never log secret values, passphrases, token payloads, child environments or decrypted vault contents.
- Fail closed when the vault is missing, cannot authenticate, is malformed, has unsupported parameters, or the cryptography dependency is unavailable.
- Create a task for rotation failure, provider outage, suspected disclosure or required reauthorisation.

## Allowed operations and permissions

Read `/memory/projects/credential-management/RULES.md` before changing credential storage.

- Initialise and authenticate the approved vault.
- Start, unlock and lock the Vault Agent.
- Add or replace fields through hidden input or standard input from an authorised producer.
- Inject selected text fields only into an authorised child process (never the master passphrase).
- Read and atomically replace rotating JSON credentials through `BrokerOAuthStore` / `PortableVaultJsonStore` via the agent.
- Change the vault passphrase after authenticating with the current passphrase.
- List the entry names held in this computer's vault (`list`): names and their count only, never a field name or value.
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

An agent can start `init --window` instead, so the person types the passphrase in a small window,
not a terminal (see Password windows under Store credentials).

The default file is `/memory/projects/credential-management/data/credentials.vault`. It is explicitly excluded from Git. To use another location, add `--vault "D:\secure\credentials.vault"` or set `PORTABLE_VAULT_PATH`.

Verify the passphrase and authenticated vault:

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python shared/skills/manage-credentials/scripts/vault_credentials.py check
```

List the names of the entries this computer's vault holds, in alphabetical order, then one line with their count. It unlocks the way `check` does and never prints a field name, value, token or passphrase; when the vault cannot be unlocked it prints nothing, gives a one-line reason on stderr and exits non-zero:

```powershell
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)
python shared/skills/manage-credentials/scripts/vault_credentials.py list
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

Tray menu: Unlock… / Lock / Status… / Quit. After reboot/login the Startup shortcut (and the logon task, when one could be registered) starts the tray app automatically.

A start that finds the agent's lock busy retries for 10 seconds before it concludes another agent is running. When a healthy agent already answers, the second tray ends quietly with no dialog. Every other start failure is shown with its real cause. The tray has no console, so each start, quiet exit and failure is also written to `%USERPROFILE%\.portable-ai-brain\vault-agent\tray.log` (never secret material; the file is cut back once it passes 64 KiB). When the icon is missing after login, read that file first.

Before prompting for the recovery passphrase, check the tray colour or run `python shared/skills/manage-credentials/scripts/vaultctl.py status`. If already unlocked, reuse that same tray agent and do not prompt again.

### Access from a sandboxed Python process

The tray broker publishes its discovery record at `%USERPROFILE%\.portable-ai-brain\vault-agent\agent-state.json` (until 1 October 2026 it was under `%LOCALAPPDATA%\PortableAIBrain\`). The file contains broker authentication material, is restricted to the current Windows user, and must never be displayed, copied into the repository, or logged.

A restricted or sandboxed process may be able to see this file while being unable to read it. In that case, `vaultctl status`, `BrokerOAuthStore`, or an integration client may misleadingly report that the Vault Agent is not running even when the tray icon is red and unlocked.

A process started by a packaged Windows app (MSIX), such as the Claude desktop app, sees the app's
own view of `%LOCALAPPDATA%`, which hides files the tray writes there. That is why the runtime folder
is in the user profile outside AppData: sessions in such an app read the running tray's state file
like any other process. Still, never start the tray or `vault_agent.py serve` from a session: start it
from your own terminal or the login shortcut. The client refuses a state file whose process has ended
rather than connect with a dead agent's key, and the agent survives a client with a wrong key.

The state file belongs to the running agent. An agent that stops removes it only when it names
its own process; a running agent writes it back within a few seconds if it goes missing; and a
second tray started by mistake leaves it alone. Until 16 November 2026 the skill's own test run
could remove a running tray's state file, which left the tray looking unlocked while no script
could reach it.

`vaultctl.py get-access-token` returns the access token stored on this computer and never
refreshes or syncs. For an entry shared through the token relay, use the provider's client, which
takes the newest shared token first.

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

### Password windows (`--window`)

`init --window` and `put-entry --window` ask in a small masked window instead of a terminal, so an
agent can start them and the person only types or pastes. One script, `scripts/secret_window.py`
(Python's own tkinter), serves Windows, macOS and Linux. The window stays on top; Enter is OK,
Esc or closing it is Cancel, which exits with code 1 and `Cancelled; nothing stored.`

- `init --window` asks for the new passphrase twice and refuses, inside the window, fewer than
  20 characters or a mismatch. There is no reset.
- `put-entry --window` shows one masked field per `--secret`. With the Vault Agent unlocked, each
  field is stored through the agent (`set_text`, and `set_json` with an empty object for each
  `--empty-json`) and no passphrase is asked; that path writes field by field. With the agent
  locked, the window asks for the vault passphrase too and the whole entry is written at once.
  With the agent unlocked and only `--empty-json` fields, no window opens.

Values are never printed, logged, or put in the command line or the environment; the output names
only the entry and its fields. Where tkinter is missing or there is no display, the command fails
at once and says to install python-tk (macOS with Homebrew: `brew install python-tk`) or to run
the terminal command without `--window`. Without `--window` both commands behave as before.

Delete an obsolete complete entry only after the owner explicitly requests it:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py delete-entry `
  --entry obsolete-entry
```

Delete one obsolete field and keep the rest of its entry, for example a client secret that now
lives in a shared entry, the same way:

```powershell
python shared/skills/manage-credentials/scripts/vault_credentials.py delete-field `
  --entry example-entry --field obsolete_field
```

Both deletions are the owner's own act: each asks the owner to type what is deleted, then for the
vault passphrase, in a terminal. Neither goes through the unlocked Vault Agent, so an agent or a
script cannot delete on its own. `delete-field` refuses the last field of an entry.

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

## Running without a terminal

`run` never waits for input nobody can give. When the unlocked Vault Agent answers that an entry
or a field does not exist, `run` fails at once with that message: it does not fall back to a
passphrase prompt, which could only find the same vault lacking the same field. When the
passphrase is needed and there is no terminal to ask for it (a scheduled run, an agent's
shell), every command fails at once and says to unlock the tray app.

## Share a rotating sign-in between brains (token relay)

Some providers issue a new refresh token at every refresh and retire the old one. When several
people's brains use the same sign-in, the token relay lets each of them refresh without one
computer being the refresher for all. It is off until an owner sets it up, and it is governed by
the *Credential policy* above: without a relay, one writer per sign-in.

**What it is.** One private store all the sharing brains can reach – a private GitHub repository,
read and written through the `gh` command line each brain is already signed in to – holding one
file per shared vault entry. The file carries the current token bundle, encrypted with the relay
key (AES-256-GCM), a version number and a lease. The store never holds the relay key or the
provider's client secret, so the file is useless to anyone who takes it.

**How a refresh goes.** A brain whose token is about to expire reads the file. If another brain
has already refreshed, it adopts that token and is done. Otherwise it writes a lease into the
file; the store refuses the write when someone else wrote first, so one brain holds it. It
refreshes with the provider, saves the new token in its own vault, writes it to the file and
clears the lease. Only a lease holder changes the tokens in the file; any other save changes
other data only.

**It refuses instead of guessing.** A listed entry is not refreshed when the store cannot be
reached, the file is missing, the file is older than this computer's copy, the file does not
decrypt, or the relay key is absent. A token saved locally whose write-back failed is pushed at
the next use; if another brain has moved on meanwhile, the shared token wins and a warning says
so.

**Limits.** Everyone sharing an entry holds the client secret and a working token, so the relay
suits trusted partners and cannot make anyone read-only. A brain that crashes while holding the
lease blocks the others for the length of the lease (`lease_seconds`, 300 unless set, 120 to
900). Only the field `oauth_token_json` is relayed. A client must pass its token keys to the
store and skip the provider when the token is already fresh; the Xero and HighLevel clients in
the skill library do.

**Where the config is found, and failing closed.** `token-relay.json` is looked for beside the
vault the unlocked Vault Agent serves, then beside the named or default vault, then (when that is
the default vault, as in a session copy whose own memory holds no vault) beside the default vault
under `brain_root` in `/memory/OWNER.md`; the first that exists is used. `token_relay.py status`
names it in each row, and the Xero vault store prints `Token relay config: <path>` (or where it
looked) on stderr. When none is found and the stored token carries a relay version, a refresh or
a new authorisation is refused with the places looked in, and nothing is sent to the provider.

### Set it up (the owner, once)

1. Create a private repository for the relay and invite each person who shares the sign-in.
2. Beside the vault file, write `token-relay.json`:

   ```json
   {"backend": "github", "repository": "<owner>/<name>", "entries": ["<vault entry>"], "lease_seconds": 300}
   ```

3. With the Vault Agent unlocked, in your own terminal:

   ```powershell
   python shared/skills/manage-credentials/scripts/token_relay.py key-new
   python shared/skills/manage-credentials/scripts/token_relay.py seed --entry <vault entry>
   python shared/skills/manage-credentials/scripts/token_relay.py status
   ```

   `seed` pushes this computer's token as version 1 and refuses when a file already exists.
   `seed --replace` overwrites the shared file with this computer's token at a higher version;
   use it after replacing the relay key, or when the file is damaged. An entry listed before
   its first sign-in signs in locally with a warning; run `seed` straight after.
4. `key-export` prints the relay key to a terminal only. Put it and the provider's client id and
   secret in a password manager entry shared with the other person; never in chat, e-mail or a
   repository.

### Join it (each other person, once)

1. Accept the invitation to the relay repository and check `gh auth status`.
2. Write the same `token-relay.json` beside your vault file.
3. Store the client id and secret in the vault entry as usual, with an empty `oauth_token_json`
   (`init-json`), then `token_relay.py key-import` (a hidden prompt).
4. `token_relay.py status` shows the shared version; the first use of the sign-in adopts it.

### Remove a person

Remove them from the relay repository, then refresh once from any remaining brain (each client's
manual refresh does it). Their copy of the refresh token stops working; an access token they
still hold runs until it expires. After an exit that was not friendly, replace the client secret
and the relay key (`key-new --replace`), authorise again, run `seed --replace`, and give the
others the new key.

A computer whose local token was cleared takes the shared one again at its next use. With
`--vault`, the relay commands refuse a vault other than the one the running Vault Agent serves;
the JSON store itself does not make that check.

`status` prints, per entry, the shared and local versions, the lease and whether a local change
is still unpushed; never a secret.

## Synced secrets store (opt-in)

An alternative provider keeps secrets as encrypted, signed files in private Git repositories, with
each computer's keys in the operating system's keychain and no passphrase. Its code is in
`scripts/secret_store/`, its commands are `scripts/brain_secrets.py` and `scripts/migrate_to_store.py`,
and `scripts/secret_store/README.md` describes the rules, files, roles, commands and recovery. The
*Credential policy* vault rules above apply until the owner accepts `PROPOSAL-synced-secrets-store`
and switches the store on (`config/secret-store.json` in the owner's memory folder for this skill,
`enabled` true). `CREDENTIAL-PATHS.md` in this folder lists every path that reads, writes, spends or
copies a credential, and `tests/test_credential_paths.py` fails when a script gains a caller of the
agent or the vault that the list does not name.

With the store on the old vault is closed: no path reads or writes a credential in it.

- `vault_agent.py serve` and the login tray build their agent through one function: with the store on
  it serves the store and shows no unlock window. A Vault Agent that was started before the store was
  switched on still has the old vault as its backend; it refuses every credential request, and
  `vaultctl.py` (except `unlock` and `lock`), the broker client and the vault stores refuse it, with
  "the Vault Agent was started before the secrets store was switched on; restart it". Restart the agent.
- Opening the vault with the passphrase is refused ("the secrets store is on; start the Vault Agent"),
  for every `vault_credentials.py` command and every connector's passphrase fallback. Only the Vault
  Agent opens it, for the migration and rollback operations, while the migration lock is held.
- A connector's plain token file is refused.
- A store configuration that cannot be read, has unknown keys, or is enabled without a person stops
  the Vault Agent at start (exit code 2, with the reason on stderr). It never falls back to the old vault.
- The token relay is ignored: no relay is built, whatever `token-relay.json` lists, and the store's
  journal decides every refresh. `vaultctl.py status` shows a line "Token relay: ignored while the
  secrets store is on (<path>)" when such a file is still found.
- The Vault Agent rebuilds the personal recovery package on a timer, at least every 6 hours, with no
  credential request: it pulls the stores, then rebuilds a package that is stale or no longer matches
  the policy. If a check fails, `vaultctl.py status` shows "Package timer: ..." and the failure is
  written to a `.upkeep-error` file beside the checkpoint on this computer. The daily due check reads
  that file and reports it; the next timer run retries, and a success clears the file.

### The cut-over

Rehearse the store with throwaway secrets before the cut-over: rehearsal/README.md

The move to the store is one run, not entry by entry, in this order:

1. With the store off, start the Vault Agent and unlock it on the old vault.
2. Switch the store on. Do not restart the agent: it still serves the old vault, for the migration
   only.
3. `python migrate_to_store.py --dry-run` lists the entry and field names.
4. `python migrate_to_store.py` takes the migration lock beside the vault (`<vault>.migration.lock`,
   naming its process and start time), makes a verified backup, copies every entry and reads each back.
   A verified sign-in has its tokens removed from the old vault and is named in the migration marker
   (`<vault>.migrated.json`). A sign-in that fails its read-back has its store copy removed in the same
   run; the vault entry stays as it was, the run names it and exits non-zero. Nothing is served from two
   places.
5. Restart the Vault Agent so it serves the store. A sign-in the run reported as not moved is then
   signed in again in the browser; the sign-ins it moved need nothing.

What fails closed: the agent's scrub, restore-static and marker operations, and its opening of the old
vault with the store on, need a live migration lock; an absent, unreadable or stale lock (its process
gone, or older than six hours) refuses, and a second migration cannot take a held lock. The legacy
paths refuse every sign-in named in the marker, store on or off.

Rollback goes the same way round. With the store off, start the Vault Agent on the old vault and unlock
it. Switch the store on without restarting the agent. Run `python migrate_to_store.py rollback --dry-run`,
then `python migrate_to_store.py rollback`, then switch the store off; the agent then serves the old
vault. The rollback also runs under the lock. It restores static secrets only, from the store's current
value, and clears the marker. It walks every static entry of the store, so an entry or field created
after the migration comes back too, a static field under a migrated sign-in's name included. The store
keeps each static field's kind (text or JSON) beside its value, and the rollback restores each field
at that kind and nothing else. It names each entry it restored and each it could not (a field with no
recorded kind, a token, or a sign-in the store still holds under that name); one it could not ends
with exit code 5 and the marker kept, so it can be run again. A field with no recorded kind occurs
only in a store made before kinds were kept: store that entry again, then run the rollback again. It never
writes a token out of the store, so every migrated sign-in needs a browser sign-in after a rollback.

### Recovery and replacing a sign-in

- `brain_secrets.py recovery-package [--team]` writes the personal or the team recovery package now. If
  the folder cannot be written it warns, records the upkeep error and exits 1.
- `brain_secrets.py restore [--team] --package FILE --target FOLDER` recovers a store into a new or empty
  folder. The recovery words are typed only into the masked window; the package's age is reported. Wrong
  words, a damaged package, a non-empty target or a cancelled window write nothing.
- `brain_secrets.py replace-signin ENTRY [--field F] [--group G] [--even-if-working]` ends an uncertain
  sign-in. It runs only on the sign-in's refresher, by an administrator of the repository, and only when
  the last refresh is uncertain unless `--even-if-working` is given. The shared settings are kept in an
  encrypted hand-over file beside the journal, one commit deletes the sign-in and retires both ids, and
  the next browser sign-in under the same name gets the kept settings. A failed commit or push leaves
  the sign-in as it was; `status` reports a hand-over file whose sign-in was never completed.
  A team sign-in whose refresher is not an administrator is ended by the store's ordinary deletion. On
  the refresher, with the last refresh uncertain, the command changes nothing and exits 3: the sign-in
  stays blocked there, because its uncertain journal record refuses every refresh, offline, from a stale
  copy and across restarts. The message names the administrator's step: delete the entry on their own
  computer with `brain_secrets.py delete --entry E --group G` (one commit retiring both ids), sign in
  again in the browser there and hand the new sign-in back with `handover-release` and
  `handover-accept`. No settings are carried over that way; choose them again when signing in. On that
  refresher `--even-if-working` is refused: a working sign-in moves to an administrator by the
  cooperative handover. An administrator who is not the refresher is refused, and the message names the
  delete command. The old refresher's next operation discards its record of the exact retired grant; a
  refresh answer that arrives after the deletion is never published and never retried.
- `brain_secrets.py unfinished [--team] [--apply ID | --discard ID]` lists the pending writes kept on this
  computer by write id, entry and time, never a value. Every typed value (`put`, plain or grant fields, and
  the agent's `set_text` and `set_json` of a static or grant field) is kept in one encrypted pending-write
  record, written after the change is verified and before its local commit; it is removed once the write is
  confirmed. A crash or a failed push keeps it, and the next operation writes it again when every object it
  was built on is unchanged, removes it when the store already holds that very write, and otherwise marks it
  held: `--apply ID` writes the kept values over the present ones, `--discard ID` removes them (type the id
  to confirm). A browser sign-in, the migration and a settings save make no record, and no record holds a
  token. A refused commit is named by a fixed rule code and the commit id, never by text from the commit.

### A failed refresh

Every token-endpoint call goes through `token_endpoint.post_token`, a new connection each time, never
retried. A failure is one of three sorts:

| Sort | When | What happens |
|---|---|---|
| Not sent | the connection, proxy tunnel or TLS handshake failed before any byte of the request | the journal record is removed; the next attempt refreshes normally |
| Refused | the provider answered HTTP 400 or 401 with an OAuth error body | the record is removed; `invalid_grant` raises the connector's sign-in-needed error, and a browser sign-in is allowed |
| Uncertain | anything else after the request was written: a time-out, a reset, HTTP 5xx, any other 4xx including 429, an unreadable answer | the record stays `calling` and the sign-in is blocked, never retried with the old token; end it with `replace-signin` |

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
- The vault file data lock is short-lived around each read/write; it is not a session lease. Agent singleton state lives under `%USERPROFILE%\.portable-ai-brain\vault-agent\`.

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
