---
id: delegate-work-host-cursor
title: Dispatching packets on Cursor
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Dispatching packets on Cursor

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Not yet verified on the owner's machine. Cursor's agent has offered subagent and background-agent
facilities in recent versions; the exact controls change between releases, so check the
running version before claiming parallel execution.

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
- The session-log listener covers Cursor `agent-transcripts`; whether subagent transcripts land
  there is unverified.
