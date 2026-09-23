---
id: skill-ai-session-log
title: AI Session Log
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/ai-session-log/scripts/session_log.py
  - /shared/skills/ai-session-log/scripts/listen_transcripts.py
  - /shared/skills/ai-session-log/scripts/cursor_hook_writer.py
  - /shared/skills/ai-session-log/scripts/view_log.py
created: 2026-08-06T11:10:00+10:00
updated: 2026-09-23T18:00:00+10:00
owner: brain-owner
---

# AI Session Log

## Purpose

Provide a **portable**, append-only temporary log of AI send/receive traffic and observable Python script runs.

This is **not** node governance history (`LOG.md`) and **not** immutable evidence (`/memory/raw/`).

**Capture is automatic** (not agent-decided):

1. **Portable baseline:** `session_log.py listen` watches host transcript JSONL.
2. **Cursor option 2 (fullest):** project hooks → `cursor_hook_writer.py` append the same log with payloads transcripts omit.

## Allowed operations

- Watch host transcript folders (Cursor, Claude Code, Codex, or any `--transcripts-dir`) and append converted records to `/temp/ai-session/ai-call-log.jsonl`.
- Append manual `model_call`, `model_response`, `thinking`, `tool_result` and `python_run` records, and wrap a Python run so its output is logged.
- Serve the local read-only HTML viewer on `127.0.0.1:8768`.
- Redact and clip payloads before append. Never write outside `/temp/ai-session/`, never edit a node `LOG.md`, never read or write the vault.

## Required inputs

- Repository root discovered from `CONTRACT.md`, or `--root`.
- Optional `--model` / `PORTABLE_AI_SESSION_MODEL`: the user-facing model name when known; never invented.
- Optional `--transcripts-dir` / `PORTABLE_AI_TRANSCRIPTS_DIR` for hosts that are not auto-detected; `--once`, `--from-start` and `--poll-ms` for the listener.
- For Cursor option 2: `.cursor/hooks.json` pointing at `cursor_hook_writer.py`.

## Canonical path

```text
/temp/ai-session/ai-call-log.jsonl
```

Listener state (gitignored): `/temp/ai-session/listener.state.json`

Path choice:

- Under the repository root discovered via `CONTRACT.md` (portable across tools/models)
- Outside `.cursor/` so logging does not depend on Cursor as the contract
- Outside `/memory/raw/` because the file is disposable instrumentation, not source evidence
- Outside node `LOG.md` files, which remain the durable activity record

## Payload hygiene

Before append, `clip()` runs `compact_heavy_payloads()` then secret redaction and length caps:

- Oversized `data:image/...;base64,...` URLs, JSON image `data` fields (`/9j/…`, `iVBORw0…`), and other long base64 runs are replaced with `[… omitted sha256=… bytes=…]`
- This keeps `/temp/ai-session/ai-call-log.jsonl` reviewable (image payloads can otherwise dominate response characters)

Efficiency baseline / remeasure (brain-development, not this skill’s runtime path): an owner may keep a baseline measurement under `/memory/projects/brain-development/data/` and a measuring script under `/memory/projects/brain-development/scripts/`, and compare later logs against it.

## Schema

### `model_call`

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `"model_call"` |
| `ts` | yes | Call timestamp (ISO-8601) |
| `call_text` | yes | Full prompt text (or host-provided text) |
| `model` | if known | User-facing underlying model name |
| `sidechain`, `agent_id`, `session_id` | subagent lines only | Present when the host marked the line as written by a subagent (Claude Code `isSidechain`); `session_id` is the parent session |

### `model_response`

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `"model_response"` |
| `ts` | yes | Response timestamp (ISO-8601) |
| `response_text` | yes | Full reply text |
| `model` | if known | Same model label as the call when known |
| `token_usage` | if known | Per-turn token counts, only when the host transcript exposes them (see below) |
| `sidechain`, `agent_id`, `session_id` | subagent lines only | As for `model_call`; lets a delegation run's worker turns be grouped and costed |

### `thinking`

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `"thinking"` |
| `ts` | yes | Timestamp (ISO-8601) |
| `thinking_text` | yes | Full aggregated thinking / reasoning text |
| `model` | if known | When known |

### `tool_result`

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `"tool_result"` |
| `ts` | yes | Timestamp (ISO-8601) |
| `content` | yes | Full tool / read / shell / MCP payload text |
| `tool_name` | if known | e.g. `Read`, `Shell`, `MCP:browser_tabs` |
| `model` | if known | When known |

### `python_run`

| Field | Required | Notes |
|---|---|---|
| `kind` | yes | `"python_run"` |
| `ts_start` | yes | When the script was invoked |
| `ts_end` | yes | When output was available |
| `script_name` | yes | Script basename or label |
| `output` | yes | Captured stdout/stderr (may note when stdout is unavailable) |

Do **not** log latency or other provider-internal telemetry. `token_usage` is the one
exception (kept deliberately for cost analysis): include it on `model_response` only when the host
transcript actually exposes per-turn counts – never fabricate it for a host that
doesn't. Currently populated for Claude Code (`message.usage`: `input_tokens`,
`output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) and Codex
(`event_msg` type `token_count` → `info.last_token_usage`). Cursor's transcript format
has no usage/token data anywhere (verified against every local transcript file), so it
is never present there.

## Model field guidance

- Prefer real user-facing names: `Cursor Grok 4.5`, `Composer 2.5 Fast`, `GPT-5.6 Sol`
- Never invent a model name
- Never use vague host labels such as `cursor-agent`
- If unknown, omit `model`
- Cursor hooks may pass through a host-provided model slug when present
- Fallback default: env `PORTABLE_AI_SESSION_MODEL`, or `--model` on the listener

## Primary: start the listener

The listener is a durable Python process. Leave it running while using the brain.

```bash
# Foreground (recommended while working)
python shared/skills/ai-session-log/scripts/session_log.py listen --model "Cursor Grok 4.5"

# Same entrypoint
python shared/skills/ai-session-log/scripts/listen_transcripts.py --model "Cursor Grok 4.5"

# One-shot catch-up (no loop)
python shared/skills/ai-session-log/scripts/session_log.py listen --once --model "Cursor Grok 4.5"

# Windows background example
Start-Process python -ArgumentList 'shared/skills/ai-session-log/scripts/session_log.py','listen','--model','Cursor Grok 4.5' -WorkingDirectory '<brain root>' -WindowStyle Minimized
```

Defaults – auto-detected with **no flags required**, on any host present on the machine:

- Cursor: `~/.cursor/projects/<slug>/agent-transcripts/` (already scoped to this repo)
- Claude Code: `~/.claude/projects/<slug>/` (already scoped to this repo; Claude Code
  uses a different slug algorithm than Cursor for the same path – both are computed,
  not guessed)
- Codex (CLI/desktop/VS Code): `~/.codex/sessions/**/*.jsonl` – **not** project-scoped
  by the host (every project's rollouts share one tree on disk), so the listener
  filters per file by matching each session's recorded `cwd` against this repo root.
  A Codex session only appears in this log when it was run directly in (or under) this
  repo directory – e.g. `codex` from a terminal `cd`'d into the repo, or the VS Code
  extension with this repo open. Sessions run from an unrelated scratch/worktree
  directory (observed: the desktop/chat-panel variant does this by default) are not
  captured – there is no reliable way to associate them with this repo without
  guessing, so they are excluded rather than mis-attributed.
- Or `PORTABLE_AI_TRANSCRIPTS_DIR` / `--transcripts-dir` (repeatable) for any other
  host that drops JSONL transcripts into a folder
- Tracks byte offsets in `/temp/ai-session/listener.state.json` so restarts do not re-append forever
- New transcript files default to **EOF** (live capture only); use `--from-start` to backfill existing history. Exception: a child transcript of a live session (a file under a `subagents/` folder, or whose parent folder names a session file already tracked) is read from its first line, because it is new work rather than history
- Codex additionally carries its per-turn model (`turn_context.payload.model`, e.g.
  `gpt-5.6-sol`) forward across lines and across restarts, persisted per file in
  `listener.state.json`

### Claude Code coverage note

Claude Code's transcript format is not limited to `user`/`assistant` turns. It also
emits `type: "attachment"` lines for mid-turn queued messages (`attachment.type ==
"queued_command"`, captured as `model_call`) and host-injected scaffolding – todo
reminders, tool/agent/skill listings, permission deltas – captured as tagged
`model_response` entries (`[host_context type=...]`) rather than dropped. Claude
Code also blanks the plaintext of extended-thinking blocks before writing them to
disk (only an opaque continuity `signature` remains); this is a host limitation, not
a listener gap, and is marked plainly in the log rather than silently omitted.

## Cursor option 2 – broader hooks (fullest Cursor capture)

Design choice: capture **every bit of communication** Cursor exposes.

| Layer | Role |
|---|---|
| `.cursor/hooks.json` | Thin **Cursor host adapter** only |
| `cursor_hook_writer.py` | Parses hook stdin → appends portable JSONL |
| `/temp/ai-session/ai-call-log.jsonl` | Canonical log (unchanged path) |
| `session_log.py listen` | Still required as portable baseline / other hosts |

### Enable / reload

1. Ensure project file `.cursor/hooks.json` exists (checked into the repo).
2. Cursor **reloads hooks on save** of `hooks.json`.
3. If hooks still do not fire: **restart Cursor**, then check **Settings → Hooks** or the **Hooks** output channel.
4. Optional: set user/env `PORTABLE_AI_SESSION_MODEL=Cursor Grok 4.5` when payloads omit model.
5. Keep the transcript listener running; hooks fill gaps transcripts omit (some prompt/response overlap is expected).

Windows: `python` must be on `PATH` (hooks run from the project root). Alternate launcher: `.cursor/hooks/ai-session-log.cmd`.

Smoke-test the writer (no Cursor required):

```bash
python shared/skills/ai-session-log/scripts/cursor_hook_writer.py --self-test
```

### Hook → log mapping (option 2)

| Cursor hook | Log kind | Payload |
|---|---|---|
| `beforeSubmitPrompt` | `model_call` | Full `prompt` (+ attachment paths) |
| `afterAgentResponse` | `model_response` | Full assistant `text` |
| `afterAgentThought` | `thinking` | Full aggregated thinking `text` |
| `postToolUse` | `tool_result` | `tool_name` + input + **full** `tool_output` |
| `postToolUseFailure` | `tool_result` | Failure type + error + input |
| `beforeReadFile` | `tool_result` | `file_path` + **full** `content` (always allows) |
| `afterShellExecution` | `tool_result` | Full `command` + `output` |
| `afterMCPExecution` | `tool_result` | MCP tool name + input + `result_json` |
| `afterFileEdit` | `tool_result` | `file_path` + edits |

### Cursor limitations (still apply)

Even with option 2, Cursor may:

- Redact secrets or sensitive attachment bodies before hooks see them
- Truncate or omit very large tool outputs
- Omit thinking when the model/UI does not expose a thinking block
- Omit or slugify the underlying model name
- Skip hooks during some cloud read-only exploratory turns

Hooks are Cursor-specific. Other hosts keep using the transcript listener (or their own adapters writing the same JSONL kinds).

## What the transcript listener captures

| Transcript material | Log kind | Content |
|---|---|---|
| `user` text / `<user_query>` | `model_call` | Full user query text |
| `assistant` text | `model_response` | Visible reply text |
| `thinking` / `reasoning` blocks | `model_response` | Prefixed with `[thinking]` when present in JSONL |
| `tool_use` blocks | `model_response` | JSON `tool_use` (name + input) |
| `tool_result` / role `tool` | `model_response` | JSON `tool_result` with full content when present |
| Shell `python …` tool_use | `python_run` | Script name + command (stdout usually absent in Cursor transcripts) |

### Observed Cursor transcript reality

Inspected local `agent-transcripts`: roles are only `user` / `assistant` / `turn_ended`; content blocks are only `text` and `tool_use`. Therefore transcripts alone miss thinking, tool **results**, and shell stdout – **option 2 hooks** supply those.

### Observed Claude Code subagent transcripts

Claude Code writes each Agent-tool subagent to `~/.claude/projects/<slug>/<session-uuid>/subagents/agent-<hex>.jsonl` with a sibling `.meta.json` (`agentType`, `description`, `spawnDepth`, `toolUseId`). Every line carries `isSidechain: true`, `agentId` and `sessionId`; the parent session file holds only the Agent tool use and the returned report. The listener finds these files through its recursive walk. It reads a subagent file from its first line instead of from end-of-file, and every record from a sidechain line carries `sidechain`, `agent_id` and `session_id`, so a delegation run's worker turns can be grouped and costed. `tool-results/*.txt` spill files and `.meta.json` are ignored. `session_log.py self-test` proves both behaviours with a fixture under `/temp/ai-session/_listener_self_test_subagents/`.

## Manual fallbacks (optional)

```bash
python shared/skills/ai-session-log/scripts/session_log.py append \
  --kind model_call \
  --model "Cursor Grok 4.5" \
  --call-text "..."

python shared/skills/ai-session-log/scripts/session_log.py append \
  --kind model_response \
  --model "Cursor Grok 4.5" \
  --response-text "..."

python shared/skills/ai-session-log/scripts/session_log.py run -- \
  python path/to/script.py

python shared/skills/ai-session-log/scripts/session_log.py self-test
python shared/skills/ai-session-log/scripts/cursor_hook_writer.py --self-test
python shared/skills/ai-session-log/scripts/session_log.py path
python shared/skills/ai-session-log/scripts/session_log.py rotate
```

### Python helpers (importable)

```python
from session_log import (
    log_model_call,
    log_model_response,
    log_thinking,
    log_tool_result,
    log_python_run,
    run_and_log,
)

log_model_call(call_text="...", model="Cursor Grok 4.5")
log_model_response(response_text="...", model="Cursor Grok 4.5")
log_thinking(thinking_text="...", model="Cursor Grok 4.5")
log_tool_result(content="...", tool_name="Read", model="Cursor Grok 4.5")
run_and_log(["python", "script.py"])
```

## Local HTML viewer

Browse `/temp/ai-session/ai-call-log.jsonl` as a filterable timeline (kinds, search,
limit, auto-refresh). Stdlib-only local server on `127.0.0.1:8768`.

```bash
cd <brain root>   # the folder holding CONTRACT.md; see brain_root in /memory/OWNER.md
python shared/skills/ai-session-log/scripts/session_log.py view --open

# Same entrypoint
python shared/skills/ai-session-log/scripts/view_log.py --open
```

Open `http://127.0.0.1:8768/` in any browser, or in Cursor/VS Code via
**Simple Browser: Show** (Command Palette) so the UI stays inside the editor.

API: `GET /api/log?limit=100&kinds=model_call,model_response` · `GET /api/health`

## Permissions

- Write only under `/temp/ai-session/`
- Read host transcript directories configured for listening
- Local HTTP bind for `view` (default `127.0.0.1:8768` only; no network clients required)
- No outbound network access required
- Standard library only

## Failure behaviour

- CLI exits non-zero on hard errors and prints JSON `{"ok": false, ...}` to stderr
- Hook writer always fail-opens (exit 0, `{}`) on empty/invalid stdin or internal errors
- Missing model name is not an error: omit the field
- Incomplete final JSONL lines are retried on the next poll

## Repository updates

None required for ordinary listening. The JSONL and `listener.state.json` are gitignored. Use `rotate` to cut over after a schema change.
