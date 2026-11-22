---
id: delegate-work-host-cursor
title: Dispatching packets on Cursor
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-11-22T10:47:07+10:00
owner: brain-owner
---

# Dispatching packets on Cursor

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Cursor's agent launches subagents from the conversation; several launched in one message run at
once (C2). Read from the vendor's documentation on 22 November 2026; not yet run on the owner's
machine, and the controls change between releases, so check the running version before claiming
parallel execution and correct this note after the first run.

## Mapping packet fields to Cursor subagents

| Packet field | Cursor |
|---|---|
| `context_mode: isolated` | any subagent: each starts with a clean, separate context (C2) |
| `context_mode: fork` | none documented: treat as isolated and say so in the result |
| `writes: none` | `readonly: true` on the subagent: no edits and no state-changing shell commands (C2) |
| `writes: worktree` | ask for isolation: the subagent's own Git worktree and branch (C2) |
| `model`, `effort` | the subagent's `model` field (default `inherit`), with effort in brackets after the model id, for example `<model-id>[effort=high]` (C2) |
| parallel execution | several subagent calls in one message; `is_background: true` returns at once (C2) |
| depth one | a subagent may launch children of its own (C2). The packet still forbids delegation |

A custom subagent is a Markdown file with YAML front matter in `.cursor/agents/` (project) or
`~/.cursor/agents/` (user), with `name`, `description`, `model`, `readonly` and `is_background`
(C2). Cursor also reads `.claude/agents/` and `.codex/agents/`; on a name clash `.cursor/` wins and
a project file beats a user file (C2). So the brain's worker definitions for another host reach
Cursor too, carrying that host's model names, which Cursor does not list as its own: what it does
with them is not verified. Until the brain ships Cursor definitions, name the model in the request
that launches the subagent and record the model that ran. Cursor may substitute another model when
an administrator blocks the named one or the plan lacks it (C2).

## The ladder on Cursor

The ladder of SKILL.md (*Choosing a worker's model and effort*). Cursor's own models draw on one
weekly pool on paid plans; other vendors' models are billed from prepaid credit at list price (C1).
So the lower rungs prefer Cursor's own models.

| Ladder rung | Cursor model and effort | Notes |
|---|---|---|
| no judgement, rework only | `composer-2.5`, default effort | Cursor's own model, in the pool (C1, C2) |
| bounded judgement, or a person sees the result | Grok 4.7, medium | in the pool (C1, C3); only the display name is documented, the id is not verified |
| open judgement, or data, money, security or production | the current Opus-class model with `[effort=high]`, or `inherit` | from credit (C1); the id is not verified |
| specialised, large reading load | Gemini 4 Argon | listed (C1); context size and id not verified |

The automatic modes pick the model themselves (C1): a packet that names a model does not run under
one. Model names change: check the picker or C1 before a run, and record the model that ran.

## Reading the allowance

The remaining pool and its next reset appear in the editor's settings and under Usage on the
dashboard (C1). Nothing documents a reading the agent can take: the conductor asks the owner, and
weighs prepaid credit separately from the pool.

## Reading the context size

A per-chat context percentage is shown to the person (community posts, not documentation: not
verified). When the owner reads the figure out, pass it as `--context-tokens`. Otherwise pass
`--context-unknown "Cursor shows no context size"` and drain (SKILL.md, *When to stop
dispatching*) at the first compaction or after the fourth run in the thread, whichever comes
first.

## Compaction hooks

Cursor documents `sessionStart`, `preCompact` and other hooks in `~/.cursor/hooks.json` (user) and
`<project>/.cursor/hooks.json` (C4), so `hooks.py pre-compact` and `hooks.py session-start` could
run here. No trigger after a compaction is documented, so the reload after one falls to the
conductor, who tells the owner itself. Whether `hooks.py` reads Cursor's hook input unchanged is
not verified, and the brain's setup does not write these hooks yet.

## Procedure

1. Create the run and packets with `delegation.py`, then print each packet's dispatch prompt.
2. Launch one subagent per packet with the dispatch prompt, read-only for `writes: none` packets.
3. If the running version offers no subagents, run the packets in sequence in the same
   conversation, one at a time, each time reading only the packet and its context references.
   Record `--parallel no` at `close-run`.
4. Validate, summarise, route, log and commit as the skill describes.

## Known limits

- Cursor writes `agent-transcripts`; whether subagent transcripts land there is unverified,
  which matters if a transcript logger is in use.

## Sources

Read on 22 November 2026.

- C1: `https://cursor.com/docs/models`.
- C2: `https://cursor.com/docs/subagents`.
- C3: `https://cursor.com/help/models-and-usage/available-models`.
- C4: `https://cursor.com/docs/hooks`.
