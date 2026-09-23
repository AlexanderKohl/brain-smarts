---
id: agents-entry
title: Agent Entry Point
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-06T11:10:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Agent entry point

**Start here:** read [`/CONTRACT.md`](./CONTRACT.md).

Portable discovery steps: [`/BOOTSTRAP.md`](./BOOTSTRAP.md).

Then:

1. Root [`/RULES.md`](./RULES.md), the owner profile `/memory/OWNER.md`, the owner-layer rules `/memory/RULES.md`, and inherited `RULES.md` down to the active node
2. Active node `README.md`, `STATE.md`, and relevant dependencies
3. Skill/index notes in [`/ONBOARDING_AGENT.md`](./ONBOARDING_AGENT.md), and the owner's own notes in `/memory/ONBOARDING_OWNER.md`

Temporary AI call/response log (not governance `LOG.md`):

- Path: `/temp/ai-session/ai-call-log.jsonl` (not `.cursor/temp/`)
- **Primary:** start the transcript listener (Python process) – agents do not append each chat turn
- **Cursor option 2:** `.cursor/hooks.json` → `cursor_hook_writer.py` for fullest send/receive capture (thinking, tool/shell/MCP I/O)
- Kinds: `model_call` / `model_response` / `thinking` / `tool_result` / `python_run`
- `--model` / `PORTABLE_AI_SESSION_MODEL` = user-facing underlying model name when known (e.g. `Cursor Grok 4.5`); never invent; never `cursor-agent`
- Skill: [`/shared/skills/ai-session-log/SKILL.md`](./shared/skills/ai-session-log/SKILL.md)

```bash
python shared/skills/ai-session-log/scripts/session_log.py listen --model "Cursor Grok 4.5"
```

This file is a cross-tool pointer. It does not replace the contract.
