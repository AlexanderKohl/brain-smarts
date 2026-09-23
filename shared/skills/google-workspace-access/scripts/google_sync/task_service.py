"""Local operational task service with Google Tasks outbox sync."""

from __future__ import annotations

import uuid
from typing import Any

from .config import SyncConfig
from .db import Database
from .observability import utc_now_iso


class TaskService:
    def __init__(self, db: Database, config: SyncConfig):
        self.db = db
        self.config = config

    def _google_sync_meta(self, task_id: str, account_id: str | None) -> dict[str, Any]:
        if not account_id:
            return {
                "status": "not_linked",
                "lastSyncedAt": None,
                "error": None,
            }
        mapping = self.db.fetchone(
            """
            SELECT * FROM google_task_mappings
            WHERE internal_task_id = ? AND google_account_id = ?
            """,
            (task_id, account_id),
        )
        outbox = self.db.fetchone(
            """
            SELECT * FROM sync_outbox
            WHERE internal_task_id = ? AND google_account_id = ?
              AND status IN ('pending', 'running', 'failed')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (task_id, account_id),
        )
        if mapping is None:
            if outbox:
                return {
                    "status": "failed" if outbox["status"] == "failed" else "pending",
                    "lastSyncedAt": None,
                    "error": outbox["last_error"],
                }
            return {
                "status": "not_linked",
                "lastSyncedAt": None,
                "error": None,
            }
        if mapping["mapping_status"] == "externally_deleted":
            return {
                "status": "externally_deleted",
                "lastSyncedAt": mapping["last_pulled_at"] or mapping["last_pushed_at"],
                "error": mapping["last_sync_error"],
            }
        if outbox and outbox["status"] in {"pending", "running"}:
            return {
                "status": "pending",
                "lastSyncedAt": mapping["last_pushed_at"] or mapping["last_pulled_at"],
                "error": None,
            }
        if outbox and outbox["status"] == "failed":
            return {
                "status": "failed",
                "lastSyncedAt": mapping["last_pushed_at"] or mapping["last_pulled_at"],
                "error": outbox["last_error"],
            }
        return {
            "status": "synced",
            "lastSyncedAt": mapping["last_pushed_at"] or mapping["last_pulled_at"],
            "error": mapping["last_sync_error"],
        }

    def _row_to_task(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "googleAccountId": row["google_account_id"],
            "title": row["title"],
            "description": row["description"],
            "dueAt": row["due_at"],
            "status": row["status"],
            "completedAt": row["completed_at"],
            "completedSource": row["completed_source"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "googleSync": self._google_sync_meta(row["id"], row["google_account_id"]),
        }

    def list_tasks(
        self,
        account_id: str | None = None,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        sql = "SELECT * FROM internal_tasks WHERE 1=1"
        params: list[Any] = []
        if account_id:
            sql += " AND google_account_id = ?"
            params.append(account_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.db.fetchall(sql, params)
        return {"data": [self._row_to_task(r) for r in rows]}

    def get_task(self, task_id: str) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (task_id,)
        )
        if row is None:
            return {"data": None, "error": "not_found"}
        return {"data": self._row_to_task(row)}

    def search_tasks(
        self, query: str, *, account_id: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        q = f"%{query.strip()}%"
        sql = """
            SELECT * FROM internal_tasks
            WHERE (title LIKE ? OR description LIKE ?)
        """
        params: list[Any] = [q, q]
        if account_id:
            sql += " AND google_account_id = ?"
            params.append(account_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.db.fetchall(sql, params)
        return {"data": [self._row_to_task(r) for r in rows], "query": query}

    def create_task(
        self,
        *,
        title: str,
        google_account_id: str,
        description: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO internal_tasks (
                    id, google_account_id, title, description, due_at,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    task_id,
                    google_account_id,
                    title,
                    description,
                    due_at,
                    now,
                    now,
                ),
            )
            if self.config.google_tasks_sync_enabled:
                outbox_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO sync_outbox (
                        id, operation, google_account_id, internal_task_id,
                        status, attempts, max_attempts, run_after, payload_json,
                        created_at, updated_at
                    ) VALUES (?, 'create_task', ?, ?, 'pending', 0, ?, ?, '{}', ?, ?)
                    """,
                    (
                        outbox_id,
                        google_account_id,
                        task_id,
                        self.config.max_job_attempts,
                        now,
                        now,
                        now,
                    ),
                )
        row = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (task_id,)
        )
        return {"data": self._row_to_task(row)}

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (task_id,)
        )
        if row is None:
            return {"data": None, "error": "not_found"}
        now = utc_now_iso()
        new_title = title if title is not None else row["title"]
        new_description = (
            description if description is not None else row["description"]
        )
        new_due = due_at if due_at is not None else row["due_at"]
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE internal_tasks
                SET title = ?, description = ?, due_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_description, new_due, now, task_id),
            )
            if self.config.google_tasks_sync_enabled and row["google_account_id"]:
                self._enqueue_outbox_in_conn(
                    conn,
                    operation="update_task",
                    google_account_id=row["google_account_id"],
                    internal_task_id=task_id,
                )
        return self.get_task(task_id)

    def complete_task(
        self, task_id: str, *, source: str = "internal"
    ) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT * FROM internal_tasks WHERE id = ?", (task_id,)
        )
        if row is None:
            return {"data": None, "error": "not_found"}
        if row["status"] == "completed":
            return {"data": self._row_to_task(row)}
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE internal_tasks
                SET status = 'completed',
                    completed_at = ?,
                    completed_source = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, source, now, task_id),
            )
            if (
                self.config.google_tasks_sync_enabled
                and row["google_account_id"]
                and source != "google_tasks"
            ):
                self._enqueue_outbox_in_conn(
                    conn,
                    operation="complete_task",
                    google_account_id=row["google_account_id"],
                    internal_task_id=task_id,
                )
        return self.get_task(task_id)

    def _enqueue_outbox_in_conn(
        self,
        conn: Any,
        *,
        operation: str,
        google_account_id: str,
        internal_task_id: str,
    ) -> None:
        now = utc_now_iso()
        existing = conn.execute(
            """
            SELECT id, status FROM sync_outbox
            WHERE operation = ? AND internal_task_id = ? AND google_account_id = ?
            """,
            (operation, internal_task_id, google_account_id),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE sync_outbox
                SET status = 'pending',
                    run_after = ?,
                    updated_at = ?,
                    last_error = NULL,
                    last_error_category = NULL
                WHERE id = ?
                """,
                (now, now, existing["id"]),
            )
            return
        conn.execute(
            """
            INSERT INTO sync_outbox (
                id, operation, google_account_id, internal_task_id,
                status, attempts, max_attempts, run_after, payload_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, '{}', ?, ?)
            """,
            (
                str(uuid.uuid4()),
                operation,
                google_account_id,
                internal_task_id,
                self.config.max_job_attempts,
                now,
                now,
                now,
            ),
        )

    def get_task_sync_status(self, account_id: str) -> dict[str, Any]:
        state = self.db.fetchall(
            """
            SELECT * FROM google_task_sync_state
            WHERE google_account_id = ?
            """,
            (account_id,),
        )
        pending = self.db.fetchone(
            """
            SELECT COUNT(*) AS n FROM sync_outbox
            WHERE google_account_id = ? AND status IN ('pending', 'running', 'failed')
            """,
            (account_id,),
        )
        return {
            "data": {
                "accountId": account_id,
                "lists": [dict(r) for r in state],
                "pendingOutbox": pending["n"] if pending else 0,
            }
        }

    def refresh_tasks_on_demand(self, account_id: str) -> dict[str, Any]:
        job_id = self.db.enqueue_job(
            job_type="google_tasks_poll",
            google_account_id=account_id,
            dedupe_key=f"google_tasks_poll:{account_id}",
            payload={"trigger": "on_demand", "requested_at": utc_now_iso()},
            max_attempts=self.config.max_job_attempts,
        )
        return {
            "data": {"jobId": job_id, "enqueued": job_id is not None},
        }
