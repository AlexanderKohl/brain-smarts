---
id: RULE-2026-0006
title: Forward-Looking Rules And External Target Confirmation
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
owner: brain-owner
created: 2026-08-05T11:45:00+10:00
updated: 2026-08-05T11:48:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-05T11:48:00+10:00
implemented_at: 2026-08-05T11:48:00+10:00
previous_contract_version: 0.3.0
new_contract_version: 0.4.0
target_files:
  - /CONTRACT.md
---

# Forward-Looking Rules And External Target Confirmation

## Status

Accepted and implemented from the owner's explicit acceptance of proposal `RULE-2026-0006` as written. Applied to `/CONTRACT.md` at 2026-08-05T11:48:00+10:00 (`contract_version` `0.3.0` → `0.4.0`).

## Current problem

1. When the owner uses forward-looking language ("in the future", "from now on", and similar), agents may treat the instruction as a one-off chat preference. Durable behavioural constraints then fail to land in `CONTRACT.md` or the relevant `RULES.md`, so later sessions do not inherit them. Contract section 5 already distinguishes temporary instructions from durable knowledge, but does not require promoting forward-looking behavioural instructions into operating rules at the correct governance level.

2. HighLevel work routinely spans many subaccounts. The owner expects agents to always confirm which subaccount is the target before writes or other side-effecting operations. Today that expectation is only weakly covered:
   - `/shared/skills/gohighlevel-access/SKILL.md` says "Confirm the target company or location and intended change before a write" (skill-level; not inherited as repository governance).
   - a client communications project's `RULES.md` requires confirming "the exact action, target and consequence" before live writes, but does not explicitly require asking which HighLevel subaccount.
   - `/CONTRACT.md` records account/organisation/location in external-data provenance (section 10.4) but does not require confirming the target before side-effecting operations.

## Current wording

`/CONTRACT.md` section 5 ends at subsection 5.5 (Mixed input). There is no subsection for forward-looking operating rules.

`/CONTRACT.md` section 10.4 (External data) currently reads:

```markdown
### 10.4 External data

Data retrieved through a skill must record:

- source system
- retrieval time
- relevant account, organisation or location
- query or scope
- whether the data is live, cached or partial
- any transformation applied

Do not represent retrieved data as complete when coverage is partial or uncertain.
```

There is no section 10.5.

## Placement options considered

| Option | Forward-looking rule | Subaccount / target confirmation | Recommendation |
| --- | --- | --- | --- |
| A | CONTRACT §5 (input classification) | CONTRACT §10 (external systems), general multi-tenant wording | **Recommended.** Owner asked for a CONTRACT rule for forward-looking language. A general CONTRACT rule for external targets covers HighLevel subaccounts and other multi-tenant systems; HighLevel-specific wording stays in the GHL skill. |
| B | CONTRACT only | GHL `SKILL.md` only | Weaker for non-GHL systems; relies on agents reading the skill every time. |
| C | CONTRACT only | Also tighten a client communications project's `RULES.md` | Narrower than needed; that project's `RULES.md` is protected and would need its own accepted proposal. Not included here. |

This proposal implements **option A** for `/CONTRACT.md` only. A companion clarification in `/shared/skills/gohighlevel-access/SKILL.md` (not protected governance) may be applied separately without this proposal.

## Proposed wording or exact diff

### Change 1 – insert new subsection after section 5.5

Insert immediately after the Mixed input example block (before `## 6. Routing information`):

```markdown
### 5.6 Durable operating rule

A forward-looking instruction that changes how agents must behave in future sessions.

Signals include phrases such as "in the future", "from now on", "going forward", "always", "never again", or equivalent language that clearly intends ongoing behaviour rather than a one-off action.

When such an instruction is identified:

1. Do not treat it as a temporary chat preference.
2. Identify the correct governance level: this contract, root `RULES.md`, a node `RULES.md`, or a skill's permissions and operating instructions.
3. Draft or update the rule at that level. If the target is protected governance under section 13.2, follow the proposal-and-acceptance process before applying it.
4. Record the decision in the relevant log when the rule becomes active.

Until the rule is active in the governing file, do not claim the instruction is durable repository policy.
```

### Change 2 – insert new subsection after section 10.4

Insert immediately after section 10.4 (before `## 11. Raw files and Markdown derivatives`):

```markdown
### 10.5 External target confirmation

Before any write or other side-effecting operation against an external system that has multiple accounts, organisations, companies, locations or subaccounts:

1. Ask the owner which specific target applies for this operation, or obtain an explicit confirmation of the named target, before proceeding.
2. Identify the target at the precision the system requires (for HighLevel: company and subaccount/location; for other systems: the equivalent account or organisation scope).
3. Do not infer the target solely from recent chat context, the most recently used account, a project default, or an earlier session without a current confirmation for this operation.
4. Stop and ask when the target is missing, ambiguous or conflicts with another candidate.

Read-only discovery that lists available targets does not require prior target confirmation. Using a discovered target for a write or other side effect does.
```

### Change 3 – metadata

In `/CONTRACT.md` front matter:

- set `contract_version` from `0.3.0` to `0.4.0`
- update `updated` to the implementation timestamp

## Reason

1. Forward-looking owner language is a recurring failure mode: agents comply in the current chat and omit updating the governing rule file, so the next session loses the constraint. Section 5.6 closes that gap by classifying such input as a durable operating rule and requiring a level-correct persistence path.
2. Multi-tenant external writes are high-risk. A CONTRACT-level confirmation rule makes "ask which target" inherited repository behaviour, not an optional skill courtesy. HighLevel subaccounts are the motivating case; the wording stays system-neutral so Xero organisations and similar scopes are covered the same way.

## Scope and behavioural consequences

- Applies repository-wide once `/CONTRACT.md` is updated to `contract_version` `0.4.0`.
- Agents must promote "from now on / in the future" behavioural instructions into the correct rule file (via section 13.2 when protected), not leave them as chat memory.
- Agents must confirm the external multi-tenant target before side-effecting operations; HighLevel subaccount confirmation becomes a CONTRACT obligation, not only a GHL skill bullet.
- Does not change a client communications project's `RULES.md` or any other active `RULES.md`.
- Does not itself authorise any live HighLevel or other external write.

## Risks and conflicts

- Slightly more owner prompts before external writes. Intended.
- Overlap with existing GHL skill and AI Communications Brain live-write rules is additive, not contradictory; skill/project wording may stay stricter for their scopes.
- "Always ask" could be read as requiring a fresh question even when the owner just named the target in the same turn. The proposed wording allows explicit confirmation of an already-named target for this operation, while still forbidding silent inference from defaults or prior context.
- No conflict with section 13.2; this proposal itself follows that process.

## Migration

- Update any repository manifest or preflight expectation that pins `contract_version` `0.3.0` so it accepts `0.4.0` after implementation.
- No historical content rewrite. Existing skill and project rules remain valid and may be tightened later under their own proposals if desired.

## Rollback

Revert the two inserted subsections and restore `contract_version` to `0.3.0` as one version-control change; mark this proposal `reverted` and record the reason.

## Validation

- After acceptance and apply: run `/shared/skills/repository-preflight/scripts/preflight.py`
- Confirm `/CONTRACT.md` `contract_version` is `0.4.0` and both new subsections match this proposal verbatim
- Confirm this proposal's `target_files` covers `/CONTRACT.md`

## Acceptance

The owner explicitly accepted proposal `RULE-2026-0006` as written (insert CONTRACT §5.6 and §10.5, and bump `contract_version` from `0.3.0` to `0.4.0`) at 2026-08-05T11:48:00+10:00, before the live `/CONTRACT.md` change was applied.

## Implementation record

- Applied Change 1, Change 2 and Change 3 verbatim to `/CONTRACT.md` (2026-08-05T11:48:00+10:00).
- Updated `/repository-manifest.json` `contract_version` to `0.4.0` to match the contract.
- Updated root and brain-development `LOG.md` / `STATE.md`.
- Ran the repository preflight validator after apply: reported `contract 0.4.0`; no protected-governance coverage error for `/CONTRACT.md` (covered by this proposal's `target_files`). Remaining FAIL is the pre-existing client project module `README.md` UTF-8 decode error (and a warning for undocumented root folder `ghl_docs_tmp`), unrelated to this change set.
