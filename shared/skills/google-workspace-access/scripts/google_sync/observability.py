"""Structured logging for sync operations (no tokens or message bodies)."""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator


SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "client_secret",
        "authorization",
        "token",
        "text_body",
        "html_body",
        "body",
        "raw",
        "notes",
        "description",
        "attachment_data",
        "payload_data",
    }
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _redact(value: Any, *, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: _redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…[truncated]"
    return value


def emit_event(event: str, **fields: Any) -> None:
    """Write one structured JSON log line to stderr."""
    payload = {
        "ts": utc_now_iso(),
        "event": event,
        **_redact(fields),
    }
    line = json.dumps(payload, ensure_ascii=False, default=str)
    print(line, file=sys.stderr, flush=True)


@dataclass
class TimedOp:
    event_started: str
    event_completed: str
    event_failed: str
    fields: dict[str, Any] = field(default_factory=dict)
    started_monotonic: float = 0.0

    def start(self) -> None:
        self.started_monotonic = time.monotonic()
        emit_event(self.event_started, **self.fields)

    def complete(self, **extra: Any) -> None:
        duration_ms = int((time.monotonic() - self.started_monotonic) * 1000)
        merged = {**self.fields, **extra}
        emit_event(
            self.event_completed,
            duration_ms=duration_ms,
            **merged,
        )

    def fail(self, *, error_category: str, error: str, **extra: Any) -> None:
        duration_ms = int((time.monotonic() - self.started_monotonic) * 1000)
        emit_event(
            self.event_failed,
            duration_ms=duration_ms,
            error_category=error_category,
            error=error,
            **self.fields,
            **extra,
        )


@contextmanager
def timed_event(
    started: str,
    completed: str,
    failed: str,
    **fields: Any,
) -> Iterator[TimedOp]:
    op = TimedOp(started, completed, failed, fields=dict(fields))
    op.start()
    try:
        yield op
    except Exception as exc:
        from .errors import classify_google_error, safe_error_message

        sync_exc = classify_google_error(exc)
        op.fail(
            error_category=sync_exc.category.value,
            error=safe_error_message(exc),
        )
        raise
