#!/usr/bin/env python3
"""Portable append-only temporary AI session log helper.

Canonical path (relative to repository root discovered via CONTRACT.md):
  /temp/ai-session/ai-call-log.jsonl

Ephemeral instrumentation — not node governance LOG.md and not /raw/.

Primary capture path: run `session_log.py listen` (transcript watcher). Agents
do not need to append chat turns. Manual `append` / `run` remain as fallbacks.

Schema (default kinds):
  model_call     {kind, ts, call_text, model?}
  model_response {kind, ts, response_text, model?, token_usage?}
  thinking       {kind, ts, thinking_text, model?}
  tool_result    {kind, ts, content, tool_name?, model?}
  python_run     {kind, ts_start, ts_end, script_name, output}

token_usage is optional and included only when a host transcript actually exposes
per-turn counts (observed: Claude Code's message.usage, Codex's token_count event).
Never fabricated for a host that omits it (e.g. Cursor's transcript format has no
usage data at all). Latency and other provider-internal telemetry remain excluded.

Pass --model as the user-facing underlying model name when known
(e.g. "Cursor Grok 4.5", "Composer 2.5 Fast", "GPT-5.6 Sol").
Never invent a model name. Never use vague labels like "cursor-agent".
Omit model when unknown.

Cursor option-2 hooks write via cursor_hook_writer.py (thinking / tool_result
plus full prompts/responses). Transcript listener remains the portable baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Large enough for "every bit" capture; still truncate pathological payloads.
MAX_TEXT = 500_000
MAX_OUTPUT = 500_000
HOOK_MAX_TEXT = 2_000_000
# Base64 / data-URL blobs larger than this are replaced with a hash stub.
HEAVY_BLOB_MIN = 2_000

SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(passphrase|password|secret|token|api[_-]?key)\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\bPORTABLE_VAULT_PASSPHRASE\s*=\s*\S+"),
    re.compile(r"(?i)\b(client_secret|refresh_token|access_token)\s*[:=]\s*\S+"),
]

# data:image/...;base64,AAAA... or JSON "data": "/9j/..." / "iVBORw0..."
_DATA_URL_B64 = re.compile(
    r"(data:(?:image|application)/[a-z0-9.+-]+;base64,)([A-Za-z0-9+/=\s]{2000,})",
    re.IGNORECASE,
)
_JSON_B64_FIELD = re.compile(
    r'(("(?:data|image_data|content|body)"\s*:\s*")\s*)(/9j/[A-Za-z0-9+/=\s]{500,}|iVBORw0[A-Za-z0-9+/=\s]{500,})',
    re.IGNORECASE,
)
_RAW_B64_RUN = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{2000,}={0,2})")

VALID_KINDS = frozenset(
    {"model_call", "model_response", "thinking", "tool_result", "python_run"}
)


def find_repo_root(start: Path | None = None) -> Path:
    """Locate repository root by walking upward until CONTRACT.md is found.

    Prefer an explicit start, then this script's path (so hooks/CLIs work even
    when process cwd is not the brain root), then cwd.
    """
    starts: list[Path] = []
    if start is not None:
        starts.append(start.resolve())
    starts.append(Path(__file__).resolve())
    starts.append(Path.cwd().resolve())

    seen: set[Path] = set()
    for origin in starts:
        current = origin
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "CONTRACT.md").is_file():
                return candidate
    raise FileNotFoundError(
        "CONTRACT.md not found above starting path; cannot resolve portable brain root"
    )


def temp_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return root / "temp" / "ai-session"


def log_path(repo_root: Path | None = None) -> Path:
    return temp_dir(repo_root) / "ai-call-log.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def redact(text: str) -> str:
    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


def _blob_stub(label: str, blob: str) -> str:
    raw = re.sub(r"\s+", "", blob)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"[{label} omitted sha256={digest} bytes={len(raw)}]"


def compact_heavy_payloads(text: str) -> str:
    """Replace oversized base64 / data-URL blobs with hash stubs before clip().

    Keeps the session log reviewable: image tool results previously dominated
    character volume (~36% of response chars in the 2026-08-12 baseline).
    """

    def _data_url(match: re.Match[str]) -> str:
        return match.group(1) + _blob_stub("image_base64", match.group(2))

    def _json_field(match: re.Match[str]) -> str:
        return match.group(1) + _blob_stub("image_base64", match.group(3))

    def _raw_run(match: re.Match[str]) -> str:
        blob = match.group(1)
        if len(blob) < HEAVY_BLOB_MIN:
            return blob
        return _blob_stub("base64", blob)

    out = _DATA_URL_B64.sub(_data_url, text)
    out = _JSON_B64_FIELD.sub(_json_field, out)
    out = _RAW_B64_RUN.sub(_raw_run, out)
    return out


def clip(text: str | None, limit: int = MAX_TEXT) -> str | None:
    if text is None:
        return None
    cleaned = compact_heavy_payloads(redact(str(text)))
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 20] + "\n...[truncated]..."


def normalize_model(model: str | None) -> str | None:
    """Return a cleaned model label, or None when unknown / forbidden placeholders."""
    if model is None:
        return None
    cleaned = str(model).strip()
    if not cleaned:
        return None
    if cleaned.lower() in {"cursor-agent", "cursor agent", "unknown", "null", "none"}:
        return None
    return cleaned


def ensure_log(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    directory = temp_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = log_path(root)
    if not path.exists():
        header = {
            "event": "log_initialized",
            "ts": now_iso(),
            "note": (
                "Temporary append-only AI session log (not governance LOG.md, not /raw/). "
                "Schema: model_call / model_response / thinking / tool_result / python_run. "
                "Filled by session_log.py listen (transcript watcher) and, on Cursor, "
                "option-2 hooks via cursor_hook_writer.py; manual append/run are fallbacks. "
                "Safe to delete."
            ),
            "schema": {
                "model_call": ["kind", "ts", "call_text", "model?"],
                "model_response": ["kind", "ts", "response_text", "model?", "token_usage?"],
                "thinking": ["kind", "ts", "thinking_text", "model?"],
                "tool_result": ["kind", "ts", "content", "tool_name?", "model?"],
                "python_run": ["kind", "ts_start", "ts_end", "script_name", "output"],
            },
        }
        path.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def rotate_log(
    *,
    note: str | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Replace the JSONL with a cutover marker (discards prior lines)."""
    root = repo_root or find_repo_root()
    directory = temp_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = log_path(root)
    marker = {
        "event": "schema_cutover",
        "ts": now_iso(),
        "note": note
        or (
            "Rotated schema: model_call / model_response / thinking / "
            "tool_result / python_run. Prior lines discarded; ephemeral log."
        ),
        "schema": {
            "model_call": ["kind", "ts", "call_text", "model?"],
            "model_response": ["kind", "ts", "response_text", "model?", "token_usage?"],
            "thinking": ["kind", "ts", "thinking_text", "model?"],
            "tool_result": ["kind", "ts", "content", "tool_name?", "model?"],
            "python_run": ["kind", "ts_start", "ts_end", "script_name", "output"],
        },
    }
    path.write_text(json.dumps(marker, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def append_record(entry: dict[str, Any], repo_root: Path | None = None) -> Path:
    """Append one JSON object to the portable session log."""
    root = repo_root or find_repo_root()
    path = ensure_log(root)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return path


def _drop_none(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if v is not None}


def script_name_from_command(command: list[str] | str) -> str:
    """Best-effort script/command label for python_run.script_name."""
    if isinstance(command, str):
        parts = command.strip().split()
    else:
        parts = [str(p) for p in command]
    if not parts:
        return "unknown"
    for part in parts:
        lowered = part.lower().replace("\\", "/")
        if lowered.endswith(".py"):
            return Path(part).name
    # Skip interpreter tokens
    for part in parts:
        base = Path(part).name.lower()
        if base.startswith("python"):
            continue
        if part in {"-c", "-m", "--"}:
            continue
        return Path(part).name if ("/" in part or "\\" in part) else part
    return Path(parts[0]).name


# --- Reusable helpers for agents / other Python tools ---


def log_model_call(
    *,
    call_text: str,
    model: str | None = None,
    ts: str | None = None,
    repo_root: Path | None = None,
    max_len: int = MAX_TEXT,
) -> Path:
    """Append a model_call event (call text + timestamp; model if known)."""
    root = repo_root or find_repo_root()
    entry = _drop_none(
        {
            "kind": "model_call",
            "ts": ts or now_iso(),
            "model": normalize_model(model),
            "call_text": clip(call_text, max_len),
        }
    )
    return append_record(entry, root)


def log_model_response(
    *,
    response_text: str,
    model: str | None = None,
    token_usage: dict[str, int] | None = None,
    ts: str | None = None,
    repo_root: Path | None = None,
    max_len: int = MAX_TEXT,
) -> Path:
    """Append a model_response event (response text + timestamp; model if known).

    token_usage is optional and included only when the caller/host actually knows
    it (e.g. Claude Code's per-turn counts). Never fabricate it for a host that
    doesn't expose it (e.g. Cursor's transcript format has no usage data at all).
    """
    root = repo_root or find_repo_root()
    entry = _drop_none(
        {
            "kind": "model_response",
            "ts": ts or now_iso(),
            "model": normalize_model(model),
            "response_text": clip(response_text, max_len),
            "token_usage": token_usage or None,
        }
    )
    return append_record(entry, root)


def log_thinking(
    *,
    thinking_text: str,
    model: str | None = None,
    ts: str | None = None,
    repo_root: Path | None = None,
    max_len: int = MAX_TEXT,
) -> Path:
    """Append a thinking event (full reasoning text when the host exposes it)."""
    root = repo_root or find_repo_root()
    entry = _drop_none(
        {
            "kind": "thinking",
            "ts": ts or now_iso(),
            "model": normalize_model(model),
            "thinking_text": clip(thinking_text, max_len),
        }
    )
    return append_record(entry, root)


def log_tool_result(
    *,
    content: str,
    tool_name: str | None = None,
    model: str | None = None,
    ts: str | None = None,
    repo_root: Path | None = None,
    max_len: int = MAX_TEXT,
) -> Path:
    """Append a tool_result event (full tool / shell / MCP / read payload)."""
    root = repo_root or find_repo_root()
    entry = _drop_none(
        {
            "kind": "tool_result",
            "ts": ts or now_iso(),
            "model": normalize_model(model),
            "tool_name": (str(tool_name).strip() if tool_name else None) or None,
            "content": clip(content, max_len),
        }
    )
    return append_record(entry, root)


def log_python_run(
    *,
    script_name: str,
    output: str | None = None,
    ts_start: str | None = None,
    ts_end: str | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Append a python_run event with start/end timestamps and captured output."""
    root = repo_root or find_repo_root()
    end = ts_end or now_iso()
    start = ts_start or end
    entry = {
        "kind": "python_run",
        "ts_start": start,
        "ts_end": end,
        "script_name": script_name,
        "output": clip(output, MAX_OUTPUT) if output is not None else "",
    }
    return append_record(entry, root)


def run_and_log(
    command: list[str] | str,
    *,
    cwd: Path | None = None,
    shell: bool = False,
    capture_output: bool = True,
    script_name: str | None = None,
    repo_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command, append python_run with ts_start/ts_end + output, return result."""
    root = repo_root or find_repo_root()
    if isinstance(command, str):
        popen_args: list[str] | str = command
        use_shell = True
        name = script_name or script_name_from_command(command)
    else:
        popen_args = command
        use_shell = shell
        name = script_name or script_name_from_command(command)

    ts_start = now_iso()
    completed = subprocess.run(
        popen_args,
        cwd=str(cwd) if cwd else None,
        shell=use_shell,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    ts_end = now_iso()
    out_bits: list[str] = []
    if capture_output:
        if completed.stdout:
            out_bits.append(completed.stdout)
        if completed.stderr:
            out_bits.append(completed.stderr)
    log_python_run(
        script_name=name,
        output="".join(out_bits) if out_bits else "",
        ts_start=ts_start,
        ts_end=ts_end,
        repo_root=root,
    )
    return completed


def cmd_path(_: argparse.Namespace) -> int:
    root = find_repo_root()
    path = ensure_log(root)
    print(path)
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    path = rotate_log(note=args.note, repo_root=root)
    print(json.dumps({"ok": True, "log_path": str(path)}, ensure_ascii=False))
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    kind = args.kind
    if kind not in VALID_KINDS:
        raise SystemExit(
            f"kind must be one of: {', '.join(sorted(VALID_KINDS))} (got {kind!r})"
        )

    if kind == "model_call":
        if not args.call_text:
            raise SystemExit("model_call requires --call-text")
        path = log_model_call(
            call_text=args.call_text,
            model=args.model,
            ts=args.ts,
            repo_root=root,
        )
    elif kind == "model_response":
        if not args.response_text:
            raise SystemExit("model_response requires --response-text")
        path = log_model_response(
            response_text=args.response_text,
            model=args.model,
            ts=args.ts,
            repo_root=root,
        )
    elif kind == "thinking":
        if not args.thinking_text:
            raise SystemExit("thinking requires --thinking-text")
        path = log_thinking(
            thinking_text=args.thinking_text,
            model=args.model,
            ts=args.ts,
            repo_root=root,
        )
    elif kind == "tool_result":
        if args.content is None:
            raise SystemExit("tool_result requires --content")
        path = log_tool_result(
            content=args.content,
            tool_name=args.tool_name,
            model=args.model,
            ts=args.ts,
            repo_root=root,
        )
    else:  # python_run
        if not args.script_name:
            raise SystemExit("python_run requires --script-name")
        path = log_python_run(
            script_name=args.script_name,
            output=args.output if args.output is not None else "",
            ts_start=args.ts_start,
            ts_end=args.ts_end,
            repo_root=root,
        )

    print(json.dumps({"ok": True, "log_path": str(path)}, ensure_ascii=False))
    return 0


def cmd_append_json(args: argparse.Namespace) -> int:
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        raise SystemExit("append-json expects a JSON object on stdin")
    kind = payload.get("kind")
    if kind not in VALID_KINDS:
        raise SystemExit(
            f"JSON kind must be one of: {', '.join(sorted(VALID_KINDS))} (got {kind!r})"
        )
    if "model" in payload:
        payload["model"] = normalize_model(payload.get("model"))
        if payload["model"] is None:
            payload.pop("model", None)
    for text_key in ("call_text", "response_text", "thinking_text", "content", "output"):
        if text_key in payload and payload[text_key] is not None:
            limit = MAX_OUTPUT if text_key == "output" else MAX_TEXT
            payload[text_key] = clip(str(payload[text_key]), limit)
    if kind in {"model_call", "model_response", "thinking", "tool_result"}:
        payload.setdefault("ts", now_iso())
    if kind == "thinking" and not payload.get("thinking_text"):
        raise SystemExit("thinking JSON requires thinking_text")
    if kind == "tool_result" and payload.get("content") is None:
        raise SystemExit("tool_result JSON requires content")
    if kind == "python_run":
        payload.setdefault("ts_end", now_iso())
        payload.setdefault("ts_start", payload["ts_end"])
        payload.setdefault("output", "")
        if not payload.get("script_name"):
            raise SystemExit("python_run JSON requires script_name")
    path = append_record(_drop_none(payload), root)
    print(json.dumps({"ok": True, "log_path": str(path)}, ensure_ascii=False))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a command, capture output + timestamps, append python_run, forward exit code."""
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    argv = list(args.cmd_argv or [])
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise SystemExit(
            "run requires a command after -- , e.g. session_log.py run -- python -V"
        )
    completed = run_and_log(
        argv,
        cwd=Path(args.cwd).resolve() if args.cwd else None,
        shell=bool(args.shell),
        capture_output=not bool(args.no_capture),
        script_name=args.script_name,
        repo_root=root,
    )
    if not args.no_capture:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
    print(
        json.dumps(
            {
                "ok": completed.returncode == 0,
                "exit_code": completed.returncode,
                "log_path": str(log_path(root)),
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return int(completed.returncode)


def cmd_self_test(_: argparse.Namespace) -> int:
    """Validate manual append helpers and the transcript listener."""
    root = find_repo_root()
    # Payload hygiene: oversized base64 must become a stub before append.
    heavy = "iVBORw0" + ("A" * 2500)
    compacted = compact_heavy_payloads(
        json.dumps({"tool_result": [{"type": "image", "source": {"data": heavy}}]})
    )
    if "omitted sha256=" not in compacted or heavy[:80] in compacted:
        print(
            json.dumps(
                {"ok": False, "error": "compact_heavy_payloads did not stub base64"},
                ensure_ascii=False,
            )
        )
        return 1
    log_model_call(
        call_text="self-test call",
        model="Cursor Grok 4.5",
        repo_root=root,
    )
    log_model_response(
        response_text="self-test response",
        model="Cursor Grok 4.5",
        repo_root=root,
    )
    log_model_response(
        response_text=json.dumps(
            {"tool_result": [{"type": "image", "source": {"data": heavy}}]}
        ),
        model="Cursor Grok 4.5",
        repo_root=root,
    )
    completed = run_and_log(
        [sys.executable, "-c", "print('session_log_self_test_ok')"],
        script_name="-c",
        repo_root=root,
    )
    path = log_path(root)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    recent = [json.loads(line) for line in lines[-4:]]
    image_logged = recent[2].get("response_text") or ""
    manual_ok = (
        completed.returncode == 0
        and recent[0].get("kind") == "model_call"
        and recent[0].get("call_text") == "self-test call"
        and recent[0].get("model") == "Cursor Grok 4.5"
        and "ts" in recent[0]
        and recent[1].get("kind") == "model_response"
        and recent[1].get("response_text") == "self-test response"
        and recent[2].get("kind") == "model_response"
        and "omitted sha256=" in image_logged
        and len(image_logged) < 500
        and recent[3].get("kind") == "python_run"
        and "ts_start" in recent[3]
        and "ts_end" in recent[3]
        and "session_log_self_test_ok" in (recent[3].get("output") or "")
        and "latency_ms" not in recent[0]
        and "token_usage" not in recent[0]
        and "source" not in recent[0]
    )

    # Listener path: simulate a host transcript JSONL and prove auto-append.
    from listen_transcripts import (
        self_test_listener,
        self_test_new_hosts,
        self_test_subagent_capture,
    )

    listener_result = self_test_listener(root)
    new_hosts_result = self_test_new_hosts(root)
    subagent_result = self_test_subagent_capture(root)
    ok = bool(
        manual_ok
        and listener_result.get("ok")
        and new_hosts_result.get("ok")
        and subagent_result.get("ok")
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "log_path": str(path),
                "manual_samples": recent,
                "listener": listener_result,
                "new_hosts": new_hosts_result,
                "subagents": subagent_result,
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


def cmd_listen(args: argparse.Namespace) -> int:
    """Watch host transcript JSONL directories and append the portable session log."""
    from listen_transcripts import cmd_listen as _cmd_listen

    return int(_cmd_listen(args))


def cmd_view(args: argparse.Namespace) -> int:
    """Serve the local HTML viewer for the JSONL log."""
    from view_log import DEFAULT_HOST, DEFAULT_PORT, serve

    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    return int(
        serve(
            host=args.host or DEFAULT_HOST,
            port=int(args.port or DEFAULT_PORT),
            open_browser=bool(args.open),
            repo_root=root,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Portable temporary AI session log at /temp/ai-session/ai-call-log.jsonl. "
            "Kinds: model_call, model_response, thinking, tool_result, python_run. "
            "Primary: listen (transcript watcher); Cursor option-2: hooks → "
            "cursor_hook_writer.py."
        )
    )
    sub = parser.add_subparsers(dest="command_name", required=True)

    path_p = sub.add_parser("path", help="Print absolute path to the JSONL log")
    path_p.set_defaults(func=cmd_path)

    listen_p = sub.add_parser(
        "listen",
        help=(
            "Watch host transcript JSONL directories and auto-append model_call / "
            "model_response / python_run (Cursor agent-transcripts by default)"
        ),
    )
    listen_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    listen_p.add_argument(
        "--transcripts-dir",
        action="append",
        default=[],
        help=(
            "Transcript JSONL directory to watch (repeatable). "
            "Default: Cursor agent-transcripts for this repo, or PORTABLE_AI_TRANSCRIPTS_DIR."
        ),
    )
    listen_p.add_argument(
        "--model",
        help=(
            'Optional default user-facing model label (e.g. "Cursor Grok 4.5") '
            "when transcripts omit model; never cursor-agent"
        ),
    )
    listen_p.add_argument(
        "--poll-ms",
        type=int,
        default=750,
        help="Polling interval in milliseconds (default: 750)",
    )
    listen_p.add_argument(
        "--once",
        action="store_true",
        help="Process current transcript tails once and exit",
    )
    listen_p.add_argument(
        "--from-start",
        action="store_true",
        help=(
            "On first sight of a transcript file, ingest from byte 0 "
            "(default: start at EOF and only capture new lines)"
        ),
    )
    listen_p.set_defaults(func=cmd_listen)

    rotate_p = sub.add_parser(
        "rotate",
        help="Truncate log and write a schema_cutover marker",
    )
    rotate_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    rotate_p.add_argument("--note", help="Optional cutover note")
    rotate_p.set_defaults(func=cmd_rotate)

    append_p = sub.add_parser("append", help="Append one structured session event")
    append_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    append_p.add_argument(
        "--kind",
        required=True,
        help="model_call | model_response | thinking | tool_result | python_run",
    )
    append_p.add_argument(
        "--model",
        help=(
            "User-facing underlying model name when known "
            '(e.g. "Cursor Grok 4.5"); omit if unknown; never "cursor-agent"'
        ),
    )
    append_p.add_argument(
        "--ts",
        help="ISO timestamp (model_call / model_response / thinking / tool_result)",
    )
    append_p.add_argument("--call-text", help="Required for model_call")
    append_p.add_argument("--response-text", help="Required for model_response")
    append_p.add_argument("--thinking-text", help="Required for thinking")
    append_p.add_argument("--content", help="Required for tool_result")
    append_p.add_argument("--tool-name", help="Optional tool label for tool_result")
    append_p.add_argument("--script-name", help="Required for python_run")
    append_p.add_argument("--output", help="Captured stdout/stderr for python_run")
    append_p.add_argument("--ts-start", help="Start timestamp for python_run")
    append_p.add_argument("--ts-end", help="End timestamp for python_run")
    append_p.set_defaults(func=cmd_append)

    json_p = sub.add_parser("append-json", help="Append a JSON object from stdin")
    json_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    json_p.set_defaults(func=cmd_append_json)

    run_p = sub.add_parser(
        "run",
        help="Run a command, capture output + timestamps, append python_run",
    )
    run_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    run_p.add_argument("--cwd", help="Working directory for the child process")
    run_p.add_argument(
        "--script-name",
        help="Override script_name stored in the log (default: inferred)",
    )
    run_p.add_argument(
        "--shell",
        action="store_true",
        help="Run via the system shell (Windows often needs this for builtins)",
    )
    run_p.add_argument(
        "--no-capture",
        action="store_true",
        help="Do not capture stdout/stderr into the log (child inherits console)",
    )
    run_p.add_argument(
        "cmd_argv",
        nargs=argparse.REMAINDER,
        help="Command to run; prefer: run -- python script.py",
    )
    run_p.set_defaults(func=cmd_run)

    test_p = sub.add_parser(
        "self-test",
        help="Append synthetic model_call / model_response / python_run and validate",
    )
    test_p.set_defaults(func=cmd_self_test)

    view_p = sub.add_parser(
        "view",
        help=(
            "Serve a local HTML timeline for the JSONL log "
            "(default http://127.0.0.1:8768/)"
        ),
    )
    view_p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    view_p.add_argument("--host", default="127.0.0.1", help="Bind host")
    view_p.add_argument("--port", type=int, default=8768, help="Bind port (default 8768)")
    view_p.add_argument(
        "--open",
        action="store_true",
        help="Open the system browser after start",
    )
    view_p.set_defaults(func=cmd_view)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) >= 1 and argv[0] == "run":
        try:
            sep = argv.index("--")
            argv = argv[:sep] + argv[sep + 1 :]
        except ValueError:
            pass
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
