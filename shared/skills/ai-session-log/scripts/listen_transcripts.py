#!/usr/bin/env python3
"""Watch host transcript JSONL directories and append portable AI session log records.

Auto-detected sources on this machine:
  Cursor:       ~/.cursor/projects/<slug>/agent-transcripts/   (already project-scoped)
  Claude Code:  ~/.claude/projects/<slug>/                     (already project-scoped)
  Codex:        ~/.codex/sessions/**/*.jsonl                   (NOT project-scoped —
                every project's rollouts share one tree; filtered per file by
                matching the session's recorded cwd against the repo root)

This process does the logging — agents do not decide whether turns are recorded.
Other hosts can drop compatible JSONL into a configured transcripts directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# Allow `python listen_transcripts.py` and import from session_log.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from session_log import (  # noqa: E402
    append_record,
    clip,
    ensure_log,
    find_repo_root,
    log_path,
    normalize_model,
    now_iso,
    redact,
    temp_dir,
)

# Listener keeps near-full text (still redact secrets; extreme safety cap).
LISTEN_MAX_TEXT = 2_000_000
LISTEN_MAX_OUTPUT = 500_000

TIMESTAMP_RE = re.compile(
    r"<timestamp>\s*(.*?)\s*</timestamp>",
    re.IGNORECASE | re.DOTALL,
)
USER_QUERY_RE = re.compile(
    r"<user_query>\s*(.*?)\s*</user_query>",
    re.IGNORECASE | re.DOTALL,
)
STATE_NAME = "listener.state.json"


def cursor_project_slug(repo_root: Path) -> str:
    """Map repo path to Cursor's projects folder slug (e.g. c-example-brain)."""
    text = str(repo_root.resolve())
    text = text.replace(":", "")
    text = text.replace("\\", "-").replace("/", "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-").lower()


def default_cursor_transcripts_dir(repo_root: Path) -> Path | None:
    home = Path.home()
    candidate = (
        home / ".cursor" / "projects" / cursor_project_slug(repo_root) / "agent-transcripts"
    )
    if candidate.is_dir():
        return candidate
    # Fallback: scan projects for a folder whose name matches the slug
    projects = home / ".cursor" / "projects"
    if not projects.is_dir():
        return None
    slug = cursor_project_slug(repo_root)
    direct = projects / slug / "agent-transcripts"
    if direct.is_dir():
        return direct
    return None


def claude_code_project_slug(repo_root: Path) -> str:
    """Map repo path to Claude Code's ~/.claude/projects folder slug.

    Unlike cursor_project_slug (which collapses repeated separators), Claude Code
    does not collapse them, so a drive-letter colon followed by a leading
    backslash produces a double dash: C:\\dev\\x -> c--dev-x (verified against
    this repo's actual ~/.claude/projects folder name).
    """
    text = str(repo_root.resolve())
    text = text.replace(":", "-").replace("\\", "-").replace("/", "-")
    return text.lower()


def default_claude_code_transcripts_dir(repo_root: Path) -> Path | None:
    candidate = Path.home() / ".claude" / "projects" / claude_code_project_slug(repo_root)
    if candidate.is_dir():
        return candidate
    return None


def default_codex_sessions_dir() -> Path | None:
    """Codex CLI/desktop rollout store — NOT project-scoped (see iter_transcript_files,
    which filters each file's lines out unless its recorded cwd matches this repo)."""
    candidate = Path.home() / ".codex" / "sessions"
    if candidate.is_dir():
        return candidate
    return None


def resolve_transcripts_dirs(
    repo_root: Path,
    explicit: list[str] | None = None,
) -> list[Path]:
    dirs: list[Path] = []
    if explicit:
        dirs.extend(Path(p).expanduser().resolve() for p in explicit)
    env = os.environ.get("PORTABLE_AI_TRANSCRIPTS_DIR", "").strip()
    if env:
        dirs.append(Path(env).expanduser().resolve())
    auto = default_cursor_transcripts_dir(repo_root)
    if auto is not None:
        dirs.append(auto.resolve())
    auto_claude_code = default_claude_code_transcripts_dir(repo_root)
    if auto_claude_code is not None:
        dirs.append(auto_claude_code.resolve())
    auto_codex = default_codex_sessions_dir()
    if auto_codex is not None:
        dirs.append(auto_codex.resolve())
    # Deduplicate while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def state_path(repo_root: Path) -> Path:
    return temp_dir(repo_root) / STATE_NAME


def load_state(repo_root: Path) -> dict[str, Any]:
    path = state_path(repo_root)
    if not path.is_file():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "files": {}}
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    data.setdefault("version", 1)
    data.setdefault("files", {})
    if not isinstance(data["files"], dict):
        data["files"] = {}
    return data


def save_state(repo_root: Path, state: dict[str, Any]) -> None:
    directory = temp_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = state_path(repo_root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_embedded_timestamp(text: str) -> str | None:
    match = TIMESTAMP_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).strip()
    # Cursor style: "Thursday, Aug 6, 2026, 12:33 PM (UTC+10)"
    for fmt in (
        "%A, %b %d, %Y, %I:%M %p (UTC%z)",
        "%A, %B %d, %Y, %I:%M %p (UTC%z)",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ):
        try:
            normalized = raw
            # Convert (UTC+10) -> +1000 for strptime %z
            if "(UTC" in normalized and normalized.endswith(")"):
                inner = normalized[normalized.rfind("(UTC") + 4 : -1]
                # inner like +10 or -5 or +10:30
                if re.fullmatch(r"[+-]\d{1,2}", inner):
                    sign = inner[0]
                    hours = int(inner[1:])
                    tz = f"{sign}{hours:02d}00"
                elif re.fullmatch(r"[+-]\d{1,2}:\d{2}", inner):
                    sign = inner[0]
                    hh, mm = inner[1:].split(":")
                    tz = f"{sign}{int(hh):02d}{int(mm):02d}"
                else:
                    tz = None
                if tz:
                    normalized = normalized[: normalized.rfind("(UTC")] + tz
                    normalized = normalized.strip()
            dt = datetime.strptime(normalized, fmt)
            return dt.isoformat(timespec="milliseconds")
        except ValueError:
            continue
    return None


def extract_user_call_text(text: str) -> str:
    match = USER_QUERY_RE.search(text or "")
    if match:
        return match.group(1).strip()
    # Strip wrapper tags if present but keep remainder
    cleaned = TIMESTAMP_RE.sub("", text or "").strip()
    return cleaned if cleaned else (text or "")


def content_blocks(obj: dict[str, Any]) -> list[dict[str, Any]]:
    message = obj.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            return [c for c in content if isinstance(c, dict)]
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
    content = obj.get("content")
    if isinstance(content, list):
        return [c for c in content if isinstance(c, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def join_text_blocks(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            text = block.get("text")
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


THINKING_BLOCK_TYPES = frozenset(
    {
        "thinking",
        "reasoning",
        "redacted_thinking",
        "thought",
        "model_thought",
        "agent_thought",
    }
)
TOOL_RESULT_BLOCK_TYPES = frozenset(
    {
        "tool_result",
        "tool_use_result",
        "function_result",
    }
)


def _block_text_payload(block: dict[str, Any]) -> str:
    """Best-effort extract of human/model-visible text from a content block."""
    for key in ("thinking", "reasoning", "text", "content", "output", "result"):
        value = block.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    parts.append(item)
                elif isinstance(item, dict):
                    nested = item.get("text") or item.get("content")
                    if nested:
                        parts.append(str(nested))
            if parts:
                return "\n".join(parts)
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        text = str(value)
        if text.strip():
            return text
    return ""


def format_thinking_blocks(blocks: list[dict[str, Any]]) -> str:
    thoughts: list[str] = []
    for block in blocks:
        btype = str(block.get("type") or "").lower()
        if btype not in THINKING_BLOCK_TYPES and "thinking" not in btype and "reason" not in btype:
            continue
        payload = _block_text_payload(block)
        if not payload.strip():
            # Some hosts (observed: Claude Code) blank the reasoning text before
            # writing the transcript to disk, keeping only an opaque continuity
            # signature. That is a host-side omission, not a parse failure — note
            # it plainly rather than emitting a bare, ambiguous type tag.
            if block.get("signature"):
                thoughts.append(
                    "[thinking occurred; this host does not persist the reasoning "
                    "text to its transcript file, only an opaque continuity signature]"
                )
            else:
                thoughts.append(f"[thinking type={block.get('type')}]")
            continue
        thoughts.append(f"[thinking]\n{payload}")
    return "\n\n".join(thoughts).strip()


def format_tool_uses(blocks: list[dict[str, Any]]) -> str:
    tools: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "tool_use":
            continue
        entry: dict[str, Any] = {
            "name": block.get("name"),
            "input": block.get("input"),
        }
        if block.get("id") is not None:
            entry["id"] = block.get("id")
        tools.append(entry)
    if not tools:
        return ""
    return json.dumps({"tool_use": tools}, ensure_ascii=False, default=str)


def format_tool_results(blocks: list[dict[str, Any]]) -> str:
    """Serialize tool_result / function_result blocks with full content when present."""
    results: list[dict[str, Any]] = []
    for block in blocks:
        btype = str(block.get("type") or "").lower()
        if btype not in TOOL_RESULT_BLOCK_TYPES and "tool_result" not in btype:
            continue
        entry: dict[str, Any] = {"type": block.get("type")}
        for key in (
            "tool_use_id",
            "tool_call_id",
            "id",
            "name",
            "is_error",
            "status",
        ):
            if key in block and block[key] is not None:
                entry[key] = block[key]
        # Prefer full content fields; keep raw structure when not a plain string.
        content = block.get("content")
        if content is None:
            content = block.get("output")
        if content is None:
            content = block.get("result")
        if content is None:
            content = _block_text_payload(block)
        entry["content"] = content
        results.append(entry)
    if not results:
        return ""
    return json.dumps({"tool_result": results}, ensure_ascii=False, default=str)


def format_other_model_blocks(blocks: list[dict[str, Any]]) -> str:
    """Capture uncommon block types that still represent model/host communication."""
    known = (
        {"text", "tool_use"}
        | THINKING_BLOCK_TYPES
        | TOOL_RESULT_BLOCK_TYPES
    )
    others: list[dict[str, Any]] = []
    for block in blocks:
        btype = str(block.get("type") or "")
        lowered = btype.lower()
        if not btype:
            others.append(block)
            continue
        if lowered in known:
            continue
        if "thinking" in lowered or "reason" in lowered or "tool_result" in lowered:
            continue
        # Skip pure UI/metadata noise if ever present without payload.
        if lowered in {"turn_ended", "status", "progress"}:
            continue
        others.append(block)
    if not others:
        return ""
    return json.dumps({"other_blocks": others}, ensure_ascii=False, default=str)


def build_response_text(blocks: list[dict[str, Any]]) -> str:
    thinking = format_thinking_blocks(blocks)
    text = join_text_blocks(blocks)
    tools = format_tool_uses(blocks)
    results = format_tool_results(blocks)
    other = format_other_model_blocks(blocks)
    parts = [p for p in (thinking, text, tools, results, other) if p]
    return "\n\n".join(parts).strip()


def top_level_thinking_text(obj: dict[str, Any]) -> str:
    """Some hosts put reasoning outside message.content."""
    message = obj.get("message")
    candidates: list[Any] = []
    for key in ("thinking", "reasoning", "thought", "model_thought"):
        if key in obj and obj[key]:
            candidates.append(obj[key])
        if isinstance(message, dict) and message.get(key):
            candidates.append(message.get(key))
    parts: list[str] = []
    for value in candidates:
        if isinstance(value, str) and value.strip():
            parts.append(f"[thinking]\n{value}")
        elif isinstance(value, dict):
            nested = _block_text_payload(value) or json.dumps(value, ensure_ascii=False, default=str)
            if nested.strip():
                parts.append(f"[thinking]\n{nested}")
        elif value:
            parts.append(f"[thinking]\n{value}")
    return "\n\n".join(parts).strip()


def extract_model(obj: dict[str, Any]) -> str | None:
    for key in ("model", "modelName", "model_name", "underlyingModel"):
        if key in obj:
            return normalize_model(obj.get(key))
    message = obj.get("message")
    if isinstance(message, dict):
        for key in ("model", "modelName", "model_name"):
            if key in message:
                return normalize_model(message.get(key))
    return None


TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def extract_token_usage(obj: dict[str, Any]) -> dict[str, int] | None:
    """Best-effort per-turn token counts when the host transcript exposes them.

    Observed: Claude Code's assistant lines carry message.usage with these fields.
    Cursor's transcript format never includes usage/token data at all (verified
    against every line across every local transcript file) — omitted there, never
    fabricated. Only a known, meaningful subset of fields is kept; provider-internal
    noise (service tier, cache-creation breakdown, iterations, ...) is dropped.
    """
    message = obj.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    fields = {
        key: usage[key] for key in TOKEN_USAGE_FIELDS if isinstance(usage.get(key), (int, float))
    }
    return fields or None


def records_from_attachment_line(
    obj: dict[str, Any], *, default_model: str | None
) -> list[dict[str, Any]]:
    """Claude Code (and compatible hosts) surface mid-turn queued user messages,
    plus host-injected scaffolding (tool/agent/skill listings, todo reminders,
    permission deltas), as `type: "attachment"` lines rather than ordinary
    user/assistant turns. These were previously silently dropped."""
    attachment = obj.get("attachment")
    if not isinstance(attachment, dict):
        return []
    subtype = attachment.get("type")
    model = extract_model(obj) or normalize_model(default_model)
    ts = obj.get("timestamp") or now_iso()

    if subtype == "queued_command":
        prompt_blocks = attachment.get("prompt")
        text = ""
        if isinstance(prompt_blocks, list):
            text = join_text_blocks([b for b in prompt_blocks if isinstance(b, dict)])
        if not text.strip():
            return []
        entry: dict[str, Any] = {
            "kind": "model_call",
            "ts": ts,
            "call_text": clip(text, LISTEN_MAX_TEXT),
        }
        if model:
            entry["model"] = model
        return [entry]

    # Any other host-injected event: keep full fidelity rather than dropping it,
    # tagged clearly as host context (not user or model output).
    payload = {k: v for k, v in attachment.items() if k != "type"}
    blob = json.dumps(
        {"host_context": {"type": subtype, **payload}}, ensure_ascii=False, default=str
    )
    entry = {
        "kind": "model_response",
        "ts": ts,
        "response_text": clip(f"[host_context type={subtype}]\n{blob}", LISTEN_MAX_TEXT),
    }
    if model:
        entry["model"] = model
    return [entry]


CODEX_TOP_LEVEL_TYPES = frozenset(
    {"session_meta", "turn_context", "response_item", "event_msg", "world_state"}
)
CODEX_MESSAGE_TEXT_TYPES = frozenset({"input_text", "output_text", "text"})


def codex_content_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    content = payload.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in CODEX_MESSAGE_TEXT_TYPES:
                text = block.get("text")
                if text:
                    parts.append(str(text))
    return "\n".join(parts).strip()


def records_from_codex_line(
    obj: dict[str, Any], *, default_model: str | None
) -> list[dict[str, Any]]:
    """Convert one OpenAI Codex rollout-transcript line into portable log records."""
    obj_type = obj.get("type")
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return []
    if obj_type in {"session_meta", "turn_context", "world_state"}:
        return []
    if obj_type not in {"response_item", "event_msg"}:
        return []

    ts = obj.get("timestamp") or now_iso()
    model = normalize_model(default_model)

    if obj_type == "response_item":
        item_type = payload.get("type")
        role = payload.get("role")

        if item_type == "message" and role == "user":
            text = codex_content_text(payload)
            if not text.strip():
                return []
            entry: dict[str, Any] = {
                "kind": "model_call",
                "ts": ts,
                "call_text": clip(text, LISTEN_MAX_TEXT),
            }
            if model:
                entry["model"] = model
            return [entry]

        if item_type == "message" and role == "assistant":
            text = codex_content_text(payload)
            if not text.strip():
                return []
            entry = {
                "kind": "model_response",
                "ts": ts,
                "response_text": clip(text, LISTEN_MAX_TEXT),
            }
            if model:
                entry["model"] = model
            return [entry]

        if item_type in {"function_call", "custom_tool_call"}:
            arguments = payload.get("arguments", payload.get("input"))
            blob = json.dumps(
                {"tool_use": [{"name": payload.get("name"), "input": arguments}]},
                ensure_ascii=False,
                default=str,
            )
            entry = {
                "kind": "model_response",
                "ts": ts,
                "response_text": clip(blob, LISTEN_MAX_TEXT),
            }
            if model:
                entry["model"] = model
            records = [entry]
            command_text = (
                arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False, default=str)
            )
            if re.search(r"\bpython(?:3|\.exe)?\b", command_text, re.IGNORECASE):
                script = "python"
                for token in command_text.replace("`", " ").split():
                    if token.lower().endswith(".py"):
                        script = Path(token.strip("\"'")).name
                        break
                records.append(
                    {
                        "kind": "python_run",
                        "ts_start": ts,
                        "ts_end": ts,
                        "script_name": script,
                        "output": clip(
                            "[from Codex transcript tool call; output arrives in a "
                            f"later line]\n{redact(command_text)}",
                            LISTEN_MAX_OUTPUT,
                        ),
                    }
                )
            return records

        if item_type in {"function_call_output", "custom_tool_call_output"}:
            output = payload.get("output")
            blob = json.dumps(
                {"tool_result": [{"content": output}]}, ensure_ascii=False, default=str
            )
            entry = {
                "kind": "model_response",
                "ts": ts,
                "response_text": clip(blob, LISTEN_MAX_TEXT),
            }
            if model:
                entry["model"] = model
            return [entry]

        # payload.type == "reasoning": content is encrypted at rest, nothing
        # plaintext to capture. The visible summary (when the host emits one)
        # arrives separately as an event_msg agent_reasoning line, handled below.
        return []

    # event_msg
    event_type = payload.get("type")
    if event_type == "agent_reasoning":
        text = payload.get("text") or ""
        if not text.strip():
            return []
        entry = {
            "kind": "model_response",
            "ts": ts,
            "response_text": clip(f"[thinking]\n{text}", LISTEN_MAX_TEXT),
        }
        if model:
            entry["model"] = model
        return [entry]

    if event_type == "token_count":
        info = payload.get("info")
        last = info.get("last_token_usage") if isinstance(info, dict) else None
        fields = (
            {k: v for k, v in last.items() if isinstance(v, (int, float))}
            if isinstance(last, dict)
            else None
        )
        if not fields:
            return []
        entry = {
            "kind": "model_response",
            "ts": ts,
            "response_text": "[token_usage]",
            "token_usage": fields,
        }
        if model:
            entry["model"] = model
        return [entry]

    # user_message / agent_message duplicate the response_item message text
    # already captured above; task_started/task_complete/thread_settings_applied
    # are bookkeeping. Skip to avoid duplication/noise.
    return []


def line_fingerprint(path_key: str, line_no: int, line: str) -> str:
    digest = hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{path_key}:{line_no}:{digest}"


def codex_peek_session_meta(path: Path) -> dict[str, Any] | None:
    """Peek the first meaningful line of a rollout file for its session_meta payload.

    Returns None for anything that isn't Codex-shaped (including unreadable files),
    so callers can treat that as "not a Codex file, include unconditionally."
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for _ in range(5):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") == "session_meta":
                    payload = obj.get("payload")
                    return payload if isinstance(payload, dict) else {}
                # First real line wasn't session_meta: not Codex-shaped.
                return None
    except OSError:
        return None
    return None


def codex_scope_ok(meta: dict[str, Any], repo_root: Path) -> bool:
    """True when a Codex session's recorded cwd is this repo (or a subdirectory).

    Codex rollouts are not stored per-project — every project's sessions on this
    machine share one ~/.codex/sessions tree — so this filter is what keeps other
    repos' conversations out of this repo's log.
    """
    cwd = meta.get("cwd")
    if not cwd:
        return False
    try:
        root_s = str(repo_root.resolve()).rstrip("\\/").lower()
        cwd_s = str(Path(cwd)).rstrip("\\/").lower()
    except OSError:
        return False
    return cwd_s == root_s or cwd_s.startswith(root_s + "\\") or cwd_s.startswith(root_s + "/")


def iter_transcript_files(directories: Iterable[Path], repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.jsonl")):
            meta = codex_peek_session_meta(path)
            if meta is not None and not codex_scope_ok(meta, repo_root):
                continue
            files.append(path)
    return files


def path_key(path: Path, roots: list[Path]) -> str:
    resolved = path.resolve()
    for root in roots:
        try:
            return str(resolved.relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            continue
    return str(resolved).replace("\\", "/")


def _python_runs_from_shell_tool_uses(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Observable python_run when a Shell tool invokes python (command; stdout if absent)."""
    records: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "")
        inp = block.get("input") or {}
        if not isinstance(inp, dict):
            continue
        if name != "Shell":
            continue
        command = str(inp.get("command") or "")
        if not re.search(r"\bpython(?:3|\.exe)?\b", command, re.IGNORECASE):
            continue
        script = "python"
        for token in command.replace("`", " ").split():
            if token.lower().endswith(".py"):
                script = Path(token.strip("\"'")).name
                break
        ts = now_iso()
        records.append(
            {
                "kind": "python_run",
                "ts_start": ts,
                "ts_end": ts,
                "script_name": script,
                "output": clip(
                    f"[from transcript Shell tool; stdout not in transcript]\n{redact(command)}",
                    LISTEN_MAX_OUTPUT,
                ),
            }
        )
    return records


def _python_runs_from_tool_results(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When tool_result content for a python Shell call is present, log it as python_run."""
    records: list[dict[str, Any]] = []
    for block in blocks:
        btype = str(block.get("type") or "").lower()
        if btype not in TOOL_RESULT_BLOCK_TYPES and "tool_result" not in btype:
            continue
        name = str(block.get("name") or "")
        content = block.get("content")
        if content is None:
            content = block.get("output")
        if content is None:
            content = _block_text_payload(block)
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
        # Only promote to python_run when the tool name suggests a python shell, or
        # when content itself looks like a python invocation result labeled as such.
        looks_python = bool(re.search(r"\bpython(?:3|\.exe)?\b", name, re.IGNORECASE)) or (
            name.lower() in {"shell", "bash"} and "python" in text.lower()[:200]
        )
        if not looks_python:
            continue
        ts = now_iso()
        records.append(
            {
                "kind": "python_run",
                "ts_start": ts,
                "ts_end": ts,
                "script_name": Path(name).name if name else "python",
                "output": clip(redact(text), LISTEN_MAX_OUTPUT),
            }
        )
    return records


def attribution_fields(obj: dict[str, Any]) -> dict[str, Any]:
    """Provenance for lines a host wrote on behalf of a subagent.

    Claude Code marks every line of an Agent-tool subagent transcript with
    ``isSidechain: true`` plus ``agentId`` and ``sessionId`` (the parent session).
    Without these fields on the log record, subagent turns are indistinguishable
    from the parent's.
    """
    if not obj.get("isSidechain"):
        return {}
    fields: dict[str, Any] = {"sidechain": True}
    if obj.get("agentId"):
        fields["agent_id"] = str(obj["agentId"])
    if obj.get("sessionId"):
        fields["session_id"] = str(obj["sessionId"])
    return fields


def records_from_transcript_line(
    obj: dict[str, Any],
    *,
    default_model: str | None,
) -> list[dict[str, Any]]:
    """Convert one host transcript object into portable log records, attributed."""
    records = _records_from_transcript_line(obj, default_model=default_model)
    extra = attribution_fields(obj)
    if extra:
        for record in records:
            record.update(extra)
    return records


def _records_from_transcript_line(
    obj: dict[str, Any],
    *,
    default_model: str | None,
) -> list[dict[str, Any]]:
    """Convert one host transcript object into portable log records."""
    obj_type = obj.get("type")
    if obj_type == "attachment":
        return records_from_attachment_line(obj, default_model=default_model)
    if obj_type in CODEX_TOP_LEVEL_TYPES:
        return records_from_codex_line(obj, default_model=default_model)

    role = obj.get("role") or obj.get("type") or obj.get("event")
    if role in {"turn_ended", "system"}:
        return []

    model = extract_model(obj) or normalize_model(default_model)
    blocks = content_blocks(obj)
    records: list[dict[str, Any]] = []

    if role == "user":
        raw_text = join_text_blocks(blocks) or str(obj.get("text") or "")
        # Tool results sometimes appear as user-role messages in other hosts.
        tool_results = format_tool_results(blocks)
        call_text = extract_user_call_text(raw_text)
        if tool_results and not call_text.strip():
            entry = {
                "kind": "model_response",
                "ts": now_iso(),
                "response_text": clip(tool_results, LISTEN_MAX_TEXT),
            }
            if model:
                entry["model"] = model
            records.append(entry)
            records.extend(_python_runs_from_tool_results(blocks))
            return records
        if not call_text.strip() and not tool_results:
            return []
        ts = parse_embedded_timestamp(raw_text) or now_iso()
        combined = call_text
        if tool_results:
            combined = f"{call_text}\n\n{tool_results}" if call_text.strip() else tool_results
        entry = {
            "kind": "model_call",
            "ts": ts,
            "call_text": clip(combined, LISTEN_MAX_TEXT),
        }
        if model:
            entry["model"] = model
        records.append(entry)
        return records

    if role in {"assistant", "model"}:
        response_text = build_response_text(blocks)
        top_thinking = top_level_thinking_text(obj)
        if top_thinking:
            response_text = (
                f"{top_thinking}\n\n{response_text}" if response_text else top_thinking
            )
        if not response_text.strip():
            return []
        entry = {
            "kind": "model_response",
            "ts": now_iso(),
            "response_text": clip(response_text, LISTEN_MAX_TEXT),
        }
        if model:
            entry["model"] = model
        token_usage = extract_token_usage(obj)
        if token_usage:
            entry["token_usage"] = token_usage
        records.append(entry)
        records.extend(_python_runs_from_shell_tool_uses(blocks))
        records.extend(_python_runs_from_tool_results(blocks))
        return records

    # Dedicated tool-result rows (Anthropic-style / some hosts).
    if role in {"tool", "tool_result", "function"}:
        response_text = build_response_text(blocks) or format_tool_results(blocks)
        if not response_text.strip():
            # Fall back to whole object content fields.
            raw = obj.get("content") or obj.get("output") or obj.get("result")
            if raw is not None:
                response_text = json.dumps(
                    {"tool_result": [{"content": raw, "name": obj.get("name")}]},
                    ensure_ascii=False,
                    default=str,
                )
        if not str(response_text).strip():
            return []
        entry = {
            "kind": "model_response",
            "ts": now_iso(),
            "response_text": clip(str(response_text), LISTEN_MAX_TEXT),
        }
        if model:
            entry["model"] = model
        records.append(entry)
        records.extend(_python_runs_from_tool_results(blocks))
        return records

    # Generic host format: already portable kinds
    kind = obj.get("kind")
    if kind in {"model_call", "model_response", "python_run"}:
        payload = dict(obj)
        if "model" in payload:
            payload["model"] = normalize_model(payload.get("model"))
            if payload["model"] is None:
                payload.pop("model", None)
        for key, limit in (
            ("call_text", LISTEN_MAX_TEXT),
            ("response_text", LISTEN_MAX_TEXT),
            ("output", LISTEN_MAX_OUTPUT),
        ):
            if key in payload and payload[key] is not None:
                payload[key] = clip(str(payload[key]), limit)
        if kind in {"model_call", "model_response"}:
            payload.setdefault("ts", now_iso())
        if kind == "python_run":
            payload.setdefault("ts_end", now_iso())
            payload.setdefault("ts_start", payload["ts_end"])
            payload.setdefault("output", "")
            if not payload.get("script_name"):
                return []
        return [payload]

    return []


def is_child_transcript(path: Path, files_state: dict[str, Any], roots: list[Path]) -> bool:
    """True for a transcript that belongs to a session already in progress.

    Claude Code writes Agent-tool subagents to ``<session>/subagents/agent-*.jsonl``
    while the parent session is live. Treating such a file like pre-existing history
    (first sight at end-of-file) loses its opening prompt and any turns written
    before the next poll, and loses a short-lived subagent entirely. A file under a
    ``subagents`` folder, or whose parent folder names a session file that is
    already tracked, is therefore read from offset zero.
    """
    if any(part.lower() == "subagents" for part in path.parts):
        return True
    parent_session = path.parent.name
    if parent_session:
        sibling = path.parent.parent / f"{parent_session}.jsonl"
        if path_key(sibling, roots) in files_state:
            return True
    return False


def process_file(
    path: Path,
    *,
    roots: list[Path],
    state: dict[str, Any],
    repo_root: Path,
    default_model: str | None,
    seen_fps: set[str],
    from_start: bool = False,
) -> int:
    key = path_key(path, roots)
    files_state: dict[str, Any] = state.setdefault("files", {})
    known = key in files_state
    meta = files_state.get(key) or {"offset": 0, "line_no": 0}
    offset = int(meta.get("offset") or 0)
    line_no = int(meta.get("line_no") or 0)
    # Codex rollout files carry their model per-turn (turn_context.payload.model)
    # rather than once per file; carry the last-seen value forward across lines
    # and across polls/restarts (persisted alongside the byte offset below).
    session_model = meta.get("codex_model") if isinstance(meta, dict) else None

    try:
        size = path.stat().st_size
    except OSError:
        return 0

    # First sight of a file: default to EOF so we do not backfill entire history
    # unless --from-start was requested, the file was already tracked, or it is a
    # child transcript of a live session (read from the start, see is_child_transcript).
    if not known and not from_start and not is_child_transcript(path, files_state, roots):
        files_state[key] = {"offset": size, "line_no": 0, "size": size, "skipped_existing": True}
        return 0

    # Truncation / rewrite → restart from beginning
    if offset > size:
        offset = 0
        line_no = 0

    written = 0
    try:
        # Binary mode keeps byte offsets stable on Windows.
        with path.open("rb") as handle:
            handle.seek(offset)
            while True:
                line_start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    # Incomplete final line — wait for the writer to finish it.
                    offset = line_start
                    break
                line_no += 1
                offset = handle.tell()
                stripped = raw.decode("utf-8", errors="replace").strip()
                if not stripped:
                    continue
                fp = line_fingerprint(key, line_no, stripped)
                if fp in seen_fps:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    # Skip corrupt complete lines; do not rewind forever.
                    seen_fps.add(fp)
                    continue
                if not isinstance(obj, dict):
                    seen_fps.add(fp)
                    continue
                if obj.get("type") == "turn_context":
                    turn_model = normalize_model((obj.get("payload") or {}).get("model"))
                    if turn_model:
                        session_model = turn_model
                effective_model = session_model or default_model
                for record in records_from_transcript_line(obj, default_model=effective_model):
                    append_record(record, repo_root)
                    written += 1
                seen_fps.add(fp)
                if len(seen_fps) > 50000:
                    for _ in range(10000):
                        if not seen_fps:
                            break
                        seen_fps.pop()
    except OSError:
        return written

    new_meta: dict[str, Any] = {"offset": offset, "line_no": line_no, "size": size}
    if session_model:
        new_meta["codex_model"] = session_model
    files_state[key] = new_meta
    return written


def poll_once(
    *,
    repo_root: Path,
    directories: list[Path],
    default_model: str | None,
    state: dict[str, Any] | None = None,
    from_start: bool = False,
) -> dict[str, Any]:
    ensure_log(repo_root)
    st = state if state is not None else load_state(repo_root)
    seen_fps: set[str] = set(st.get("recent_fingerprints") or [])
    total = 0
    files = iter_transcript_files(directories, repo_root)
    for path in files:
        total += process_file(
            path,
            roots=directories,
            state=st,
            repo_root=repo_root,
            default_model=default_model,
            seen_fps=seen_fps,
            from_start=from_start,
        )
    # Persist a bounded fingerprint window for idempotency across restarts of the same offset
    st["recent_fingerprints"] = list(seen_fps)[-5000:]
    st["updated_at"] = now_iso()
    st["transcripts_dirs"] = [str(d) for d in directories]
    save_state(repo_root, st)
    return {
        "ok": True,
        "written": total,
        "files_seen": len(files),
        "log_path": str(log_path(repo_root)),
        "state_path": str(state_path(repo_root)),
        "transcripts_dirs": [str(d) for d in directories],
    }


def run_listen_loop(
    *,
    repo_root: Path,
    directories: list[Path],
    default_model: str | None,
    poll_ms: int,
    once: bool,
    from_start: bool = False,
) -> int:
    if not directories:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "No transcripts directories found. Pass --transcripts-dir, set "
                        "PORTABLE_AI_TRANSCRIPTS_DIR, or ensure Cursor agent-transcripts exist."
                    ),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "event": "listener_start",
                "poll_ms": poll_ms,
                "once": once,
                "from_start": from_start,
                "model": normalize_model(default_model),
                "transcripts_dirs": [str(d) for d in directories],
                "log_path": str(log_path(repo_root)),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    while True:
        result = poll_once(
            repo_root=repo_root,
            directories=directories,
            default_model=default_model,
            from_start=from_start,
        )
        if result.get("written"):
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if once:
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return 0
        time.sleep(max(poll_ms, 50) / 1000.0)


def cmd_listen(args: argparse.Namespace) -> int:
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    dirs = resolve_transcripts_dirs(root, list(args.transcripts_dir or []))
    # If caller passed dirs that don't exist yet, still watch them (they may appear)
    for raw in args.transcripts_dir or []:
        p = Path(raw).expanduser().resolve()
        if p not in dirs:
            dirs.append(p)
    return run_listen_loop(
        repo_root=root,
        directories=dirs,
        default_model=args.model,
        poll_ms=int(args.poll_ms),
        once=bool(args.once),
        from_start=bool(getattr(args, "from_start", False)),
    )


def self_test_listener(repo_root: Path | None = None) -> dict[str, Any]:
    """Simulate a small transcript and prove listener writes full call/response lines."""
    root = repo_root or find_repo_root()
    ensure_log(root)
    fixture_root = temp_dir(root) / "_listener_self_test_transcripts"
    if fixture_root.exists():
        for child in fixture_root.rglob("*"):
            if child.is_file():
                child.unlink()
    session_dir = fixture_root / "sim-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    transcript = session_dir / "sim-session.jsonl"
    lines = [
        {
            "role": "user",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "<timestamp>Thursday, Aug 6, 2026, 12:00 PM (UTC+10)</timestamp>\n"
                            "<user_query>\nListener self-test prompt with full text.\n</user_query>"
                        ),
                    }
                ]
            },
        },
        {
            "role": "assistant",
            "message": {
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Listener self-test internal reasoning about CONTRACT.md.",
                    },
                    {"type": "text", "text": "Listener self-test reply step 1."},
                    {
                        "type": "tool_use",
                        "name": "Shell",
                        "input": {
                            "command": "python shared/skills/ai-session-log/scripts/session_log.py path"
                        },
                    },
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"path": "C:/example/brain/CONTRACT.md"},
                    },
                ]
            },
        },
        {
            "role": "tool",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "read-1",
                        "name": "Read",
                        "content": (
                            "---\nid: brain-contract\ntitle: Portable AI Brain Contract\n"
                            "FULL_DOCUMENT_BODY_FOR_LISTENER_TEST\n"
                        ),
                    }
                ]
            },
        },
        {
            "role": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Listener self-test reply step 2 final."},
                ]
            },
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(obj, ensure_ascii=False) for obj in lines) + "\n",
        encoding="utf-8",
    )

    # Isolate state for the test by using a fresh state file key namespace via temp override:
    # process only the fixture dir with a throwaway state by clearing listener state files keys
    # for this fixture path after loading.
    st = load_state(root)
    # Remove prior fixture keys (path keys are relative to the watched dir).
    files = st.get("files") or {}

    def _is_fixture_key(key: str) -> bool:
        norm = str(key).replace("\\", "/")
        return (
            "_listener_self_test_transcripts" in norm
            or norm.endswith("sim-session/sim-session.jsonl")
            or "sim-session/" in norm
        )

    st["files"] = {k: v for k, v in files.items() if not _is_fixture_key(k)}
    fps = [
        fp
        for fp in (st.get("recent_fingerprints") or [])
        if not _is_fixture_key(str(fp))
    ]
    st["recent_fingerprints"] = fps
    save_state(root, st)

    before_lines = log_path(root).read_text(encoding="utf-8").splitlines()
    result = poll_once(
        repo_root=root,
        directories=[fixture_root.resolve()],
        default_model="Cursor Grok 4.5",
        state=load_state(root),
        from_start=True,
    )
    after_lines = log_path(root).read_text(encoding="utf-8").splitlines()
    new_records = [json.loads(line) for line in after_lines[len(before_lines) :]]

    kinds = [r.get("kind") for r in new_records]
    call = next((r for r in new_records if r.get("kind") == "model_call"), None)
    responses = [r for r in new_records if r.get("kind") == "model_response"]
    py_runs = [r for r in new_records if r.get("kind") == "python_run"]

    thinking_ok = any(
        "[thinking]" in (r.get("response_text") or "")
        and "Listener self-test internal reasoning" in (r.get("response_text") or "")
        for r in responses
    )
    tool_result_ok = any(
        "tool_result" in (r.get("response_text") or "")
        and "FULL_DOCUMENT_BODY_FOR_LISTENER_TEST" in (r.get("response_text") or "")
        for r in responses
    )
    step1 = next(
        (
            r
            for r in responses
            if "Listener self-test reply step 1." in (r.get("response_text") or "")
        ),
        None,
    )
    step2 = next(
        (
            r
            for r in responses
            if "Listener self-test reply step 2 final." in (r.get("response_text") or "")
        ),
        None,
    )
    ok = (
        result.get("written", 0) >= 4
        and call is not None
        and "Listener self-test prompt with full text." in (call.get("call_text") or "")
        and call.get("model") == "Cursor Grok 4.5"
        and step1 is not None
        and "tool_use" in (step1.get("response_text") or "")
        and "Read" in (step1.get("response_text") or "")
        and thinking_ok
        and tool_result_ok
        and step2 is not None
        and len(py_runs) >= 1
        and py_runs[0].get("script_name") == "session_log.py"
        and "latency_ms" not in (call or {})
    )

    # Idempotency: second poll must write 0 new records
    again = poll_once(
        repo_root=root,
        directories=[fixture_root.resolve()],
        default_model="Cursor Grok 4.5",
    )
    ok = ok and again.get("written", 0) == 0

    return {
        "ok": ok,
        "written": result.get("written"),
        "kinds": kinds,
        "thinking_mapped": thinking_ok,
        "tool_result_mapped": tool_result_ok,
        "idempotent_second_written": again.get("written"),
        "log_path": str(log_path(root)),
        "fixture": str(transcript),
    }


def self_test_subagent_capture(repo_root: Path | None = None) -> dict[str, Any]:
    """Prove a subagent transcript is captured from its first line and attributed.

    Fixture: a parent session file (pre-existing, must be skipped to EOF under the
    default rule) and a ``subagents/agent-*.jsonl`` written by the same session
    (must be read from offset zero without --from-start, and every record must
    carry ``sidechain``, ``agent_id`` and ``session_id``).
    """
    root = repo_root or find_repo_root()
    ensure_log(root)
    fixture_root = temp_dir(root) / "_listener_self_test_subagents"
    if fixture_root.exists():
        for child in fixture_root.rglob("*"):
            if child.is_file():
                child.unlink()
    session_dir = fixture_root / "sess-1"
    (session_dir / "subagents").mkdir(parents=True, exist_ok=True)
    parent_line = {
        "type": "assistant",
        "sessionId": "sess-1",
        "message": {
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "PARENT_HISTORY_LINE_MUST_BE_SKIPPED"}],
        },
    }
    (session_dir / "sess-1.jsonl").write_text(
        json.dumps(parent_line, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    child_lines = [
        {
            "type": "user",
            "isSidechain": True,
            "agentId": "abc123",
            "sessionId": "sess-1",
            "message": {"content": [{"type": "text", "text": "SUBAGENT_OPENING_PROMPT_LINE"}]},
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": "abc123",
            "sessionId": "sess-1",
            "message": {
                "model": "claude-sonnet-5",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "content": [{"type": "text", "text": "SUBAGENT_REPLY_LINE"}],
            },
        },
    ]
    (session_dir / "subagents" / "agent-abc123.jsonl").write_text(
        "\n".join(json.dumps(obj, ensure_ascii=False) for obj in child_lines) + "\n",
        encoding="utf-8",
    )

    st = load_state(root)
    files = st.get("files") or {}

    def _is_fixture_key(key: str) -> bool:
        return "_listener_self_test_subagents" in str(key).replace("\\", "/") or "sess-1" in str(key)

    st["files"] = {k: v for k, v in files.items() if not _is_fixture_key(k)}
    st["recent_fingerprints"] = [
        fp for fp in (st.get("recent_fingerprints") or []) if not _is_fixture_key(str(fp))
    ]
    save_state(root, st)

    before = log_path(root).read_text(encoding="utf-8").splitlines()
    result = poll_once(
        repo_root=root,
        directories=[fixture_root.resolve()],
        default_model=None,
        state=load_state(root),
    )
    after = log_path(root).read_text(encoding="utf-8").splitlines()
    new_records = [json.loads(line) for line in after[len(before):]]
    texts = " ".join(
        str(r.get("call_text") or "") + " " + str(r.get("response_text") or "") for r in new_records
    )
    parent_skipped = "PARENT_HISTORY_LINE_MUST_BE_SKIPPED" not in texts
    opening_captured = "SUBAGENT_OPENING_PROMPT_LINE" in texts
    reply_captured = "SUBAGENT_REPLY_LINE" in texts
    attributed = bool(new_records) and all(
        r.get("sidechain") is True
        and r.get("agent_id") == "abc123"
        and r.get("session_id") == "sess-1"
        for r in new_records
    )
    again = poll_once(
        repo_root=root,
        directories=[fixture_root.resolve()],
        default_model=None,
    )
    ok = (
        parent_skipped
        and opening_captured
        and reply_captured
        and attributed
        and again.get("written", 0) == 0
    )
    return {
        "ok": ok,
        "written": result.get("written"),
        "parent_skipped_to_eof": parent_skipped,
        "subagent_opening_line_captured": opening_captured,
        "subagent_reply_captured": reply_captured,
        "records_attributed": attributed,
        "idempotent_second_written": again.get("written"),
        "fixture": str(session_dir),
    }


def self_test_new_hosts(repo_root: Path | None = None) -> dict[str, Any]:
    """Verify Claude Code attachment capture and Codex repo-scoped capture.

    Covers the two gaps found in production: (1) Claude Code's mid-turn queued
    messages and host-context deltas arrive as `type: "attachment"` lines that
    the original parser silently dropped; (2) Codex rollouts are not stored
    per-project, so an in-scope and an out-of-scope fixture both run through the
    same poll to prove the cwd filter keeps unrelated repos' sessions out.
    """
    root = repo_root or find_repo_root()
    ensure_log(root)
    fixture_root = temp_dir(root) / "_listener_self_test_new_hosts"
    if fixture_root.exists():
        for child in fixture_root.rglob("*"):
            if child.is_file():
                child.unlink()

    cc_dir = fixture_root / "claude-code-session"
    cc_dir.mkdir(parents=True, exist_ok=True)
    cc_lines = [
        {
            "type": "attachment",
            "timestamp": "2026-08-06T04:40:00.000Z",
            "attachment": {
                "type": "queued_command",
                "prompt": [{"type": "text", "text": "Self-test mid-turn queued message."}],
            },
        },
        {
            "type": "attachment",
            "timestamp": "2026-08-06T04:40:01.000Z",
            "attachment": {
                "type": "todo_reminder",
                "content": ["SELF_TEST_TODO_MARKER"],
                "itemCount": 1,
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": "Claude Code self-test reply with usage."}],
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 22,
                    "cache_creation_input_tokens": 33,
                    "cache_read_input_tokens": 44,
                    "service_tier": "standard",
                },
            },
        },
    ]
    (cc_dir / "claude-code-session.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in cc_lines) + "\n",
        encoding="utf-8",
    )

    codex_in_dir = fixture_root / "codex-in-scope"
    codex_in_dir.mkdir(parents=True, exist_ok=True)
    codex_in_lines = [
        {"type": "session_meta", "payload": {"cwd": str(root), "originator": "codex_vscode"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {
            "type": "response_item",
            "timestamp": "2026-08-06T04:41:00.000Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Codex self-test in-scope prompt."}],
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-08-06T04:41:01.000Z",
            "payload": {"type": "agent_reasoning", "text": "Codex self-test reasoning summary."},
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-06T04:41:02.000Z",
            "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": '{"command": "python shared/skills/ai-session-log/scripts/session_log.py path"}',
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-06T04:41:03.000Z",
            "payload": {"type": "function_call_output", "output": "CODEX_SELF_TEST_TOOL_OUTPUT"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-06T04:41:04.000Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Codex self-test in-scope reply."}],
            },
        },
    ]
    (codex_in_dir / "rollout-in-scope.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in codex_in_lines) + "\n",
        encoding="utf-8",
    )

    codex_out_dir = fixture_root / "codex-out-of-scope"
    codex_out_dir.mkdir(parents=True, exist_ok=True)
    unrelated_cwd = str(root.resolve().parent / "definitely-not-this-repo")
    codex_out_lines = [
        {"type": "session_meta", "payload": {"cwd": unrelated_cwd, "originator": "codex_vscode"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {
            "type": "response_item",
            "timestamp": "2026-08-06T04:42:00.000Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "SHOULD_NEVER_APPEAR_IN_LOG unrelated repo prompt."}
                ],
            },
        },
    ]
    (codex_out_dir / "rollout-out-of-scope.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in codex_out_lines) + "\n",
        encoding="utf-8",
    )

    st = load_state(root)
    files = st.get("files") or {}

    def _is_fixture_key(key: str) -> bool:
        # path_key() resolves relative to the watched directory (fixture_root
        # itself), so the fixture_root name is stripped and never appears here —
        # match on the fixture's subfolder names instead (mirrors the "sim-session/"
        # pattern self_test_listener uses for the same reason).
        norm = str(key).replace("\\", "/")
        return (
            norm.startswith("claude-code-session/")
            or norm.startswith("codex-in-scope/")
            or norm.startswith("codex-out-of-scope/")
        )

    st["files"] = {k: v for k, v in files.items() if not _is_fixture_key(k)}
    st["recent_fingerprints"] = [
        fp for fp in (st.get("recent_fingerprints") or []) if not _is_fixture_key(str(fp))
    ]
    save_state(root, st)

    before_lines = log_path(root).read_text(encoding="utf-8").splitlines()
    result = poll_once(
        repo_root=root,
        directories=[fixture_root.resolve()],
        default_model=None,
        state=load_state(root),
        from_start=True,
    )
    after_lines = log_path(root).read_text(encoding="utf-8").splitlines()
    new_records = [json.loads(line) for line in after_lines[len(before_lines) :]]

    queued_ok = any(
        r.get("kind") == "model_call"
        and "Self-test mid-turn queued message." in (r.get("call_text") or "")
        for r in new_records
    )
    host_context_ok = any(
        r.get("kind") == "model_response"
        and "host_context type=todo_reminder" in (r.get("response_text") or "")
        and "SELF_TEST_TODO_MARKER" in (r.get("response_text") or "")
        for r in new_records
    )
    cc_reply = next(
        (
            r
            for r in new_records
            if r.get("kind") == "model_response"
            and "Claude Code self-test reply with usage." in (r.get("response_text") or "")
        ),
        None,
    )
    token_usage_ok = (
        cc_reply is not None
        and cc_reply.get("token_usage")
        == {
            "input_tokens": 11,
            "output_tokens": 22,
            "cache_creation_input_tokens": 33,
            "cache_read_input_tokens": 44,
        }
    )
    codex_call = next(
        (
            r
            for r in new_records
            if r.get("kind") == "model_call"
            and "Codex self-test in-scope prompt." in (r.get("call_text") or "")
        ),
        None,
    )
    codex_reasoning_ok = any(
        r.get("kind") == "model_response"
        and "[thinking]" in (r.get("response_text") or "")
        and "Codex self-test reasoning summary." in (r.get("response_text") or "")
        for r in new_records
    )
    codex_tool_ok = any(
        "shell_command" in (r.get("response_text") or "") for r in new_records
    ) and any("CODEX_SELF_TEST_TOOL_OUTPUT" in (r.get("response_text") or "") for r in new_records)
    codex_reply_ok = any(
        r.get("kind") == "model_response"
        and "Codex self-test in-scope reply." in (r.get("response_text") or "")
        for r in new_records
    )
    out_of_scope_leaked = any(
        "SHOULD_NEVER_APPEAR_IN_LOG" in json.dumps(r, ensure_ascii=False) for r in new_records
    )
    model_attributed_ok = codex_call is not None and codex_call.get("model") == "gpt-5.6-sol"

    ok = (
        queued_ok
        and host_context_ok
        and token_usage_ok
        and codex_call is not None
        and codex_reasoning_ok
        and codex_tool_ok
        and codex_reply_ok
        and model_attributed_ok
        and not out_of_scope_leaked
    )

    again = poll_once(repo_root=root, directories=[fixture_root.resolve()], default_model=None)
    ok = ok and again.get("written", 0) == 0

    return {
        "ok": ok,
        "written": result.get("written"),
        "queued_command_captured": queued_ok,
        "host_context_captured": host_context_ok,
        "claude_code_token_usage_captured": token_usage_ok,
        "codex_user_call_captured": codex_call is not None,
        "codex_reasoning_captured": codex_reasoning_ok,
        "codex_tool_call_captured": codex_tool_ok,
        "codex_reply_captured": codex_reply_ok,
        "codex_model_attributed": model_attributed_ok,
        "codex_out_of_scope_excluded": not out_of_scope_leaked,
        "idempotent_second_written": again.get("written"),
    }


def build_listen_parser(sub: Any = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Listen to host transcript JSONL folders and append "
            "/temp/ai-session/ai-call-log.jsonl automatically."
        )
    )
    parser.add_argument("--root", help="Repository root (optional; auto-discovered)")
    parser.add_argument(
        "--transcripts-dir",
        action="append",
        default=[],
        help=(
            "Transcript JSONL directory to watch (repeatable). "
            "Default: Cursor agent-transcripts for this repo, or PORTABLE_AI_TRANSCRIPTS_DIR."
        ),
    )
    parser.add_argument(
        "--model",
        help=(
            'Optional default user-facing model label (e.g. "Cursor Grok 4.5") '
            "when transcripts omit model; never cursor-agent"
        ),
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=750,
        help="Polling interval in milliseconds (default: 750)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process current transcript tails once and exit",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help=(
            "On first sight of a transcript file, ingest from byte 0 "
            "(default: start at EOF and only capture new lines)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_listen_parser()
    args = parser.parse_args(argv)
    return cmd_listen(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
