"""SQLite persistence, migrations, locks, jobs and outbox helpers."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from .observability import utc_now_iso


SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


class Database:
    """Thin SQLite wrapper used by sync services and workers."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise

    def execute(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq)

    def fetchone(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def migrate(self) -> list[str]:
        """Apply pending SQL migrations from schema/."""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in self.fetchall("SELECT version FROM schema_migrations")
        }
        newly: list[str] = []
        files = sorted(SCHEMA_DIR.glob("*.sql"))
        for path in files:
            version = path.name
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # executescript auto-commits; do not wrap it in an explicit transaction.
            with self._lock:
                self._conn.executescript(sql)
                self._conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_now_iso()),
                )
            newly.append(version)
        return newly

    # --- connections -----------------------------------------------------

    def upsert_connection(
        self, *, account_id: str, alias: str, email: str
    ) -> None:
        now = utc_now_iso()
        self.execute(
            """
            INSERT INTO google_connections (
                id, account_alias, email, reconnect_required, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 0, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                account_alias = excluded.account_alias,
                email = excluded.email,
                updated_at = excluded.updated_at
            """,
            (account_id, alias, email, now, now),
        )
        self.execute(
            """
            INSERT INTO gmail_sync_state (
                google_account_id, sync_status, created_at, updated_at
            ) VALUES (?, 'idle', ?, ?)
            ON CONFLICT(google_account_id) DO NOTHING
            """,
            (account_id, now, now),
        )

    def get_connection_by_alias(self, alias: str) -> sqlite3.Row | None:
        return self.fetchone(
            "SELECT * FROM google_connections WHERE account_alias = ?",
            (alias,),
        )

    def get_connection_by_email(self, email: str) -> sqlite3.Row | None:
        return self.fetchone(
            "SELECT * FROM google_connections WHERE lower(email) = lower(?)",
            (email,),
        )

    def get_connection(self, account_id: str) -> sqlite3.Row | None:
        return self.fetchone(
            "SELECT * FROM google_connections WHERE id = ?",
            (account_id,),
        )

    def mark_reconnect_required(self, account_id: str, error: str) -> None:
        self.execute(
            """
            UPDATE google_connections
            SET reconnect_required = 1,
                last_auth_error = ?,
                status = 'needs_reauth',
                updated_at = ?
            WHERE id = ?
            """,
            (error[:500], utc_now_iso(), account_id),
        )

    # --- locks -----------------------------------------------------------

    def try_acquire_lock(
        self, lock_key: str, holder: str, ttl_seconds: int = 600
    ) -> bool:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        now_s = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        exp_s = expires.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT holder, expires_at FROM account_locks WHERE lock_key = ?",
                (lock_key,),
            ).fetchone()
            if row is not None:
                exp = _parse_iso(row["expires_at"])
                if exp and exp > now and row["holder"] != holder:
                    return False
            conn.execute(
                """
                INSERT INTO account_locks(lock_key, holder, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lock_key) DO UPDATE SET
                    holder = excluded.holder,
                    acquired_at = excluded.acquired_at,
                    expires_at = excluded.expires_at
                """,
                (lock_key, holder, now_s, exp_s),
            )
        return True

    def release_lock(self, lock_key: str, holder: str) -> None:
        self.execute(
            "DELETE FROM account_locks WHERE lock_key = ? AND holder = ?",
            (lock_key, holder),
        )

    @contextmanager
    def account_lock(
        self, lock_key: str, holder: str, ttl_seconds: int = 600
    ) -> Iterator[bool]:
        acquired = self.try_acquire_lock(lock_key, holder, ttl_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_lock(lock_key, holder)

    # --- jobs ------------------------------------------------------------

    def enqueue_job(
        self,
        *,
        job_type: str,
        google_account_id: str | None,
        dedupe_key: str | None = None,
        payload: dict[str, Any] | None = None,
        run_after: str | None = None,
        max_attempts: int = 8,
    ) -> str | None:
        """Enqueue a job. Returns job id, or None if an active dedupe exists."""
        job_id = str(uuid.uuid4())
        now = utc_now_iso()
        try:
            with self.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO sync_jobs (
                        id, job_type, google_account_id, dedupe_key, status,
                        attempts, max_attempts, run_after, payload_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_type,
                        google_account_id,
                        dedupe_key,
                        max_attempts,
                        run_after or now,
                        json.dumps(payload or {}),
                        now,
                        now,
                    ),
                )
            return job_id
        except sqlite3.IntegrityError:
            return None

    def claim_due_jobs(self, limit: int = 10) -> list[sqlite3.Row]:
        now = utc_now_iso()
        claimed: list[sqlite3.Row] = []
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sync_jobs
                WHERE status = 'pending' AND run_after <= ?
                ORDER BY run_after ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE sync_jobs
                    SET status = 'running',
                        attempts = attempts + 1,
                        started_at = ?,
                        updated_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (now, now, row["id"]),
                )
                if conn.execute(
                    "SELECT changes()"
                ).fetchone()[0]:
                    claimed.append(
                        conn.execute(
                            "SELECT * FROM sync_jobs WHERE id = ?", (row["id"],)
                        ).fetchone()
                    )
        return claimed

    def complete_job(self, job_id: str) -> None:
        now = utc_now_iso()
        self.execute(
            """
            UPDATE sync_jobs
            SET status = 'completed', completed_at = ?, updated_at = ?,
                last_error = NULL, last_error_category = NULL
            WHERE id = ?
            """,
            (now, now, job_id),
        )

    def fail_job(
        self,
        job_id: str,
        *,
        error: str,
        category: str,
        retry: bool,
        delay_seconds: float = 0,
    ) -> None:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        row = self.fetchone("SELECT * FROM sync_jobs WHERE id = ?", (job_id,))
        if row is None:
            return
        if retry and row["attempts"] < row["max_attempts"]:
            run_after = (
                now_dt + timedelta(seconds=delay_seconds)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            self.execute(
                """
                UPDATE sync_jobs
                SET status = 'pending',
                    run_after = ?,
                    last_error = ?,
                    last_error_category = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (run_after, error[:500], category, now, job_id),
            )
        else:
            self.execute(
                """
                UPDATE sync_jobs
                SET status = 'failed',
                    last_error = ?,
                    last_error_category = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (error[:500], category, now, now, job_id),
            )
        self.record_error(
            google_account_id=row["google_account_id"],
            job_id=job_id,
            category=category,
            message=error,
        )

    # --- outbox ----------------------------------------------------------

    def enqueue_outbox(
        self,
        *,
        operation: str,
        google_account_id: str,
        internal_task_id: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 8,
    ) -> str:
        outbox_id = str(uuid.uuid4())
        now = utc_now_iso()
        existing = self.fetchone(
            """
            SELECT id, status FROM sync_outbox
            WHERE operation = ? AND internal_task_id = ? AND google_account_id = ?
            """,
            (operation, internal_task_id, google_account_id),
        )
        if existing is not None:
            if existing["status"] in {"pending", "running", "failed"}:
                self.execute(
                    """
                    UPDATE sync_outbox
                    SET status = 'pending',
                        run_after = ?,
                        payload_json = ?,
                        updated_at = ?,
                        last_error = NULL,
                        last_error_category = NULL
                    WHERE id = ?
                    """,
                    (
                        now,
                        json.dumps(payload or {}),
                        now,
                        existing["id"],
                    ),
                )
                return str(existing["id"])
            # already completed — return existing id (idempotent)
            return str(existing["id"])
        self.execute(
            """
            INSERT INTO sync_outbox (
                id, operation, google_account_id, internal_task_id, status,
                attempts, max_attempts, run_after, payload_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?)
            """,
            (
                outbox_id,
                operation,
                google_account_id,
                internal_task_id,
                max_attempts,
                now,
                json.dumps(payload or {}),
                now,
                now,
            ),
        )
        return outbox_id

    def claim_due_outbox(self, limit: int = 20) -> list[sqlite3.Row]:
        now = utc_now_iso()
        claimed: list[sqlite3.Row] = []
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sync_outbox
                WHERE status IN ('pending', 'failed') AND run_after <= ?
                ORDER BY run_after ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE sync_outbox
                    SET status = 'running',
                        attempts = attempts + 1,
                        updated_at = ?
                    WHERE id = ? AND status IN ('pending', 'failed')
                    """,
                    (now, row["id"]),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    claimed.append(
                        conn.execute(
                            "SELECT * FROM sync_outbox WHERE id = ?",
                            (row["id"],),
                        ).fetchone()
                    )
        return claimed

    def complete_outbox(self, outbox_id: str) -> None:
        now = utc_now_iso()
        self.execute(
            """
            UPDATE sync_outbox
            SET status = 'completed', completed_at = ?, updated_at = ?,
                last_error = NULL, last_error_category = NULL
            WHERE id = ?
            """,
            (now, now, outbox_id),
        )

    def fail_outbox(
        self,
        outbox_id: str,
        *,
        error: str,
        category: str,
        retry: bool,
        delay_seconds: float = 0,
    ) -> None:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        row = self.fetchone("SELECT * FROM sync_outbox WHERE id = ?", (outbox_id,))
        if row is None:
            return
        if retry and row["attempts"] < row["max_attempts"]:
            run_after = (
                now_dt + timedelta(seconds=delay_seconds)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            status = "pending"
        else:
            run_after = now
            status = "failed"
        self.execute(
            """
            UPDATE sync_outbox
            SET status = ?,
                run_after = ?,
                last_error = ?,
                last_error_category = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, run_after, error[:500], category, now, outbox_id),
        )
        self.record_error(
            google_account_id=row["google_account_id"],
            outbox_id=outbox_id,
            category=category,
            message=error,
        )

    def record_error(
        self,
        *,
        category: str,
        message: str,
        google_account_id: str | None = None,
        job_id: str | None = None,
        outbox_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO sync_errors (
                google_account_id, job_id, outbox_id, error_category,
                error_message, context_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                google_account_id,
                job_id,
                outbox_id,
                category,
                message[:1000],
                json.dumps(context or {}),
                utc_now_iso(),
            ),
        )
