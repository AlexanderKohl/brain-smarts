---
id: PROPOSAL-timestamps-not-ahead-of-the-clock
title: A timestamp is read from the clock, and the validator refuses one ahead of it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-23T20:37:08+10:00
updated: 2026-09-23T20:37:08+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.0.0
new_contract_version: 2.0.1
target_files:
  - /CONTRACT.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
---

# A timestamp is read from the clock, and the validator refuses one ahead of it

## Summary

Agents write `created`, `updated` and log-heading timestamps by guessing a plausible round time
instead of reading the clock, and the guess lands ahead of the real time. CONTRACT §8.2 gains one
sentence saying where a timestamp comes from, and the repository preflight validator fails on any
of these timestamps more than five minutes ahead of the moment it runs. A check holds where
reminders do not.

## Current problem

In one working day an owner's brain recorded four separate corrections of timestamps written ahead
of the clock – by two different sessions – each found only because an agent happened to run
`date`. Nothing checks it: the validator accepts any well-formed timestamp, so a future stamp
passes and is committed. A future `updated` misorders records and makes a log read as though
work happened later than it did.

## Current wording

CONTRACT §8.2, the bullet list after "Do not use a date without a time for these fields or
entries.":

> - Keep `created` unchanged after the item is created.
> - Set `updated` to the time of the latest substantive content or metadata change.
> - Use the timezone of the event when known; otherwise use UTC.
> - Do not invent precision for migrated legacy records. […]

## Proposed wording or exact diff

CONTRACT §8.2, one bullet inserted after "Set `updated` …":

> - Take a new timestamp from the system clock at the moment of writing – the command's or the
>   script's own clock, never a remembered or rounded time. A timestamp is never later than the
>   moment it was written; the repository preflight validator fails on one more than five minutes
>   ahead of the time it runs.

Validator (`/shared/skills/repository-preflight/`):

- For every validated Markdown file outside a `templates/` folder: `created` and `updated` in
  front matter, and every log-entry heading (`## <timestamp>`) in a file named `LOG.md`, are
  compared with the time the validator runs. One more than five minutes ahead is an **error**
  naming the file, the field or heading, and how far ahead it is.
- The five minutes allow for clocks on different machines disagreeing slightly when repositories
  are synced; it is a constant in the script, named and explained.
- Raw evidence (`/memory/raw/`) is not checked, as for every other metadata rule.
- `SKILL.md` lists the new check.

Contract version 2.0.0 → **2.0.1** (patch: a clarification of an existing duty plus a check that
enforces it; no content becomes invalid – a scan of every brain file finds none ahead of the
clock today).

## Reason

- The failure is a habit, not an accident, and it recurs across sessions; the working-method fix
  (read the clock) is written down and still failed three times in one session.
- Following the recorded lesson that a check holds where reminders do not, the validator makes a
  future stamp impossible to commit rather than merely discouraged.

## Scope and behavioural consequences

- **Agents:** read the clock when writing a stamp; a guessed future stamp fails the commit check.
- **The owner:** nothing to do; a commit that fails names the file and the stamp.
- **Owners on several machines:** a clock more than five minutes fast on one machine would make
  that machine's fresh stamps fail on another; the message says how far ahead, so the clock can be
  corrected.

## Risks and conflicts

- **Legitimate future times:** none of the checked fields is meant to be in the future; due dates
  and review dates are separate fields and are not checked.
- **A slow validator clock** would reject correct stamps; the tolerance and the message cover it.
- No conflict with active rules.

## Migration

None: a scan today finds no timestamp ahead of the clock.

## Rollback

Revert the contract bullet and the validator commit; set `contract_version` back to 2.0.0.

## Validation

- Validator tests on a fictional brain: a front-matter `updated` ten minutes ahead fails; one two
  minutes ahead passes; a `LOG.md` heading an hour ahead fails; the same heading in a template or
  under raw evidence is not checked; a past stamp passes.
- The validator passes on every brain repository after the change.

## Acceptance

Not yet requested. Ask one direct question that identifies
`PROPOSAL-timestamps-not-ahead-of-the-clock`. Do not treat silence, adjacent approval or general
agreement as acceptance.

## Implementation record

None.
