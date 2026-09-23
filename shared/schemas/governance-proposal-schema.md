---
id: schema-governance-proposal
title: Governance Proposal Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T23:16:08+10:00
updated: 2026-09-23T20:00:00+10:00
owner: brain-owner
---

# Governance Proposal Schema

## Lifecycle

```text
draft -> proposed -> accepted -> implemented -> verified
                  \-> rejected
                  \-> superseded
implemented -> reverted
```

- `draft`: incomplete and not offered for acceptance
- `proposed`: exact change and consequences have been presented
- `accepted`: the owner explicitly accepted the identified proposal
- `implemented`: only the accepted change set has been applied
- `verified`: implementation and required migration have passed validation
- `rejected`: the owner declined the proposal
- `superseded`: a different proposal replaced it before implementation. For a small amendment to a live rule, do not mint a new ID and supersede; amend the existing numbered rule instead.
- `reverted`: an implemented change was rolled back

No status makes proposed wording active. Only the implemented content of the protected target file is active governance.

## Required metadata

All proposals require:

```yaml
id: PROPOSAL-short-slug
type: governance_proposal
status: draft
owner: OWNER
previous_contract_version: CURRENT_VERSION
new_contract_version: PROPOSED_VERSION
target_files: []
```

Statuses `accepted`, `implemented`, `verified` and `reverted` also require:

```yaml
accepted_by: OWNER
accepted_at: YYYY-MM-DDTHH:mm:ss+HH:MM
```

A proposal that introduces or amends a rule also records, from acceptance onwards:

```yaml
rule_id: SMART-RULE-NNNN   # or MEMORY-RULE-NNNN, <PROJECT>-RULE-NNNN
```

Statuses `implemented`, `verified` and `reverted` require:

```yaml
implemented_at: YYYY-MM-DDTHH:mm:ss+HH:MM
```

## Required content before acceptance

- current problem
- current wording
- proposed wording or exact diff
- reason
- scope and behavioural consequences
- risks and conflicts
- migration
- rollback
- validation

Acceptance must unambiguously identify the proposal or displayed exact change set.

## Rule IDs

Keep a rule's ID stable. Small additive or clarifying changes amend the existing numbered rule and its proposal record, and are presented for acceptance under that same ID.

A proposal's `id` is `PROPOSAL-<short-slug>`, matching its file name `<short-slug>.md`, and never changes. It carries no rule number while it is under review. When the owner accepts a proposal that introduces a distinct new rule, the rule takes the next free number in its layer (`SMART-RULE-NNNN`, `MEMORY-RULE-NNNN` or `<PROJECT>-RULE-NNNN`; CONTRACT §13.2, *Rule identifiers*), recorded in the proposal as `rule_id`. A proposal that amends an existing rule records that rule's identifier in `rule_id` from the start. Assign a new number only when introducing a distinct new rule. `superseded` remains available when a distinct new rule replaces an old rule's behaviour (for example a broad commit-checkpoint rule replacing a narrower rule about when to commit), not as the default path for a wording tweak.
