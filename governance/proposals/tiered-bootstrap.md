---
id: PROPOSAL-tiered-bootstrap
title: Read the core at start-up, and each rule when it applies
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-29T06:36:01+10:00
updated: 2026-09-29T08:20:35+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.2.0
new_contract_version: 2.3.0
target_files:
  - /AGENTS.md
  - /BOOTSTRAP.md
  - /CLAUDE.md
  - /CONTRACT.md
  - /CORE.md
  - /RULES.md
  - /repository-manifest.json
  - /shared/skills/delegate-work/SKILL.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/core.py
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/scripts/session.py
  - /shared/skills/repository-preflight/tests/test_core.py
---

# Read the core at start-up, and each rule when it applies

Read `/CONTRACT.md` first. This is the rework of part 6 of `PROPOSAL-research-changes`, which was
set aside after the before-and-after test. The owner agreed the design on 29 September 2026. The
exact diff is the branch `proposal/tiered-bootstrap` in the mechanics, with the contract-version
bump of the library and memory manifests on the same branch name there. Nothing here is active.

## Plain-language summary

Today every session that may write reads the whole contract and the whole of `/RULES.md` first:
117 KB with the owner files, about 29k tokens, whether it edits one task or builds software. After
this change it reads one generated file, `/CORE.md` (41 KB), and the owner files: 49 KB, about 12k
tokens, 58 % less. `/CORE.md` holds, word for word, the contract sections and rules that always
apply, and two tables that say, for every other section and rule, the situation in which to read it.
A read-only question reads only what it needs. No rule is dropped or reworded; only when it is read
changes.

## Current problem

1. **Start-up cost.** On four read-only code questions the brain made the final context 1.83 times
   a plain worker's; about 41.5k tokens on one of them.
2. **The scoped tier is unreachable in practice.** The tier is defined inside the contract, so an
   agent must read the contract to learn it may skip reading it, and host pointers say "read it in
   full".
3. **Part 6 cost more, not less.** Loading rules where they apply was 40–42k tokens on light
   sessions against 38k. It added session hooks and extra steps; smaller files did not mean fewer
   tokens.

## Current wording and exact diff

The branch holds the exact diff; the parts that change behaviour:

- **CONTRACT §1, item 4, before:** "Full bootstrap (required when creating, changing or deleting
  brain content, …): read the discovered `/CONTRACT.md`, then `/RULES.md`, then the owner profile
  …" and "Scoped bootstrap (…): if the needed fact is already available … do not re-read the full
  contract tree. Escalate immediately to full bootstrap when a durable write … appears."
- **CONTRACT §1, item 4, after:**
  - "Choose a bootstrap tier for the current turn, before reading further:"
  - "**Scoped bootstrap** (allowed only for answer-only / read-only fact retrieval with no durable
    writes): read what the answer needs – injected host context, a file already read in this
    session, or targeted reads of known paths – and nothing else."
  - "**Full bootstrap** (required before the first creation, change or deletion of brain content, a
    governance change, use of a skill with side effects, or when applicable policy is unclear): read
    `/CORE.md`, then the owner profile `/memory/OWNER.md` and the owner-layer rules
    `/memory/RULES.md`, then inherited node `RULES.md` files down to the active node, then the
    active node's `README.md`, `STATE.md` and relevant dependencies before acting. `/CORE.md` is
    generated from this contract and `/RULES.md`: it holds, verbatim, the sections and rules that
    always apply, and the tables that say when every other section and rule applies."
  - "**Read by situation.** Before acting in a situation named under `Applies when` in those
    tables, read that section of this contract, or that rule in its canonical home, in full. When
    it is unclear whether a row applies, read it."
  - "**Escalation.** A turn that began scoped escalates to full bootstrap the moment it is about to
    write, take a side effect, use a credential or meet policy doubt: before that first action,
    never after it. A write to a brain repository begins with `session.py start`
    (`SMART-RULE-0038`), which prints the full-bootstrap reading list, so every agent in every host
    meets the escalation at the same step."
- **CONTRACT §1, front-matter meaning, before:** "if the contract has not been read in the current
  working session, read it before using the file." **After:** "if the bootstrap of the tier the work
  needs (item 4 above) has not been done in the current working session, do it before using the
  file."
- **CONTRACT §14, steps 1 and 4:** "read this contract" becomes "choose the bootstrap tier; for full
  bootstrap read `/CORE.md` (section 1)"; step 4 reads a contract section or `/RULES.md` rule
  "when its `Applies when` fits the work".
- **CONTRACT §15:** adds "`/CORE.md` is current with this contract and `/RULES.md`
  (`core.py check`)".
- **`/RULES.md`:** the identifier table gains an `Applies when` column; a new table lists every
  contract section with its `Applies when`. `always` rules: `SMART-RULE-0003`, `0009`, `0010`,
  `0014`, `0027`, `0034`, `0036`, `0038`; `always` contract sections: §1, §2, §3.4–§3.6, §5, §6,
  §13, §14. No rule text changes.
- **`/BOOTSTRAP.md`, `/AGENTS.md`, `/CLAUDE.md`, delegate-work's successor steps:** choose the tier
  first; a writing session reads `/CORE.md`, not the contract and `/RULES.md` whole.
- **`core.py`** builds `/CORE.md`; the **preflight** fails when it is stale, a row has no
  `Applies when`, or a rule heading has no row; **`session.py start`** prints the reading list.

## Change from the agreed design

One point, for simplicity: the `Applies when` text sits in a column of the existing index table in
`/RULES.md`, not on a line under each rule heading. Rules whose canonical home is the contract or a
skill have no heading in `/RULES.md`, so a column is the one place every rule already has a row.
The generated file is `/CORE.md` (the index plus the always-applicable text, one read) rather than
an index alone, so a writing session needs three reads instead of seven.

## Reason

The brain's value is in rules applied at the right moment, not in rules read at the start of every
session. The research's leaders keep a small always-loaded core; the test showed the brain should
too, and showed how not to do it.

## Scope and behavioural consequences

- Every session in every host, and new owners. Contract 2.2.0 to 2.3.0 (minor: compatible;
  changes when rules are read).
- An agent must notice that a situation in the tables has arisen and read the rule then.
- A host that injects the owner's own global pointer should point to `/BOOTSTRAP.md` rather than
  say "read `CONTRACT.md` before anything else"; that file is the owner's, outside the
  repositories, and is changed after acceptance.

## Risks and conflicts

- **Missed triggers.** A rule not read cannot be followed. Mitigation: the rules the test found
  weakest (the Git accounting line, suggested answers, list order) are `always`, the owner layer is
  still read whole, "when unclear, read it", and pass marks on adherence below.
- **A session that never writes through `session.py`** (a host that cannot use a separate folder)
  still meets the escalation rule in §1, without the printed reminder.
- **Conflicts:** none known; `SMART-RULE-0003` asks for exactly this.

## Migration

None for records. At acceptance: merge the branch in each repository, rebuild `/CORE.md`, write the
manifests, update the owner's global host pointer.

## Rollback

Revert the merge commits; the full read is today's behaviour and needs nothing else.

## Validation

Done on the branch: `core.py check` passes; preflight tests 99 of 99 pass, including five new tests
(the core holds what always applies and both tables; a row without `Applies when` fails; a rule
heading without a row fails; a stale core fails and a fresh one passes; the real core is current).

To do before acceptance, in the before-and-after harness with the first test's scenarios, today's
brain (A), a repeat of A as control, and this change (B), pass marks fixed now:

1. Light sessions: B uses no more total tokens processed than A; the aim is at least 30 % fewer.
2. Heavy sessions: B uses at least 15 % fewer.
3. Rule adherence: B's automatic and blind manual scores within 2 points of A's.
4. Trigger checks: in the scenarios that need them, B reads the triggered rule before acting
   (commit, delegation, external write, software change), and a scenario that starts as a question
   and turns into a write reads the core before the first write.

Total tokens processed are measured, not final context, because the two differ.

## Acceptance

Not yet requested. One direct acceptance question on this diff after the harness results.

## Implementation record

None.
