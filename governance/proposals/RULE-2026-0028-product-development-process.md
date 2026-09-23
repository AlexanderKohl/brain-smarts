---
id: RULE-2026-0028
title: Apply the Product Development Process
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-03T14:08:39+10:00
updated: 2026-09-03T14:20:39+10:00
accepted_by: brain-owner
accepted_at: 2026-09-03T14:17:49+10:00
implemented_at: 2026-09-03T14:17:49+10:00
previous_contract_version: 0.7.0
new_contract_version: 0.8.0
target_files:
  - /CONTRACT.md
  - /RULES.md
---

# Apply the Product Development Process

## Current problem

The reusable `/shared/skills/product-development/` process exists, but no active root rule requires future agents to invoke it for applicable work. An agent could therefore begin material product or feature development without proportional discovery, lifecycle positioning, evidence-backed owner gates or the required independent-review checkpoints.

## Current wording

Root `/RULES.md` contains no general product-development lifecycle rule. `RULE-2026-0025` governs reuse of project-native UI patterns but does not govern whether or how a product or feature should be developed.

`/CONTRACT.md` currently declares `contract_version: 0.7.0`.

## Proposed wording or exact diff

```diff
--- a/CONTRACT.md
+++ b/CONTRACT.md
@@
-contract_version: 0.7.0
+contract_version: 0.8.0
--- a/RULES.md
+++ b/RULES.md
@@
-Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`.
+Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`.
@@
+## RULE-2026-0028 – Product-development process
+
+- Before starting or continuing a non-trivial discovery, design, implementation, release or lifecycle-investment increment for a software product or internal tool, follow this rule and use `/shared/skills/product-development/` as its implementation guide. Clearly non-material copy/formatting corrections, behaviour-preserving mechanical refactors and like-for-like bounded repairs use ordinary proportionate engineering discipline; a small reversible behavioural improvement may use the skill's compact light path.
+- Establish whether the work is a new product, existing-product baseline, feature/change, urgent repair or lifecycle review; locate existing work at its current lifecycle position; reuse valid evidence; and reopen only the gates whose assumptions or downstream consequences are affected.
+- Select light, standard or high-assurance depth from investment, uncertainty, reversibility, affected users, security/privacy exposure, operational criticality and consequence of failure. Always consider both internal-use and commercial routes, while scaling the research to their plausible value. A light change may be recorded compactly without reconstructing the full product lifecycle.
+- The acting agent researches, tests, collects and presents the evidence and a recommendation for each applicable gate. The owner decides each gate unless an accepted active rule explicitly delegates that defined gate and risk class. Record the decision and the exact next investment it authorises.
+- Maintain a canonical product-development record or equivalent project-native plan. At minimum, record lifecycle position, depth and its rationale, affected gate dispositions, evidence freshness, decisions and the exact next investment authorised; a compact entry is sufficient for a light change.
+- At standard and high-assurance depth, use at least two distinct underlying AI models at material opportunity/build-versus-buy, design/delivery and release-readiness checkpoints when proportionate, available and permitted. Protect secrets and minimize personal, customer, security-sensitive and commercially sensitive context before review. Synthesize disagreements as evidence rather than votes. If distinct models are unavailable, disclose the limitation and do not claim that multi-model review occurred.
+- The mandatory semantics are contained in this rule. `/shared/skills/product-development/` supplies operational detail and may not weaken these requirements or expand an agent's authority.
```

## Reason

This makes product development a repeatable Brain behaviour while preserving proportionality. It gives the owner evidence and recommendations at investment gates, supports both internal and commercial possibilities, prevents existing products and new features from being forced through an artificial restart, and broadens important reviews through genuinely independent models.

## Scope and behavioural consequences

- Applies primarily to software the owner and agents build together.
- Applies to new products, internal tools, material product changes and lifecycle investment decisions.
- Does not turn trivial bug fixes or formatting changes into product ceremonies.
- Does not give agents authority to pass gates, deploy, purchase or take external side effects beyond existing permissions.
- Allows future accepted rules to delegate specific gates for defined low-risk classes without weakening owner control elsewhere.

Plain-language summary: future agents will first understand where a product or feature sits, do only the amount of research and design justified by its investment and risk, consider both internal and commercial value, bring the owner evidence-based decisions, and obtain independent AI perspectives at the most important checkpoints when practical.

## Risks and conflicts

- Over-processing small work is mitigated by the explicit small-fix exclusion and light depth.
- Multi-model review can add cost and latency; it is required only at standard and high-assurance checkpoints when proportionate, available and permitted, with disclosure when unavailable.
- Model agreement can create false confidence; the skill requires evidence verification and disagreement synthesis rather than voting.
- Cross-model evidence sharing can expose sensitive material; the process now requires provider permission, minimisation, redaction and existing authorization.
- The rule complements, rather than replaces, existing authorization, governance, Git and UI-pattern rules.

## Migration

No retrospective redevelopment is required. When an existing product or feature is next worked on, create a proportionate baseline from current evidence and begin at the earliest materially affected gate.

## Rollback

Remove `RULE-2026-0028` from root `/RULES.md`, remove `0028` from its root-ID list and issue a new accepted governance proposal for the resulting contract-version change. Existing project records and source evidence remain valid history.

## Validation

After acceptance and implementation:

1. Confirm the live rule matches this exact diff.
2. Confirm `/shared/skills/product-development/SKILL.md` and its referenced process files resolve.
3. Run repository preflight and update `/repository-manifest.json`.
4. Confirm the contract version is `0.8.0` and the protected files are covered by this proposal.

## Acceptance

Explicitly accepted by the owner on 2026-09-03T14:17:49+10:00 with “i accept”, in direct response to the acceptance question identifying `RULE-2026-0028` and its exact proposed diff.

## Implementation record

Applied the accepted rule wording and root-ID inventory to `/RULES.md`, activated the root pointer to this proposal, and updated `/CONTRACT.md` from version `0.7.0` to `0.8.0` on 2026-09-03T14:17:49+10:00. Required metadata timestamps were updated as implementation bookkeeping. Validation results are recorded below after execution.

The live rule contains all seven accepted requirements, its skill and references resolve, `git diff --check` passed, and repository preflight recognised contract version `0.8.0`. Preflight remains globally failed only by six unrelated pre-existing errors: one missing YAML delimiter, four broken HighLevel knowledge references and one waiting task without `next_review`. The manifest was regenerated with those results; no unrelated issue was repaired as part of this change.
