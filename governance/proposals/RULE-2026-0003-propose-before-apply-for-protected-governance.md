---
id: RULE-2026-0003
title: Propose Before Apply For Protected Governance
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
owner: brain-owner
created: 2026-08-05T08:02:00+10:00
updated: 2026-08-05T08:17:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-05T08:17:00+10:00
implemented_at: 2026-08-05T08:17:00+10:00
previous_contract_version: 0.3.0
new_contract_version: 0.3.0
target_files:
  - /memory/projects/brain-development/RULES.md
---

# Propose Before Apply For Protected Governance

## Status

Accepted and implemented from the owner's explicit acceptance of the exact diff shown below, obtained before `/projects/brain-development/RULES.md` was changed. This proposal deliberately followed the sequence it defines: drafted first with status `proposed`, presented for one direct acceptance question, and only applied to the live file after the owner's explicit acceptance at 2026-08-05T08:17:00+10:00.

## Current problem

In the immediately preceding work in this repository, an agent edited `/projects/credential-management/RULES.md` (a protected governance file under Contract §13.2) directly and immediately, in response to a fully specified owner instruction, before any governance-proposal record existed and before the owner had accepted an identified proposal or displayed diff through the formal process. The owner then accepted the change after the fact, and a covering proposal (`RULE-2026-0002`) had to be created retroactively purely to satisfy the preflight validator's protected-governance check. `/projects/brain-development/RULES.md` currently states that protected governance may be promoted "only after explicit owner acceptance under Contract section 13.2," but does not explicitly state that the proposal-and-acceptance step must happen *before* the live protected file is changed, so the existing wording did not by itself prevent this apply-then-reconcile sequencing.

## Current wording

`/projects/brain-development/RULES.md`, current complete rule list:

```markdown
- Treat the repository as an evolving system.
- Test rules against real work before expanding metadata.
- Prefer simple conventions that different AI systems can follow.
- Record unresolved design questions as tasks.
- Draft governance changes under `/projects/brain-development/proposals/`; proposal content is not active governance.
- Promote stable decisions into protected governance only after explicit owner acceptance under Contract section 13.2.
- Keep experimental detail inside this project until validated.
```

## Proposed wording or exact diff

Replace the existing bullet:

```markdown
- Promote stable decisions into protected governance only after explicit owner acceptance under Contract section 13.2.
```

with:

```markdown
- Promote stable decisions into protected governance only after explicit owner acceptance under Contract section 13.2.
- Before writing any substantive or semantic change to a protected governance file (`/CONTRACT.md`, an active `RULES.md`, a governance schema or template, bootstrap-loading instructions, or the repository preflight skill and validator), first draft or identify its governance-proposal record under `/projects/brain-development/proposals/` and obtain the owner's explicit acceptance of the exact diff. Apply the change and update the proposal's status only after that acceptance.
- Do not edit the live protected file first and seek acceptance, or file the covering proposal, afterward – even when the owner's instructions were highly specific and detailed. A detailed instruction describes desired content; it does not itself substitute for presenting the exact diff and receiving one direct acceptance answer.
- If an unavoidable prior sequencing error results in a protected file already being changed without a preceding accepted proposal, pause further related work immediately, present the exact diff for owner acceptance, and create or complete the covering proposal before continuing – do not mark that proposal `accepted` or `verified` without the owner's explicit answer to a direct acceptance question.
```

## Reason

Close the gap that allowed an agent to change protected governance immediately from a detailed instruction and only formalise proposal-and-acceptance afterward. The preceding session showed this gap concretely: `/projects/credential-management/RULES.md` was changed first, and `RULE-2026-0002` had to be filed retroactively just to make the preflight validator pass, which is a repair rather than the intended workflow.

## Scope and behavioural consequences

- Applies to `/projects/brain-development/RULES.md`, which governs process rules for this project and, by extension, sets the expected practice for handling every protected governance file across the repository.
- Any agent handling a request that would change `/CONTRACT.md`, an active `RULES.md`, a governance schema/template, bootstrap instructions, or the preflight skill/validator must draft the proposal and obtain explicit acceptance before writing to the live file, not after.
- Detailed or highly specific owner instructions no longer count as sufficient acceptance by themselves; they must still be reflected back as an exact diff with one direct acceptance question, per the existing Contract §13.2 requirement.
- The narrow exception for pausing and reconciling after an unavoidable prior sequencing error remains available, but only as an immediate, explicitly flagged correction – not as a routine substitute for proposing first.
- No `/CONTRACT.md` behavioural change; `contract_version` remains `0.3.0`. This proposal only strengthens existing `/projects/brain-development/RULES.md` wording.

## Risks and conflicts

- None identified against existing rules or `RULE-2026-0001`; this proposal reinforces rather than contradicts the existing acceptance protocol, and explicitly narrows the one-time bootstrap exception already recorded there so it is not read as a repeatable pattern.
- Slightly slower turnaround for future protected-governance changes, since a proposal must be drafted and explicitly accepted before the live file changes rather than concurrently. This is an intended consequence, not an unintended risk.

## Migration

No historical content migration is required. `RULE-2026-0002` remains valid as the record covering the specific `/projects/credential-management/RULES.md` change it already documents; this proposal does not revise or invalidate it, only tightens the process for future changes.

## Rollback

Revert the added bullets in `/projects/brain-development/RULES.md` as one version-control change, restoring the single existing acceptance bullet; mark this proposal `reverted` and record the reason.

## Validation

- run `/shared/skills/repository-preflight/scripts/preflight.py` after the change is applied and confirm `/projects/brain-development/RULES.md` is covered by this proposal's `target_files`
- inspect the complete diff against the wording shown above

## Acceptance

The owner explicitly accepted the exact diff shown above for `/projects/brain-development/RULES.md` in this proposal (`RULE-2026-0003`) at 2026-08-05T08:17:00+10:00, before the live file was changed.

## Implementation record

- Applied the accepted three bullets verbatim to `/projects/brain-development/RULES.md`, immediately after the existing "Promote stable decisions..." bullet (2026-08-05T08:17:00+10:00).
- Logged the owner's acceptance and the applied change in `/projects/brain-development/LOG.md`.
- Ran the repository preflight validator and confirmed `/projects/brain-development/RULES.md` remains covered by this proposal's `target_files`.
