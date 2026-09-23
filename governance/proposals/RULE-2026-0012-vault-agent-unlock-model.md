---
id: RULE-2026-0012
title: Vault Agent unlock model (replace chat-long PowerShell session)
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0012
target: /projects/credential-management/RULES.md
target_files:
  - /memory/projects/credential-management/RULES.md
created: 2026-08-06T14:08:00+10:00
updated: 2026-08-06T14:12:00+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T14:12:00+10:00
implemented_at: 2026-08-06T14:12:00+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
  - /memory/projects/credential-management
  - /memory/projects/brain-development
skill_refs:
  - /shared/skills/manage-credentials
  - /shared/skills/xero-access
  - /shared/skills/gohighlevel-access
  - /shared/skills/google-workspace-access
supersedes:
  - RULE-2026-0002
---

# RULE-2026-0012: Vault Agent unlock model

## Status

Accepted and implemented for the protected RULES target from the owner's explicit acceptance of proposal `RULE-2026-0012` in chat ("i accept 2026-0012") at 2026-08-06T14:12:00+10:00. Applied to `/projects/credential-management/RULES.md`. Companion Phase 2 runtime (Vault Agent / broker) ships in the same change set. No `contract_version` change (project rules only).

## Current problem

The active credential-management rules required one chat-long credential-aware PowerShell session that held `PORTABLE_VAULT_PASSPHRASE` in the process environment, exposing the vault master passphrase too broadly and coupling OAuth usability to an open shell.

## Proposed wording

Applied exactly as drafted in the pre-acceptance proposal body (Storage policy, Passphrase and encryption, and Portability and concurrency sections of `/projects/credential-management/RULES.md`).

## Reason

Remove the master-passphrase-in-shell exposure model while preserving durable OAuth grants and practical repeated use of vault-backed integrations during a Windows login without keeping PowerShell open.

## Scope and behavioural consequences

- Protected target: `/projects/credential-management/RULES.md` only.
- Agents must prefer Vault Agent unlock + broker over chat-long `session`.
- Supersedes PowerShell-centred concurrency instructions from `RULE-2026-0002` for future operations.
- No `/CONTRACT.md` behavioural change; `contract_version` remains `0.4.0`.

## Risks and conflicts

Broker ACLs alone are insufficient against same-user processes; implementation adds a local session auth token and scoped operations. Migration updates skill/onboarding docs with the RULES change.

## Migration

Phase 2 Vault Agent, broker client, BrokerOAuthStore, and skill/onboarding updates accompany this acceptance.

## Rollback

Revert `/projects/credential-management/RULES.md` to the pre-acceptance wording; disable Vault Agent entrypoints; mark this proposal `reverted`.

## Validation

Run `/shared/skills/repository-preflight/scripts/preflight.py` after the change set.

## Acceptance

The owner explicitly accepted proposal `RULE-2026-0012` in chat at 2026-08-06T14:12:00+10:00 with the wording “i accept 2026-0012”.

## Implementation record

- Applied accepted RULES wording to `/projects/credential-management/RULES.md` (`accepted_proposal: RULE-2026-0012`).
- Phase 2 Vault Agent / broker / OAuth store migration implemented under `/shared/skills/manage-credentials/` and consumer skills in the same session.
