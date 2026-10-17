---
id: PROPOSAL-eight-workers-under-an-approved-plan
title: Up to eight file-changing workers in a run that an approved plan has split
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-10-17T11:39:36+10:00
updated: 2026-10-17T11:39:36+10:00
rule_id: SMART-RULE-0024
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.5.0
new_contract_version: 2.5.0
target_files:
  - /RULES.md
  - /memory/RULES.md
  - /shared/skills/delegate-work/SKILL.md
  - /shared/skills/delegate-work/scripts/delegation.py
---

# Up to eight file-changing workers in a run that an approved plan has split

Read `/CONTRACT.md` first. This amends `SMART-RULE-0024` in place (a tighter, conditional raise of
its budget, CONTRACT §13.2) and keeps its identifier. It also retires the trial bullet of the owner
layer that asked for the measurement, because the measurement has been made.

## Current problem

`SMART-RULE-0024` holds every run to four workers "until a measured trial … justifies more". The
owner asked for that trial (owner layer, the trial bullet of the rule on one conversation with the
owner), and it ran on 2026-10-17: eight file-changing workers in one run, built from one approved
plan that gave each worker its own write paths and fixed every interface between them. The rule
still says four, and the delegation script refuses a fifth packet unless the run is marked as the
trial.

## Current wording

`/RULES.md`, `SMART-RULE-0024`:

```text
- Budget: depth one (workers do not delegate) and at most four workers per run, until a
  measured trial recorded under `/memory/projects/brain-development/` justifies more.
```

`/memory/RULES.md`: the second bullet of the owner layer's rule on one conversation with the owner,
which sets four workers until the trial is decided and asks the conductor to run the trial of six to
eight workers and report it. Its exact wording and the exact diff are shown to the owner with this
proposal (they name the owner, so they are not copied into the mechanics).

## Proposed wording or exact diff

`/RULES.md`, `SMART-RULE-0024`:

```diff
-- Budget: depth one (workers do not delegate) and at most four workers per run, until a
-  measured trial recorded under `/memory/projects/brain-development/` justifies more.
+- Budget: depth one (workers do not delegate) and at most four workers per run. A run may hold
+  up to eight workers when an approved build plan splits the work first: the plan names each
+  packet's write paths, no two packets share a path, and the plan fixes every interface between
+  the packets (names, data shapes, identifiers), so no worker needs another's result to finish.
+  The conductor approves the plan before the run opens and names it on the run. The machine
+  limit of `SMART-RULE-0037` still applies, and the number is the lower of the two. A raise
+  beyond eight needs another measured trial recorded under `/memory/projects/brain-development/`.
```

`/memory/RULES.md`: the trial bullet is replaced by one sentence saying that workers are the default
way to work in parallel within the budget of `SMART-RULE-0024`, and that the trial of 2026-10-17 is
recorded in the owner's brain-development log.

`/shared/skills/delegate-work/` (not protected; changes with the rule): `delegation.py new-run` gains
`--plan PATH` (a plan file that exists, recorded on the run); with it, `--max-workers` may be five to
eight; without it, the hard limit stays four. `--trial-workers` stays for a future trial beyond
eight. SKILL.md's budget paragraph and its failure behaviour say the same.

## Reason

The trial, as measured (the owner's brain-development log, 2026-10-17):

- eight workers, launched in one turn, about 15.5 minutes from launch to the last result; the
  slowest packet set the pace;
- `check-writes` clean; every result valid in substance (one on form only); the merged tree passed
  the full suites first time; the only fixes were two lines in shared code that named an owner
  node, and one gap in the plan itself, closed by one follow-up packet;
- conductor context about 5,000 tokens per result; free memory unchanged (10.5 GB before,
  10.8 GB after) on a machine with 16 logical processors.

What made it work was the plan, not the number: disjoint write paths and fixed interfaces. The raise
is therefore conditional on such a plan.

## Scope and behavioural consequences

- Conductors: a run of five to eight workers needs an approved plan named on the run; without one,
  four as today.
- Workers: unchanged.
- The owner: larger batches finish in about the time of their slowest packet; the plan is the place
  a choice for the owner surfaces, before any build.

## Risks and conflicts

- A plan that looks disjoint but is not (two packets reach the same file through a shared helper):
  `check-writes` finds it at merge, and the conductor reviews each diff before staging.
- A plan gap (something no packet owns) is found only at integration; the trial had one. The
  conductor's pre-merge checklist and the owner-layer rule's plan step stay in force.
- More parallel workers spend more tokens in a burst; `SMART-RULE-0003` and the machine limit still
  apply.
- No conflict with `SMART-RULE-0037`: the lower of the two limits wins.

## Migration

After acceptance: apply the two rule edits; change `delegation.py` and the skill; add tests for
`--plan` (five to eight allowed with a plan file, refused without, refused for a missing file);
update the rule index row if its wording changes; record the acceptance in the owner's
`/memory/governance/proposals/`.

## Rollback

Revert the commits in the mechanics and memory repositories; the budget returns to four and the
trial bullet returns.

## Validation

The delegate-work test suite (`python -m unittest discover -s shared/skills/delegate-work/scripts/tests`),
the repository preflight, and one real run opened with `--plan`.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record
