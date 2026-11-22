---
id: skill-manage-credentials-credential-paths
title: Credential paths of the manage-credentials skill
type: knowledge
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-21T14:31:20+10:00
updated: 2026-11-21T14:31:20+10:00
---

# Credential paths

Read `/CONTRACT.md` first. This is the closed list of every path that reads, writes, spends, copies or
serves a credential of this skill and of the library connectors that use it, as the code stands after the
round-9 build (the cut-over rule, the token endpoint, `restore`, `recovery-package --team` and
`replace-signin`). `tests/test_credential_paths.py` holds the reviewed list of the callers below and fails
when a script gains a call it does not name.

## The rule the list rests on

While the secrets store is switched on, the old vault is closed: no path reads or writes a credential in it.
The rule is enforced where the data is opened, never caller by caller:

1. **The agent.** `vault_agent.build_agent` builds the agent for `vault_agent.py serve` and the login tray.
   Store on: a store-backed agent, no unlock window. A vault-backed agent refuses every credential request with
   the restart message while the store is on.
2. **The vault file.** `PortableVault` opens the vault with a passphrase only while the store is off, or when the
   caller passes `migration=True`: only the Vault Agent does, for the migration and rollback operations, under
   the migration lock that `migrate_to_store.py` holds.
3. **Token files.** A connector's plain token file is refused while the store is on.

So the callers below may call because the agent and the vault refuse for them; the list exists so that a new
caller is looked at before it ships.

## Reviewed callers

Every call of `broker_request` (or a stored `_broker_request`), every `PortableVault(` and every `migration=`
keyword in `scripts/`, by file and function, with the number of calls `tests/test_credential_paths.py` expects.
"Passed" means the function is handed on rather than called.

| Caller | What | Calls | Why it may call |
|---|---|---|---|
| `migrate_to_store.py` `main` | broker_request passed | 2 | migrate and rollback reach the agent's vault, scrub and marker operations only through it, under the migration lock |
| `portable_vault.py` `BrokerOAuthStore.__init__` | PortableVault( | 1 | path only: names the store and its local rotation lock |
| `portable_vault.py` `BrokerOAuthStore.__init__` | broker_request | 2 | ping, and with the store on status: a vault-only agent is refused |
| `portable_vault.py` `BrokerOAuthStore.__init__` | broker_request passed | 1 | keeps the broker function for the store's own calls |
| `portable_vault.py` `BrokerOAuthStore.clear` | broker_request | 1 | clear_signin: the agent checks the marker, the store switch and the refresher |
| `portable_vault.py` `BrokerOAuthStore.load` | broker_request | 1 | get_json of one sign-in: the agent answers by role and refuses a migrated field |
| `portable_vault.py` `BrokerOAuthStore.save` | broker_request | 1 | set_json of one sign-in, with the journalled operation in store mode |
| `portable_vault.py` `BrokerOAuthStore.store_mode` | broker_request | 1 | status only |
| `portable_vault.py` `BrokerOAuthStore.sync_store` | broker_request | 1 | the agent pulls the store; no credential is returned |
| `portable_vault.py` `PortableVaultJsonStore.__init__` | PortableVault( | 1 | the passphrase fallback's vault; its open refuses while the store is on |
| `secret_store/broker_backend.py` `agent_operation` | migration= | 1 | opens the old vault in store mode only while a live migration lock is held |
| `secret_store/broker_backend.py` `vault_request` | migration= | 1 | the verify-copy backup inherits the given vault's permission: under a live migration lock only |
| `token_relay.py` `_check_vault` | PortableVault( | 1 | path only: compares `--vault` with the vault the agent serves |
| `token_relay.py` `_store_key` | broker_request | 1 | key-import through the agent; every key command is refused in store mode first |
| `token_relay.py` `config_candidates` | PortableVault( | 1 | path only: where `token-relay.json` may sit |
| `token_relay.py` `config_path` | PortableVault( | 1 | path only: `token-relay.json` beside the vault |
| `token_relay.py` `main` | PortableVault( | 1 | path only: reads the migration marker, never the vault |
| `token_relay.py` `read_relay_key` | broker_request | 1 | the relay key through the agent; no relay is built while the store is on |
| `token_relay_store.py` `holder_name` | PortableVault( | 1 | path only: the non-secret computer id file |
| `vault_agent.py` `VaultAgent.__init__` | PortableVault( | 1 | the agent's vault; a vault-backed agent refuses every credential request while the store is on |
| `vault_agent.py` `VaultAgent.unlock` | PortableVault( | 1 | checks the passphrase without keeping a wrong one |
| `vault_agent.py` `VaultAgent.unlock` | migration= | 1 | store mode only: the passphrase is held for migration and rollback |
| `vault_broker_client.py` `_wait_for_refresher` | broker_request | 1 | poll_refresh: waits for the refresher, never calls the provider |
| `vault_broker_client.py` `broker_status` | broker_request | 1 | status, no credential |
| `vault_broker_client.py` `store_refresh` | broker_request | 1 | begin_refresh: the journalled refresh lock |
| `vault_broker_client.py` `store_refresh.end` | broker_request | 1 | abort or release of the journalled refresh |
| `vault_credentials.py` `_put_entry_window` | broker_request | 2 | typed values through the unlocked agent, which refuses a vault backend while the store is on |
| `vault_credentials.py` `_try_broker_fields` | broker_request | 2 | run and session: the store agent is required, then static fields only |
| `vault_credentials.py` `main` | PortableVault( | 1 | the command's vault; every passphrase open refuses while the store is on |
| `vault_credentials.py` `main` | broker_request | 1 | put through the agent, which refuses a vault backend while the store is on |
| `vaultctl.py` `_mapped_environment` | broker_request | 1 | run: static fields, after `main` required the store agent |
| `vaultctl.py` `main` | broker_request | 4 | unlock, lock, access-token, secret-put; the store agent is required except for unlock and lock |

A new caller: review it against the rule above, add it to `REVIEWED` in the test with its reason, and add a
row here.

### Library connectors

When the brain holds `/library/skills`, the same test scans every `/library/skills/<skill>/scripts` folder for
the same names against `LIBRARY_REVIEWED`; test files there (a `tests` folder or a `test_*.py` file) are left
out. Without a library the check is skipped with a message.

| Caller | What | Calls | Why it may call |
|---|---|---|---|
| `abr-access/scripts/abr_import_guid_from_gmail.py` `_store_guid` | PortableVault( | 1 | the passphrase fallback writes the GUID text field; its open refuses while the store is on |
| `abr-access/scripts/abr_import_guid_from_gmail.py` `_store_guid` | broker_request | 1 | set_text of the GUID through the unlocked agent |
| `gohighlevel-access/scripts/ghl_oauth/vault_store.py` `_credential_modules` | PortableVault passed | 1 | returns the class to `_vault_static_fields`; no vault is opened |
| `gohighlevel-access/scripts/ghl_oauth/vault_store.py` `_vault_static_fields` | PortableVault( | 1 | the passphrase fallback for static fields; its open refuses while the store is on |
| `gohighlevel-access/scripts/ghl_oauth/vault_store.py` `_vault_static_fields` | broker_request | 1 | get_fields of static fields; off the refresher a client secret is refused |
| `google-workspace-access/scripts/google_oauth/client.py` `client_from_vault` | broker_request | 2 | get_fields of the client ID and secret, then the client ID alone when the secret lives on the refresher |
| `google-workspace-access/scripts/google_tray_token.py` `_broker` | broker_request passed | 1 | hands the agent client to the two tray functions |
| `google-workspace-access/scripts/google_tray_token.py` `_refresh_under_lock` | broker_request | 1 | client ID and secret inside the store's rotation lock, on the refresher |
| `google-workspace-access/scripts/google_tray_token.py` `load_tray_access_token` | broker_request | 1 | get_json of the account's sign-in: answered by role, a migrated field refused |
| `google-workspace-access/scripts/google_tray_token.py` `refresh_tray_access_token` | broker_request passed | 1 | passes the agent client on; no call of its own |
| `linkedin-access/scripts/linkedin_client.py` `vault_static_fields` | broker_request | 1 | get_fields of static fields through the unlocked agent; no passphrase fallback |

## All paths

States: **S1** store off, nothing migrated; **S2** store on, the agent serves the store; **S3** store on, no
agent, or an agent started before the store was switched on; **S4** store off, entry named in the migration
marker. Touches: a read, b write or delete, c provider token or revocation call, d export, copy or publish,
e start or configure the agent. `mc/` is this skill's `scripts/`, `lib/` the skill library.

| # | Path | Touches | Store on (S2, S3) | S4 | Status |
|---|---|---|---|---|---|
| 1 | `mc/brain_secrets.py` init, team-init | b, d | store only, no agent needed | same | OK |
| 2 | `brain_secrets.py` put, delete | b | direct store write | same | OK |
| 3 | `brain_secrets.py` status, list, get-check, grant-scan | a (names) | names only | same | OK |
| 4 | `brain_secrets.py recovery-package [--team]` | d | personal or team package; an unwritable folder warns and writes the upkeep-error file | same | OK |
| 5 | `brain_secrets.py` enrol-request, enrol-approve | b, d | direct store | same | OK |
| 6 | `brain_secrets.py` team-admit, team-groups, team-remove | b, d | direct store, re-key | same | OK |
| 7 | `brain_secrets.py` handover-release, handover-accept, supersede | b | refused without a verified profile where one is needed | same | OK |
| 8 | `brain_secrets.py restore [--team]` | a, d | words in the masked window only; wrong words, damaged package, non-empty target: nothing written | same | OK |
| 9 | `secret_store/store.py` package upkeep, `broker_backend` package timer | d | timer every 6 hours, both stores | n/a | OK |
| 10 | `store_ops.package_health`, the daily due check | a (files) | personal and team checked | none | OK |
| 11 | `secret_store/keys.py` keychain keys | a, b | allowlisted backends only, fails closed | same | OK |
| 12 | `secret_store/journal.py` `resolve_uncertain` | b | no production caller; refused while no profile is verified; an uncertain sign-in is ended by `replace-signin` (row 52) | same | OK |
| 13 | `mc/migrate_to_store.py` migrate | a, b, d | one run under the migration lock; an unverified sign-in has its store copy removed in the same run and the run exits non-zero | marked entries skipped | OK |
| 14 | `migrate_to_store.py` backup | d | encrypted byte copy; status shows the newest backup's age; no retention limit | same | OK, noted |
| 15 | `migrate_to_store.py rollback` | b, d | under the lock; every static object of the store, text and JSON, entries created after the migration included; each entry not restored is named and exits 5; sign-ins need a browser sign-in | same | OK |
| 16 | `mc/portable_vault.py` `PortableVaultJsonStore` | a, b, e | store agent required; passphrase open refused; relay ignored | marked field refused | OK |
| 17 | `portable_vault.py` `BrokerOAuthStore` | a, b | store agent required | agent refuses marked field | OK |
| 18 | `mc/vault_credentials.py` run, session | a | store agent required | text only | OK |
| 19 | `vault_credentials.py` put, put-entry `--window` | b | a vault-backed agent refuses; passphrase open refused | text, no marker check | OK |
| 20 | `vault_credentials.py` check, list, change-passphrase, delete-entry, delete-field, init-json, init | a, b | every passphrase open refused; one refusal test per command | direct vault | OK |
| 21 | `mc/vaultctl.py` status, access-token, secret-put, run | a, b | store agent required | via the agent | OK |
| 22 | `vaultctl.py` unlock, lock | e | allowed; the passphrase is held only for migration and rollback; tested | vault | OK |
| 23 | `mc/vault_agent.py` `get_json`, `get_access_token`, `set_json` | a, b | store backend; a vault backend refuses | marker refuses | OK |
| 24 | `vault_agent.py` `get_fields`, `set_text` | a, b | store backend; a vault backend refuses | no marker check; the scrubbed record holds no token | GAP (low), store off only |
| 25 | `vault_agent.py` serve, status, unlock, lock | e | `build_agent`; a malformed configuration exits 2 | vault agent | OK |
| 26 | `mc/vault_tray.py`, `install_vault_agent_login.ps1` | e | built by `build_agent`: serves the store, no unlock window; a malformed configuration stops it | vault agent | OK |
| 27 | `broker_backend.vault_request` list, get-fields, get-json, verify-copy | a | refused with the store on unless the migration lock is held | scrubbed records | OK |
| 28 | `broker_backend.vault_request` scrub, clear-marker, restore-static | b | only while a live migration lock is held | same | OK |
| 29 | `broker_backend.StoreBackend` get and set | a, b | refresher full record, others the access token | – | OK |
| 30 | `StoreBackend` begin, set with operation, abort, release, poll, sync, clear | b, c | journalled; a refused answer releases like not-sent | – | OK |
| 31 | `StoreBackend.status`, `package_state` | a (state) | both packages | – | OK |
| 32 | `mc/token_relay.py` seed, key commands | a, c, d | refused | refused (marker) | OK |
| 33 | `token_relay.py status` | a | "retired" | local error for marked | OK |
| 34 | relay store and backend | a, b, c, d | none built | not reached | OK |
| 35 | `lib/xero-access` exchange, refresh, tenant | a, b, c | via 16 and `post_token` | refused | OK |
| 36 | Xero and Google plain token files | a, b, c | refused while the store is on | refused | OK |
| 37 | Xero `revoke` | b, c | refused unless this computer is the refresher | refused | OK |
| 38 | `lib/google-workspace-access` exchange, refresh | a, b, c | via 16 and `post_token` | refused | OK |
| 39 | Google `revoke` | b, c | refused unless this computer is the refresher | refused | OK |
| 40 | Google `client_from_vault`, tray token loader | a | refused by rule 1 or 2 | marker refuses | OK; per-client test is follow-up F1.3 |
| 41 | Google tray refresh | a, b, c | journalled | refused | OK |
| 42 | HighLevel static fields | a | refused by rule 1 or 2 | text | OK; per-client test is follow-up F2.3 |
| 43 | `lib/gohighlevel-access` exchange, refresh, location token | a, b, c | via 16 and `post_token` | refused | OK |
| 44 | LinkedIn static fields | a | refused by rule 1 | text | OK; per-client test is follow-up F2.3 |
| 45 | LinkedIn token store and connect | a, b, c | via 16 and `post_token` | refused | OK |
| 46 | Meta token store and exchange | a, b, c | via 16; no rotating refresh | refused | OK; store-mode test is follow-up F2.2, F2.3 |
| 47 | ABR GUID store | b | refused by rule 1 or 2 | text | OK; per-client test is follow-up F2.3 |
| 48 | ABR, Railway, mail-review clients (environment from row 18) | a | via 18 | via 18 | OK |
| 49 | `repository-preflight` host wiring | none | – | – | not a credential path |
| 50 | `mc/token_endpoint.py` `post_token` | c | not sent, refused and uncertain decided by fact; https only; never retried | – | OK |
| 51 | `mc/migration_lock.py` | b (lock file) | exclusive; an absent, dead, old or malformed lock refuses | – | OK |
| 52 | `brain_secrets.py replace-signin` | b, d | the refresher that is an administrator; a refresher that is not an administrator changes nothing and gets the step, the ordinary `delete` by an administrator (exit 3), and is refused with `--even-if-working`; an administrator that is not the refresher is refused, naming `delete`; settings kept in an encrypted hand-over file; one commit retires both ids; a failed push changes nothing; the old refresher discards its record of the retired grant | – | OK |

Tests: rows 1 to 11 and 29 to 31 in `tests/test_secret_store_*.py`; rows 13 to 28 in `test_secret_store_round8.py`
and `test_secret_store_round9.py`, and row 15 also in `test_secret_store_rollback_static.py`; rows 4, 8 and 52 in `test_secret_store_restore_cli.py`,
`test_secret_store_replace_signin.py` and `test_secret_store_replace_team.py`; rows 30 and 50 in
`test_token_endpoint.py`; rows 35 to 47 in `test_secret_store_connectors.py` and each library skill's own tests.

## Open

- Row 24: with the store off, the agent's `get_fields` and `set_text` skip the marker check. A scrubbed record
  holds no token, so nothing can be spent.
- Row 14: migration backups keep old refresh tokens, encrypted, with no retention limit; status shows their age.
