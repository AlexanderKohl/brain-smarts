---
id: PROPOSAL-tiered-bootstrap
title: Read the core at start-up, and each rule when it applies
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-29T06:36:01+10:00
updated: 2026-10-01T11:06:07+10:00
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
  - /CORE-RULES.md
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
114 KB with the owner files, about 28k tokens, whether it edits one task or builds software. After
this change it reads two generated files, `/CORE.md` and `/CORE-RULES.md` (about 21 KB each), and
the owner files: 51 KB, about 13k tokens, 55 % less. They hold, word for word, the contract sections
and rules that always apply, and two tables that say, for every other section and rule, the
situation in which to read it. Each is short enough for a host to show whole, and every pointer says
to read the bootstrap files with the host's file-reading tool, not a shell command.
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

## Revision of 1 October 2026: two parts, and the file-reading tool

TASK-2026-0003's probe (31 runs in Claude Code on the web, 30 September 2026) found that Claude Code
replaces a shell output of more than about 30,000 characters with a 2 KB preview and the path of the
saved output (29,000 shown whole, 31,000 cut). 12 of the 31 runs read the bootstrap files with a
shell command, and only 4 of those opened every saved output; one model opened none and answered as
if it had read the contract. The Read tool showed every file whole. The one-file core of
29 September, 41 KB, would have been cut the same way. So, at the owner's answer of 1 October:

1. The core is two files: `/CORE.md` holds the contract sections that always apply; `/CORE-RULES.md`
   holds the two tables and the rules that always apply. Each is about 21,000 characters.
2. `core.py` fails, and so the preflight fails, when either part is longer than 28,000 characters.
3. CONTRACT §1, `/BOOTSTRAP.md`, `/CLAUDE.md` and `/AGENTS.md` say to read the bootstrap files with
   the host's file-reading tool, not a shell command such as `cat`.
4. The branch is brought up to date with `main` (the validator's split into modules, and
   `SMART-RULE-0041` and `0042`, each with its `Applies when`).

Codex, Cursor and Claude Code on Windows were not probed; their limits may differ, and the retest
records how each arm's sessions read the core.

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
    `/CORE.md` and `/CORE-RULES.md`, then the owner profile `/memory/OWNER.md` and the owner-layer
    rules `/memory/RULES.md`, then inherited node `RULES.md` files down to the active node, then the
    active node's `README.md`, `STATE.md` and relevant dependencies before acting. The two files are
    generated from this contract and `/RULES.md`: `/CORE.md` holds, verbatim, the sections of this
    contract that always apply; `/CORE-RULES.md` holds the tables that say when every other section
    and rule applies, and, verbatim, the rules that always apply. Each is short enough for a host to
    show whole; read them, and every bootstrap file, with the host's file-reading tool (for example
    Read), not a shell command such as `cat`: a shell may show only the start of a long file."
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
  bootstrap read `/CORE.md` and `/CORE-RULES.md` (section 1)"; step 4 reads a contract section or
  `/RULES.md` rule "when its `Applies when` fits the work".
- **CONTRACT §15:** adds "`/CORE.md` and `/CORE-RULES.md` are current with this contract and
  `/RULES.md` (`core.py check`)".
- **`/RULES.md`:** the identifier table gains an `Applies when` column; a new table lists every
  contract section with its `Applies when`. `always` rules: `SMART-RULE-0003`, `0009`, `0010`,
  `0014`, `0027`, `0034`, `0036`, `0038`; `always` contract sections: §1, §2, §3.4–§3.6, §5, §6,
  §13, §14. No rule text changes.
- **`/BOOTSTRAP.md`, `/AGENTS.md`, `/CLAUDE.md`, delegate-work's successor steps:** choose the tier
  first; a writing session reads `/CORE.md` and `/CORE-RULES.md` with the file-reading tool, not
  the contract and `/RULES.md` whole.
- **`core.py`** builds both parts; the **preflight** fails when a part is stale or longer than
  28,000 characters, a row has no `Applies when`, or a rule heading has no row; **`session.py
  start`** prints the reading list.

## Change from the agreed design

One point, for simplicity: the `Applies when` text sits in a column of the existing index table in
`/RULES.md`, not on a line under each rule heading. Rules whose canonical home is the contract or a
skill have no heading in `/RULES.md`, so a column is the one place every rule already has a row.
The generated core holds the index and the always-applicable text rather than an index alone, so a
writing session needs four reads instead of seven (two since the revision of 1 October).

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

None for records. At acceptance: merge the branch in each repository, rebuild the core, write the
manifests, update the owner's global host pointer. `new_contract_version` is 2.3.0; if
`PROPOSAL-placeholder-and-mirror-nodes` is accepted first, this change becomes 2.4.0.

## Rollback

Revert the merge commits; the full read is today's behaviour and needs nothing else.

## Validation

Done on the branch: `core.py check` passes; the preflight's tests pass, including six for the core
(the parts hold what always applies and both tables; a part over 28,000 characters fails; a row
without `Applies when` fails; a rule heading without a row fails; a stale part fails and a fresh one
passes; the real core is current).

To do before acceptance, in the before-and-after harness with the first test's scenarios, today's
brain (A), a repeat of A as control, and this change (B), pass marks fixed now:

1. Light sessions: B uses no more total tokens processed than A; the aim is at least 30 % fewer.
2. Heavy sessions: B uses at least 15 % fewer.
3. Rule adherence: B's automatic and blind manual scores within 2 points of A's.
4. Trigger checks: in the scenarios that need them, B reads the triggered rule before acting
   (commit, delegation, external write, software change), and a scenario that starts as a question
   and turns into a write reads the core before the first write.
5. Reading: every B session that bootstraps reads both parts whole (with the file-reading tool, or
   a shell output short enough to be shown whole).

Total tokens processed are measured, not final context, because the two differ.

## Acceptance

Not yet requested. One direct acceptance question on this diff after the harness results.

## Implementation record

None.
