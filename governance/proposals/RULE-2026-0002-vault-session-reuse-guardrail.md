---
id: RULE-2026-0002
title: Vault Session Reuse Guardrail
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: superseded
superseded_by: RULE-2026-0012
owner: brain-owner
created: 2026-08-05T07:59:00+10:00
updated: 2026-08-05T07:59:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-05T07:55:00+10:00
implemented_at: 2026-08-05T07:49:00+10:00
previous_contract_version: 0.3.0
new_contract_version: 0.3.0
target_files:
  - /memory/projects/credential-management/RULES.md
  - /shared/skills/manage-credentials/SKILL.md
---

# Vault Session Reuse Guardrail

## Status

Implemented and accepted from the owner's explicit instruction in the current interaction. The change was applied at 2026-08-05T07:49:00+10:00 in direct response to a fully specified change request; the owner then explicitly accepted the exact displayed diff to `RULES.md` at 2026-08-05T07:55:00+10:00. This proposal record is created retroactively at the owner's request to formally cover the change under Contract §13.2, following the same one-time bootstrap-exception pattern already recorded in `RULE-2026-0001`: acceptance of exact wording preceded the filed proposal record.

## Current problem

The owner already had one active credential-aware PowerShell session open (unlocked via `vault_credentials.py session` for the `ghl-agency-oauth` entry). A separate request to add reusable household-member fields to the vault risked starting a second concurrent `vault_credentials.py session` or `put-entry` invocation from a different process. The vault's OS-level file lock on `credentials.vault.lock` permits only one exclusive writer at a time, so a second concurrent invocation would not fail cleanly; it would block waiting on the same lock, or prompt for the passphrase a second time unnecessarily. Neither `/shared/skills/manage-credentials/SKILL.md` nor `/projects/credential-management/RULES.md` previously instructed checking for an existing active session or lock before opening a new one.

## Current wording

`/projects/credential-management/RULES.md`, end of the "Portability and concurrency" section, before this change:

```markdown
- Use one active writer for each rotating OAuth credential set across devices.
- Do not enable unattended vault use without a separately approved runtime secret-injection design.
- Do not substitute a plaintext `.env` passphrase for interactive unlock; use one chat-long unlocked shell for repeated operations and do not create parallel sessions.
```

`/shared/skills/manage-credentials/SKILL.md` had no section addressing detection of an already-active session before unlocking; the topic did not exist prior to this change.

## Proposed wording or exact diff

Added to `/projects/credential-management/RULES.md`, "Portability and concurrency" section (appended after the existing bullets shown above):

```markdown
- Before opening a new vault session or prompting for the passphrase, check whether one is already active: an existing `PORTABLE_VAULT_PASSPHRASE` in the current shell, a held `credentials.vault.lock`, or an already-open credential-aware PowerShell for the active chat.
- Reuse an already-active session for every further vault operation in that chat; never open a second concurrent session or lock, since the vault permits only one exclusive writer at a time.
```

Added to `/shared/skills/manage-credentials/SKILL.md`, a new section inserted before "## Keep one vault session open for the active chat":

```markdown
## Check for an active session before unlocking

The vault permits only one exclusive writer at a time: `PortableVault` takes an OS file lock on `credentials.vault.lock` for the duration of every `init`, `check`, `change-passphrase`, `put`, `put-entry`, `delete-entry`, `get`, `run`, and `session` operation. Before running any of these and before prompting the owner for the passphrase, check whether a session is already active:

- Check whether `PORTABLE_VAULT_PASSPHRASE` is already set in the current shell's environment. If it is, a credential-aware session already unlocked this process tree; run the needed subcommand directly in that same shell so it reuses the in-memory passphrase instead of prompting again.
- Check whether `credentials.vault.lock` next to the vault is currently held, or whether a terminal is already running `vault_credentials.py session ...` (visible as an open, unclosed PowerShell for this chat). A second concurrent `session`, `run`, `put`, or `put-entry` invocation from a different process does not fail cleanly; it blocks waiting for the same OS lock.
- If a session or lock is already active, reuse it: paste or run the new command inside that existing open PowerShell instead of starting a second one. Never start a second concurrent session, and never ask the owner for the passphrase a second time while one session is already open.
- Only open a new session when no credential-aware session is currently open for the active chat.
```

## Reason

Prevent a second concurrent vault lock or passphrase prompt from colliding with an already-open credential-aware session, which would otherwise block silently, risk a confusing duplicate passphrase prompt, or tempt an agent to work around the lock in an unapproved way.

## Scope and behavioural consequences

- Applies to `/projects/credential-management/RULES.md` (durable operating rule for this project) and `/shared/skills/manage-credentials/SKILL.md` (operating instructions read by any agent or skill invocation before a vault operation).
- Any agent or person about to run a vault-unlocking command must first check for an existing session (`PORTABLE_VAULT_PASSPHRASE`, `credentials.vault.lock`, or a visibly open credential-aware PowerShell) and reuse it instead of starting a second one.
- No change to vault cryptography, entry structure, field naming, or the `vault_credentials.py` CLI surface itself.
- No `/CONTRACT.md` behavioural change; `contract_version` remains `0.3.0`.

## Risks and conflicts

- None identified against existing rules; this is additive and narrows previously unspecified concurrency behaviour.
- Detection is documentary, not automatically enforced by `vault_credentials.py` itself: an agent that has not read the updated guardrail could still attempt a second session and hit the OS-level lock. A future enhancement could add an explicit lock-check/error message to the script; not in scope for this proposal.

## Migration

No historical content migration is required. The guardrail applies to all vault operations from this point forward.

## Rollback

Revert the two added bullets in `/projects/credential-management/RULES.md` under "Portability and concurrency" and the added "Check for an active session before unlocking" section in `/shared/skills/manage-credentials/SKILL.md` as one version-control change; mark this proposal `reverted` and record the reason.

## Validation

- run `/shared/skills/repository-preflight/scripts/preflight.py`
- confirm `/projects/credential-management/RULES.md` no longer appears among the protected-governance coverage errors
- inspect the complete diff for both target files against the wording shown above

## Acceptance

The owner explicitly accepted the exact displayed diff to `/projects/credential-management/RULES.md` (the two new bullets under "Portability and concurrency") in chat at 2026-08-05T07:55:00+10:00, and separately confirmed the wording of both target files was already applied as intended.

## Implementation record

- Added the two guardrail bullets to `/projects/credential-management/RULES.md` under "Portability and concurrency" (2026-08-05T07:49:00+10:00).
- Added the matching "Check for an active session before unlocking" section to `/shared/skills/manage-credentials/SKILL.md` (2026-08-05T07:49:00+10:00).
- Logged the change and the owner's acceptance in `/projects/credential-management/LOG.md` (entries at 2026-08-05T07:49:00+10:00 and 2026-08-05T07:55:00+10:00).
- Created this proposal record to formally close the Contract §13.2 acceptance step for both target files.
