---
id: cursor-hooks-adapter
title: Cursor Hooks Adapter (AI Session Log)
type: note
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-06T12:55:00+10:00
updated: 2026-08-06T12:55:00+10:00
owner: brain-owner
---

# Cursor hooks = host adapter only

[`../hooks.json`](../hooks.json) is a **Cursor-specific** adapter. It does **not** own the log schema.

| Layer | Path | Role |
|---|---|---|
| Cursor adapter | `.cursor/hooks.json` | Invokes the portable writer on hook events |
| Portable writer | `/shared/skills/ai-session-log/scripts/cursor_hook_writer.py` | Parses hook stdin → appends JSONL |
| Canonical log | `/temp/ai-session/ai-call-log.jsonl` | Portable append-only session log |
| Baseline (any host) | `session_log.py listen` | Transcript watcher; keep running |

**Option 2** = fullest Cursor capture (prompts, responses, thinking, tool/read/shell/MCP I/O).

Reload: Cursor watches `hooks.json` and reloads on save; if hooks do not fire, restart Cursor. Check **Cursor Settings → Hooks** or the **Hooks** output channel.

Windows: requires `python` on `PATH` (project hooks run from the repo root). Optional env: `PORTABLE_AI_SESSION_MODEL` for a default model label when the hook payload omits one.
