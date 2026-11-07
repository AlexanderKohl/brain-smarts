---
id: delegate-work-host-cursor
title: Dispatching packets on Cursor
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-10-01T22:44:24+10:00
owner: brain-owner
---

# Dispatching packets on Cursor

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Not yet verified on the owner's machine. Cursor's agent has offered subagent and background-agent
facilities in recent versions; the exact controls change between releases, so check the
running version before claiming parallel execution.

## Reading the context size

Cursor shows a context meter in its agent panel in recent versions; when the running version
does, read it and pass the token figure as `--context-tokens`. When it does not, pass
`--context-unknown "Cursor shows no context size"` and drain (SKILL.md, *When to stop
dispatching*) at the first compaction or after the fourth run in the thread, whichever comes
first. No compaction hook is installed here; the conductor tells the owner itself.

## Procedure

1. Create the run and packets with `delegation.py`, then print each packet's dispatch prompt.
2. If the running Cursor version offers subagents that can be launched from the agent
   conversation, launch one per packet with the dispatch prompt. Prefer any read-only or
   isolated-context option for `writes: none` packets.
3. If it does not, run the packets in sequence in the same conversation, one at a time, each
   time reading only the packet and its context references. Record `--parallel no` at
   `close-run`.
4. Validate, summarise, route, log and commit as the skill describes.

## Known limits

- Model selection per subagent is a host setting, not something the packet can force. Record
  the model that ran, or `unknown`.
- Cursor writes `agent-transcripts`; whether subagent transcripts land there is unverified,
  which matters if a transcript logger is in use.
