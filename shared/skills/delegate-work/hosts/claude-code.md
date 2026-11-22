---
id: delegate-work-host-claude-code
title: Dispatching packets on Claude Code
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-11-22T10:48:05+10:00
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
| `model: inherit` | omit the model parameter; the subagent runs at the conductor's model and effort |
| `model` and `effort` | the Agent tool's `model` (`haiku`, `sonnet`, `opus`, `fable`) and `effort` parameters on a `general-purpose` worker; the pinned types (`worker-sonnet-medium` for the ladder's first rung, `worker-opus-medium`, `worker-fable-medium`) remain shortcuts for their pair; the Agent tool's type and model must match the packet's `model`, so a packet that names Sonnet is never sent to a Fable type. Ladder on Claude Code: `sonnet` medium; `opus` medium; `opus` high or `inherit`; `fable` only for open judgement with its allowance healthy |
| allowance | `get_usage` (`plan.windows`, per-model weekly percentages) before every `new-run` and `new-packet` |
| parallel execution | launch every packet with `run_in_background: true` in the same turn, then wait for the completion notifications |

## Reading the context size

The desktop app offers a session-usage tool (`get_usage`, session `self`) that reports the
tokens in this session's context, the window size and the percentage at which auto-compaction
starts. Read it before every `new-run` and `new-packet` and pass the token figure as
`--context-tokens`; state it in the dispatch line. In the terminal CLI the status line can show
the same figure; when no reading is available, pass `--context-unknown "<reason>"`. After a
compaction the app runs the brain's `SessionStart` hook for the `compact` matcher, which tells the
thread to open its next reply to the owner by saying it was compacted and when, and to end that
reply with the handover prompt and the offer of a new thread; it also prints the session id and the
`checkpoint-done` command, and dispatching is refused until that has run. Every compaction from
25 October to 21 November 2026 (57 of 57) shows this hook's `hook_success` record; the host labels
a command given by its absolute path `command hook` in that record, so count by `hookName`
(`SessionStart:compact`), not by the command text.

Before a compaction, the `UserPromptSubmit` hook `hooks.py context-check` reads the size of the
thread's context from the last assistant record of its transcript (the last 256 kB only). Below
the threshold it says nothing; at or above it, once per 50 000 further tokens, it tells the thread
to finish the current step, write the checkpoint and end the reply with the handover prompt and
the context size. The threshold is `context_warn_tokens` in
`/memory/skills/repository-preflight/config/context-guard.json`, else 70 % of the largest
context before an earlier compaction of the session, else 600 000. Every hook exits 0 whatever
fails, because a failed hook can block a compaction and end the thread.

## Procedure

1. Read the context size (above). Create the run and packets with `delegation.py`, then print
   each packet's dispatch prompt.
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
- **The notification's token figure is the worker's final context size, not what it processed.**
  Measured on 28 read-only workers: it equals the last API call's input, cache and output tokens.
  Each worker also re-read its cached context between steps, 9 to 28 times that figure, which
  the notification does not show. Say which of the two a reported cost means; the per-call
  `usage` in the transcript under `<session>/subagents/` holds both. The `output_file` the
  launch result names was empty for workers that handed back.
- Workers name the model inconsistently (a model id in one result, a display name in another). Both are honest;
  the conductor normalises when logging.
- In a trial of three read-only workers in parallel, all returned `completed` and passed
  validation first time, and the wall clock was well under half that of running them in
  sequence. Read each worker's token cost from its completion notification.
- A subagent inherits the conductor's effort level unless its definition pins one. At maximum
  effort an implementation card that takes a minute at medium can take ten or more, so a packet
  that does not name a worker type runs at whatever the conductor is set to. A definitions folder
  created during a session is watched only from the next session.
- The pinned worker types are defined in `<brain_root>/.claude/agents/`, which Claude Code loads
  only for sessions opened in the brain root. A session opened in a project repository has them
  only when they were also copied to `~/.claude/agents/` (`/SETUP.md` step E). When they are
  missing, dispatch a `general-purpose` worker with the packet's `model` and `effort`, and tell
  the owner the copy is missing.
