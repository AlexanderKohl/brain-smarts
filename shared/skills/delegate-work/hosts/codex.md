---
id: delegate-work-host-codex
title: Dispatching packets on Codex
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-11-22T12:52:34+10:00
owner: brain-owner
---

# Dispatching packets on Codex

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Codex spawns subagents in parallel in the Codex app, the CLI and the IDE extension when asked to
("spawn one agent per packet"), or when `AGENTS.md` or a skill asks for it (S2). Each subagent runs
in its own thread and returns a summary to the main thread. The CLI's `/subagents` switches between
threads; the IDE extension's background-agent panel can stop one (S2). Read from the vendor's
documentation on 22 November 2026; not yet run on the owner's machine, so the first run on Codex
records what actually happened and corrects this note.

## Mapping packet fields to Codex subagents

| Packet field | Codex |
|---|---|
| `context_mode: isolated` | a spawned subagent; it starts its own thread (S2). Whether it sees any of the parent's conversation is not verified: give it only the dispatch prompt |
| `context_mode: fork` | no fork option documented (S2): treat as isolated and say so in the result |
| `writes: none` | sandbox and approval cannot be set per agent; subagents inherit the parent's (S2). Read-only rests on the packet's instructions |
| `writes: worktree` | no worktree option documented for subagents (S2): the conductor creates the worktree with Git and names it in the packet, or the packet runs in sequence |
| `model`, `effort` | a custom agent's `model` and `model_reasoning_effort`, or `agents.default_subagent_model` and `agents.default_subagent_reasoning_effort`; unset means the parent's model and effort (S2) |
| parallel limit | `agents.max_concurrent_threads_per_session` (legacy `agents.max_threads`); unset lets Codex choose (S2). Set it to `4` to match `SMART-RULE-0024` |
| depth one | effort `ultra` "uses subagents for parallel work" (S1). Never give a worker `ultra`: it would delegate further |

## The ladder on Codex

The ladder of SKILL.md (*Choosing a worker's model and effort*) in Codex model ids (S1). Effort
values: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (S2); the app calls `low` "Light" (S1).

| Ladder rung | Codex model and effort | Worker type | What the vendor says it is for (S1, paraphrased) |
|---|---|---|---|
| no judgement, rework only | `gpt-6-luna`, `medium`; step up to `high` before changing model | `worker-no-judgement` | focused, high-volume work: summarising, extraction, focused coding |
| bounded judgement, or a person sees the result | `gpt-6.2-sol`, `medium` | `worker-bounded-judgement` | everyday work such as editing code or drafting a report; 500 000-token default context |
| open judgement, or data, money, security or production | `gpt-6.2-astra`, `high`, or `inherit` | `worker-open-judgement` | demanding work such as tracing a bug across services; 272 000-token default context |
| specialised, allowance healthy | `gpt-6.1-sol`, `medium`, for long repeated runs; `gpt-6.1-terra`, `medium`, for visual or computer-use work (CLI 0.159.0 or later, not the IDE extension) | `worker-specialised-long-runs`, `worker-specialised-visual` | close to GPT-6 Astra at lower cost (6.1 Sol); fast writing, visual understanding, computer use (6.1 Terra) |

S1 marks none of these as a preview (read 22 November 2026). `gpt-6-luna` must first be enabled by
an administrator on Enterprise and Edu plans (S1). The effort for the two specialised types is the
brain's choice, not the vendor's. Model names change: check the picker or S1 before a run, and
record the model that actually ran.

A custom agent is one TOML file in `~/.codex/agents/` or `.codex/agents/`; `name`, `description`
and `developer_instructions` are required, `model` and `model_reasoning_effort` optional, and the
`name` field, not the file name, identifies the agent (S2). The brain ships one file per row above
in `/.codex/agents/`, with the worker instructions of `/.claude/agents/`. `host_wiring.py apply
--host codex` copies them to `~/.codex/agents/` (SETUP.md step E), so they reach sessions opened in
a project repository too; a file there that is not a brain copy, or that defines an agent of the
same name, is the person's own and is kept. Spawn a worker by its type name ("spawn
worker-no-judgement for packet W01"), or name the model and effort in the request when no type
fits.

## Reading the allowance

- CLI: `/status` in an active session; app: Settings > Usage (S3). There is a 5-hour and a weekly
  window (S3).
- The allowance is one pool shared by Codex and the vendor's other agent products, not one per
  model; each model draws at its own rate (S3). So the ladder's "a model past 75 %" reads here as
  "the pool past 75 %": step down a rung rather than across models.
- No reading the model itself can take is documented. The conductor asks the owner for the figure
  before a run, or records in the run that it could not read it.

## Reading the context size

`/status` shows the remaining context to the person, and `/statusline` can add it to the footer
(search summary of the CLI reference, not verified). No reading the model can take is known. Pass
`--context-unknown "Codex reports no context size to the model"` to `new-run`, `new-packet` and
`close-run`, and drain (SKILL.md, *When to stop dispatching*) at the first compaction or after the
fourth run in the thread, whichever comes first. The default windows (272 000 and 500 000 tokens,
S1) are below the brain's 750 000-token drain threshold, so on Codex the window ends a thread
before the guard does.

## Compaction hooks

Codex offers the same two hooks as Claude Code (S4): every hook gets one JSON object on stdin with
`session_id`, `transcript_path`, `cwd`, `hook_event_name` and `model`; `PreCompact` adds `trigger`
(`manual` or `auto`), and `SessionStart` adds `source`, with matchers `startup`, `resume`, `clear`,
`compact` and `fork`. Hooks are on by default (`[features] hooks`). So `hooks.py` reads the input
unchanged.

`host_wiring.py apply --host codex` (at the `routine` and `edits` levels, SETUP.md step F.3) writes
into `~/.codex/config.toml`, by merging and never replacing: `[features] hooks = true`,
`[agents] max_concurrent_threads_per_session = 4`, and one `[[hooks.<event>]]` table for each
`PreCompact` and `SessionStart` entry of the repository-preflight skill's `hooks/events.json`
(session start and resume, before compaction, after compaction), each naming `hooks.py` by its
absolute path, because Codex runs a hook in the session's folder. A hook the file already runs
under the same matcher, the person's own copy included, is kept and not added twice; a value the
person set is kept and reported.

What reaches the model differs from Claude Code (S4): `SessionStart` adds plain text or a
`hookSpecificOutput.additionalContext` reply to the context, so `session-start` and `post-compact`
are heard; `PreCompact` ignores plain text, so `pre-compact` writes its marker but its reminder is
not shown. Codex's compaction summary is an opaque blob the model cannot steer, and `AGENTS.md`
is re-read every turn, so the pointer survives a compaction on its own; the `## Handover` reload
still needs the hook. Not yet run on the owner's machine.

## Procedure

1. Create the run and packets with `delegation.py` exactly as on other hosts, so the packets
   are portable and a later session on another host could pick them up.
2. Spawn one subagent per packet with the dispatch prompt, naming the packet's model and effort.
   When the running version offers no subagents, run the packets in sequence in the same session,
   each time reading only the packet and its context references.
3. Record at `close-run` whether the packets actually ran in parallel. Never describe a run as
   parallel that ran in sequence.
4. Validate, summarise, route, log and commit as the skill describes.

## Known limits

- Packets run in sequence in one context forfeit the isolation benefit: later packets see earlier
  results. Note this under Assumed or unverified in each result when it could have mattered.
- Codex does not store transcripts per project; if a transcript logger is in use, it must
  filter Codex sessions to this repository per file.

## Sources

Read on 22 November 2026 unless a line says otherwise.

- S1: the vendor's Codex models page, `https://learn.chatgpt.com/docs/models`.
- S2: the vendor's subagents page, `https://learn.chatgpt.com/docs/agent-configuration/subagents.md`.
- S3: `https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan`.
- S4: the vendor's hooks page, `https://learn.chatgpt.com/docs/hooks`.
