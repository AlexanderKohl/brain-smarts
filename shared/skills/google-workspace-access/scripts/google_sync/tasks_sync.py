"""Google Tasks local mirror: list ensure, outbox push, poll, completion policy."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import SyncConfig
from .db import Database
from .errors import ErrorCategory, SyncError, classify_google_error, safe_error_message
from .observability import emit_event, timed_event, utc_now_iso
from .tasks_api import TasksApiClient


ClientFactory = Callable[[str], TasksApiClient]

TASK_ID_MARKER_RE = re.compile(
    r"\[portable-ai-brain-task-id:([0-9a-fA-F-]{36})\]"
)


def task_id_marker(internal_task_id: str) -> str:
    return f"[portable-ai-brain-task-id:{internal_task_id}]"


def extract_internal_task_id(notes: str | None) -> str | None:
    if not notes:
        return None
    match = TASK_ID_MARKER_RE.search(notes)
    return match.group(1) if match else None


def due_date_only(due_at: str | None) -> str | None:
    """Google Tasks accepts date-only RFC3339; strip time-of-day for Google."""
    if not due_at:
        return None
    text = due_at.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Already date-only?
        if len(due_at) >= 10:
            return due_at[:10] + "T00:00:00.000Z"
        return None
    return dt.date().isoformat() + "T00:00:00.000Z"


class TasksSyncService:
    def __init__(
        self,
        db: Database,
        config: SyncConfig,
        client_factory: ClientFactory,
    ):
        self.db = db
        self.config = config
        self.client_factory = client_factory

    def _client(self, account_id: str) -> TasksApiClient:
        return self.client_factory(account_id)

    def ensure_task_list(self, account_id: str) -> str:
        title = self.config.google_tasks_list_name
        existing = self.db.fetchone(
            """
            SELECT google_task_list_id FROM google_task_sync_state
            WHERE google_account_id = ? AND list_title = ?
            """,
            (account_id, title),
        )
        if existing and existing["google_task_list_id"]:
            return str(existing["google_task_list_id"])

        client = self._client(account_id)
        lists = client.list_task_lists()
        match = next((item for item in lists if item.get("title") == title), None)
        if match is None:
            match = client.create_task_list(title)
        list_id = str(match["id"])
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO google_task_sync_state (
                google_account_id, google_task_list_id, list_title,
                sync_status, created_at, updated_at
            ) VALUES (?, ?, ?, 'idle', ?, ?)
            ON CONFLICT(google_account_id, google_task_list_id) DO UPDATE SET
                list_title = excluded.list_title,
                updated_at = excluded.updated_at
            """,
            (account_id, list_id, title, now, now),
        )
        return list_id

    def create_external_task(self, internal_task_id: str) -> None:
        task = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (internal_task_id,)
        )
        if task is None:
            raise SyncError(
                f"internal task {internal_task_id} not found",
                ErrorCategory.DATA_MAPPING,
            )
        account_id = task["google_account_id"]
        if not account_id:
            raise SyncError(
                "internal task has no google_account_id",
                ErrorCategory.DATA_MAPPING,
            )

        mapping = self.db.fetchone(
            """
            SELECT * FROM google_task_mappings
            WHERE internal_task_id = ? AND google_account_id = ?
            """,
            (internal_task_id, account_id),
        )
        if mapping and mapping["mapping_status"] == "active":
            emit_event(
                "google_task_create_skipped_exists",
                account_id=account_id,
                internal_task_id=internal_task_id,
                google_task_id=mapping["google_task_id"],
            )
            return

        list_id = self.ensure_task_list(account_id)
        client = self._client(account_id)
        notes = task["description"] or ""
        marker = task_id_marker(internal_task_id)
        if marker not in notes:
            notes = (notes + "\n\n" + marker).strip() if notes else marker
        body: dict[str, Any] = {
            "title": task["title"],
            "notes": notes,
            "status": "completed" if task["status"] == "completed" else "needsAction",
        }
        due = due_date_only(task["due_at"])
        if due:
            body["due"] = due

        try:
            created = client.insert_task(tasklist=list_id, body=body)
        except Exception as exc:
            sync_exc = classify_google_error(exc)
            emit_event(
                "google_task_create_failed",
                account_id=account_id,
                internal_task_id=internal_task_id,
                error_category=sync_exc.category.value,
                error=safe_error_message(exc),
            )
            if sync_exc.category == ErrorCategory.AUTHENTICATION:
                self.db.mark_reconnect_required(
                    account_id, safe_error_message(exc)
                )
            raise sync_exc from exc

        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO google_task_mappings (
                internal_task_id, google_account_id, google_task_list_id,
                google_task_id, google_etag, google_status, google_updated_at,
                google_self_link, google_web_view_link, mapping_status,
                last_pushed_at, last_pulled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            ON CONFLICT(internal_task_id, google_account_id) DO UPDATE SET
                google_task_list_id = excluded.google_task_list_id,
                google_task_id = excluded.google_task_id,
                google_etag = excluded.google_etag,
                google_status = excluded.google_status,
                google_updated_at = excluded.google_updated_at,
                google_self_link = excluded.google_self_link,
                google_web_view_link = excluded.google_web_view_link,
                mapping_status = 'active',
                last_pushed_at = excluded.last_pushed_at,
                last_sync_error = NULL,
                updated_at = excluded.updated_at
            """,
            (
                internal_task_id,
                account_id,
                list_id,
                created.get("id"),
                created.get("etag"),
                created.get("status"),
                created.get("updated"),
                created.get("selfLink"),
                created.get("webViewLink"),
                now,
                now,
                now,
                now,
            ),
        )
        emit_event(
            "google_task_created",
            account_id=account_id,
            internal_task_id=internal_task_id,
            google_task_id=created.get("id"),
        )

    def update_external_task(self, internal_task_id: str) -> None:
        task = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (internal_task_id,)
        )
        if task is None:
            raise SyncError(
                f"internal task {internal_task_id} not found",
                ErrorCategory.DATA_MAPPING,
            )
        account_id = task["google_account_id"]
        mapping = self.db.fetchone(
            """
            SELECT * FROM google_task_mappings
            WHERE internal_task_id = ? AND google_account_id = ?
              AND mapping_status = 'active'
            """,
            (internal_task_id, account_id),
        )
        if mapping is None:
            # No mapping yet — create instead.
            self.create_external_task(internal_task_id)
            return

        client = self._client(account_id)
        body: dict[str, Any] = {
            "title": task["title"],
            "status": "completed" if task["status"] == "completed" else "needsAction",
        }
        notes = task["description"] or ""
        marker = task_id_marker(internal_task_id)
        if marker not in notes:
            notes = (notes + "\n\n" + marker).strip() if notes else marker
        body["notes"] = notes
        due = due_date_only(task["due_at"])
        if due:
            body["due"] = due

        try:
            updated = client.patch_task(
                tasklist=mapping["google_task_list_id"],
                task_id=mapping["google_task_id"],
                body=body,
            )
        except Exception as exc:
            sync_exc = classify_google_error(exc)
            emit_event(
                "google_task_sync_failed",
                account_id=account_id,
                internal_task_id=internal_task_id,
                error_category=sync_exc.category.value,
                error=safe_error_message(exc),
            )
            raise sync_exc from exc

        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE google_task_mappings
            SET google_etag = ?,
                google_status = ?,
                google_updated_at = ?,
                last_pushed_at = ?,
                last_sync_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                updated.get("etag"),
                updated.get("status"),
                updated.get("updated"),
                now,
                now,
                mapping["id"],
            ),
        )
        if task["status"] == "completed":
            emit_event(
                "google_task_completed_from_internal",
                account_id=account_id,
                internal_task_id=internal_task_id,
                google_task_id=mapping["google_task_id"],
            )

    def poll_external_changes(self, account_id: str) -> dict[str, Any]:
        holder = f"tasks_poll:{uuid.uuid4()}"
        lock_key = f"google_tasks_poll:{account_id}"
        with self.db.account_lock(lock_key, holder, ttl_seconds=300) as acquired:
            if not acquired:
                emit_event(
                    "google_tasks_poll_skipped_lock",
                    account_id=account_id,
                )
                return {"skipped": True, "reason": "lock_held"}
            return self._poll(account_id)

    def _poll(self, account_id: str) -> dict[str, Any]:
        list_id = self.ensure_task_list(account_id)
        state = self.db.fetchone(
            """
            SELECT * FROM google_task_sync_state
            WHERE google_account_id = ? AND google_task_list_id = ?
            """,
            (account_id, list_id),
        )
        overlap = self.config.google_tasks_updated_min_overlap
        updated_min = None
        if state and state["last_updated_min"]:
            try:
                base = datetime.fromisoformat(
                    state["last_updated_min"].replace("Z", "+00:00")
                )
                updated_min = (
                    (base - timedelta(seconds=overlap))
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except ValueError:
                updated_min = state["last_updated_min"]
        elif state and state["last_successful_poll_at"]:
            try:
                base = datetime.fromisoformat(
                    state["last_successful_poll_at"].replace("Z", "+00:00")
                )
                updated_min = (
                    (base - timedelta(seconds=overlap))
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except ValueError:
                updated_min = None

        client = self._client(account_id)
        with timed_event(
            "google_tasks_poll_started",
            "google_tasks_poll_completed",
            "google_task_sync_failed",
            account_id=account_id,
            google_task_list_id=list_id,
            updated_min=updated_min,
        ) as op:
            started = utc_now_iso()
            self.db.execute(
                """
                UPDATE google_task_sync_state
                SET sync_status = 'polling',
                    last_poll_started_at = ?,
                    updated_at = ?
                WHERE google_account_id = ? AND google_task_list_id = ?
                """,
                (started, started, account_id, list_id),
            )
            try:
                pages = 0
                processed = 0
                completed_from_google = 0
                newest_updated: str | None = state["last_updated_min"] if state else None
                page_token: str | None = None
                # Collect all pages first; advance checkpoint only after success.
                items: list[dict[str, Any]] = []
                while True:
                    response = client.list_tasks(
                        tasklist=list_id,
                        updated_min=updated_min,
                        page_token=page_token,
                        page_size=self.config.google_tasks_page_size,
                        show_completed=True,
                        show_hidden=True,
                        show_deleted=True,
                    )
                    pages += 1
                    batch = list(response.get("items") or [])
                    items.extend(batch)
                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break

                for item in items:
                    outcome = self._apply_google_task(account_id, list_id, item)
                    processed += 1
                    if outcome.get("completed_from_google"):
                        completed_from_google += 1
                    updated = item.get("updated")
                    if updated and (
                        newest_updated is None or updated > newest_updated
                    ):
                        newest_updated = updated

                completed = utc_now_iso()
                self.db.execute(
                    """
                    UPDATE google_task_sync_state
                    SET sync_status = 'idle',
                        last_poll_completed_at = ?,
                        last_successful_poll_at = ?,
                        last_updated_min = COALESCE(?, last_updated_min),
                        last_sync_error = NULL,
                        updated_at = ?
                    WHERE google_account_id = ? AND google_task_list_id = ?
                    """,
                    (
                        completed,
                        completed,
                        newest_updated,
                        completed,
                        account_id,
                        list_id,
                    ),
                )
                result = {
                    "record_count": processed,
                    "page_count": pages,
                    "completed_from_google": completed_from_google,
                    "checkpoint": newest_updated,
                    "poll_updated_min": updated_min,
                    "showCompleted": True,
                    "showHidden": True,
                    "showDeleted": True,
                }
                op.complete(
                    record_count=processed,
                    page_count=pages,
                    completed_from_google=completed_from_google,
                    checkpoint=newest_updated,
                )
                return result
            except Exception as exc:
                sync_exc = classify_google_error(exc)
                self.db.execute(
                    """
                    UPDATE google_task_sync_state
                    SET sync_status = 'error',
                        last_sync_error = ?,
                        updated_at = ?
                    WHERE google_account_id = ? AND google_task_list_id = ?
                    """,
                    (
                        safe_error_message(sync_exc),
                        utc_now_iso(),
                        account_id,
                        list_id,
                    ),
                )
                if sync_exc.category == ErrorCategory.AUTHENTICATION:
                    self.db.mark_reconnect_required(
                        account_id, safe_error_message(sync_exc)
                    )
                raise

    def _apply_google_task(
        self,
        account_id: str,
        list_id: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        google_task_id = item.get("id")
        if not google_task_id:
            return {}
        mapping = self.db.fetchone(
            """
            SELECT * FROM google_task_mappings
            WHERE google_account_id = ?
              AND google_task_list_id = ?
              AND google_task_id = ?
            """,
            (account_id, list_id, google_task_id),
        )
        if mapping is None:
            # Ignore unmapped Google tasks (no import feature in this cut).
            return {"ignored_unmapped": True}

        now = utc_now_iso()
        if item.get("deleted"):
            self.db.execute(
                """
                UPDATE google_task_mappings
                SET mapping_status = 'externally_deleted',
                    google_etag = ?,
                    google_status = ?,
                    google_updated_at = ?,
                    last_pulled_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    item.get("etag"),
                    item.get("status"),
                    item.get("updated"),
                    now,
                    now,
                    mapping["id"],
                ),
            )
            return {"externally_deleted": True}

        # Idempotent mapping update
        self.db.execute(
            """
            UPDATE google_task_mappings
            SET google_etag = ?,
                google_status = ?,
                google_updated_at = ?,
                last_pulled_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                item.get("etag"),
                item.get("status"),
                item.get("updated"),
                now,
                now,
                mapping["id"],
            ),
        )

        internal = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?",
            (mapping["internal_task_id"],),
        )
        if internal is None:
            return {}

        google_status = item.get("status")
        if google_status == "completed" and internal["status"] != "completed":
            self.db.execute(
                """
                UPDATE internal_tasks
                SET status = 'completed',
                    completed_at = COALESCE(completed_at, ?),
                    completed_source = 'google_tasks',
                    updated_at = ?
                WHERE id = ?
                """,
                (item.get("completed") or now, now, internal["id"]),
            )
            emit_event(
                "google_task_completed_from_google",
                account_id=account_id,
                internal_task_id=internal["id"],
                google_task_id=google_task_id,
            )
            return {"completed_from_google": True}

        if (
            google_status == "needsAction"
            and internal["status"] == "completed"
        ):
            # Monotonic completion: do not reopen from stale Google state.
            emit_event(
                "google_task_stale_needs_action_ignored",
                account_id=account_id,
                internal_task_id=internal["id"],
                google_task_id=google_task_id,
            )
            return {"stale_needs_action_ignored": True}

        return {"updated": True}

    def process_outbox_item(self, row: Any) -> None:
        operation = row["operation"]
        internal_task_id = row["internal_task_id"]
        if operation == "create_task":
            self.create_external_task(internal_task_id)
        elif operation in {"update_task", "complete_task"}:
            self.update_external_task(internal_task_id)
        else:
            raise SyncError(
                f"unknown outbox operation {operation}",
                ErrorCategory.INVALID_REQUEST,
            )
