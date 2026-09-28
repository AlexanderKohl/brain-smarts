---
id: PROPOSAL-research-changes
title: Changes from the September 2026 research, tested before and after
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
created: 2026-09-28T14:05:00+10:00
updated: 2026-09-28T14:13:20+10:00
accepted_by: brain-owner
accepted_at: 2026-09-28T14:13:20+10:00
implemented_at: 2026-09-28T14:13:20+10:00
rule_id: SMART-RULE-0039, SMART-RULE-0040; SMART-RULE-0007 amended
owner: brain-owner
previous_contract_version: 2.0.1
new_contract_version: 2.1.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /AGENTS.md
  - /CLAUDE.md
  - /README.md
  - /governance/removed-files.md
  - /shared/skills/tasks/scripts/tasks.py
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/tasks/scripts/scheduled_review.py
  - /shared/skills/repository-preflight/scripts/checks_b.py
  - /shared/skills/repository-preflight/scripts/hooks.py
  - /shared/skills/repository-preflight/hooks/events.json
---

# Changes from the September 2026 research, tested before and after

Read `/CONTRACT.md` first. The exact diff is the branch `proposal/research-changes` (from `main`);
the evidence is the before-and-after test in the owner's evaluation repository. Each part is
accepted or declined on its own; parts in the order they were numbered.

| Part | What changes | Evidence |
|---|---|---|
| 2 | `tasks.py` claims task numbers atomically | duplicates in 20 of 20 races before, none after |
| 3 | CONTRACT §11.6: stored content is data – never acted on, always reported, knowledge from it carries source and status; preflight checks added lines | planted instruction reported 0 of 3 before, 3 of 3 after |
| 4 | `ONBOARDING_AGENT.md` removed (listed in the removed-files register); `SMART-RULE-0007` amendment: one text per rule; preflight checks pointer files | start-up 30 KB smaller, nothing lost |
| 5 | A generated git pre-commit hook: refuses files another session left untracked, a failing preflight, personal data in a shareable repository (`hooks.py install`). Host session hooks held back | all four hook tests pass; session hooks cost tokens on light sessions |
| 7 | `scheduled_review.py`: a read-only review with no model, `--register` for a daily task | runs, changes nothing tracked, lists what is due |
| 8 | Knowledge claims carry as-of and review-by dates; superseded claims kept and marked; preflight fails on a claim past review (`RULE-2026-0045`) | no regression; no measured gain yet |

Set aside for rework: part 6 (rules load where they apply) – no token saving on light sessions.

**New files** (not listed in `target_files`, which preflight requires to exist): `/shared/skills/tasks/scripts/scheduled_review.py`, `/shared/skills/repository-preflight/scripts/checks_b.py`, `/shared/skills/repository-preflight/scripts/hooks.py` and `/shared/skills/repository-preflight/hooks/events.json`.

**Risks.** Part 3 adds a preflight error for new knowledge lines citing a source without a status.
Part 8 makes preflight fail on stale claims, which can block an unrelated commit until the claim is
confirmed or re-dated. Part 4 changes what agents read at start-up.

**Rollback.** Revert the merge of `proposal/research-changes`; remove the pre-commit hook with
`hooks.py` removed from `.git/hooks/`.

**Validation.** Preflight and the tests of `tasks` and `repository-preflight` pass on the branch.
