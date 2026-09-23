"""Wire sync services to vault-backed GoogleConnection clients."""

from __future__ import annotations

from typing import Any

from .config import SyncConfig
from .db import Database
from .email_service import EmailService
from .gmail_api import GmailApiClient
from .gmail_sync import GmailSyncService
from .gmail_watch import GmailWatchService
from .task_service import TaskService
from .tasks_api import TasksApiClient
from .tasks_sync import TasksSyncService
from .worker import SyncWorker


def account_id_for_alias(alias: str) -> str:
    """Stable local account id derived from registry alias."""
    return f"google:{alias}"


def ensure_connection(db: Database, alias: str, email: str) -> str:
    account_id = account_id_for_alias(alias)
    db.upsert_connection(account_id=account_id, alias=alias, email=email)
    return account_id


def resolve_account_from_env(alias: str | None = None) -> tuple[str, str, str]:
    """Return (account_id, alias, email) using google_oauth registry."""
    from google_oauth.accounts import get_account, resolve_alias

    resolved = resolve_alias(alias)
    account = get_account(resolved)
    account_id = account_id_for_alias(account.alias)
    return account_id, account.alias, account.email


def build_gmail_client(account_id: str, db: Database) -> GmailApiClient:
    from google_oauth import GoogleConnection

    conn = db.get_connection(account_id)
    if conn is None:
        raise RuntimeError(f"Unknown google account id {account_id}")
    google = GoogleConnection.from_environment(conn["account_alias"])
    return GmailApiClient(google.build_service("gmail", "v1"))


def build_tasks_client(account_id: str, db: Database) -> TasksApiClient:
    from google_oauth import GoogleConnection

    conn = db.get_connection(account_id)
    if conn is None:
        raise RuntimeError(f"Unknown google account id {account_id}")
    google = GoogleConnection.from_environment(conn["account_alias"])
    return TasksApiClient(google.build_service("tasks", "v1"))


def build_stack(
    config: SyncConfig | None = None,
    db: Database | None = None,
    *,
    gmail_factory: Any = None,
    tasks_factory: Any = None,
) -> dict[str, Any]:
    config = config or SyncConfig.from_environment()
    db = db or Database(config.db_path)
    db.migrate()

    def _gmail(account_id: str) -> GmailApiClient:
        if gmail_factory:
            return gmail_factory(account_id)
        return build_gmail_client(account_id, db)

    def _tasks(account_id: str) -> TasksApiClient:
        if tasks_factory:
            return tasks_factory(account_id)
        return build_tasks_client(account_id, db)

    gmail_sync = GmailSyncService(db, config, _gmail)
    tasks_sync = TasksSyncService(db, config, _tasks)
    watch = GmailWatchService(db, config, gmail_sync)
    email_service = EmailService(db, config, gmail_sync)
    task_service = TaskService(db, config)
    worker = SyncWorker(
        db,
        config,
        gmail_sync=gmail_sync,
        tasks_sync=tasks_sync,
        watch_service=watch,
    )
    return {
        "config": config,
        "db": db,
        "gmail_sync": gmail_sync,
        "tasks_sync": tasks_sync,
        "watch": watch,
        "email_service": email_service,
        "task_service": task_service,
        "worker": worker,
    }
