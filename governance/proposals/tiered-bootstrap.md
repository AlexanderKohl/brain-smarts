---
id: PROPOSAL-tiered-bootstrap
title: Read the core at start-up, and each rule when it applies
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-29T06:36:01+10:00
updated: 2026-09-29T06:36:01+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.2.0
new_contract_version: 2.3.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /BOOTSTRAP.md
  - /AGENTS.md
  - /CLAUDE.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/templates/memory-skeleton/RULES.md
---

# Read the core at start-up, and each rule when it applies

Read `/CONTRACT.md` first. This is the rework of part 6 of `PROPOSAL-research-changes`, which was
set aside after the before-and-after test. It is presented in two steps: the design below for the
owner's agreement, then the exact diff on the branch `proposal/tiered-bootstrap` for acceptance.
Nothing here is active.

## Plain-language summary

Today every session that may write reads the whole contract and the whole of `/RULES.md` first,
about 25k tokens before any work, whether the session edits a task or builds software. After this
change a session reads a short core (the contract's always-needed sections, a generated one-page
index of every rule with when it applies, the owner's rules and profile), about 7k tokens, and
reads a rule's full text only when the work reaches the situation the index names. A read-only
question reads nothing beyond what it needs. No rule is dropped or reworded; only when it is read
changes.

## Current problem

1. **Start-up cost.** Full bootstrap reads `/CONTRACT.md` (about 43 KB) and `/RULES.md` (about
   60 KB). On four read-only code questions the brain made the final context 1.83 times the size of
   a plain worker's; about 41.5k tokens on one of them.
2. **The scoped tier is unreachable in practice.** CONTRACT §1 already allows a scoped bootstrap
   for read-only answers, but the tier is defined inside the contract, so an agent must read the
   contract to learn it may skip reading it, and host pointers say "read `CONTRACT.md` before
   anything else".
3. **Part 6 cost more, not less.** Loading rules where they apply was measured at 40–42k tokens
   on light sessions against 38k for today's brain. It added session hooks and extra steps; each
   costs a round trip and repeats context. Smaller files did not mean fewer tokens.

## Current wording

- CONTRACT §1, item 4: the two tiers, full and scoped, as now written.
- `/BOOTSTRAP.md` steps 3, 3a and 4: read the contract, then choose the tier, then read
  `/RULES.md` whole.
- `/RULES.md`: the identifier table (ID, rule, canonical home), then every rule's full text.

## Proposed design

1. **Choose the tier before reading, in `/BOOTSTRAP.md`.** The tier test moves ahead of the
   contract read, word for word from CONTRACT §1 (one text: BOOTSTRAP points to the section and
   quotes only its condition). Read-only answer: read what the answer needs and nothing else;
   escalate the moment a write, a side effect or a policy doubt appears.
2. **Each rule says when it applies, in its own canonical home.** One line, `Applies when:`,
   directly under each rule's heading in `/RULES.md`, the contract and the skills that hold
   `SMART-RULE` wording, for example `Applies when: committing, or before any final reply after a
   change` for `SMART-RULE-0014`. Rules that apply to every turn say `always`.
3. **A generated rule index.** `rule_index.py` builds `/RULES-INDEX.md` from those lines: ID,
   title, applies when, link to the canonical text. It is a generated list (`SMART-RULE-0007`, one
   text per rule) and the preflight fails when it is out of date, or when a rule has no
   `Applies when:` line.
4. **The core read at full bootstrap:** CONTRACT §1, §3.4–§3.6, §13 and §14 (marked in the
   contract as the core), `/RULES-INDEX.md`, every rule whose index line says `always`, then
   `/memory/OWNER.md`, `/memory/RULES.md` and the active node as today. The rest of the contract
   and `/RULES.md` is read by section when the index says it applies.
5. **No hooks and no extra steps.** The core is a fixed list of reads in one pass, fewer file
   reads than today's seven, so the part 6 failure cannot repeat.

## Reason

The brain's value is in rules applied at the right moment, not in rules read at the start of every
session. The research's leaders keep a small always-loaded core; the test showed the brain should
too, and showed how not to do it.

## Scope and behavioural consequences

- Every session in every host, the mechanics and new owners' skeletons. Contract 2.2.0 to 2.3.0
  (minor: compatible, changes when rules are read).
- An agent must now notice that a situation in the index has arisen and read the rule then. A
  missed trigger is the main risk; see below.

## Risks and conflicts

- **Missed triggers.** A rule not read cannot be followed. Mitigation: `always` for the rules the
  test found weakest (Git accounting line, en dashes, suggested answers), and pass marks on
  adherence below.
- **Trigger wording drifts from the rule.** Each trigger lives beside its rule and is reviewed in
  the same change.
- **Conflicts:** none known with an active rule; `SMART-RULE-0003` (token-efficient operation)
  asks for exactly this.

## Migration

Add the `Applies when:` lines, generate the index, mark the contract's core sections, update the
bootstrap and pointer files and the memory skeleton. New files, listed here because
`target_files` names only existing ones: `/RULES-INDEX.md` (generated),
`/shared/skills/repository-preflight/scripts/rule_index.py` and its test
`/shared/skills/repository-preflight/tests/test_rule_index.py`. No record changes.

## Rollback

Revert the merge commit; the full read is today's behaviour and needs nothing else.

## Validation

Pass marks fixed before any run, in the before-and-after harness with the same scenarios as the
first test, today's brain (A), a repeat of A as control, and this change (B):

1. Light sessions: B uses no more total tokens processed than A, and the aim is at least 30 %
   fewer.
2. Heavy sessions: B uses at least 15 % fewer.
3. Rule adherence: B's automatic and blind manual scores within 2 points of A's.
4. Trigger checks: in the scenarios that need them, B reads the triggered rule before acting
   (commit, delegation, external write, software change).

Total tokens processed are measured, not final context, because the two differ.

## Acceptance

Not yet requested. First step: the owner agrees the design above. Second step: one direct
acceptance question on the exact diff and the test results.

## Implementation record

None.
