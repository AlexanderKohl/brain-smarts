---
id: delegate-work-host-cursor
title: Dispatching packets on Cursor
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-11-22T12:52:34+10:00
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
`~/.cursor/agents/` (user), with the optional fields `name` (default: the file name), `description`,
`model` (default `inherit`), `readonly` and `is_background` (C2). Cursor also reads `.claude/agents/`
and `.codex/agents/` (and the same folders under `~`); on a name clash `.cursor/` wins and a project
file beats a user file (C2). C2 shows only Markdown files and does not say whether the TOML files
in `.codex/agents/` are read, nor how `.claude/` and `.codex/` rank against each other.

The brain ships Cursor worker types in `/.cursor/agents/` under the same names as the Codex and
Claude Code ones (`worker-no-judgement`, `worker-open-judgement`; Claude Code also has
`worker-bounded-judgement`): a work packet names the same worker type on every host (owner,
23 Nov 2026), and a name means one rung of the ladder, not a model (`SMART-RULE-0033`). Where Cursor
reads both its own folder and a Claude Code one, its own file wins. Cursor still lists the Claude
Code types, with Claude model ids it does not document; what it does with them is not verified.
`host_wiring.py apply --host cursor` copies the Cursor types to `~/.cursor/agents/` (SETUP.md step
E); a file there without the brain's marker line, or one defining an agent of the same name, is the
person's own and is kept. The files also carry the brain's own metadata fields (`id`, `type`,
`contract` and the rest), which the repository validator requires; C2 does not say how Cursor
treats fields it does not list. Cursor may substitute another model when an administrator blocks
the named one or the plan lacks it, and on legacy request-based plans without Max Mode subagents run
on Composer whatever `model` says (C2).

## The ladder on Cursor

The ladder of SKILL.md (*Choosing a worker's model and effort*). Cursor's own models draw on one
weekly pool on paid plans; other vendors' models are billed from prepaid credit at list price (C1).
So the lower rungs prefer Cursor's own models.

| Ladder rung | Cursor model and effort | Worker type | Notes |
|---|---|---|---|
| no judgement, rework only | `composer-2.5[fast=false]`: Composer 2.5, standard variant | `worker-no-judgement` | in the pool (C1); the id and the `[fast=false]` option are written in C2; without brackets the fast variant may be chosen (C2) |
| bounded judgement, or a person sees the result | Grok 4.7, medium | none | in the pool (C1); C1 gives the display name only and no id, so no worker file: name the model in the request |
| open judgement, or data, money, security or production | `inherit`: the conductor's own model and effort | `worker-open-judgement` | `inherit` is documented (C2); the current Opus-class model's own id is not (C1 gives only `claude-opus-5-5-fast`, the fast mode), so the type inherits rather than naming it |
| specialised, large reading load | Gemini 4 Argon | none | billed from credit (C1); no id given, so no worker file |

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
`<project>/.cursor/hooks.json` (C4). The brain's setup writes **none** of them, because the input
and the reply do not match what `hooks.py` reads and prints (C4, read 22 November 2026):

- `preCompact` receives the common fields (`conversation_id`, `generation_id`, `hook_event_name`,
  `workspace_roots` and others) plus `trigger` and context figures, but no `session_id` and no
  `cwd`; `hooks.py pre-compact` keys its marker on `session_id`, so every marker would be named
  `unknown`. It reads a JSON reply with `user_message`; `hooks.py` prints plain text.
- `sessionStart` receives `session_id` but no `cwd` or `source`, and reads a JSON reply with
  `additional_context`; `hooks.py session-start` prints Claude Code's `hookSpecificOutput` shape,
  which Cursor does not document, so its message would not reach the model.
- No event fires after a compaction, so `post-compact` has no trigger; the reload after one falls
  to the conductor, who tells the owner itself.

Wiring Cursor needs `hooks.py` to read `conversation_id` when `session_id` is absent and to print
Cursor's reply shapes; until then the conductor drains early, as on a host without hooks.

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
