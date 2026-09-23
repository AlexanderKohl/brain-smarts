---
id: RULE-2026-0001
title: Governance Safety, Bootstrap and Preflight
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
owner: brain-owner
created: 2026-08-04T23:16:08+10:00
updated: 2026-08-04T23:21:31+10:00
accepted_by: brain-owner
accepted_at: 2026-08-04T23:16:08+10:00
implemented_at: 2026-08-04T23:16:08+10:00
previous_contract_version: unversioned
new_contract_version: 0.3.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /BOOTSTRAP.md
  - /README.md
  - /memory/projects/brain-development/RULES.md
  - /shared/templates/node-RULES.template.md
  - /shared/templates/governance-proposal.template.md
  - /shared/schemas/governance-proposal-schema.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight.py
---

# Governance Safety, Bootstrap and Preflight

## Status

Implemented from the owner's explicit instruction in the current interaction: “1. Is done. Implement 2 to 6.”

This acceptance preceded the protocol created by this proposal. It explicitly identified the numbered scope but delegated exact implementation wording. This is recorded as a one-time bootstrap exception; future proposals must present their exact wording or diff before acceptance.

The accepted numbered scope was:

2. correct bootstrap-path ambiguity
3. add an explicit proposal-and-acceptance clause
4. add the proposal template and status lifecycle
5. introduce `contract_version`
6. build the validation/preflight check

## Current problem

- Bootstrap instructions could identify a directory ambiguously or conflict with a second machine-specific location.
- Active governance could be edited through the ordinary persistent-file protocol without explicit owner acceptance.
- Proposed wording had no safe, non-active lifecycle.
- `schema_version` did not distinguish document shape from behavioural contract version.
- Repository integrity relied on manual judgement and a non-reproducible manifest.

## Accepted change

- Discover `CONTRACT.md` from the supplied repository or nested path and treat absolute paths as verified hints.
- Stop and report conflicting contract locations.
- Protect the contract, active rules, governance schemas/templates and bootstrap-loading instructions.
- Require an identified proposal, disclosed consequences, one direct acceptance question and explicit owner acceptance.
- Store proposals outside inherited rule paths with a defined lifecycle.
- Add independent semantic `contract_version`.
- Add a standard-library repository validator and reproducible manifest output.

## Behavioural consequences

- Agents may draft governance proposals without changing active rules.
- Agents must not infer governance acceptance from silence or adjacent approval.
- Material undisclosed consequences require a revised proposal and new acceptance.
- Contract behaviour changes are independently versioned.
- Substantive repository updates must pass the preflight validator.

## Migration

No existing content migration is required. Future governance changes must use this lifecycle. External bootstrap instructions should reference the exact `CONTRACT.md` file or rely on upward discovery.

## Risks

- Governance edits require an additional explicit exchange.
- The validator may initially expose pre-existing inconsistencies that need correction.
- Automated governance checks depend on Git history being available.

## Rollback

Revert this proposal's target-file changes as one version-control change and remove `contract_version` to restore the previously unversioned contract. Preserve this proposal record as historical evidence with status `reverted`.

## Validation

- run `/shared/skills/repository-preflight/scripts/preflight.py`
- generate `/repository-manifest.json`
- inspect the complete version-control diff
- confirm no unapproved protected file is changed

## Implementation record

- implemented the accepted numbered scope
- advanced the behavioural contract to `0.3.0`
- ran the repository preflight successfully across 122 Markdown files and 122 unique IDs
- generated a clean repository manifest with no errors or warnings
