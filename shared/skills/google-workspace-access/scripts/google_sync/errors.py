"""Error classification and retry helpers for Google sync."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_GOOGLE_ERROR = "transient_google_error"
    INVALID_REQUEST = "invalid_request"
    EXPIRED_CHECKPOINT = "expired_checkpoint"
    DATA_MAPPING = "data_mapping"
    INTERNAL_DATABASE = "internal_database"
    UNKNOWN = "unknown"


class SyncError(RuntimeError):
    """Base sync error with a stable category."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        *,
        retryable: bool | None = None,
        retry_after_seconds: float | None = None,
        cause: BaseException | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.retryable = (
            retryable
            if retryable is not None
            else category
            in {
                ErrorCategory.RATE_LIMIT,
                ErrorCategory.TRANSIENT_GOOGLE_ERROR,
                ErrorCategory.INTERNAL_DATABASE,
            }
        )
        self.retry_after_seconds = retry_after_seconds
        self.cause = cause


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    category: ErrorCategory


_RATE_LIMIT_RE = re.compile(r"\b(429|rate[_ ]?limit|quota)\b", re.I)
_AUTH_RE = re.compile(
    r"\b(401|invalid[_ ]?grant|unauthorized|token.*(revoked|expired)|login[_ ]?required)\b",
    re.I,
)
_PERM_RE = re.compile(r"\b(403|forbidden|insufficient[_ ]?permission|access[_ ]?denied)\b", re.I)
_EXPIRED_HIST_RE = re.compile(r"\b(404|history.*(?:not found|expired|invalid)|startHistoryId)\b", re.I)
_TRANSIENT_RE = re.compile(r"\b(500|502|503|504|backendError|timeout|temporar|unavailable)\b", re.I)


def classify_google_error(exc: BaseException) -> SyncError:
    """Map a Google / HTTP exception into a SyncError."""
    if isinstance(exc, SyncError):
        return exc

    status = getattr(exc, "status_code", None) or getattr(exc, "resp", None)
    if status is not None and hasattr(status, "status"):
        status = status.status
    text = str(exc)
    combined = f"{status or ''} {text}"

    retry_after = None
    resp = getattr(exc, "resp", None)
    if resp is not None:
        headers = getattr(resp, "headers", None) or {}
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw:
            try:
                retry_after = float(raw)
            except (TypeError, ValueError):
                retry_after = None

    if _AUTH_RE.search(combined) or status == 401:
        return SyncError(
            text,
            ErrorCategory.AUTHENTICATION,
            retryable=False,
            cause=exc,
        )
    if _PERM_RE.search(combined) or status == 403:
        return SyncError(
            text,
            ErrorCategory.PERMISSION,
            retryable=False,
            cause=exc,
        )
    if _RATE_LIMIT_RE.search(combined) or status == 429:
        return SyncError(
            text,
            ErrorCategory.RATE_LIMIT,
            retryable=True,
            retry_after_seconds=retry_after,
            cause=exc,
        )
    if _EXPIRED_HIST_RE.search(combined) or status == 404:
        return SyncError(
            text,
            ErrorCategory.EXPIRED_CHECKPOINT,
            retryable=False,
            cause=exc,
        )
    if _TRANSIENT_RE.search(combined) or status in {500, 502, 503, 504}:
        return SyncError(
            text,
            ErrorCategory.TRANSIENT_GOOGLE_ERROR,
            retryable=True,
            retry_after_seconds=retry_after,
            cause=exc,
        )
    if status == 400:
        return SyncError(
            text,
            ErrorCategory.INVALID_REQUEST,
            retryable=False,
            cause=exc,
        )
    return SyncError(
        text,
        ErrorCategory.UNKNOWN,
        retryable=True,
        cause=exc,
    )


def compute_backoff(
    attempt: int,
    *,
    category: ErrorCategory,
    retry_after_seconds: float | None = None,
    base_seconds: float = 2.0,
    max_seconds: float = 300.0,
) -> float:
    """Exponential backoff with jitter; honour Retry-After when present."""
    if retry_after_seconds is not None and retry_after_seconds >= 0:
        jitter = random.uniform(0, min(5.0, retry_after_seconds * 0.2 + 0.1))
        return min(max_seconds, retry_after_seconds + jitter)
    exp = min(max_seconds, base_seconds * (2 ** max(0, attempt - 1)))
    if category == ErrorCategory.RATE_LIMIT:
        exp = min(max_seconds, exp * 1.5)
    jitter = random.uniform(0, exp * 0.25 + 0.05)
    return min(max_seconds, exp + jitter)


def decide_retry(
    exc: BaseException,
    *,
    attempt: int,
    max_attempts: int,
) -> RetryDecision:
    sync_exc = classify_google_error(exc)
    if attempt >= max_attempts or not sync_exc.retryable:
        return RetryDecision(False, 0.0, sync_exc.category)
    delay = compute_backoff(
        attempt,
        category=sync_exc.category,
        retry_after_seconds=sync_exc.retry_after_seconds,
    )
    return RetryDecision(True, delay, sync_exc.category)


def safe_error_message(exc: BaseException, limit: int = 500) -> str:
    """Stringify an error without leaking obvious secret material."""
    text = str(exc)
    text = re.sub(r"(?i)\bauthorization:\s*.+", "Authorization: [REDACTED]", text)
    text = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret)\s*[:=]\s*\S+",
        r"\g<1>=[REDACTED]",
        text,
    )
    return text[:limit]


def error_context(**kwargs: Any) -> dict[str, Any]:
    """Build a log-safe context dict (values must already be non-sensitive)."""
    return {key: value for key, value in kwargs.items() if value is not None}
