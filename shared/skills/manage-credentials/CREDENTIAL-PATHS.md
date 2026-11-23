---
id: skill-manage-credentials-credential-paths
title: Credential paths of the manage-credentials skill
type: knowledge
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-21T14:31:20+10:00
updated: 2026-11-22T16:01:21+10:00
---

# Credential paths

Read `/CONTRACT.md` first. This is the closed list of every path that reads, writes, spends, copies or
serves a credential of this skill and of the library connectors that use it, as the code stands after the
round-9 build (the cut-over rule, the token endpoint, `restore`, `recovery-package --team` and
`replace-signin`). `tests/test_credential_paths.py` holds the reviewed list of the callers below and fails
when a script gains a call it does not name. The section "Inside the store" is the inventory of the store's
own code (round 11, rule 6): every module, every function in which a credential first exists in the clear,
every function that writes or sends one, every public operation, with the checks that are exact and, in
plain words, what no check does.

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
| 2 | `brain_secrets.py` put, delete | b | direct store write; `delete --field F` by an administrator retires exactly that sign-in's oauth and grant ids, the entry's plain fields and other sign-ins untouched; `delete` without `--field` the whole entry | same | OK |
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
| 14 | `migrate_to_store.py` backup | d | encrypted byte copy inside the vault's own folder (`--backup-dir` too); status shows the newest backup's age; no retention limit | same | OK, noted |
| 15 | `migrate_to_store.py rollback` | b, d | under the lock; every static object of the store, entries created after the migration and static fields under a migrated sign-in's name included (restored after the ordinary fields through restore-marked-static, which leaves the marker as it is; the marker is cleared last, only when every restore succeeded, never early, and nothing is scrubbed); each field at the kind recorded in the store's payload and nothing else; no recorded kind (a store made before kinds were kept), malformed kind data, a token or a shadowing sign-in is named and exits 5; sign-ins need a browser sign-in | same | OK |
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
| 28 | `broker_backend.vault_request` scrub, clear-marker, restore-static, restore-marked-static | b | only while a live migration lock is held; each restore checks its whole request before one write: restore-static refuses a marked name, restore-marked-static takes only marked names, neither a sign-in-shaped value | same | OK |
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
| 52 | `brain_secrets.py replace-signin` | b, d | the refresher that is an administrator; a refresher that is not an administrator changes nothing and gets the step, `delete --entry E --field F` by an administrator (exit 3), and is refused with `--even-if-working`; an administrator that is not the refresher is refused, naming `delete --field`; settings kept in an encrypted hand-over file; one commit retires both ids; a failed push changes nothing; the old refresher discards its record of the retired grant | – | OK |
| 53 | `brain_secrets.py unfinished [--team] [--apply ID \| --discard ID]`, `secret_store/pending.py`, `secret_store/typed_write.py` | a, b | one pending-write record per typed write (`put`, the agent's `set_text` and `set_json` of a static or grant field), encrypted to this computer's key beside the journal; a typed value whatever its field is called; a provider's token answer never enters a record (an authorisation, the migration, `save_settings` and a refresh make none); listed by write id, entry and time, never a value; replayed only while every base identity holds, held otherwise; `--apply` writes through the normal store path; `--discard` removes a record after its id is typed; a damaged record, one of another repository or one without field kinds is never applied; nothing is read from or sent to the vault | same | OK |

Tests: rows 1 to 11 and 29 to 31 in `tests/test_secret_store_*.py`; rows 13 to 28 in `test_secret_store_round8.py`
and `test_secret_store_round9.py`, and row 15 also in `test_secret_store_rollback_static.py`; rows 4, 8 and 52 in `test_secret_store_restore_cli.py`,
`test_secret_store_replace_signin.py` and `test_secret_store_replace_team.py`; rows 30 and 50 in
`test_token_endpoint.py`; row 53 in `test_secret_store_typed_write.py` (the pending-write records and their replay)
and `test_secret_store_two_processes.py` (two processes on one clone); rows 35 to 47 in
`test_secret_store_connectors.py` and each library skill's own tests.

## Inside the store

The inventory of this skill's own code under `scripts/` and `scripts/secret_store/`, as the code stands after the
round-11 fixes (merge `43d1374`). Its tables are held, in the same words, in `tests/credential_inventory.py`;
`tests/test_credential_paths.py` compares them with the source (never by running it) and
`tests/test_credential_paths_runtime.py` with what the code does when its operations run in-process. A test
fails when the code and a table disagree, in either direction: a path a table lacks, or a row the code no longer
has. Section "The limit" says, in plain words, what none of these checks does.

What "a credential" means here: a stored value (a static field, a sign-in record, a grant, a passphrase, the
recovery words, the relay key, the agent's IPC key) and this computer's private keys as read from or written to
the keychain. A module that uses a private-key object to sign or to decrypt, without reading its bytes, is listed
by that use, not as carrying the key. "In the clear" means the value is in the process's memory as plaintext,
whether a Python string, a dictionary or the canonical bytes before encryption or after decryption.

### External modules, closed

Every external module the scripts import, and nothing else, is one of: `PIL`, `__future__`, `argparse`, `atexit`,
`base64`, `binascii`, `contextlib`, `copy`, `cryptography`, `ctypes`, `dataclasses`, `datetime`, `errno`, `fcntl`,
`functools`, `getpass`, `hashlib`, `hmac`, `http`, `json`, `keyring`, `math`, `msvcrt`, `multiprocessing`, `os`,
`pathlib`, `pystray`, `re`, `secrets`, `shutil`, `socket`, `ssl`, `stat`, `struct`, `subprocess`, `sys`,
`tempfile`, `threading`, `time`, `tkinter`, `types`, `typing`, `urllib`, `warnings`. An import of any other fails
the test (`logging` and every HTTP client library among them).

Of these, the ones that can carry data into or out of the process are `cryptography`, `keyring`, `getpass`,
`tkinter`, `socket`, `ssl`, `http`, `urllib`, `subprocess`, `multiprocessing`, `ctypes`, `msvcrt`, `fcntl`,
`tempfile` and `shutil`. For each, the table names the skill modules allowed to import it and the exact symbols
each takes; an import anywhere else, or one symbol more, fails. A symbol is counted whatever its form: `import x
as y`, `from x import a as b`, a re-export through another module of the skill (`from secret_store.envelope import
AESGCM`), a name bound to the symbol later (`user32 = ctypes.windll.user32`) and `getattr(obj, "literal")`.
Symbols are written as the import name followed by the attribute path used, three components at most.

| External module | Skill module: exact symbols taken |
|---|---|
| `cryptography.exceptions` | `portable_vault.py`, `secret_store/envelope.py`, `secret_store/hpke.py`, `secret_store/recovery_package.py`, `token_relay_backend.py`: InvalidTag. `secret_store/policy.py`, `secret_store/signing.py`: InvalidSignature |
| `cryptography.hazmat.primitives` | `secret_store/recovery.py`: hashes, hashes.SHA256 |
| `cryptography.hazmat.primitives.asymmetric.ed25519` | `secret_store/checkpoint.py`, `secret_store/signing.py`: Ed25519PrivateKey, Ed25519PublicKey. `secret_store/keys.py`: those two, Ed25519PrivateKey.from_private_bytes, Ed25519PrivateKey.generate. `secret_store/policy.py`: those two, Ed25519PublicKey.from_public_bytes. `secret_store/recovery.py`: Ed25519PrivateKey, Ed25519PrivateKey.from_private_bytes. `secret_store/recovery_package.py`: Ed25519PublicKey. `secret_store/store.py`, `secret_store/store_ops.py`: Ed25519PrivateKey |
| `cryptography.hazmat.primitives.asymmetric.x25519` | `secret_store/envelope.py`, `secret_store/recovery_package.py`: X25519PrivateKey, X25519PublicKey. `secret_store/hpke.py`: those two, X25519PrivateKey.from_private_bytes, X25519PrivateKey.generate, X25519PublicKey.from_public_bytes. `secret_store/keys.py`: those two, X25519PrivateKey.from_private_bytes, X25519PrivateKey.generate. `secret_store/policy.py`: X25519PublicKey, X25519PublicKey.from_public_bytes. `secret_store/recovery.py`: X25519PrivateKey, X25519PrivateKey.from_private_bytes. `secret_store/store.py`: X25519PrivateKey |
| `cryptography.hazmat.primitives.ciphers.aead` | `portable_vault.py`, `secret_store/hpke.py`, `token_relay_backend.py`: AESGCM. `secret_store/envelope.py`, `secret_store/recovery_package.py`: AESGCM, AESGCM.generate_key |
| `cryptography.hazmat.primitives.kdf.hkdf` | `secret_store/recovery.py`: HKDF |
| `cryptography.hazmat.primitives.serialization` | `secret_store/hpke.py`: Encoding, Encoding.Raw, PublicFormat, PublicFormat.Raw. `secret_store/keys.py`: those four, NoEncryption, PrivateFormat, PrivateFormat.Raw |
| `ctypes` | `secret_store/fileio.py`: WinDLL, WinError, get_last_error, wintypes, wintypes.BOOL, wintypes.DWORD, wintypes.LPCWSTR (MoveFileExW with write-through). `vault_agent_runtime.py`: CDLL, POINTER, Structure, WinDLL, byref, c_int, c_long, c_long.from_buffer, c_ubyte, c_ushort, c_void_p, c_void_p.from_buffer, cast, create_string_buffer, get_errno, get_last_error, sizeof, wintypes and its BOOL, DWORD, HANDLE, LPCWSTR, LPWSTR, ULONG, WORD (`make_private` and `is_private`: advapi32 and kernel32 through WinDLL – the process token's user, the access list and the owner set and read back; on Linux the C library's `fstatfs` through CDLL, into a zeroed 1,024-byte buffer, for the file system's type); windll, windll.kernel32, windll.kernel32.CloseHandle, windll.kernel32.OpenProcess (is a process alive). `vault_credentials.py`: byref, c_ulong, c_void_p, windll, windll.kernel32, windll.kernel32.GetConsoleMode (is there a console). `vault_tray.py`: Structure, WINFUNCTYPE, byref, c_int, c_ssize_t, c_void_p, create_unicode_buffer, windll, windll.kernel32, windll.kernel32.GetModuleHandleW, windll.user32 and its AdjustWindowRectEx, CreateWindowExW, DefWindowProcW (argtypes, restype), DestroyWindow, DispatchMessageW, GetMessageW, GetWindowTextLengthW, GetWindowTextW, IsDialogMessageW, LoadCursorW, MessageBoxW, PostMessageW (argtypes, restype; closes the passphrase window when the agent stops), PostQuitMessage, RegisterClassW, SendMessageW (argtypes, restype), SetFocus, SetForegroundWindow, SetWindowPos, ShowWindow, SystemParametersInfoW, TranslateMessage, UpdateWindow; wintypes and its BOOL, HANDLE, HBRUSH, HICON, HINSTANCE, HWND, LONG, LPARAM, LPCWSTR, MSG, UINT, WPARAM (the passphrase dialog) |
| `fcntl` | `secret_store/fileio.py`, `secret_store/repo.py`, `vault_agent.py`: LOCK_EX, LOCK_NB, LOCK_UN, flock |
| `getpass` | `token_relay.py`, `vault_credentials.py`, `vaultctl.py`: GetPassWarning, getpass |
| `http.client` | `token_endpoint.py`: HTTPSConnection |
| `keyring` | `secret_store/keys.py`: get_keyring |
| `msvcrt` | `secret_store/fileio.py`, `secret_store/repo.py`, `vault_agent.py`: LK_NBLCK, LK_UNLCK, locking. `vault_credentials.py`: get_osfhandle |
| `multiprocessing` | `vault_agent.py`: AuthenticationError |
| `multiprocessing.connection` | `vault_agent.py`: Client (one connection without a key, to end a waiting accept after `_keep_state` shut the agent down), Listener. `vault_broker_client.py`: Client |
| `shutil` | `migrate_to_store.py`: copyfile (the backup, a byte copy of ciphertext). `secret_store/recovery_package.py`, `secret_store/team.py`: rmtree |
| `socket` | `secret_store/store_ops.py`, `token_relay_store.py`: gethostname |
| `ssl` | `token_endpoint.py`: create_default_context |
| `subprocess` | `brain_secrets.py`, `secret_store/recovery_package.py`, `secret_store/store.py`, `secret_store/team.py`, `vault_credentials.py`, `vaultctl.py`: run. `secret_store/repo.py`: CompletedProcess, PIPE, Popen (the one launch of `git commit`), run. `token_relay_backend.py`: TimeoutExpired, run |
| `tempfile` | `portable_vault.py`: gettempdir, mkstemp. `secret_store/recovery_package.py`: TemporaryDirectory, mkstemp. `vault_agent_runtime.py`: mkstemp |
| `tkinter` | `secret_window.py`: BooleanVar, Button, Checkbutton, Entry, Frame, Label, TclError, Tk |
| `urllib.parse` | `token_endpoint.py`: urlencode, urlsplit. `token_relay_backend.py`: quote |
| `urllib.request` | `token_endpoint.py`: getproxies, proxy_bypass |

Where a module of the no-credential table holds one of these imports, the test requires a reason: `policy.py`,
`checkpoint.py` and `signing.py` take key types and `InvalidSignature` for signatures and public keys, never the
cipher or key bytes; `fileio.py` takes the lock calls and the write-through move.

### Forms that need no import

The exact forms and the functions allowed each. A use anywhere else fails; so does a listed function that no
longer uses the form.

| Form | Allowed in |
|---|---|
| the terminal: `print`, or a reference to `sys.stdout` or `sys.stderr` (names, presence and fingerprints only, except the two sinks `vaultctl.py` `main` and `token_relay.py` `main` below) | `brain_secrets.py` `_delete`, `_recovery_package`, `_restore`, `_unfinished`, `main`; `migrate_to_store.py` `main`, `migrate`, `rollback`; `token_relay.py` `_seed`, `_status`, `main`; `token_relay_store.py` `RelayedStore._warn`; `vault_agent.py` `VaultAgent._serve_with_listener`, `_diagnose.write` (in a bounded daemon thread, best effort, only when standard error exists: why a rewrite could not be proved private, or why the agent ends its process), `main`; `vault_credentials.py` `_cancelled`, `_put_entry_window`, `main`; `vaultctl.py` `main` |
| `input()`: a typed confirmation (an entry name, a write id), never a value | `brain_secrets.py` `_delete`, `_unfinished`; `vault_credentials.py` `main` |
| `sys.stdin.read`: a value piped in | `vault_credentials.py` `_secret_value` (put --stdin) |
| an environment write: `os.environ[...] =`, `del`, `update`, `pop`, `setdefault`, `clear`, `os.putenv`, `os.unsetenv` | `token_relay.py` `main` (PORTABLE_VAULT_PATH, a path) |
| a file write: `open` or `Path.open` in a writing mode, `os.fdopen`, `write_text`, `write_bytes`, `os.replace`, `os.rename`, `tempfile.mkstemp`, `NamedTemporaryFile`, `shutil.copyfile`, `copy`, `copy2`, `copytree`, `move` | `migrate_to_store.py` `_backup`, `_migrate`; `migration_lock.py` `MigrationLock._create`; `portable_vault.py` `PortableVault._write_unlocked`, `write_migration_marker`; `secret_store/checkpoint.py` `save`; `secret_store/enrol.py` `_save_pending`; `secret_store/fileio.py` `locked`, `write_durable`; `secret_store/recovery_package.py` `_write_atomic`, `restore`; `secret_store/repo.py` `SecretRepo._set_state`, `SecretRepo._stage`, `SecretRepo.clone_or_open`, `repo_lock`; `secret_store/store.py` `SecretStore._save_pin`; `secret_store/store_ops.py` `write_marker`, `write_upkeep_error`; `token_relay_store.py` `holder_name`; `vault_agent.py` `VaultAgent._acquire_singleton`; `vault_agent_runtime.py` `log_tray`, `write_state` |
| reflection: `eval`, `exec`, `__import__`, `compile`, `globals`, `locals`, `vars`; `getattr`, `setattr` or `delattr` with a name that is not a literal | `secret_store/store_ops.py` `store_status` (getattr over a tuple of two literal attribute names) |
| the string `PORTABLE_VAULT_PASSPHRASE`: read from the environment, or removed from a child's | `portable_vault.py` `PortableVaultJsonStore.__init__`; `vault_credentials.py` `_passphrase`, `_credential_environment`; `vaultctl.py` `_mapped_environment` |

### Primitives

The functions in which a credential first exists in the clear in the process. The test fails when a function
outside this table and the sinks uses one of the library symbols beneath (next table), and when a function calls
a primitive, or names it without calling it (assigns, passes, returns or stores it; `getattr` with its literal
name), without being one of its reviewed direct callers.

| Id | Function | What first exists here | Reviewed direct callers |
|---|---|---|---|
| open | `secret_store/envelope.py` `open_` | the payload of a store object: static values and kinds, a sign-in record, a grant, an index, a journal, pending-write or hand-over record | `secret_store/store.py` `SecretStore._open_object` (the store's one reader); `secret_store/accept.py` `_content` (every object this computer reads when a commit is judged); `secret_store/journal.py` `Journal.read`; `secret_store/pending.py` `PendingWrites.read`; `secret_store/replace_ops.py` `_open` (a hand-over file), `discard_retired` (the entry name of each journal record) |
| hpke-open | `secret_store/hpke.py` `open_` | the data key of an object or package; the enrolment challenge | `secret_store/envelope.py` `open_`; `secret_store/recovery_package.py` `_open`; `secret_store/enrol.py` `prove` |
| package-open | `secret_store/recovery_package.py` `_open` | the package plaintext: the signed checkpoint and the Git bundle of sealed objects (listed because it calls the cipher's decryption) | `secret_store/recovery_package.py` `restore` |
| vault-load | `portable_vault.py` `PortableVault._load_unlocked` | the whole old vault | `PortableVault.load`, `change_passphrase`, `set_fields`, `delete_entry`, `delete_field` (its own read-modify-write) |
| relay-decrypt | `token_relay_backend.py` `decrypt_token` | the relayed token record | `token_relay_store.py` `RelayedStore._verified` |
| keychain-read | `secret_store/keys.py` `load_private_keys` | this computer's private keys from the keychain | `secret_store/store.py` `SecretStore._identity` (once per store object) |
| token-endpoint | `token_endpoint.py` `post_token` | the token endpoint's answer (also a sink: the request carries the refresh token or code) | none under `scripts/`: the library connectors call it (section "Library connectors") |
| window | `secret_window.py` `_dialog` | values typed into the masked window: secrets, passphrases, recovery words | `secret_window.py` `ask_new_passphrase`, `ask_secrets` |
| prompt-passphrase | `vault_credentials.py` `_passphrase` | the vault passphrase from the hidden prompt or PORTABLE_VAULT_PASSPHRASE | `vault_credentials.py` `_new_passphrase`, `main` |
| prompt-value | `vault_credentials.py` `_secret_value` | a value from the hidden prompt or standard input | `vault_credentials.py` `main` (put, put-entry) |
| vaultctl-prompt | `vaultctl.py` `_hidden_passphrase` | the passphrase or a value from the hidden prompt | `vaultctl.py` `main` (unlock, secret-put) |
| relay-prompt | `token_relay.py` `_hidden_input` | the relay key from the hidden prompt | `token_relay.py` `main` (key-import) |
| tray-dialog | `vault_tray.py` `_win_password_dialog` | the passphrase from the Win32 dialog | `vault_tray.py` `_prompt_passphrase.ui` (its own thread, with a time limit) |
| session-passphrase | `portable_vault.py` `PortableVaultJsonStore` (its `__init__`) | PORTABLE_VAULT_PASSPHRASE from the environment | `token_relay.py` `_status`, `_seed` |
| agent-client | `vault_broker_client.py` `broker_request` (also stored as `_broker_request`) | the agent's answer: values, records, access tokens (also a sink: the request carries a value or the unlock passphrase, and the authentication token in every request) | the rows of "Reviewed callers" above with broker_request: `migrate_to_store.py` `main`; `portable_vault.py` `BrokerOAuthStore.__init__`, `clear`, `load`, `save`, `store_mode`, `sync_store`; `token_relay.py` `_store_key`, `read_relay_key`; `vault_broker_client.py` `_wait_for_refresher`, `broker_status`, `store_refresh`, `store_refresh.end`; `vault_credentials.py` `_put_entry_window`, `_try_broker_fields`, `main`; `vaultctl.py` `_mapped_environment`, `main` |
| agent-pipe | `vault_agent.py` `VaultAgent._serve_connection` | the request from the pipe: a passphrase, a value (`handle` compares its token; also a sink: the reply) | `vault_agent.py` `VaultAgent._accept_loop` (one thread per admitted connection) |
| agent-auth-make | `vault_agent.py` `VaultAgent` (its `__init__`) | the agent's authentication token and pipe key, made fresh at each start (`secrets.token_hex`, `secrets.token_bytes`); `serve_forever` gives the key to the `Listener` | `vault_agent.py` `build_agent` (the one way serve and the tray build the agent); `vault_tray.py` `VaultTrayApp._start_broker` (reads `LOCK_WAIT_SECONDS` only) |
| agent-state-read | `vault_agent_runtime.py` `read_state` | the token and key first in the client process, from the state file | `vault_broker_client.py` `_connect` (the client's one read); `vault_agent.py` `VaultAgent._keep_state` (compares the file with its own payload); `vault_agent_runtime.py` `clear_state` (the pid only); `vault_tray.py` `VaultTrayApp._start_broker` (the pid only) |
| agent-connect | `vault_broker_client.py` `_connect` | spends the key in the pipe's handshake (`Client(..., authkey=...)`) and returns the token to `broker_request` (also a sink: the key goes into the handshake) | `vault_broker_client.py` `broker_request` (every request) |
| keygen | `secret_store/keys.py` `generate_key_pairs` | new private keys | `secret_store/store.py` `SecretStore.init_personal`; `secret_store/enrol.py` `request`; `secret_store/team.py` `TeamStore.init_team` |
| words | `secret_store/recovery.py` `generate_mnemonic` | new recovery words | `secret_store/store.py` `SecretStore.init_personal`; `secret_store/team.py` `TeamStore.init_team` |
| recovery-keys | `secret_store/recovery.py` `derive_recovery_keys` | the recovery keys from typed words | `secret_store/store.py` `SecretStore.init_personal`, `SecretStore.restore_from_package`; `secret_store/team.py` `TeamStore.init_team` |
| relay-key | `token_relay_backend.py` `new_key_text` | a new relay key | `token_relay.py` `main` (key-new) |

### Sinks

The functions that write or send cleartext. The journal, the pending-write records and the hand-over file are
sealed by `envelope.seal` in `Journal.write`, `PendingWrites.write` and `replace_ops._write`, which are its
reviewed callers; the ciphertext then goes to disk through `fileio.write_durable`. The store objects are sealed in
`store_ops.seal_object` and `oauth_ops.seal_revision` and committed by `repo.py`.

| Id | Function | What leaves here | Reviewed direct callers |
|---|---|---|---|
| seal | `secret_store/envelope.py` `seal` | encryption into a store object (`store_ops.seal_object`, `oauth_ops.seal_revision`), a journal record (`Journal.write`), a pending-write record (`PendingWrites.write`), a hand-over file (`replace_ops._write`) | those five |
| hpke-seal | `secret_store/hpke.py` `seal` | a data key wrapped to a reader; the sealed challenge | `secret_store/envelope.py` `seal`; `secret_store/recovery_package.py` `build`; `secret_store/enrol.py` `answer` |
| package | `secret_store/recovery_package.py` `build` | the recovery package | `secret_store/store.py` `SecretStore.refresh_recovery_package` (weekly, or after a policy change) |
| keychain-write | `secret_store/keys.py` `store_private_keys` | the keychain (it also reads, to refuse an overwrite) | `secret_store/store.py` `SecretStore.init_personal`; `secret_store/enrol.py` `request`; `secret_store/team.py` `TeamStore.init_team` |
| vault-write | `portable_vault.py` `PortableVault._write_unlocked` | the old vault file (migration, rollback, and every write while the store is off) | `PortableVault.initialize`, `save`, `change_passphrase`, `set_fields`, `delete_entry`, `delete_field` |
| relay-encrypt | `token_relay_backend.py` `encrypt_token` | the relay record | `token_relay_backend.py` `build_record` |
| agent-pipe | `vault_agent.py` `VaultAgent._serve_connection` | the agent's reply to its caller | as above |
| agent-state-write | `vault_agent_runtime.py` `write_state` | the agent's token and key in the clear, written only into the published file, made private while empty, proved private in place before the first byte (`is_private`) and again after the last, through a handle kept open that empties the file on any failure after the first byte (or `NotPrivate` says content remains), inside a folder proved private the same way; proved on Windows and on Linux (the ext family and tmpfs only); macOS and every other system refused; the agent does not start, or stops, when that cannot be proved (`NotPrivate`), and its shutdown is a barrier after which nothing is served or answered | `vault_agent.py` `VaultAgent._serve_with_listener` (once the listener is up; `serve_forever` fences any failure), `VaultAgent._keep_state` (again when the file went missing) |
| agent-connect | `vault_broker_client.py` `_connect` | the key into the pipe's handshake | as above |
| token-endpoint | `token_endpoint.py` `post_token` | the request to the token endpoint | as above |
| agent-client | `vault_broker_client.py` `broker_request` | the request to the agent | as above |
| vaultctl-main | `vaultctl.py` `main` | the terminal: `access-token` prints the token, for piping; a child's environment: `run` | the command line (`<module>`) |
| relay-main | `token_relay.py` `main` | the terminal: `key-export` prints the relay key, to a terminal only, never a pipe | the command line |
| credentials-main | `vault_credentials.py` `main` | a child's environment: `run`, `session` | the command line |
| words-window | `secret_window.py` `show_recovery_words` | the screen: the recovery words, once, behind a mask until shown | `secret_store/store.py` `_default_words_window` (init, team-init) |

Library symbols beneath the primitives and sinks, and the only functions allowed to use each (through an alias, a
bound name or `getattr` with a literal too): `decrypt` in `envelope.open_`, `hpke.open_`, `recovery_package._open`,
`PortableVault._load_unlocked`, `decrypt_token`; `encrypt` in `envelope.seal`, `hpke.seal`, `recovery_package.build`,
`PortableVault._write_unlocked`, `encrypt_token`; `generate_key` in `envelope.seal`, `recovery_package.build`;
`get_password` in `keys.load_private_keys`, `keys.store_private_keys`; `set_password` in `keys.store_private_keys`;
`getpass` in `token_relay._hidden_input`, `vault_credentials._passphrase`, `vault_credentials._secret_value`,
`vaultctl._hidden_passphrase`; `scrypt` in `portable_vault._derive_key`, `PortableVault._write_unlocked`; `derive`
in `recovery._hkdf`; `from_private_bytes` in `keys.load_private_keys`, `recovery.derive_recovery_keys`,
`hpke.derive_key_pair` (the RFC test vectors; no caller under `scripts/`); `private_bytes` in `keys.raw_private`;
`generate` in `keys.generate_key_pairs`, `hpke.load_public_key`, `hpke.encap` (ephemeral keys); `exchange` in
`hpke._dh`; `Entry` (the masked field) in `secret_window._dialog`; `GetWindowTextW` in
`vault_tray._win_password_dialog.wndproc`; `recv` and `send` in `VaultAgent._serve_connection`, `broker_request`.

### Public operations

Read from the code: every subcommand of every argument parser under `scripts/` (a module that builds an
`ArgumentParser` and the names it gives `add_parser` or `choices`), and every name `VaultAgent.handle` dispatches
on (its comparisons, the frozensets `VAULT_OPS` and `STORE_OPS`, and `shutdown` in `_serve_connection`). An
operation the code gains and this table does not name fails the test, as does a row the code no longer has. What
each uses is a person's reading of the code, corroborated by the runtime recorder: the scenario named produced
every pair of "Uses"; "May also use" names pairs another branch adds (a pull with new commits, a computer's first
open, a hand-over file present), each explained in the note, which the recorder accepts but no scenario is held
to; `window`, `words-window` and `tray-dialog` need a display, and their callers run with the typed values
injected. `open` always brings `hpke-open` (the object's data key) and `package` brings `hpke-seal`. Every operation
that goes through the agent client reads the state file (`agent-state-read`) and spends the key (`agent-connect`)
before its request; the scenarios' stand-in for the agent client answers in-process without a state file, so those
two pairs are excused for such an operation and are produced instead by the scenario agent-state (the row "the
agent's state file"), while `agent-connect` needs the real pipe and is never run by a test. Behind every command
line that talks to the agent, the stand-in answers through the in-process agent's pipe handler, so `agent-pipe` and
the agent's own pairs are recorded under the command too. The ids are those of the two tables above.

| Parser | Operation | Uses | May also use | Scenario | Note |
|---|---|---|---|---|---|
| `brain_secrets.py` | `init` | words, recovery-keys, keygen, keychain-write, package, hpke-seal | | cli-init | the words window needs a display: the callback is injected |
| | `status` | keychain-read | open, hpke-open | cli-status | names, state and pending-write ids only; a hand-over file or a pending-write record, when one exists, is opened to name it |
| | `list` | keychain-read, open, hpke-open | | cli-list | the index: entry names |
| | `put` | keychain-read, open, hpke-open, seal, hpke-seal, package, window | | cli-put | the typed values are injected; the record, the object, the index and the package follow |
| | `get-check` | keychain-read, open, hpke-open | | cli-get-check | field names printed |
| | `delete` | keychain-read, open, hpke-open, seal, hpke-seal, package | | cli-delete | tombstones and the index, of the whole entry or with `--field` of exactly one sign-in's oauth and grant objects (`replace_ops.delete_signin`, `delete_ops.build_signin_delete`); the typed name is a confirmation |
| | `recovery-package` | keychain-read, package, hpke-seal | open, hpke-open | cli-recovery-package | a pull with new commits opens every object this computer reads |
| | `restore` | recovery-keys, package-open, hpke-open, open, window | | cli-restore | the words are injected; every commit of the bundle is verified again |
| | `replace-signin` | keychain-read, open, hpke-open, seal, hpke-seal, package | | cli-replace-signin | the hand-over file, the tombstones and the index |
| | `enrol-request` | keychain-read, keygen, keychain-write, hpke-open, package, hpke-seal | | cli-enrol | `--fingerprint` makes keys, a signed request and the computer's first package; `--request` opens the challenge |
| | `enrol-approve` | keychain-read, open, hpke-open, seal, hpke-seal, package | | cli-enrol | the challenge sealed, then every object re-keyed |
| | `team-init` | keychain-read, words, recovery-keys, keygen, keychain-write, package, hpke-seal | | cli-team | as init, for the team repository |
| | `team-admit`, `team-groups` | keychain-read, open, hpke-open, seal, hpke-seal, package | | cli-team | objects whose readers change are re-keyed |
| | `team-remove` | keychain-read, open, hpke-open, seal, hpke-seal, package | | cli-team | every object the removed computer could read is re-keyed |
| | `handover-release` | keychain-read, open, hpke-open, seal, hpke-seal | | cli-handover | the grant re-sealed to the new refresher |
| | `handover-accept` | keychain-read, open, hpke-open, package, hpke-seal | | cli-handover | the policy change and the prepared revision, then the package; no object is re-keyed (the moved grant is the prepared revision) |
| | `supersede` | keychain-read, open, hpke-open, package, hpke-seal | | cli-supersede | no object is re-keyed (a disabled refresher changes no readers); needs a verified provider profile, none is, so the scenario patches the refusal away, and every other computer then refuses that commit |
| | `grant-scan` | keychain-read, open, hpke-open | | cli-grant-scan | static payloads opened; names printed |
| | `unfinished` | keychain-read, open, hpke-open, seal, hpke-seal | package | cli-unfinished | list and `--discard` read records; `--apply` writes through the normal path, and a record that adds an entry changes the policy |
| `migrate_to_store.py` | `migrate` | agent-client, agent-state-read, agent-connect, agent-pipe, vault-load, vault-write, keychain-read, open, hpke-open, seal, hpke-seal, package | | migrate | the old vault through the agent; every entry into the store; the scrub |
| | `rollback` | agent-client, agent-state-read, agent-connect, agent-pipe, vault-load, vault-write, keychain-read, open, hpke-open | | rollback | static values read from the store and restored through the agent: `vault_restore_static`, then `vault_restore_marked_static` for fields under a migrated sign-in's name, then the marker cleared only when every restore succeeded |
| `vaultctl.py` | `status` | agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main, keychain-read | open, hpke-open | vaultctl | status only; `main` is the sink function for every command; the agent loads its keys at its first operation and opens a hand-over file or pending record to name it |
| | `unlock` | vaultctl-prompt, agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main, vault-load | | vaultctl | the passphrase, checked by the agent against the vault |
| | `lock` | agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main | | vaultctl | no credential |
| | `access-token` | agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main, open, hpke-open | keychain-read | vaultctl | the sign-in record opened; the access token printed, for piping |
| | `secret-put` | vaultctl-prompt, agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main, open, hpke-open, seal, hpke-seal | keychain-read, package | vaultctl | a typed value to the agent: its record and object; the package when the entry is new |
| | `run` | agent-client, agent-state-read, agent-connect, agent-pipe, vaultctl-main, open, hpke-open | keychain-read | vaultctl | mapped fields read and put into the child's environment |
| `vault_credentials.py` | `init` | prompt-passphrase, vault-write, credentials-main | window | vault-credentials | `--window` asks in the masked window, which needs a display |
| | `check`, `list` | prompt-passphrase, vault-load, credentials-main | | vault-credentials | |
| | `change-passphrase`, `delete-entry`, `delete-field`, `init-json` | prompt-passphrase, vault-load, vault-write, credentials-main | | vault-credentials | the typed name is a confirmation |
| | `put` | agent-client, agent-state-read, agent-connect, agent-pipe, prompt-passphrase, prompt-value, vault-load, vault-write, credentials-main | | vault-credentials | through the unlocked agent, else the vault |
| | `put-entry` | prompt-passphrase, prompt-value, vault-load, vault-write, credentials-main | window, agent-client, agent-state-read, agent-connect, agent-pipe | vault-credentials | `--window` asks in the masked window, which needs a display, and with the agent unlocked writes through it |
| | `run` | agent-client, agent-state-read, agent-connect, agent-pipe, prompt-passphrase, vault-load, credentials-main | | vault-credentials | mapped fields into the child's environment |
| | `session` | prompt-passphrase, vault-load, credentials-main | agent-client, agent-state-read, agent-connect, agent-pipe | vault-credentials | mapped fields into the shell's environment; through the unlocked agent when it answers |
| `token_relay.py` | `status` | session-passphrase, vault-load, relay-main | | token-relay | versions and holders printed |
| | `key-new` | relay-key, agent-client, agent-state-read, agent-connect, agent-pipe, vault-load, vault-write, relay-main | | token-relay | a new key, checked for an old one and stored through the agent (vault-backed, the store off) |
| | `key-import` | relay-prompt, agent-client, agent-state-read, agent-connect, agent-pipe, vault-load, vault-write, relay-main | | token-relay | a typed key stored through the agent |
| | `key-export` | agent-client, agent-state-read, agent-connect, agent-pipe, vault-load, relay-main | | token-relay | the key read through the agent and printed, to a terminal only |
| | `seed` | session-passphrase, vault-load, vault-write, relay-encrypt, relay-main | agent-client, agent-state-read, agent-connect, agent-pipe | token-relay | the local token pushed as the shared record and saved with its version; through the agent when it is unlocked |
| `vault_agent.py` | `serve` | agent-auth-make, agent-state-write, agent-state-read, agent-pipe | | none | starts the real listener on this user's pipe with the key the agent made, writes the token and key to the state file and reads it back to keep it there; its one caller of the pipe primitive, `_serve_connection`, runs with a fake connection in every agent scenario, and the state file is written and read in a temporary folder by the scenario agent-state |
| `vault_tray.py` | `(the tray)` | tray-dialog, agent-auth-make, agent-state-write, agent-state-read, agent-pipe | | none | pystray and the Win32 dialog need a desktop; the tray builds the same agent as `serve` (its token and key) and runs `serve_forever` in its own process (`VaultTrayApp._start_broker`), which writes the token and key to the state file and accepts connections; the tray reads the state file for its pid and hands the typed passphrase to `agent.unlock` |
| agent | `status` | agent-pipe, keychain-read | open, hpke-open | agent-store, agent-vault | state only; with the store, a hand-over file or pending-write record, when one exists, is opened to name it |
| | `ping`, `lock`, `release_refresh`, `shutdown` | agent-pipe | | agent-store | no credential: a lock released, the held passphrase dropped, a refused unknown operation |
| | `unlock` | agent-pipe, vault-load | | agent-store, agent-vault | the passphrase checked against the vault, then held |
| | `get_fields`, `get_json`, `get_access_token` | agent-pipe, keychain-read, open, hpke-open, vault-load | | agent-store, agent-vault | static fields, a sign-in record by role, the access token; the vault when the store is off |
| | `set_json`, `set_text` | agent-pipe, keychain-read, open, hpke-open, seal, hpke-seal, package, vault-load, vault-write | | agent-store, agent-vault | a typed value with its record, or a refresh's save; the vault when the store is off |
| | `begin_refresh` | agent-pipe, keychain-read, open, hpke-open, seal, hpke-seal | | agent-store | the record read; the calling record sealed |
| | `abort_refresh` | agent-pipe, open, hpke-open | | agent-store | the calling record read and removed |
| | `poll_refresh` | agent-pipe, keychain-read, open, hpke-open | package, hpke-seal | agent-store | the published record after a pull; a computer's first open builds its recovery package |
| | `sync_store` | agent-pipe, keychain-read | open, hpke-open | agent-store | a pull; new commits open every object this computer reads |
| | `clear_signin` | agent-pipe, keychain-read, open, hpke-open, seal, hpke-seal | | agent-store | a revision without the tokens |
| | `vault_list_entries`, `vault_get_fields`, `vault_get_json`, `vault_verify_copy` | agent-pipe, vault-load | | agent-vault | names and kinds; values and a sign-in for the migration; the backup copy's names |
| | `vault_scrub_signin`, `vault_restore_static`, `vault_restore_marked_static` | agent-pipe, vault-load, vault-write | | agent-vault | the tokens removed; static values restored under names the marker does not hold, or (marked) only under names it holds, the marker left as it is; each request is checked whole (`static_restore`) before one write |
| | `vault_clear_migration_marker` | agent-pipe | | agent-vault | the marker file only |
| (the agent) | the agent's state file | agent-auth-make, agent-state-write, agent-state-read | | agent-state | an agent made in-process, its token and key written to and read from a state file in a temporary folder, then removed; `agent-connect` needs the real pipe and is never run |
| (a connector) | the refresh path | token-endpoint, session-passphrase, agent-client, agent-state-read, agent-connect, agent-pipe, keychain-read, open, hpke-open, seal, hpke-seal | | refresh-path | a connector's `PortableVaultJsonStore` (the session passphrase read, unused with the agent), its token call under the store's refresh: `post_token`, the agent's `begin_refresh`, the publication |

### Modules

Every module under `scripts/` and `scripts/secret_store/` is in exactly one of the two tables; a file in neither
or in both fails the test. A module of the second table may not import a module of the first except the names
its exemption row allows, may take from a data-carrying external module only the symbols its row allows (with a
reason, above), and may use none of the forms (above). The runtime recorder fails when a module of the second
table is on the chain of frames to a primitive or sink.

Through these a credential passes in the clear:

| Module | What it reads, copies or rewrites |
|---|---|
| `brain_secrets.py` | typed values from the window (put) and the recovery words (restore); prints names only |
| `migrate_to_store.py` | every old-vault value read through the agent and copied into the store; the store's static values sent back to the agent at rollback |
| `portable_vault.py` | the whole old vault (decrypt, encrypt); sign-in records through the agent (`BrokerOAuthStore`); the session passphrase (`PortableVaultJsonStore`) |
| `secret_window.py` | typed secrets and passphrases; the recovery words shown |
| `token_endpoint.py` | the refresh token or code sent; the token answer |
| `token_relay.py` | the relay key (read, stored, printed by key-export); the token seeded |
| `token_relay_backend.py` | the token record encrypted and decrypted |
| `token_relay_store.py` | the token held, synced, pushed and adopted |
| `vault_agent.py` | every request's value and every answer; the unlock passphrase held in memory |
| `vault_agent_runtime.py` | the agent's IPC key and token, written to and read from the state file (written only into a file and a folder proved private to the user and the system account; the agent does not start, or stops, when that cannot be proved) |
| `vault_broker_client.py` | every request and answer; the IPC key read from the state file |
| `vault_credentials.py` | the passphrase and typed values; vault reads; a child's environment |
| `vault_tray.py` | the passphrase from the Win32 dialog to the agent |
| `vaultctl.py` | the passphrase and a typed value; the access token printed; a child's environment |
| `secret_store/accept.py` | the payload of every object this computer reads, opened to judge a commit |
| `secret_store/accept_rules.py` | an oauth payload and its baseline, compared field by field |
| `secret_store/broker_backend.py` | every value the agent serves or saves; the old vault's values for the migration |
| `secret_store/canonical.py` | the canonical bytes of every payload before encryption and after decryption |
| `secret_store/delete_ops.py` | no value: the tombstones it seals carry the empty payload `{}`; listed here because `build_delete` and `build_signin_delete` reach `envelope.seal` through `_tombstone_commit` and `seal_object` (the stricter class) |
| `secret_store/enrol.py` | new private keys; every object re-keyed at approval; the challenge |
| `secret_store/envelope.py` | the payload sealed and opened |
| `secret_store/handover.py` | the grant re-sealed to the new refresher; every object re-keyed |
| `secret_store/hpke.py` | data keys and the challenge: the cipher's seal and open |
| `secret_store/journal.py` | refresh records with the provider's answer |
| `secret_store/keys.py` | this computer's private keys, generated, stored and loaded |
| `secret_store/oauth_ops.py` | sign-in records, grants and static payloads read, merged, split and sealed |
| `secret_store/pending.py` | pending-write records with the typed values |
| `secret_store/recovery.py` | the recovery words and the keys derived from them |
| `secret_store/recovery_package.py` | the package: the data key, and the checkpoint and bundle it encrypts |
| `secret_store/replace_ops.py` | the kept shared settings of a replaced sign-in; journal records opened |
| `secret_store/repo.py` | no value of its own: git over sealed objects and the policy; listed here because `pull` runs the store's verify callback inside its frames, which opens every object this computer reads, so `SecretRepo.pull` is on every recorded chain to `open` (the stricter class) |
| `secret_store/static_fields.py` | every static payload: its values and kinds, read (`split`), copied (`build`, `merged`) and rewritten (`without`) |
| `secret_store/store.py` | every payload read (`get_record`, `get_typed`, `get_fields`, `static_payload`) and written; the recovery words at init and restore |
| `secret_store/store_ops.py` | payloads sealed (`build_put`, `seal_object`) and re-keyed (`build_policy_change`) |
| `secret_store/team.py` | the team recovery words and keys; every object re-keyed at a policy change |
| `secret_store/typed_write.py` | the typed plain and grant values of one write, and its record |

Through these none does:

| Module | Why | Imports from a credential module (exempt, with the names) |
|---|---|---|
| `migration_lock.py` | a lock file with a process id, a time and a command name | `portable_vault.py`: CredentialError; `vault_agent_runtime.py`: _pid_is_running (a process-id check; reads no state file) |
| `secret_store/__init__.py` | re-exports the error class | none |
| `secret_store/checkpoint.py` | object ids, revisions and hashes, signed with the key object | `canonical.py`: dumps, loads (the signed checkpoint); `keys.py`: key_id |
| `secret_store/errors.py` | the error classes | none |
| `secret_store/fileio.py` | locks, and bytes already sealed (the journal, pending and hand-over files) | none |
| `secret_store/policy.py` | public keys, assignments, groups and signatures | `canonical.py`: dumps (hashes and endorsement bytes); `hpke.py`: load_public_key; `keys.py`: key_id, raw_public |
| `secret_store/provider_profiles.py` | field names per provider | none |
| `secret_store/signing.py` | signatures over documents and sealed objects, with the key object | `canonical.py`: dumps (the bytes signed or verified) |

### The limit

These checks are exact about what they look at: the imports and the symbols taken, the forms, the functions
that call or name a primitive or a sink, the operations the parsers and the agent define, and the frames and
pairs the scenarios record. None of them follows a credential, an object that carries one, or a callback handed
from one function to another: a listed module that passes a value to a helper in the other table is not seen,
unless a scenario runs that path and the helper's frame appears on the recorded chain. None of them runs a branch
no scenario runs, and the scenarios run with fixtures (a fake keyring, in-process agents, bare local repositories,
an in-memory relay, injected typed values), not with a display, a keychain, a real agent or a provider. The
reasons given where an operation has no scenario, and the mapping of each operation to what it uses, are a
person's reading of the code, corroborated by the recorder for the paths it ran, not a result of a test. A static
call graph with call-site exemptions would follow the hand-overs; its measured size at `6119672` (744 functions,
2,875 attribute calls, 788 unresolved call sites that share a name with a function of the skill) is in the plan,
and it is a task of its own.

The proof of a private state file (`make_private`, `is_private` in `vault_agent_runtime.py`) has run for real on
Windows (NTFS) and on Linux, in WSL on the computer it was written on (`tests/test_state_private_posix.py`: ext4
and tmpfs, a second, unprivileged user id refused after the proof, a 9p folder refused). Never run, and therefore
refused: macOS (no proof is shipped for it; a task carries it) and every POSIX system but Linux, and on Linux
every file system but the ext family and tmpfs (XFS, Btrfs, F2FS, ZFS, NFS, CIFS, 9p, FUSE, overlay). On a refused
POSIX system `restrict_to_current_user` still sets the mode best effort, nothing proved. The proof covers the
runtime folder and the state file, not the folder's ancestors; SYSTEM and the Administrators group on Windows, and
root on Linux, can read by design.

## Open

- Row 24: with the store off, the agent's `get_fields` and `set_text` skip the marker check. A scrubbed record
  holds no token, so nothing can be spent.
- Row 14: migration backups keep old refresh tokens, encrypted, with no retention limit; status shows their age.
