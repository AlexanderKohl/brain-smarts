---
id: PROPOSAL-follow-upstream-preflight-coverage
title: Preflight coverage for a recorded upstream merge
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: accepted
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-11-08T11:58:52+10:00
created: 2026-11-08T12:11:00+10:00
updated: 2026-11-08T12:11:00+10:00
rule_id: SMART-RULE-0032
target_files:
  - /shared/skills/repository-preflight/SKILL.md
---

# Preflight coverage for a recorded upstream merge

Read `/CONTRACT.md` first. This record carries the acceptance of the amendment of 8 November 2026
set out in full in `/governance/proposals/follow-upstream.md`, section "Amendment of 8 November
2026: preflight coverage for an upstream merge", so that the preflight's coverage check (CONTRACT
§13.2), which reads a proposal's front matter, covers the change to the protected *Failure
behaviour* section of `/shared/skills/repository-preflight/SKILL.md`. The proposal text, rationale
and rollback are in that section and are not repeated here.

Accepted by the owner at 2026-11-08T11:58:52+10:00 (answer "1. Accept"). Implemented in
`/shared/skills/repository-preflight/SKILL.md`,
`/shared/skills/repository-preflight/scripts/preflight_governance.py` and
`/shared/skills/repository-preflight/tests/test_upstream_coverage.py`.
