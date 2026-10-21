---
id: PROPOSAL-fixture-epochs-and-node-names
title: Fixture epoch values and memory node names stay clear of the personal-data check
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-21T12:53:44+10:00
updated: 2026-10-21T12:53:44+10:00
amends: SMART-RULE-0008
target_files:
  - /RULES.md
---

# Fixture epoch values and memory node names stay clear of the personal-data check

## Summary

Two habits make the personal-data check refuse clean work, and nothing written tells an agent to
avoid them. This proposal adds two bullets to `SMART-RULE-0008`, which already governs fixtures and
the check:

1. Ten-digit epoch-second values in test fixtures look like telephone numbers to the check. Agents
   will pick them inside the digit run reserved for fiction from the start, and a hit found later
   is fixed by the author of the tests, not by a blanket swap of values.
2. The check reads every memory project node's folder name as an owner term. Agents will give a new
   memory project node a name different from every skill in the library, so the skill's own name
   is never a hit in the library.

Nothing else changes. The check itself is not changed, so its *Failure behaviour* section stays as
it is.

## Placement (CONTRACT §13.2, §5)

- Both lines are generic: any owner with any fixtures or nodes meets them, and both follow from how
  the shared preflight works. They belong in the mechanics layer, not in `/memory/RULES.md`.
- Both are about keeping the personal-data check and fictional data compatible, which is
  `SMART-RULE-0008`'s subject. Under §13.2 a small additive amendment keeps the existing identifier,
  so no new rule number is taken.
- Ruled out: a preflight check (it would change what the validator refuses, a larger change with
  its own *Failure behaviour* wording, for two observations); CONTRACT §7 (node creation is about
  structure, and a contract change would raise `contract_version` for a naming detail); skill
  operating text (no single skill owns either habit).

## Current wording

`/RULES.md`, `SMART-RULE-0008`, last bullet:

```markdown
- **The check confirms; it does not clean.** The validator runs the personal-data check on every shareable repository before each commit, and a hit fails it. Fix a hit at its source. Exempt a value only when it is genuinely public or generic – a vendor's published documentation, a documented default – and give the reason beside the exemption. When a writing habit or a template invited the hit, record it as a learning (`SMART-RULE-0028`).
```

## Proposed wording

The bullet above stays unchanged; these two bullets follow it:

```markdown
- **Fixture numbers are chosen to pass from the start.** A run of nine or more digits, such as a ten-digit epoch-second timestamp, reads as a telephone number. In fixtures, choose such values so their digits contain the run reserved for fiction, `55501` (for example `1755501000`), when the fixture is first written, and derive every expected result from them. A hit found later is fixed by whoever wrote the tests, keeping their ordering and range assertions true, never by a blanket swap of values.
- **A memory node is not named after a library skill.** The check reads the folder name of every memory project node as an owner term. Give a new memory project node a name that no skill in the library has, or the skill's own name becomes a hit in the library and its commit is refused.
```

## Reason

Two learning records, both observed once on 2026-10-07 in one build and integrated on 2026-10-21:
`/memory/projects/brain-development/data/learnings/fixture-timestamps-read-as-phone-numbers.md` and
`/memory/projects/brain-development/data/learnings/a-memory-node-may-not-share-a-library-skill-name.md`.
In the first, a blanket swap of fixture values after the fact broke nine assertions. The mechanism
matches the check's code: its phone pattern matches nine to fourteen digits, the run `55501` marks
fiction, and owner terms include memory project folder names (as of 2026-10-21; source:
/shared/skills/repository-preflight/scripts/personal_data.py, verified by reading the code, RUN-20261021-125122 W01).
Owner approval to draft both as one proposal: the owner's answer to the digest of 2026-10-21.

## Scope and expected consequences

- Affects every agent writing fixtures or creating memory project nodes, in every repository the
  brain governs. Existing fixtures and nodes are not rewritten; they change only when they hit.
- Fewer refused commits, and no repair by swapping values across tests.

## Risks, conflicts and migration

- Risk: an agent might read the first bullet as allowing any value containing `55501` in
  non-fixture data; the bullet names fixtures only.
- Conflicts: none found in `/RULES.md` or `/memory/RULES.md`. No migration.
- The node-name rule depends on the check's current way of reading owner terms; if that changes,
  the bullet should be revisited.

## Rollback

Remove the two bullets from `/RULES.md` and record the reversal (`reverted_at`) in this proposal's
owner record under `/memory/governance/proposals/`.

## Validation

- Run `python shared/skills/repository-preflight/scripts/preflight.py --root .` on the change;
  it passes, and the protected-governance check finds this proposal covering `/RULES.md` once it
  is accepted.
- Confirm the example `1755501000` passes the personal-data check and a ten-digit value without
  the run is reported.
