---
id: delegate-work-host-claude-code
title: Dispatching packets on Claude Code
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T18:00:00+10:00
owner: brain-owner
---

# Dispatching packets on Claude Code

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Claude Code exposes a subagent facility (the `Agent` tool) that can run several workers at once.
Verified with a trial run of several read-only workers launched in one turn.

## Mapping packet fields to the Agent tool

| Packet field | Agent tool |
|---|---|
| `context_mode: isolated` | any subagent type other than a forking one; the worker starts from the packet |
| `context_mode: fork` | a forking subagent type when the host offers one; otherwise treat as isolated and say so in the result |
| `writes: none` | a read-only subagent type (for example `Explore`) or `general-purpose` with the packet's instructions |
| `writes: worktree` | `isolation: "worktree"` so the worker gets its own git worktree; the conductor merges |
| `model: inherit` | omit the model parameter |
| `model: <name>` | the `model` parameter, only from the host's offered list; the result must record what ran |
| parallel execution | launch every packet with `run_in_background: true` in the same turn, then wait for the completion notifications |

## Procedure

1. Create the run and packets with `delegation.py`, then print each packet's dispatch prompt.
2. Launch one Agent call per packet, all in the same response, with the dispatch prompt as the
   prompt. Do not paste the packet body; the worker reads it from the path.
3. When each completion notification arrives, run `validate-result` for that packet.
4. After all packets report, run `summarise`, synthesise, route, log, commit, and `close-run`
   with `--host "Claude Code" --parallel yes`.

## Known limits

- The subagent's model name is not always visible to the worker. The result may say `unknown`;
  the conductor records the model the host reported in the completion notification.
- A worker cannot ask the owner anything. A `blocked` result is the only escalation path.
- Claude Code writes each subagent's transcript to `<session>/subagents/agent-*.jsonl`; if a
  transcript logger is in use, it should read those files from the first line and attribute
  each record to its agent. The Agent tool's completion notifications, which report tokens, tool uses and duration per worker,
  remain the quickest cross-check of a run's cost.
- Workers name the model inconsistently (a model id in one result, a display name in another). Both are honest;
  the conductor normalises when logging.
- In a trial of three read-only workers in parallel, all returned `completed` and passed
  validation first time, and the wall clock was well under half that of running them in
  sequence. Read each worker's token cost from its completion notification.
