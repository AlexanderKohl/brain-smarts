---
id: PROPOSAL-synced-secrets-store
title: The synced secrets store becomes an approved credential provider
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-11-20T18:15:52+10:00
updated: 2026-11-20T18:15:52+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 3.2.0
new_contract_version: 3.2.0
target_files:
  - /shared/skills/manage-credentials/SKILL.md
---

# The synced secrets store becomes an approved credential provider

## Current problem

The *Credential policy* of the credential skill allows one store, the passphrase vault, unlocked by
hand after every sign-in, and lets shared client secrets reach another person only through a
password manager. Owners find this slow, and every computer and every team member repeats it. A
store has been designed and independently reviewed (six rounds, verdict SOUND) that keeps each
computer's keys in the operating system's keychain and syncs encrypted, signed objects through
private Git repositories; it is built behind an opt-in in `scripts/secret_store/`. Several policy
bullets forbid exactly what it does, so it cannot be switched on without this change.

## Current wording

From `/shared/skills/manage-credentials/SKILL.md`, *Credential policy*:

- *Storage policy*: "Use the vault file named under *Required inputs* as the canonical encrypted store
  for future credentials unless a credential set explicitly declares another approved provider."
- "Permit only the approved authenticated encrypted `credentials.vault` container in the project
  data directory; exclude it from Git."
- "Do not use Windows Credential Manager or an external password manager as the default backend."
- "Accept new secret values through a hidden prompt or standard input."
- *OAuth lifecycle*: "Allow only one active refresh writer for a credential set across all devices,
  unless the entry is listed in the token relay's configuration. [...]"
- *Portability and concurrency*: "Do not commit the vault, merge divergent copies, or assume file
  synchronisation provides locking. [...]"
- "The relay store holds ciphertext only. The relay key and the provider's client secret live in
  each brain's vault and reach another person only through a password manager, never through chat,
  e-mail or a repository. [...]"
- "Do not enable unattended vault unlock after reboot without a separately accepted runtime design
  (for example a future TPM/device-bound key slot). [...]"

## Proposed wording or exact diff

Each bullet above keeps its text and gains the sentence shown after it:

- Storage, first bullet: "The synced secrets store (`scripts/secret_store/`) is an approved provider
  for a brain whose owner has switched it on."
- Storage, `credentials.vault` bullet: "The synced secrets store's objects are permitted too: signed
  and encrypted, in their own private repositories outside every brain repository."
- Storage, Windows Credential Manager bullet: "The synced secrets store keeps each computer's private
  keys there (or in the macOS login keychain or the Linux Secret Service), and only those keys."
- Storage, hidden prompt bullet: "The masked window (`--window`, `secret_window.py`) counts as a hidden
  prompt."
- OAuth lifecycle, refresh writer bullet: "In the synced secrets store the policy names one refresher
  computer per rotating sign-in; only that computer refreshes, and its refresh token is encrypted to
  it and the recovery key only."
- Portability, commit bullet: "The synced secrets store's objects are committed to their own
  repositories by design; they are never merged as text."
- Portability, relay bullet: "With the synced secrets store, a secret reaches another person only as
  an object encrypted to that person's computers, after an administrator's signed policy change."
- Portability, unattended unlock bullet: "The synced secrets store's computer keys in the operating
  system's keychain are that accepted design (`PROPOSAL-synced-secrets-store`); they unlock with the
  person's sign-in to the computer."

And a new sub-section at the end of *Credential policy*:

```markdown
### Synced secrets store

- No secret value, private key or recovery word is ever written to Git, the chat, a log or a
  command argument. Recovery words are shown only in the masked window, once.
- Who can read an object changes only through a policy change signed by an administrator of that
  repository, judged against the current trusted policy; a commit that does not verify in full is
  refused whole.
- Removing a person or a computer re-encrypts, in the same commit, every object it could read, and
  the agent lists the provider secrets to change, because what was read cannot be recalled.
- A rotating sign-in is handed to another refresher only through a signed release, or after a
  revocation the provider's profile proves complete; without such a profile it is never handed
  over, and an uncertain refresh leaves it blocked.
- The design is `/memory/projects/brain-development/designs/synced-secrets-repository.md` in the
  owner's memory where it was made; its rules above apply to every brain that switches the store on.
```

(The last bullet names a memory path, which another owner's brain does not have; on acceptance it
is replaced by a reference to the store's own `README.md` in `scripts/secret_store/`, which carries
the design's rules in generic form.)

## Reason

It removes the passphrase, the tray and the hand-copying of shared secrets, while keeping every
secret encrypted to the computers allowed to read it and no server able to read any.

## Scope and behavioural consequences

Only brains whose owner switches the store on. For them: secrets are readable whenever the person
is signed in to the computer (today: only after the tray is unlocked); shared rotating sign-ins
refresh on one named computer; other computers use their access tokens only.

## Risks and conflicts

- A computer stolen while signed in reads what its person can, as an unlocked vault can today.
- Malware running as the person can read the keychain keys, as it can read the unlocked tray today.
- Lost computers, recovery words and recovery package together lose the personal secrets.

## Migration

The store's migration command copies each vault entry into the store after a verified encrypted
backup of the vault; the vault stays readable until the owner retires it.

## Rollback

Switch the store off; the vault and its passphrase work as before. Revert the added sentences and
sub-section.

## Validation

The store's test suites; repository preflight; a live run on the owner's computers before any
other person is invited.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record
