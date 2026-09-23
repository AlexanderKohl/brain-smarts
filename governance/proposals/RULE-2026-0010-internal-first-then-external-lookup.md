---
id: RULE-2026-0010
title: Internal-first then external lookup (root RULES)
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0010
target: /RULES.md
target_files:
  - /RULES.md
created: 2026-08-06T13:26:08+10:00
updated: 2026-08-06T13:30:36+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T13:30:36+10:00
implemented_at: 2026-08-06T13:30:36+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0010: Internal-first then external lookup

## Status

Accepted and implemented from the owner's explicit acceptance of proposal `RULE-2026-0010` as written. Applied to `/RULES.md` at 2026-08-06T13:30:36+10:00. No `contract_version` change (root rules only).

## Reason

The owner directed a durable top-level rule: always look **internally first**; only if no results are found, look **externally**. This supersedes an earlier draft recommendation to “prefer external first / skip repo search for ABN” where that conflicts.

Related session waste (ABN lookup via explore-only subagent while ABR/Gmail/vault were required; continuing doomed parallel greps after owner redirect) is reconciled here without making “skip internal” the primary path.

## Current wording

`/RULES.md` Repository rules currently include minimum-context and shared-skills bullets, but no internal-then-external lookup order, capability-matching for subagents, or abandon-on-owner-redirect behaviour.

Relevant existing bullets (unchanged by this proposal):

```markdown
- Read and prompt with only the minimum context relevant to the current task; avoid loading unrelated files, restating unchanged context, or repeating information already available elsewhere.
- Use shared skills for reusable capabilities.
```

## Proposed wording

Append these four bullets to the **Repository rules** section of `/RULES.md` (after the existing bullets, before end of list):

```markdown
- When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge, and other already-known canonical homes) with a **targeted** search. Do not run exhaustive repository grep theatre to prove absence.
- If the fact is absent or still uncertain after that internal check, use the authoritative external shared skill when one exists or is mandated (for example ABR Web Services for Australian Business Numbers and GST registration). After a verified external result, update the relevant durable brain record when the fact belongs in the repository.
- Do not delegate work to explore/repo-only subagents when the answer requires vault credentials, Gmail, or an external API. Match agent capabilities to the job, or do the lookup in-session.
- When the owner redirects to a different path (skill, external system, email), abandon or stop parallel searches that the redirect made obsolete; do not finish a doomed explore pass “for completeness.”
```

## Scope and behavioural consequences

- Applies repository-wide via root `/RULES.md` inheritance.
- Internal check is required and must stay targeted; external skills remain the fall-through for registry facts (ABN/GST via ABR once available).
- Does **not** keep “skip repo search for ABN” as primary policy.
- Does not change `contract_version` (root rules only; no CONTRACT text change).
- Does not create the ABR skill; it only routes to it when present or mandated.

## Risks and conflicts

- Supersedes the prior draft “prefer external first for ABN” package (Change A in the log-review suggestion) where that package skipped internal search as primary.
- Agents may under-search internally if they treat “targeted” too narrowly; mitigate by naming CRM/knowledge/canonical homes explicitly.
- Low migration risk: additive bullets only.

## Migration

None required for existing content. Optional later: document ABR skill in `ONBOARDING_AGENT.md` when that skill lands (not protected; not part of this proposal).

## Rollback

Remove the four accepted bullets from `/RULES.md` and mark this proposal `reverted` or `superseded`.

## Validation

After acceptance, confirm `/RULES.md` includes the four bullets and run `/shared/skills/repository-preflight/`.

## Acceptance question

Do you accept proposal `RULE-2026-0010` as written for `/RULES.md`?
