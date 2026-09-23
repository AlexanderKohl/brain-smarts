---
id: draft-existing-skill-additions
title: Additions to delegate-work and product-development (draft for review)
type: skill_draft
schema_version: 0.2
contract: /CONTRACT.md
status: draft
scope: shared
created: 2026-09-17T16:30:00+10:00
updated: 2026-09-17T17:30:00+10:00
owner: brain-owner
---

# Additions to Existing Skills

Draft text for two skills that already exist. Not active. Each section below is checked against
what the skill already says before it is added, so nothing is duplicated; where the skill already
covers it, the migration adds nothing and says so.

## To `/shared/skills/delegate-work/SKILL.md`

### What `## Handover` contains

Moved from `RULE-2026-0032`, which now names this skill as the form the section takes. The rule
keeps when to checkpoint and what a checkpoint must not do; this is the shape of the record.

Under `## Handover` in the owning node's `STATE.md`, current at every checkpoint:

- each delegation run, with its id and folder
- each worker, with its packet, what it is doing, its branch or worktree, and whether its result
  file is still pending
- the reminder that a worker's completion notice reaches only the thread that launched it, so a
  successor must read the result files itself
- branches and builds, with the commit and the folder the owner loaded
- owner steps outstanding
- decisions still open
- for work spanning nodes, one line per other node pointing at its own `## Handover`

The `## Handover` of `/projects/brain-development/STATE.md` additionally names the active conductor,
by session title and the time it took over, and the other live sessions it knows of. That
requirement stays in the rule, because a thread that never opens this skill still has to honour it.

### Packet and result format

The existing skill already specifies these. No change proposed; `RULE-2026-0037` now points here
rather than restating that packets and results live under `/temp/delegation/runs/`.

## To `/shared/skills/product-development/SKILL.md`

### Depth selection criteria

**No addition. Withdrawn from the previous draft.**

That draft introduced an ordered ranking of factors, a "highest applicable sets the depth" selection
rule, and high assurance for "a failure the owner would have to explain to someone else". None of
that is in `RULE-2026-0028` or in this skill today. It was new policy presented as a faithful move,
and it would have pushed ordinary work to heavier depth than the current criteria require.

The criteria already exist and are unchanged: `references/process.md` under *Proportional depth*
defines light, standard and high-assurance, and `SKILL.md` line 32 gives the non-material and
escalation examples. The rule's trimmed wording, "select light, standard or high-assurance depth by
the skill's criteria", points at those. The factors it previously listed inline, and which the skill
already carries, remain: investment, uncertainty, reversibility, affected users, security and privacy
exposure, operational criticality, and consequence of failure, weighed together rather than ranked.

Any deliberate change to the depth criteria is a separate proposal with its own reasoning, not a
line in a migration.

### The canonical record, minimum contents

**No addition.** `SKILL.md` line 138 already specifies it, including that a compact section in an
existing plan suffices for a low-risk light change. `RULE-2026-0028`'s removed sentence said the
same thing.

### The whole-repository review

Moved from `RULE-2026-0033`, which now says to run the review here and state its answers briefly.
Before reporting a non-trivial change complete, answer:

1. Does it follow the strongest existing pattern for this problem?
2. Has it introduced a second way of doing something that already has one?
3. Does it conflict with an architectural, product or data-model decision elsewhere?
4. Can any obsolete code now be removed?
5. Has it made the system easier or harder to maintain?

Clearly non-material changes as defined in `RULE-2026-0028` may skip it.

Note on the first two questions: they overlap `RULE-2026-0045` (look for the existing one first),
which is the duty. These are the review of whether the duty was met, asked after the fact, and the
wording says so rather than restating the duty a second time.
