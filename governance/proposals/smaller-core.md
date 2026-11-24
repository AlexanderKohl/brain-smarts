---
id: PROPOSAL-smaller-core
title: Contract §13.2 is read when governance changes, not by every session
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T17:32:22+10:00
updated: 2026-11-24T18:22:16+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /CORE-RULES.md
  - /CORE.md
  - /RULES.md
---

# Contract §13.2 is read when governance changes, not by every session

Read `/CONTRACT.md` first. This proposal amends the contract-section table in `/RULES.md`; every rule keeps its identifier
(CONTRACT §13.2). The contract is not changed. It is one of six proposals of 24 November 2026 that came out of
measuring what a session reads before it works; each can be accepted or refused alone.

## Plain-language summary

1. **One table row becomes three.** §13.1, ordinary changes, stays in the core. §13.2, protected governance with the rule-identifier scheme, and §13.3, contract versioning, are read when a rule or the contract is about to change.
2. **6,600 characters fewer in every writing session.** `/CORE.md` goes from 25,273 to about 18,700.
3. **The contract's wording does not change.** Only when §13.2 is read.

## Current problem

Every writing session reads the whole change protocol, 7,217 characters, of which 6,061 are the proposal procedure and the rule-identifier scheme. Most sessions change no rule.

## Current wording and exact diff

### 1. `/RULES.md` – the contract-section table, the row of §13

Current:

> | §13 | Change protocol | always |

Proposed:

> | §13.1 | Ordinary persistent changes | always |
> | §13.2 | Protected governance | proposing, amending, accepting or applying a change to the contract, a `RULES.md` at any level, a governance schema or template, a bootstrap file or the validator's failure behaviour; numbering a rule or naming a proposal |
> | §13.3 | Contract versioning | changing the contract |

Why: The generator already takes sub-sections (§3.1 to §3.6 have rows of their own). Splitting the row keeps the 636 characters every change needs and moves the 6,557 that only a governance change needs.

## Measured

- `/CORE.md` and `/CORE-RULES.md` together, read first by every writing session: 52,231 characters today, 45,977 with this proposal alone, 43,341 with all six of 24 November.

## Reason

`SMART-RULE-0003`. A session that will not touch governance does not need the procedure for changing it; it needs to know that the procedure exists and when it applies.

## Scope and consequences

Every agent in every host. What still reaches every session: CONTRACT §5.6 (in the core) sends a durable instruction to the proposal process; `SMART-RULE-0036` (in the core) says a rule is changed only through a proposal the owner accepts; the new row names every kind of file §13.2 protects.

## Risks, conflicts and migration

- **An agent changes a rule without having read §13.2.** The preflight refuses a protected-governance change without an accepted proposal at commit, so the change cannot land; the agent then reads the section.
- **An agent does not recognise a file as protected.** The row lists them: the contract, a `RULES.md` at any level, governance schemas and templates, bootstrap files, the validator's failure behaviour.

## Rollback

Restore the one row; `core.py build` puts §13 back in the core.

## Planned validation

Measured on a copy with `core.py build`. After acceptance: the wording by script, `core.py build`, the full preflight.
