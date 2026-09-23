---
id: RULE-2026-0045
title: A record says what is true now, and something checks it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-17T18:05:00+10:00
updated: 2026-09-17T18:05:00+10:00
accepted_by: null
accepted_at: null
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0045 – A record says what is true now, and something checks it

## What happened

On 17 September 2026 the owner asked for an audit of what had been lost in a design thread. It
found four stale records at once, and they were not four mistakes.

- `TASK-2026-0050` said `ready` after ten of its eleven increments had landed across five
  versions. **A second thread read that word and reported the track as never picked up.**
- `TASK-2026-0049` said `ready` after its first two items shipped at `0.118.0`.
- `TASK-2026-0048` said `ready` with two increments landed and a packet in flight.
- `TASK-2026-0051` and `TASK-2026-0052` existed and were in no index, so nobody reading the
  index could see them.
- Both records a design thread wrote that day carried no contract front matter and failed
  `preflight.py` – the **same** break that had been repaired on two other records that morning.

## The shape

**A status is written when work starts and never when it finishes.** Dispatching is vivid and
closing is not, so the record is written at the moment attention is highest and never again.
And **a thread that writes records without running the validator hands its errors to whoever
runs it next**, which is how the same repair happened twice in one day.

## Why a rule is the wrong instrument on its own

`TASK-2026-0049` already says this about its own class of defect: *a rule saying do not do this
would be the fifth comment nobody reads; a test that compares the two lists is what closes it.*
A rule that says *remember to update the record* is the same habit with a sentence attached.

**So the substance of this proposal is that the checking is mechanical, and the rule's only job
is to require that a check exists.**

## Proposed rule text

> ## RULE-2026-0045 – A record says what is true now, and something checks it
>
> - A record's status word describes the present, not the moment it was written. When work
>   against a task lands, the task's status and its row in the index change on the same pass as
>   the commit – not later, and not when someone notices.
> - **Where work is tracked in two places, something must compare them without being asked.**
>   A node that tracks progress outside its task records owns a check that runs whenever that
>   progress is regenerated, and reports a task whose status contradicts it. Remembering is not
>   a control; the four instances above were all found by a person.
> - Run the repository validator before handing work to another thread or another agent, not
>   only before committing. Records that fail validation are the writing thread's to fix.

## What already implements it

- a project board's `status/reconcile.py` check 10 reads every board track's
  parent task and reports one that still says `ready` while the track has landed work or has a
  card in flight, or that is missing from `/tasks/STATE.md`. It runs on every board regeneration.
  **It caught `TASK-2026-0048` on the first run it ever made.**
- `/shared/skills/delegate-work/SKILL.md` now makes updating the parent task's status a numbered
  obligation after workers report, with the four instances recorded as the reason.

## Open question for the owner

Whether the second clause should be general governance or stay this project's practice. It is
written above as general, because the shape is not specific to a Chrome extension – but the only
implementation that exists is one project's script, and a rule that nothing else can satisfy is
a rule waiting to be ignored.

**Suggested answer: adopt it as written.** A node with no second place to track progress has
nothing to compare and the clause costs it nothing; a node that grows one inherits the
obligation at the moment it matters.
