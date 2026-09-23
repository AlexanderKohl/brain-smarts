---
id: delegation-result-template
title: Delegation result template
type: template
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Result: {{TITLE}}

The script `/shared/skills/delegate-work/scripts/delegation.py new-packet` creates this
skeleton beside the packet with `status: pending`. The worker fills every section and sets
`status`, `host`, `model`, `changed_paths`, `validation` and `artifacts` in the front matter.
`validate-result` rejects a result that is missing a section, reports changed paths a packet did
not allow, names files that do not exist, or contains anything that looks like a secret.

## Summary

Three to six sentences the conductor can use without reading further.

## Conclusion

The recommendation or answer, with the acceptance criteria addressed one by one.

## Verified

Facts established by reading a file, running a command or observing a system, each with where
it was seen.

## Assumed or unverified

Anything inferred, remembered or not checked. Say what would settle it.

## Negative findings

What was ruled out and the evidence that ruled it out.

## Sources

Files read, commands run, external systems consulted with retrieval time and scope
(CONTRACT section 10.4).

## Facts to route

Durable facts the conductor should consider persisting, each with a proposed canonical home
(`KNOWLEDGE.md`, `STATE.md`, `LOG.md` or a task) and whether it is verified.

## Open questions

Questions only the owner or the conductor can answer, with enough context to act on them. A
`blocked` result must have at least one.

## Suggested tasks

Outstanding work that should outlive this run, phrased as an outcome with an owner and a next
action. The conductor decides whether to create the `/memory/tasks/` record.
