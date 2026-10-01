---
id: PROPOSAL-worker-means-a-work-packet
title: A worker is an agent started with a work packet; any other helper does its whole job
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-01T12:07:12+10:00
updated: 2026-10-01T12:07:12+10:00
rule_id: SMART-RULE-0024
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.3.0
new_contract_version: 2.3.0
target_files:
  - /RULES.md
---

# A worker is an agent started with a work packet; any other helper does its whole job

Read `/CONTRACT.md` first.

## Summary

A small amendment to `SMART-RULE-0024`, same identifier. The rule limits what a worker may do (no
commit, no shared files such as state and task lists) but does not say what a worker is. In a probe,
helper agents started without a work packet took those limits on themselves: one refused to write,
one left the task list's row for "the conductor", and none committed, so the follow-up work was
lost or done twice. After this change, only an agent started with a packet is a worker; any other
helper does its whole job.

- **For agents:** a helper asked to do part of the session's work finishes it, records included.
- **For the owner:** fewer half-finished changes that a later session has to repair.

## Current problem

TASK-2026-0003's probe (30 September 2026): subagents with no work packet treated themselves as
workers. One wrote nothing; one changed a task record but left `tasks/STATE.md` for "the
conductor", so preflight failed (`SMART-RULE-0025` wants the fix in the same turn); none committed.
When the session that started them is not acting as a conductor, those updates are lost.

## Current wording

`SMART-RULE-0024` has no definition of a worker. Its second bullet says to delegate through the
delegate-work skill's packets; its fourth lists what workers may not do.

## Proposed wording

A new bullet after the second:

> - A worker is an agent started with a work packet. An agent started without one – a host's
>   subagent given a piece of the session's own work – is not a worker and does not take on the
>   worker limits below: it does the whole job as the session would, including the state, log and
>   task-list updates the work needs and the commit. A session that wants work done in parallel,
>   or kept apart, uses a packet.

## Reason

The owner asked for speed and efficiency. Work done in part and repaired later is the slowest kind.

## Scope and behavioural consequences

Agents started without a packet, in every host. Packet workers are unchanged.

## Risks and conflicts

- **Two helpers committing in the same copy at once:** a session that runs helpers side by side
  is delegating and uses packets, which keep their paths apart.
- No conflict with an active rule.

## Migration

None.

## Rollback

Remove the bullet.

## Validation

The repository preflight passes. The next bootstrap probe or retest scenario with a helper agent
checks that it updates the records and commits.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal.

## Implementation record

None.
