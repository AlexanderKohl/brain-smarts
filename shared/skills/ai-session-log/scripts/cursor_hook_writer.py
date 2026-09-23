#!/usr/bin/env python3
"""Cursor host adapter: map Cursor hook stdin JSON → portable session log.

Canonical log + schema live under /temp/ai-session/ and this skill.
`.cursor/hooks.json` only invokes this writer — it is not the portable contract.

Transcript listener (`session_log.py listen`) remains the portable baseline;
hooks fill gaps Cursor transcripts omit (thinking, tool results, shell/MCP I/O).

Fail-open: never block the agent. Empty/invalid stdin → exit 0 with {}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from session_log import (  # noqa: E402
    HOOK_MAX_TEXT,
    find_repo_root,
    log_model_call,
    log_model_response,
    log_thinking,
    log_tool_result,
    normalize_model,
)

# Windows-friendly UTF-8 for any stdout JSON Cursor may read.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _emit(obj: dict[str, Any] | None = None) -> None:
    sys.stdout.write(json.dumps(obj if obj is not None else {}, ensure_ascii=False) + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


def _read_stdin_payload() -> dict[str, Any] | None:
    """Parse Cursor hook JSON from stdin. Empty/invalid → None (no spam)."""
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        data = json.loads(text)
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def resolve_model(payload: dict[str, Any]) -> str | None:
    """Pass through host model if known; else PORTABLE_AI_SESSION_MODEL; never invent."""
    for key in ("model", "model_id", "subagent_model"):
        found = normalize_model(payload.get(key) if isinstance(payload.get(key), str) else None)
        if found:
            return found
    return normalize_model(os.environ.get("PORTABLE_AI_SESSION_MODEL"))


def _jsonish(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _infer_event(payload: dict[str, Any]) -> str:
    name = str(payload.get("hook_event_name") or "").strip()
    if name:
        return name
    # Fixtures / older payloads may omit the name; infer from distinctive fields.
    if "prompt" in payload and "attachments" in payload:
        return "beforeSubmitPrompt"
    if "thinking" in str(payload.get("hook_event_name") or "").lower():
        return "afterAgentThought"
    if "result_json" in payload and "tool_name" in payload:
        return "afterMCPExecution"
    if "output" in payload and "command" in payload and "tool_name" not in payload:
        return "afterShellExecution"
    if "tool_output" in payload:
        return "postToolUse"
    if "failure_type" in payload or (
        "error_message" in payload and "tool_name" in payload and "tool_output" not in payload
    ):
        return "postToolUseFailure"
    if "file_path" in payload and "content" in payload:
        return "beforeReadFile"
    if "file_path" in payload and "edits" in payload:
        return "afterFileEdit"
    if "text" in payload and "duration_ms" in payload:
        return "afterAgentThought"
    if "text" in payload:
        return "afterAgentResponse"
    return ""


def handle_hook(payload: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    """Map one Cursor hook payload into portable log kinds. Returns stdout JSON for Cursor."""
    root = repo_root or find_repo_root()
    event = _infer_event(payload)
    model = resolve_model(payload)
    max_len = HOOK_MAX_TEXT

    if event == "beforeSubmitPrompt":
        prompt = str(payload.get("prompt") or "")
        attachments = payload.get("attachments")
        if attachments:
            call_text = prompt + "\n\n[attachments]\n" + _jsonish(attachments)
        else:
            call_text = prompt
        if call_text.strip():
            log_model_call(
                call_text=call_text,
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        return {"continue": True}

    if event == "afterAgentResponse":
        text = str(payload.get("text") or "")
        if text.strip():
            log_model_response(
                response_text=text,
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        return {}

    if event == "afterAgentThought":
        text = str(payload.get("text") or "")
        if text.strip():
            log_thinking(
                thinking_text=text,
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        return {}

    if event == "postToolUse":
        tool_name = str(payload.get("tool_name") or "tool")
        content = (
            f"[tool_name] {tool_name}\n"
            f"[tool_input]\n{_jsonish(payload.get('tool_input'))}\n"
            f"[tool_output]\n{_jsonish(payload.get('tool_output'))}"
        )
        log_tool_result(
            content=content,
            tool_name=tool_name,
            model=model,
            repo_root=root,
            max_len=max_len,
        )
        return {}

    if event == "postToolUseFailure":
        tool_name = str(payload.get("tool_name") or "tool")
        content = (
            f"[tool_name] {tool_name}\n"
            f"[failure_type] {payload.get('failure_type')}\n"
            f"[error_message]\n{_jsonish(payload.get('error_message'))}\n"
            f"[tool_input]\n{_jsonish(payload.get('tool_input'))}"
        )
        log_tool_result(
            content=content,
            tool_name=tool_name,
            model=model,
            repo_root=root,
            max_len=max_len,
        )
        return {}

    if event == "beforeReadFile":
        path = str(payload.get("file_path") or "")
        body = str(payload.get("content") or "")
        content = f"[file_path] {path}\n[content]\n{body}"
        if path or body:
            log_tool_result(
                content=content,
                tool_name="Read",
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        # Fail-open: never deny reads from the session logger.
        return {"permission": "allow"}

    if event == "afterShellExecution":
        command = str(payload.get("command") or "")
        output = str(payload.get("output") or "")
        content = f"[command]\n{command}\n[output]\n{output}"
        if command or output:
            log_tool_result(
                content=content,
                tool_name="Shell",
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        return {}

    if event == "afterMCPExecution":
        tool_name = str(payload.get("tool_name") or "mcp")
        content = (
            f"[tool_name] {tool_name}\n"
            f"[tool_input]\n{_jsonish(payload.get('tool_input'))}\n"
            f"[result_json]\n{_jsonish(payload.get('result_json'))}"
        )
        log_tool_result(
            content=content,
            tool_name=f"MCP:{tool_name}",
            model=model,
            repo_root=root,
            max_len=max_len,
        )
        return {}

    if event == "afterFileEdit":
        path = str(payload.get("file_path") or "")
        content = f"[file_path] {path}\n[edits]\n{_jsonish(payload.get('edits'))}"
        if path or payload.get("edits"):
            log_tool_result(
                content=content,
                tool_name="Write",
                model=model,
                repo_root=root,
                max_len=max_len,
            )
        return {}

    # Unknown / unsupported event: do not log; fail open.
    return {}


def _fixture_payloads() -> list[dict[str, Any]]:
    return [
        {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "smoke prompt full text",
            "attachments": [],
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "afterAgentThought",
            "text": "smoke thinking block",
            "duration_ms": 12,
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "afterAgentResponse",
            "text": "smoke assistant reply",
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "postToolUse",
            "tool_name": "Read",
            "tool_input": {"path": "CONTRACT.md"},
            "tool_output": "full file body here",
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "beforeReadFile",
            "file_path": "C:/example/brain/CONTRACT.md",
            "content": "# contract body",
            "attachments": [],
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "afterShellExecution",
            "command": "python -V",
            "output": "Python 3.13.7",
            "duration": 10,
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "afterMCPExecution",
            "tool_name": "browser_tabs",
            "tool_input": "{\"action\":\"list\"}",
            "result_json": "{\"tabs\":[]}",
            "duration": 5,
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "postToolUseFailure",
            "tool_name": "Shell",
            "tool_input": {"command": "false"},
            "error_message": "exit 1",
            "failure_type": "error",
            "model": "Cursor Grok 4.5",
        },
        {
            "hook_event_name": "afterFileEdit",
            "file_path": "C:/example/brain/temp/ai-session/README.md",
            "edits": [{"old_string": "a", "new_string": "b"}],
            "model": "Cursor Grok 4.5",
        },
    ]


def cmd_self_test(_: argparse.Namespace) -> int:
    root = find_repo_root()
    kinds: list[str] = []
    for payload in _fixture_payloads():
        handle_hook(payload, repo_root=root)
        kinds.append(str(payload["hook_event_name"]))
    from session_log import log_path

    path = log_path(root)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    recent = [json.loads(line) for line in lines[-len(kinds) :]]
    got_kinds = [row.get("kind") for row in recent]
    expected = [
        "model_call",
        "thinking",
        "model_response",
        "tool_result",
        "tool_result",
        "tool_result",
        "tool_result",
        "tool_result",
        "tool_result",
    ]
    ok = got_kinds == expected
    # Spot-check full payloads survived.
    ok = ok and recent[0].get("call_text") == "smoke prompt full text"
    ok = ok and recent[1].get("thinking_text") == "smoke thinking block"
    ok = ok and recent[2].get("response_text") == "smoke assistant reply"
    ok = ok and "full file body here" in (recent[3].get("content") or "")
    ok = ok and "Python 3.13.7" in (recent[5].get("content") or "")
    print(
        json.dumps(
            {
                "ok": ok,
                "log_path": str(path),
                "events": kinds,
                "kinds": got_kinds,
                "samples": recent,
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cursor hooks → portable /temp/ai-session/ai-call-log.jsonl writer"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Append fixture rows for each major hook event and validate",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return cmd_self_test(args)

    try:
        payload = _read_stdin_payload()
        if payload is None:
            _emit({})
            return 0
        response = handle_hook(payload)
        _emit(response)
        return 0
    except Exception:
        # Fail open; avoid stderr spam that floods the Hooks channel.
        _emit({})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
