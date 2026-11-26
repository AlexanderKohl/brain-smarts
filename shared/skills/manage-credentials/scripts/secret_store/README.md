---
id: secret-store-readme
title: Synced Secrets Store
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-20T19:22:05+10:00
updated: 2026-11-26T17:08:00+10:00
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
- `pending.py`, `typed_write.py`: pending-write records of typed values, and the one function that
  makes a record and writes.
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
python brain_secrets.py delete --entry "Example API"          type the name to confirm; the whole entry
python brain_secrets.py delete --entry "Example API" --field F   administrator: that one sign-in only
python brain_secrets.py recovery-package [--team]
python brain_secrets.py restore [--team] --package FILE --target EMPTY_FOLDER   words in the masked window
python brain_secrets.py enrol-request [--team] --fingerprint F     new computer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer
python brain_secrets.py enrol-request [--team] --request ID        new computer, after the answer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer, to finish
python brain_secrets.py team-init --owner ORGANISATION_OR_LOGIN
python brain_secrets.py invite --login L --group G [--group G]   administrator: invite, wait, compare, enrol, admit
python setup_store.py [--join URL] [--fingerprint F]   a person's computer: the cut-over and joining, in one run
python brain_secrets.py team-admit --login L --group G [--group G]
python brain_secrets.py team-groups --create G | --login L --group G
python brain_secrets.py team-remove --login L [--computer C]
python brain_secrets.py handover-release --entry E --to PERSON/COMPUTER [--group ops]   old refresher
python brain_secrets.py handover-accept --entry E [--group ops]   an administrator's computer
python brain_secrets.py replace-signin E [--field F] [--group ops] [--even-if-working]   refresher
python brain_secrets.py unfinished [--team] [--apply ID | --discard ID]   pending writes kept here
python migrate_to_store.py --dry-run               names only; then without it, [--replace]
python migrate_to_store.py rollback [--dry-run]    static secrets back to the old vault
```

For a new team member, `invite` on the administrator's computer and `setup_store.py --join` on theirs
run the team enrolment below by themselves (`secret_store/invite.py`): each waits for the other's file
in the team repository, so only the fingerprint and the six words travel by hand.

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
whose sign-in was never completed. On a refresher whose key is not an administrator's (a team member
who became refresher through a handover) an uncertain sign-in is not replaced there: the command
changes nothing, names the administrator's step and exits 3, and the `calling` journal record keeps
refusing every refresh of it, offline, from a stale copy and across restarts. The step is the deletion
of that one sign-in (design section 7): an administrator runs `delete --entry E --field F --group G` on
their own computer, signs in again in the browser and hands the new sign-in back with
`handover-release` and `handover-accept`. `delete --field` makes the same one commit `replace-signin`
makes (`delete_ops.build_signin_delete`, through `replace_ops._delete`): the tombstones of the sign-in's
oauth and grant objects, the index without their two names, and the policy without its refresher
mapping and with both ids retired. The pair is the one the store's lookup returns for `E` and `F`, never
a scan of names, so the entry's plain fields, its other sign-ins and every other entry stay out of the
commit. A field that names no sign-in, a computer that is not an administrator's and a typed name that
does not match are refused with nothing written. `delete --entry E` without `--field` still deletes the
whole entry, its static object and every sign-in under it. `--even-if-working` on such a refresher is
refused (a working sign-in moves by the cooperative handover), and `replace-signin` on an
administrator's computer that is not the refresher is refused, naming the `delete --field` command;
neither writes a hand-over file. The old refresher's next operation (`replace_ops.discard_retired`,
called by the agent) removes its journal record of the exact retired grant; a record held by a refresh
still in flight is left until
that refresh ends, and its late answer is refused at publication, never retried.
`recovery-package --team` writes the team package; an unwritable
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
- The agent's scrub, its two static restores and its marker operation need a live lock; an absent, unreadable
  or stale lock (its process gone, or older than six hours) refuses, and a second migration cannot
  take a held lock.
- A connector's plain token file is refused while the store is on.
- Every legacy path refuses a sign-in named in the marker, store on or off. The marker, the
  migration record and the lock are ignored by the memory skeleton's `.gitignore`.

Rollback goes the same way round. The agent is unlocked on the old vault with the store off, and the
store is switched on without restarting the agent. `migrate_to_store.py rollback --dry-run` runs, then
`rollback`, and then the store is switched off. The rollback runs under the same lock and restores static secrets only from
the store's current value and clears the marker. It walks every static object of the store, not the old
vault's listing, so an entry or field created after the migration is restored too. Each static field
carries its kind (`text` or `json`) beside its value in the object's encrypted payload
(`{"schema": 2, "values": {...}, "kinds": {...}}`, `secret_store/static_fields.py`), and that kind is the
only authority at rollback. The migration records the old vault's kind; `put` records `text` (an
`--empty-json` field `json`); `set_text` records `text` and `set_json` `json`; every partial update (a
new field, a placeholder or grant field leaving the object) keeps the kinds of the other fields. Only
`text` and `json` are kinds, a `json` field's text must be a JSON object, and malformed or unknown kind
data is refused before use. A payload is the wrapper only when its `schema` is an integer and not a
boolean, and then it must be exactly that wrapper; any other integer `schema` is refused. Every other
payload is an object written before this change, whose values are all text, a field named `schema`
included (it becomes one more entry of `values` at the next write). Every reader goes through
`static_fields.split`. An object written before this change has no kinds: it reads as before, any
write records kinds for the fields it writes, and the rollback refuses a field without one, naming the
entry and the fix (store the entry again). This affects only stores made before this change. The
payload is inside the envelope, so the acceptance rules are unchanged. A static field under a migrated sign-in's name is restored, not skipped: the agent's
ordinary restore refuses a field the marker names, so such fields come back after the ordinary ones
through `vault_restore_marked_static`, which takes only fields the marker names for that entry,
checks the whole request before it writes anything and leaves the marker as it is. The marker is
cleared last, only when every restore of both kinds succeeded; it is never cleared early and nothing
is scrubbed, so every marked name stays refused to every other caller until then, a failure or a stop
leaves the marker exactly as it was, and the rollback is run again. If the store still holds that sign-in, the static field is shadowed
and is named instead. Each entry restored and each that could not be (unreadable, no recorded kind,
malformed kind data, a token-shaped value, a shadowed field, or refused by the agent) is named; one that could not
ends with exit code 5 and the marker kept. It never writes a token out of the store, so every migrated
sign-in needs a browser sign-in afterwards. The migration's `--backup-dir` must be inside the vault's own
folder: the agent checks the copy only there.

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

## An unfinished write

A write is one local commit, then its push, then this computer's checkpoint. A commit left past the
checkpoint (a crash before the push, a push that did not complete) is never followed: it is dropped
from the clone. What a person typed survives through a pending-write record (`pending.py`):

- one function, `typed_write.write_typed`, makes the record and writes. `brain_secrets.py put` and
  the agent's `set_text` and `set_json` of a static or grant field call it, always; the replay and
  `unfinished --apply` call it under the record that exists. The writers beneath it (`put_entry`,
  `oauth_ops.put_fields`, `set_grant_fields`, `put_signin`, `put_grant_fields`) make none: they take
  a keyword `typed=None` for their one `_write`, and only `typed_write` hands one down. A typed value is
  recorded whatever its field is called; a browser authorisation, the migration, `save_settings` and a
  refresh never make a record, so a provider's token answer never enters one;
- the record holds the plain fields with their kinds, the typed grant fields (a client id or secret),
  the base and the projected identities. The base names each object the write was built on by its id
  and checkpoint hash; an entry or sign-in that did not exist is bound to the group's index object,
  or, when the group has no index yet, to that fact and the policy hash. The projected identities are
  the id and hash of every object revision the commit writes, an index excepted. It is written once,
  after the change is built and verified and before the local commit (atomically, flushed, encrypted
  to this computer's key, the repository and group in the authenticated header); each further attempt
  rewrites only the projected identities;
- the record is removed when the write is confirmed (pushed and checkpointed), or when the first
  write failed and no attempt of it ever started a commit. The repository sets its mark
  `commit_started` in the one helper that launches `git commit`, by the statement right after the
  child is created; an interrupt during the launch also sets it (the launch may have happened), and
  a launch that fails with an operating-system error leaves it unset. Once it is set the record is kept, whatever
  follows (a commit that failed, a commit dropped again, a push that failed, an interrupt), and the
  error says the values are kept and saved at the next operation;
- at every sync (the next operation, by any process on this computer, under the repository lock) a
  current record of that repository is looked at in the verified state the write is built on, after
  that write's own sync: when the checkpoint still holds every base identity it is written again by
  the function that first wrote it, under the same record; when it holds every projected identity at
  its exact hash it is *saved* and removed with nothing written; otherwise it is marked *held*. A
  replay the store refuses (a changed target, no authority, any acceptance rule) is also held. A held
  record is never applied by itself again: `unfinished --apply ID` writes the kept values over the
  present ones, `unfinished --discard ID` removes the record (type the id to confirm). `status` and
  `unfinished` name each record by write id, entry and time, never a value;
- only a failure in the commit step after the commit was started, a refusal by the store and an
  unexpected error building that record's change are kept to the record; a failed sync, a refused
  remote commit, a checkpoint, pin or local-copy check, a record that cannot be rewritten and a commit
  step that failed before any commit started stop the operation as always, the record on disk
  untouched;
- a damaged record, one for another repository, or one kept by the first version without field kinds
  is never applied; status names it until it is discarded.

A refresh answer is kept by the refresh journal instead; a browser sign-in cut off by a crash is
done again.

A refused commit is named by a fixed rule code from the closed list `REFUSAL_CODES` in
`accept_rules.py`, the commit id and at most an object id the store already holds, in the message
and in the clone's `.git/secret-store-state.json`; never a pathname, Git's output, an exception's
text or other text from the commit.

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
