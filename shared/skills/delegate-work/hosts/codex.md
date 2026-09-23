---
id: delegate-work-host-codex
title: Dispatching packets on Codex
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Dispatching packets on Codex

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Not yet verified on the owner's machine. Assume the Codex CLI session has no parallel subagent
facility unless the running version demonstrably offers one.

## Procedure

1. Create the run and packets with `delegation.py` exactly as on other hosts, so the packets
   are portable and a later session on another host could pick them up.
2. Run the packets in sequence in the same session. For each packet read only its file and its
   context references, write its result file, then move to the next.
3. Record `--parallel no` at `close-run`. Never describe the run as parallel.
4. Validate, summarise, route, log and commit as the skill describes.

## Known limits

- Sequential execution in one context forfeits the isolation benefit: later packets see earlier
  results. Note this under Assumed or unverified in each result when it could have mattered.
- The session-log listener filters Codex sessions to this repository per file; sequential
  packet work is captured as ordinary session traffic.
