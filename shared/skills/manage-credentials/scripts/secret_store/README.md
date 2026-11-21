---
id: secret-store-readme
title: Synced Secrets Store
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-20T19:22:05+10:00
updated: 2026-11-21T14:31:20+10:00
owner: brain-owner
---

# Synced secrets store

Read `/CONTRACT.md` first. This folder is the code of an opt-in credential provider for the
`manage-credentials` skill. It stays off until the owner accepts `PROPOSAL-synced-secrets-store`
and switches it on; until then the *Credential policy* vault rules in
`/shared/skills/manage-credentials/SKILL.md` apply unchanged.

## What it is

Secrets are kept as encrypted, signed files in private Git repositories. Each computer holds its
own keys in the operating system's keychain (Windows Credential Manager, the macOS login keychain
as a non-synchronising item, or the Linux Secret Service; any other backend fails closed). Nothing
is typed day to day: signing in to the computer is enough. A person reads their own secrets and
the team secrets of their groups; no server can read any of them.

## Rules

1. No secret value, private key or recovery word is ever written to Git, the chat, a log or a
   command argument. Values are typed only into the masked window; recovery and enrolment words
   are shown only in a local window.
2. Who can read an object changes only through a policy change signed by an administrator of that
   repository, judged against the current trusted policy; a commit that does not verify in full is
   refused whole.
3. Removing a person or a computer re-encrypts, in the same commit, every object it could read,
   and the command lists the provider secrets to change, because what was read cannot be recalled.
4. A rotating sign-in is handed to another refresher only through a signed release, or after a
   revocation the provider's profile proves complete; without such a profile it is never handed
   over, and an uncertain refresh leaves it blocked.
5. The policy names one refresher computer per rotating sign-in; only that computer calls the
   provider, and its refresh token is encrypted to it and the recovery key only.
6. While the store is on, the old credential store is closed: no path reads or writes a credential
   in it. The rule is enforced where the data is opened (the agent and the passphrase open), never
   caller by caller, and only the migration and rollback, under their lock, are let through.
7. A credential is never served from two places: moving to the store is one run that checks every
   copy, and a copy that fails its check is removed from the new place, never left live in both.
8. A refresh token is sent to the provider at most once. A failed refresh is sorted by fact into not
   sent, refused or uncertain; only the first two free the sign-in, and an uncertain one is ended by
   replacing the sign-in, never by a second try.
9. Every path that may reach a credential is on a reviewed list (`../../CREDENTIAL-PATHS.md`); a new
   caller fails the skill's tests until it is reviewed.

## Modules

Alphabetical, in `/shared/skills/manage-credentials/scripts/secret_store/`:

- `accept.py`, `accept_rules.py`: accept or refuse one whole commit.
- `bip39_english.txt`: the word list for recovery and enrolment words.
- `broker_backend.py`: the Vault Agent's store backend.
- `canonical.py`, `envelope.py`, `hpke.py`, `signing.py`: canonical form, objects, key wrapping, signatures.
- `checkpoint.py`: the signed local record of the newest epoch and revisions.
- `enrol.py`: the enrolment protocol.
- `handover.py`: the cooperative handover of a sign-in's refresher.
- `journal.py`: the refresh journal and the per-entry lock.
- `keys.py`: key pairs and the keychain allowlist.
- `oauth_ops.py`, `provider_profiles.py`, `provider_profiles.json`: rotating sign-ins and provider profiles.
- `policy.py`: the signed policy and trust root.
- `recovery.py`, `recovery_package.py`: recovery words and recovery packages.
- `repo.py`: the local clone, pull, push and lock.
- `store.py`, `store_ops.py`, `team.py`: the personal and team stores, configuration, administration.

Commands live beside the folder: `scripts/brain_secrets.py` and `scripts/migrate_to_store.py`.
Tests: `tests/test_secret_store_*.py`.

## Repositories and where things live

- Repositories, in setup order: `<login>/brain-secrets` (that person's secrets, that person only)
  and `<team>/brain-team-secrets` (shared secrets by group, every team member). Both are private.
- Clones sit beside the brain under the owner's project repositories folder, never inside a brain
  repository (the store refuses a clone inside the brain).
- Checkpoints, trust-root pins, enrolment state and journals sit in the per-user application data
  folder (`brain-secrets`), outside every clone.
- Recovery packages go by default to a `brain-secrets-recovery` folder in the person's own cloud
  drive when one is found (OneDrive through the `OneDrive` or `OneDriveConsumer` environment
  variable on Windows, iCloud Drive on macOS), otherwise to `recovery-packages` in that folder,
  and status then warns that the package is only on this computer; `recovery_package_dir` sets
  another place. A package older than seven days is rebuilt when the store opens (after the
  opening transaction) and after every policy change. A package is encrypted to the recovery key.
  While the Vault Agent serves the store it also runs a timer, at least every 6 hours: it pulls
  every store and rebuilds a package that is stale or does not match the current policy, with no
  credential request. A failed run is kept in `status` (`package_timer`, and `store_sync` for a pull)
  and in a `<package file name>.upkeep-error` file in the checkpoint folder on this computer (never
  in the package folder, which may be the drive that failed). The daily due check reads that file and
  reports the failure; the next run retries, and a success removes the file.
- Every file of one change is one commit with a generic message (`update`, `policy`, `recovery`).

## Roles

- Administrator: every policy change (admit and remove people and computers, create groups,
  assign objects, set refreshers). In a personal repository the person is the administrator.
- Member: reads and writes the entries of their groups; changes nothing in the policy.
- Recovery key: made from 24 words shown once, never stored on a computer; a reader of everything.

## Commands

Run from `/shared/skills/manage-credentials/scripts/`. Output names entries, fields, groups,
people and computers only. `--group` selects the team repository.

```text
python brain_secrets.py init                       first computer: keys, recovery words, repository
python brain_secrets.py status
python brain_secrets.py list [--group ops]
python brain_secrets.py put --entry "Example API" --secret api_key [--empty-json settings] [--group ops]
python brain_secrets.py get-check --entry "Example API"       field names only
python brain_secrets.py delete --entry "Example API"          type the name to confirm
python brain_secrets.py recovery-package [--team]
python brain_secrets.py restore [--team] --package FILE --target EMPTY_FOLDER   words in the masked window
python brain_secrets.py enrol-request [--team] --fingerprint F     new computer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer
python brain_secrets.py enrol-request [--team] --request ID        new computer, after the answer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer, to finish
python brain_secrets.py team-init --owner ORGANISATION
python brain_secrets.py team-admit --login L --group G [--group G]
python brain_secrets.py team-groups --create G | --login L --group G
python brain_secrets.py team-remove --login L [--computer C]
python brain_secrets.py handover-release --entry E --to PERSON/COMPUTER [--group ops]   old refresher
python brain_secrets.py handover-accept --entry E [--group ops]   an administrator's computer
python brain_secrets.py replace-signin E [--field F] [--group ops] [--even-if-working]   refresher, administrator
python migrate_to_store.py --dry-run               names only; then without it, [--replace]
python migrate_to_store.py rollback [--dry-run]    static secrets back to the old vault
```

Enrolment: the new computer runs `enrol-request --fingerprint`, the approver runs `enrol-approve`,
the new computer runs `enrol-request --request`, both screens show six words, and the approver
runs `enrol-approve` again once the words match. Each store has its own enrolment: a team
enrolment (`--team`) never covers the personal store, and the agent always serves the personal
store, so a new computer of a person is enrolled in the personal store as well; a computer that
opens a store it was never enrolled in is told so plainly, and a refused remote commit names the
rule that refused it. `migrate_to_store.py` needs the Vault Agent
unlocked on the old vault, makes a verified backup first, never changes the old vault and prints
no value; a clash with an existing entry stops it unless `--replace` is given. `put` sends a
grant field such as the client secret to the entry's grant, never to a static object.

Handover: the old refresher runs `handover-release`, which switches refreshing off there for good,
prepares the grant for the new computer and signs a release; an administrator's computer then runs
`handover-accept`, which commits the policy change, the release and the grant revision together.

Restore: `restore` takes the recovery words in the masked window, the package by path and a new or
empty target folder, reports how old the package is, and writes nothing when the words, the package
or the target are wrong. Replacing a sign-in: `replace-signin` ends an uncertain sign-in (or a working
one with `--even-if-working`) on its refresher, run by an administrator: the shared settings are kept
in a hand-over file beside the journal, one commit deletes the sign-in and retires both ids, and the
next browser sign-in under the same name gets the kept settings. `status` reports a hand-over file
whose sign-in was never completed. Only the sign-in's refresher may run it, and only if that
computer's key is an administrator's: a team member who became refresher through a handover is
refused, and nothing changes. `recovery-package --team` writes the team package; an unwritable
folder warns, writes the upkeep-error file and exits 1, as for the personal package.

## The cut-over

One run moves everything, in this order:

1. The Vault Agent is started and unlocked on the old vault while the store is off.
2. The store is switched on, and the agent is not restarted.
3. `migrate_to_store.py --dry-run` runs, then `migrate_to_store.py`.
4. The agent is restarted, so that it serves the store.

The rehearsal (`../../rehearsal/README.md`) runs this order with throwaway secrets.

`migrate_to_store.py` holds the migration lock beside the vault (`<vault>.migration.lock`, created
exclusively, naming its process and start time) for the whole run. It makes a verified backup, copies every entry and reads each back. A
verified sign-in loses its tokens in the old vault and is named in the migration marker
(`<vault>.migrated.json`); a sign-in that fails its read-back has its store copy removed in the same
run, the vault entry is left as it was, and the run names it and exits non-zero. The person signs
in again in the browser once the store is on.

What fails closed:

- With the store on, a Vault Agent whose backend is the old vault refuses every credential request
  with the restart message; the agent and the login tray are built by one function, which serves
  the store when it is on.
- With the store on, the passphrase open of the vault is refused; only the Vault Agent opens it,
  for the migration and rollback operations, while a live migration lock is held.
- The agent's scrub, restore-static and marker operations need a live lock; an absent, unreadable
  or stale lock (its process gone, or older than six hours) refuses, and a second migration cannot
  take a held lock.
- A connector's plain token file is refused while the store is on.
- Every legacy path refuses a sign-in named in the marker, store on or off. The marker, the
  migration record and the lock are ignored by the memory skeleton's `.gitignore`.

Rollback goes the same way round. The agent is unlocked on the old vault with the store off, and the
store is switched on without restarting the agent. `migrate_to_store.py rollback --dry-run` runs, then
`rollback`, and then the store is switched off. The rollback runs under the same lock and restores static secrets only from
the store's current value and clears the marker. It walks every static object of the store, not the old
vault's listing, so an entry or field created after the migration is restored too. The store holds text
only: a field the old vault holds keeps its kind there, and any other field is JSON exactly when its text
is the canonical form (sorted keys) of a JSON object, as `set_json` writes it. Each entry restored and
each that could not be (unreadable, a token-shaped value, or refused by the agent) is named; one that
could not ends with exit code 5 and the marker kept. It never writes a token out of the store, so every
migrated sign-in needs a browser sign-in afterwards.

## A failed refresh

Every token-endpoint call goes through `token_endpoint.post_token`: a new connection each time, https
only, never retried.

- **Not sent** (`ProviderNotCalled`): the connection, a proxy tunnel or the TLS handshake failed
  before any byte of the request was written. The journal record is removed; the next attempt
  refreshes normally.
- **Refused** (`ProviderRefused`): the token endpoint answered HTTP 400 or 401 with an OAuth error
  body. The record is removed. `invalid_grant` raises the connector's sign-in-needed error and a
  browser sign-in is allowed.
- **Uncertain**: anything else once the request was written (a time-out, a reset, HTTP 5xx, any
  other 4xx including 429, an unreadable answer). The record stays `calling`, the sign-in is
  blocked and is never retried with the old token; `replace-signin` ends it.

## Switching it on and off

On: create `config/secret-store.json` in the owner's memory folder for this skill, with
`"enabled": true` and `"person"` (the GitHub login); optional keys are `computer`,
`personal_repo_url`, `team_repo_url`, `personal_clone`, `team_clone`, `checkpoint_dir` and
`recovery_package_dir`. Unknown keys are refused. Off: set `"enabled": false` or remove the file;
the vault and its passphrase work as before. Without the file the store is off.

A configuration that cannot be read, has unknown keys, or is enabled without a `person` is fatal:
the Vault Agent refuses to start (exit code 2) and never serves the old vault in the store's place.
A Vault Agent started before the store was switched on reports no store backend; with the store on,
`vaultctl.py`, the broker client and the vault stores refuse it with "the Vault Agent was started
before the secrets store was switched on; restart it". The token relay is ignored while the store is
on: no relay is built, whatever `token-relay.json` lists, the store's journal decides every refresh,
and `vaultctl.py status` shows the ignored file as "Token relay".

## A computer that is not a sign-in's refresher

It reads the sign-in's access token and shared settings only. It never calls the provider and
cannot map the client secret; a request to refresh waits for the refresher to publish, or stops
with a message naming the refresher computer.

## Provider profiles

`provider_profiles.json` holds profiles for Xero, Google, HighLevel and Meta. None is verified: each
needs the provider's documentation plus a live test that revoking a refresh token retires the whole
grant and that a new browser sign-in makes a separate grant. Until a profile is verified, moving the
refresher away from an unreachable computer and recovery from an uncertain refresh are refused; an
uncertain sign-in is then replaced with `replace-signin`. The cooperative handover needs no profile.
