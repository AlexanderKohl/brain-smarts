---
id: PROPOSAL-one-conductor-per-area
title: One conductor per area of work, each the owner's one conversation for that area
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-11-03T09:22:05+10:00
updated: 2026-11-03T09:30:23+10:00
rule_id: SMART-RULE-0048
accepted_by: brain-owner
accepted_at: 2026-11-03T09:29:00+10:00
implemented_at: 2026-11-03T09:30:23+10:00
previous_contract_version: 3.0.0
new_contract_version: 3.0.0
target_files:
  - /RULES.md
---

# One conductor per area of work, each the owner's one conversation for that area

An amendment to `SMART-RULE-0048` (its first and second bullets); the rule keeps its identifier
(CONTRACT §13.2). No contract wording changes, so `contract_version` stays 3.0.0.

## Current problem

`SMART-RULE-0048` makes one conductor thread the owner's only conversation for everything the
brain does, and forbids a team session from asking the owner anything. In practice one thread then
carries every area of the owner's work at once: product builds with their tool output, writes to
external systems, financial analysis, strategy documents and governance. The record of one such
thread (the owner's main conductor, 2 November 2026) shows the cost: three automatic compactions in
one day, each followed by a handover checkpoint before any dispatch could continue, and work on a
valuation sitting beside hundreds of tool calls about cable sizing. Independent guidance says the
same: a session that mixes unrelated work degrades the current task, compaction loses what was
already tried, and separate agents are right where the areas use different data, carry different
risk and have different owners. The owner's own question of 3 November 2026 asked whether the areas
should be ring-fenced.

## Current wording

```text
- The owner talks to one conductor thread at a time. The conductor answers the owner, puts every
  question to the owner, and gets work done through workers (`SMART-RULE-0024`).
- For a task that will take more than a day and passes several of the owner's gates, the
  conductor may start a team session: a separate agent session that conducts that one body of work
  with its own workers (a team thread, `SMART-RULE-0043`). At most `team_sessions_max` in
  `/memory/OWNER.md` run at once, two when it is not set. A team session never puts a question to
  the owner and never starts another session; it sends its questions and results to the
  conductor, who asks the owner in the conversation. The conductor archives a team session the day
  it hands back. No other session is started unless the owner asks for one in words, or a rule
  names it.
```

## Proposed wording or exact diff

```text
- The owner's work is divided into areas, each with its own lifecycle, node and data: for example
  strategy and finance, a product, and operations in external systems. `/memory/OWNER.md` names
  the areas in `conductor_areas`; without that field there is one area. Each area has one
  conductor thread, the owner's one conversation for that area: it answers the owner, puts every
  question of its area to the owner, and gets work done through workers (`SMART-RULE-0024`). At
  most one live conductor per area, and no more areas than `conductor_areas` names. The
  `## Handover` of `/memory/projects/brain-development/STATE.md` names every live conductor with
  its area and the time it took over; a new thread that finds a live conductor for its area asks
  the owner which thread continues before dispatching anything. A fact one area learns that
  another needs is written to the brain's files (the node that owns it), never passed from one
  thread's context to another.
- Within an area, for a task that will take more than a day and passes several of the owner's
  gates, the conductor may start a team session: a separate agent session that conducts that one
  body of work with its own workers (a team thread, `SMART-RULE-0043`). At most `team_sessions_max`
  in `/memory/OWNER.md` run at once across all areas, two when it is not set. A team session never
  puts a question to the owner and never starts another session; it sends its questions and
  results to its area's conductor, who asks the owner in the conversation. The conductor archives
  a team session the day it hands back. No other session is started unless the owner asks for one
  in words, or a rule names it.
- The conductor routes; the owner does not have to. When the owner raises a topic that belongs to
  another area, the conductor says so in its first reply, names the area, and offers to start or
  hand to that area's session (the host's offer, where it has one) before doing anything beyond
  answering a quick question. It never carries another area's work on because the owner happened
  to raise it here, and it never leaves the owner to work out which lane a topic belongs to.
```

The third and fourth bullets of the current rule are unchanged and follow the three above; in the
last, "the only thread the owner talks to" is read as "the only thread the owner talks to for that
area". The third proposed bullet is the owner's instruction of 3 November 2026: "the conductor
should actively tell me to start a new session when a topic is in a different lane rather than
relying on the user getting that right".

## Reason

The areas differ in the three ways that justify separate agents: data (a product repository against
a strategy repository against external accounts), risk (a reversible tag against an irreversible
valuation figure), and cadence (minutes of tool output against hours of reasoning). One thread per
area keeps each conversation's context about one thing, so compaction comes rarely and loses less,
and a failure or a stop in one area leaves the others running. The owner still has one conversation
per area and never has to find a worker.

## Scope and behavioural consequences

- `/RULES.md`, `SMART-RULE-0048`, bullets one and two.
- `/memory/OWNER.md` gains an optional `conductor_areas` list (an owner-layer field, not
  governance); the owner's own memory records their areas.
- The brain-development node's `## Handover` lists every live conductor by area.
- The feedback companion (`/shared/skills/product-feedback/`) and the owner board
  (`/shared/skills/owner-board/`) serve whichever conductor owns the product area; a card is still
  owned by one conductor.
- The worker brief (`/shared/skills/delegate-work/templates/worker-brief.template.md`) digests this
  rule; its line changes in the same commit as the rule (`SMART-RULE-0007`).

## Risks and conflicts

- Two areas may touch one file (the Impact Power memory node's `STATE.md` holds strategy and
  product handovers today). Mitigation: one `## Handover` subsection per area, and merges under
  `SMART-RULE-0034`.
- The owner may be asked the same question by two areas. Mitigation: the brain-development
  handover names the live conductors; a conductor reads it before asking.
- More live threads cost more of the host's session limits. Mitigation: `conductor_areas` is short
  (three for this owner) and `team_sessions_max` still caps team sessions across areas.

## Migration

None for records. On acceptance the main conductor hands its non-product areas to new conductors
from their nodes' `## Handover`; the owner's `conductor_areas` is written at the same time.

## Rollback

Revert the commit that applies the wording; threads in flight finish their turn and the next
session starts under the previous wording. Nothing in the records depends on the new wording.

## Validation

- Repository preflight on the mechanics (the rule file and the worker brief in one commit).
- The brain-development `## Handover` lists the conductors after the first day under the rule.
- After two weeks: compactions per conductor-day and checkpoints written, compared with the
  2 November 2026 record (three compactions in one thread in one day), recorded under
  `/memory/projects/brain-development/` as a learning (`SMART-RULE-0028`).

## Acceptance

Do you accept `PROPOSAL-one-conductor-per-area`: the three bullets of `SMART-RULE-0048` above
replace the current first two, `conductor_areas` is added to `/memory/OWNER.md` as an optional owner
field, and the worker brief's line for `SMART-RULE-0048` is updated in the same commit? Yes or no.
