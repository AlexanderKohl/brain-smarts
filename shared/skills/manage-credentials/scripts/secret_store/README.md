---
id: secret-store-readme
title: Synced Secrets Store
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-20T19:22:05+10:00
updated: 2026-11-20T19:22:05+10:00
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

## Modules

Alphabetical, in `/shared/skills/manage-credentials/scripts/secret_store/`:

- `accept.py`, `accept_rules.py`: accept or refuse one whole commit.
- `bip39_english.txt`: the word list for recovery and enrolment words.
- `broker_backend.py`: the Vault Agent's store backend.
- `canonical.py`, `envelope.py`, `hpke.py`, `signing.py`: canonical form, objects, key wrapping, signatures.
- `checkpoint.py`: the signed local record of the newest epoch and revisions.
- `enrol.py`: the enrolment protocol.
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
- Recovery packages are written to `recovery-packages` in that folder by default, refreshed weekly
  and after every policy change; point `recovery_package_dir` at the person's own cloud drive to
  keep a copy outside the computer. A package is encrypted to the recovery key.
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
python brain_secrets.py recovery-package
python brain_secrets.py enrol-request [--team] --fingerprint F     new computer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer
python brain_secrets.py enrol-request [--team] --request ID        new computer, after the answer
python brain_secrets.py enrol-approve [--team] --request ID        approving computer, to finish
python brain_secrets.py team-init --owner ORGANISATION
python brain_secrets.py team-admit --login L --group G [--group G]
python brain_secrets.py team-groups --create G | --login L --group G
python brain_secrets.py team-remove --login L [--computer C]
python migrate_to_store.py --dry-run               names only; then without it, [--replace]
```

Enrolment: the new computer runs `enrol-request --fingerprint`, the approver runs `enrol-approve`,
the new computer runs `enrol-request --request`, both screens show six words, and the approver
runs `enrol-approve` again once the words match. `migrate_to_store.py` needs the Vault Agent
unlocked on the old vault, makes a verified backup first, never changes the old vault and prints
no value; a clash with an existing entry stops it unless `--replace` is given.

## Switching it on and off

On: create `config/secret-store.json` in the owner's memory folder for this skill, with
`"enabled": true` and `"person"` (the GitHub login); optional keys are `computer`,
`personal_repo_url`, `team_repo_url`, `personal_clone`, `team_clone`, `checkpoint_dir` and
`recovery_package_dir`. Unknown keys are refused. Off: set `"enabled": false` or remove the file;
the vault and its passphrase work as before. Without the file the store is off.

## A computer that is not a sign-in's refresher

It reads the sign-in's access token and shared settings only. It never calls the provider and
cannot map the client secret; a request to refresh waits for the refresher to publish, or stops
with a message naming the refresher computer.

## Provider profiles

`provider_profiles.json` holds profiles for Xero, Google and HighLevel. None is verified: each
needs the provider's documentation plus a live test that revoking a refresh token retires the whole
grant and that a new browser sign-in makes a separate grant. Until a profile is verified, handover
to another refresher and recovery from an uncertain refresh are refused and the entry stays blocked.
