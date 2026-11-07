---
id: delegate-work-host-codex
title: Dispatching packets on Codex
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-10-01T22:59:04+10:00
owner: brain-owner
---

# Dispatching packets on Codex

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Not yet verified on the owner's machine. Assume the Codex CLI session has no parallel subagent
facility unless the running version demonstrably offers one.

## Reading the context size

No reading the model can take is known on this host (`/status` in the terminal shows the
figure to the owner, not to the model). Pass `--context-unknown "Codex reports no context size
to the model"` to `new-run`, `new-packet` and `close-run`, and drain (SKILL.md, *When to stop
dispatching*) at the first compaction or after the fourth run in the thread, whichever comes
first.

## Compaction hooks

Codex offers the same two hooks as Claude Code (official configuration reference, read
1 October 2026): `PreCompact` receives `session_id`, `cwd` and `trigger` on stdin, and
`SessionStart` with matcher `compact` receives `session_id`, `cwd` and `source`, and its stdout
is added to the model's context. So the brain's `hooks.py pre-compact` and `hooks.py post-compact`
run unchanged. Enable hooks and add to `~/.codex/config.toml`, with the command run from the
brain root:

```toml
[features]
hooks = true

[[hooks.PreCompact]]
matcher = "manual|auto"
[[hooks.PreCompact.hooks]]
type = "command"
command = "python shared/skills/repository-preflight/scripts/hooks.py pre-compact"

[[hooks.SessionStart]]
matcher = "compact"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python shared/skills/repository-preflight/scripts/hooks.py post-compact"
```

Not yet verified on the owner's machine: the Codex CLI is not installed there (only the Codex
app's folder exists). Two differences to know: Codex's compaction summary is an opaque blob the
model cannot steer, and `AGENTS.md` is re-read every turn, so the pointer file survives a
compaction on its own; the `## Handover` reload still needs the hook.

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
- Codex does not store transcripts per project; if a transcript logger is in use, it must
  filter Codex sessions to this repository per file. Sequential packet work is ordinary session
  traffic.
