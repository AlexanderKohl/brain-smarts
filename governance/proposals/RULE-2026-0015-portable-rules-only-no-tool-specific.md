---
id: RULE-2026-0015
title: Portable behavioural rules only; no host-specific rule files
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0015
target: /RULES.md
target_files:
  - /RULES.md
created: 2026-08-06T15:28:00+10:00
updated: 2026-08-06T15:36:48+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T15:36:48+10:00
implemented_at: 2026-08-06T15:28:00+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0015: Portable behavioural rules only

## Status

Accepted and implemented. Owner explicitly accepted with “I accept the rule” at 2026-08-06T15:36:48+10:00. Active wording is in `/RULES.md`. No `contract_version` change.

## Reason

Behavioural policy must be identical for every agent and host. Host-specific rule files create drift from the portable brain.

## Active wording

```markdown
- Keep durable behavioural rules only in portable governance: `/CONTRACT.md`, root and node `RULES.md` files, and skill operating instructions. Do not create or maintain host-specific behavioural rule files that restate or extend how agents must behave.
- Host entry files may only point agents to portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`, `/AGENTS.md`, `/ONBOARDING_AGENT.md`) and must not carry independent behavioural policy.
```

## Acceptance

Owner explicitly accepted proposal `RULE-2026-0015` in chat at 2026-08-06T15:36:48+10:00 with the wording “I accept the rule.”
