"""Configuration for the local Gmail / Google Tasks sync layer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw.strip())


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip()


def default_db_path() -> Path:
    override = _env_str("GOOGLE_LOCAL_SYNC_DB")
    if override:
        return Path(override)
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "PortableAIBrain" / "google-local-sync" / "sync.db"
    return Path.home() / ".local" / "share" / "portable-ai-brain" / "google-local-sync" / "sync.db"


@dataclass(frozen=True)
class SyncConfig:
    """Runtime flags and intervals for local sync."""

    db_path: Path
    gmail_local_sync_enabled: bool = False
    gmail_initial_sync_query: str = "newer_than:1y"
    gmail_import_important_history: bool = True
    gmail_important_history_query: str = "is:starred OR is:important"
    gmail_reconciliation_interval: int = 1800
    gmail_watch_renewal_interval: int = 86400
    gmail_pubsub_topic: str = ""
    gmail_pubsub_subscription: str = ""
    gmail_stale_threshold_seconds: int = 600
    gmail_metadata_batch_size: int = 50
    gmail_list_page_size: int = 100
    google_tasks_sync_enabled: bool = False
    google_tasks_list_name: str = "Portable AI Brain"
    google_tasks_poll_interval: int = 90
    google_tasks_updated_min_overlap: int = 180
    google_tasks_page_size: int = 100
    worker_loop_sleep_seconds: float = 2.0
    max_job_attempts: int = 8
    body_fetch_lock_ttl_seconds: int = 120

    @classmethod
    def from_environment(cls) -> "SyncConfig":
        return cls(
            db_path=default_db_path(),
            gmail_local_sync_enabled=_env_bool("GMAIL_LOCAL_SYNC_ENABLED", False),
            gmail_initial_sync_query=_env_str(
                "GMAIL_INITIAL_SYNC_QUERY", "newer_than:1y"
            )
            or "newer_than:1y",
            gmail_import_important_history=_env_bool(
                "GMAIL_IMPORT_IMPORTANT_HISTORY", True
            ),
            gmail_important_history_query=_env_str(
                "GMAIL_IMPORTANT_HISTORY_QUERY", "is:starred OR is:important"
            )
            or "is:starred OR is:important",
            gmail_reconciliation_interval=_env_int(
                "GMAIL_RECONCILIATION_INTERVAL", 1800
            ),
            gmail_watch_renewal_interval=_env_int(
                "GMAIL_WATCH_RENEWAL_INTERVAL", 86400
            ),
            gmail_pubsub_topic=_env_str("GMAIL_PUBSUB_TOPIC"),
            gmail_pubsub_subscription=_env_str("GMAIL_PUBSUB_SUBSCRIPTION"),
            gmail_stale_threshold_seconds=_env_int(
                "GMAIL_STALE_THRESHOLD_SECONDS", 600
            ),
            gmail_metadata_batch_size=_env_int("GMAIL_METADATA_BATCH_SIZE", 50),
            gmail_list_page_size=_env_int("GMAIL_LIST_PAGE_SIZE", 100),
            google_tasks_sync_enabled=_env_bool("GOOGLE_TASKS_SYNC_ENABLED", False),
            google_tasks_list_name=_env_str(
                "GOOGLE_TASKS_LIST_NAME", "Portable AI Brain"
            )
            or "Portable AI Brain",
            google_tasks_poll_interval=_env_int("GOOGLE_TASKS_POLL_INTERVAL", 90),
            google_tasks_updated_min_overlap=_env_int(
                "GOOGLE_TASKS_UPDATED_MIN_OVERLAP", 180
            ),
            google_tasks_page_size=_env_int("GOOGLE_TASKS_PAGE_SIZE", 100),
            worker_loop_sleep_seconds=float(
                _env_str("GOOGLE_SYNC_WORKER_SLEEP", "2") or "2"
            ),
            max_job_attempts=_env_int("GOOGLE_SYNC_MAX_JOB_ATTEMPTS", 8),
            body_fetch_lock_ttl_seconds=_env_int(
                "GMAIL_BODY_FETCH_LOCK_TTL_SECONDS", 120
            ),
        )

    @property
    def pubsub_configured(self) -> bool:
        return bool(self.gmail_pubsub_topic and self.gmail_pubsub_subscription)
