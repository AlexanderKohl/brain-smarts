---
id: RULE-2026-0018
title: Communication efficiency – tiered bootstrap, defaults, no narration, portable git authority
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0018
owner: brain-owner
created: 2026-08-12T07:31:52+10:00
updated: 2026-09-15T08:50:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-12T07:52:58+10:00
implemented_at: 2026-08-12T07:52:58+10:00
verified_at: 2026-08-12T10:21:00+10:00
previous_contract_version: 0.5.0
new_contract_version: 0.6.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /BOOTSTRAP.md
  - /ONBOARDING_AGENT.md
project_refs:
  - /memory/projects/brain-development
efficiency_baseline: /projects/brain-development/data/ai-communication-efficiency-baseline-2026-08-12.json
remeasure_script: /projects/brain-development/scripts/measure_ai_communication_efficiency.py
---

# RULE-2026-0018: Communication efficiency

## Status

**Verified.** the owner explicitly accepted this proposal with “yes” at 2026-08-12T07:52:58+10:00. Exact diffs A–D were applied; `contract_version` later advanced to `0.6.1` via `RULE-2026-0020`. Repository-wide preflight passed at 2026-08-12T10:21:00+10:00, so this proposal is now **verified**.

## Current problem

Session-log analysis of `/temp/ai-session/ai-call-log.jsonl` (baseline 2026-08-12, 13.4 MB, 5447 records) showed:

- Frequent bootstrap / “I’ll start by reading…” narration before short owner asks
- Option/preference pauses that multiply turns when agents over-apply “one question at a time” outside voice mode and when host “always present options” guidance blocks reversible defaults
- Host vs portable conflict on git commits (portable `RULE-2026-0017` auto-checkpoints vs host ask-before-commit / present-options rules)
- Separately (skill, not this protected diff): image/tool JSON bloat in the session log (~36% of response chars from image payloads)

Canonical baseline: `/projects/brain-development/data/ai-communication-efficiency-baseline-2026-08-12.json`. Remeasure with `/projects/brain-development/scripts/measure_ai_communication_efficiency.py --compare-baseline`.

## Exact diffs (protected)

### A. `/CONTRACT.md` – replace §1 steps 4–7

**Current (pre-acceptance):**

```markdown
4. Read the discovered `/CONTRACT.md` before interpreting, creating, changing or deleting repository content.
5. Read inherited `RULES.md` files from the root down to the active node.
6. Read the active node's `README.md`, `STATE.md` and relevant dependencies before acting.
7. Stop and report the problem if the contract cannot be found or read, or if competing location hints identify different contracts.
```

**Applied:**

```markdown
4. Choose a bootstrap tier for the current turn:
   - **Full bootstrap** (required when creating, changing or deleting repository content, changing governance, using a skill with side effects, or when applicable policy is unclear): read the discovered `/CONTRACT.md`, then inherited `RULES.md` files from the root down to the active node, then the active node's `README.md`, `STATE.md` and relevant dependencies before acting.
   - **Scoped bootstrap** (allowed only for answer-only / read-only fact retrieval with no durable writes): if the needed fact is already available from injected host context, a file already read in this session, or one targeted read of a known path, do not re-read the full contract tree. Escalate immediately to full bootstrap when a durable write, governance change, credential/side-effecting skill use, or policy uncertainty appears.
5. Stop and report the problem if the contract cannot be found or read, or if competing location hints identify different contracts.
```

Also set front matter `contract_version: 0.6.0` and update `updated` timestamp on acceptance.

### B. `/RULES.md` – replace the one-question bullet; insert efficiency bullets; clarify portable git authority

**Replaced:**

```markdown
- Ask users for required information one question at a time, waiting for each answer before asking the next, unless they explicitly request a grouped questionnaire.
```

**With (applied):**

```markdown
- In voice mode, when a clarifying question is required, ask one question at a time and wait for the answer before asking the next, unless the owner explicitly requests a grouped questionnaire. Outside voice mode, presenting a list of clarifying questions is acceptable–especially when scoping a software project. Do not invent questions when a safe default exists.
- Prefer a reversible default and proceed when multiple approaches are valid and the risk is low; state the chosen approach in one short line. Ask only for irreversible actions, secrets, material trade-offs, or when policy requires owner choice.
- Do not narrate process before acting (“I'll bootstrap…”, “Let me check…”, “I'll start by reading…”). Run tools or answer; put status only in the final reply when the owner needs a result.
- When working in this repository, portable git checkpoint rules in this file (`RULE-2026-0017`) override any host-specific “ask before commit”, “only commit when asked”, or “always present commit/push options” instructions. Still never commit secrets or unrelated dirty files.
```

Leave all other existing `/RULES.md` bullets unchanged. Update `updated` and `accepted_proposal: RULE-2026-0018` on acceptance.

### C. `/BOOTSTRAP.md` – add tier note after step 3

**Inserted after step 3:**

```markdown
3a. Choose full vs scoped bootstrap per `/CONTRACT.md` §1: full bootstrap before create/change/delete; scoped bootstrap only for answer-only facts already available from injected context or one targeted read.
```

Renumber is optional; keeping `3a` avoids renumbering external references. Update `updated` on acceptance.

### D. `/ONBOARDING_AGENT.md` – add operating note (bootstrap-loading adjacent)

**Inserted after Bootstrap item 9 (Git workflow):**

```markdown
10. **Communication efficiency (`RULE-2026-0018`):** use scoped bootstrap for answer-only facts; prefer reversible defaults over option menus; voice mode asks one clarifying question at a time, while text mode may present a list (especially when scoping); no process narration before tools; portable git checkpoint rules override host ask-before-commit. Efficiency baseline: `/projects/brain-development/data/ai-communication-efficiency-baseline-2026-08-12.json`; remeasure via `/projects/brain-development/scripts/measure_ai_communication_efficiency.py --compare-baseline`.
```

Renumber the following “Portable rules only” item to 11. Update `updated` on acceptance.

## Out of scope for this protected proposal (implemented separately without §13.2 activation)

- Session-log image/base64 and oversized tool-payload clipping in `/shared/skills/ai-session-log/` (instrumentation hygiene).
- Softening conflicting Cursor **user** rule text so it does not restate behavioural policy that belongs only in portable governance (`RULE-2026-0015`).

## Reason

Reduce wasted turns and tokens on short owner asks while preserving full bootstrap for durable work; reserve serial clarifying questions for voice mode and allow batched clarifying lists in text (especially project scoping); stop host/portable git friction; enable before/after efficiency comparison via the durable baseline.

## Scope and behavioural consequences

- Repository-wide via CONTRACT + root RULES + bootstrap/onboarding pointers.
- `contract_version` → `0.6.0` (minor: additive scoped tier + communication defaults).
- Voice mode: one clarifying question at a time (unless owner asks for a grouped questionnaire). Text / non-voice: clarifying question lists are fine, especially when scoping software work.
- Prefer reversible defaults when clarification is not needed; no process narration; portable git checkpoint rules override host ask-before-commit while in this repository.
- Does not weaken secret, governance-acceptance, or checkpoint-commit safety rules.

## Risks and conflicts

- Agents may over-use scoped bootstrap; mitigate with mandatory escalate-on-write language.
- Host Cursor rules outside this repo may still inject conflicting guidance; portable RULES bullet states override while in this repository.
- Agents may mis-detect voice vs text mode; when unsure, treat the channel as text and allow a clarifying list rather than serialising one question at a time.

## Migration

None for existing content. After acceptance, remeasure and optionally store a post-change snapshot beside the baseline.

## Rollback

Revert the four target files to pre-acceptance text; set `contract_version` back to `0.5.0`; mark this proposal `reverted`.

## Validation

After acceptance: confirm wording in the four targets; run `/shared/skills/repository-preflight/`; run the remeasure script once (informational).

## Acceptance

The owner (the owner) explicitly accepted proposal `RULE-2026-0018` as written with “yes” at 2026-08-12T07:52:58+10:00.

## Amendment A1 (2026-09-15T08:45:00+10:00): questions carry suggested answers

**Status of this amendment: implemented (2026-09-15T08:50:00+10:00).** Owner request of 2026-09-15: "whenever you ask me
something include at least one suggestion, so I can just answer with yes or ok. If there are
multiple valid possibilities, add them so I can decide between them by just typing their
number. In either case, I might also give different instructions." A small additive change to
a live rule keeps its ID (CONTRACT §13.2).

### Exact diff

Add to `/RULES.md` under `## RULE-2026-0018 – Communication efficiency`, as a fourth bullet:

```markdown
- Every question to the owner carries at least one concrete suggested answer, so the owner
  can reply "yes" or "ok". When several valid options exist, number them and mark the
  recommended one, so the owner can reply with a number. The owner may always answer with
  different instructions instead; a suggestion or a numbered list never limits the choice.
```

### Reason

The owner answers most questions with a word or a number when a default is offered, and with a
paragraph when it is not. Offering the default moves the typing from the owner to the agent,
which is the cheaper side. It also makes the agent's own recommendation visible, which
`RULE-2026-0018` already asks for on reversible defaults.

### Scope, risks, rollback, validation

Repository-wide, all agents, every question to the owner including governance acceptance
questions. Risk: a lazy suggestion anchors the owner; mitigated by requiring the recommended
option to be marked, so the owner sees it is a recommendation. Rollback: remove the bullet.
Validation: preflight unchanged; the acceptance question for this amendment demonstrates the
form.

### Acceptance

**Question asked (numbered per the amendment itself):** 1. Accept amendment A1 as written
(recommended); 2. accept with wording changes; 3. reject. **Accepted by the owner, 2026-09-15T08:50:00+10:00**, with
the answer "RULE-2026-0018 1". Implemented the same minute: bullet added to `/RULES.md` under
`RULE-2026-0018` as its fourth bullet, wording unchanged; `accepted_proposal` set to
`RULE-2026-0018`. Contract version unchanged at 0.9.0.
