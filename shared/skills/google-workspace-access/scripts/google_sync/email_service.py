"""Local Gmail read service — returns DB data with freshness metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import SyncConfig
from .db import Database
from .gmail_sync import GmailSyncService
from .observability import utc_now_iso


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class EmailService:
    def __init__(
        self,
        db: Database,
        config: SyncConfig,
        gmail_sync: GmailSyncService | None = None,
    ):
        self.db = db
        self.config = config
        self.gmail_sync = gmail_sync

    def _sync_meta(self, account_id: str) -> dict[str, Any]:
        state = self.db.fetchone(
            "SELECT * FROM gmail_sync_state WHERE google_account_id = ?",
            (account_id,),
        )
        last = state["last_successful_sync_at"] if state else None
        in_progress = bool(
            state
            and state["sync_status"]
            in {"initial_syncing", "incremental_syncing"}
        )
        stale = True
        if last:
            age = (
                datetime.now(timezone.utc) - _parse_iso(last)  # type: ignore[operator]
            ).total_seconds()
            stale = age > self.config.gmail_stale_threshold_seconds
        return {
            "source": "local_cache",
            "lastSuccessfulSyncAt": last,
            "isSyncInProgress": in_progress,
            "isStale": stale,
            "syncStatus": state["sync_status"] if state else None,
            "lastSyncError": state["last_sync_error"] if state else None,
        }

    def _row_to_message(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["gmail_message_id"],
            "threadId": row["gmail_thread_id"],
            "historyId": row["history_id"],
            "internalDate": row["internal_date"],
            "from": {
                "name": row["sender_name"],
                "email": row["sender_email"],
            },
            "to": json.loads(row["recipients_json"] or "[]"),
            "cc": json.loads(row["cc_json"] or "[]"),
            "subject": row["subject"],
            "snippet": row["snippet"],
            "labelIds": json.loads(row["label_ids_json"] or "[]"),
            "isUnread": bool(row["is_unread"]),
            "isStarred": bool(row["is_starred"]),
            "isImportant": bool(row["is_important"]),
            "hasAttachments": bool(row["has_attachments"]),
            "sizeEstimate": row["size_estimate"],
            "mimeType": row["mime_type"],
            "bodyCached": bool(row["body_cached"]),
            "lastSyncedAt": row["last_synced_at"],
        }

    def list_recent_emails(
        self,
        account_id: str,
        *,
        limit: int = 50,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        sql = """
            SELECT * FROM gmail_messages
            WHERE google_account_id = ? AND is_deleted = 0
        """
        params: list[Any] = [account_id]
        if unread_only:
            sql += " AND is_unread = 1"
        sql += " ORDER BY internal_date DESC LIMIT ?"
        params.append(limit)
        rows = self.db.fetchall(sql, params)
        return {
            "data": [self._row_to_message(r) for r in rows],
            "sync": self._sync_meta(account_id),
        }

    def search_emails(
        self,
        account_id: str,
        *,
        query: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Simple local search over subject/snippet/from/to fields."""
        q = f"%{query.strip()}%"
        rows = self.db.fetchall(
            """
            SELECT * FROM gmail_messages
            WHERE google_account_id = ?
              AND is_deleted = 0
              AND (
                subject LIKE ?
                OR snippet LIKE ?
                OR sender_email LIKE ?
                OR sender_name LIKE ?
                OR recipients_json LIKE ?
              )
            ORDER BY internal_date DESC
            LIMIT ?
            """,
            (account_id, q, q, q, q, q, limit),
        )
        return {
            "data": [self._row_to_message(r) for r in rows],
            "sync": self._sync_meta(account_id),
            "query": query,
        }

    def get_email_metadata(
        self, account_id: str, message_id: str
    ) -> dict[str, Any]:
        row = self.db.fetchone(
            """
            SELECT * FROM gmail_messages
            WHERE google_account_id = ? AND gmail_message_id = ?
            """,
            (account_id, message_id),
        )
        if row is None:
            return {
                "data": None,
                "sync": self._sync_meta(account_id),
                "error": "not_found",
            }
        return {
            "data": self._row_to_message(row),
            "sync": self._sync_meta(account_id),
        }

    def get_email_thread(
        self, account_id: str, thread_id: str
    ) -> dict[str, Any]:
        thread = self.db.fetchone(
            """
            SELECT * FROM gmail_threads
            WHERE google_account_id = ? AND gmail_thread_id = ?
            """,
            (account_id, thread_id),
        )
        messages = self.db.fetchall(
            """
            SELECT * FROM gmail_messages
            WHERE google_account_id = ?
              AND gmail_thread_id = ?
              AND is_deleted = 0
            ORDER BY internal_date ASC
            """,
            (account_id, thread_id),
        )
        return {
            "data": {
                "threadId": thread_id,
                "subject": thread["subject"] if thread else None,
                "snippet": thread["snippet"] if thread else None,
                "messages": [self._row_to_message(m) for m in messages],
            },
            "sync": self._sync_meta(account_id),
        }

    def get_email_body(
        self, account_id: str, message_id: str, *, include_html: bool = False
    ) -> dict[str, Any]:
        if self.gmail_sync is None:
            cached = self.db.fetchone(
                """
                SELECT text_body, html_body, fetched_at FROM gmail_message_bodies
                WHERE google_account_id = ? AND gmail_message_id = ?
                """,
                (account_id, message_id),
            )
            if cached is None:
                return {
                    "data": None,
                    "sync": self._sync_meta(account_id),
                    "error": "body_not_cached",
                }
            data = {
                "id": message_id,
                "text": cached["text_body"],
                "cached": True,
                "fetchedAt": cached["fetched_at"],
            }
            if include_html:
                data["html"] = cached["html_body"]
            return {"data": data, "sync": self._sync_meta(account_id)}

        body = self.gmail_sync.fetch_message_body(account_id, message_id)
        data = {
            "id": message_id,
            "text": body.get("text"),
            "cached": body.get("cached"),
            "fetchedAt": body.get("fetched_at"),
            "deduped": body.get("deduped", False),
        }
        if include_html:
            data["html"] = body.get("html")
        return {"data": data, "sync": self._sync_meta(account_id)}

    def get_email_attachments(
        self, account_id: str, message_id: str
    ) -> dict[str, Any]:
        rows = self.db.fetchall(
            """
            SELECT gmail_attachment_id, filename, mime_type, size,
                   content_id, is_inline
            FROM gmail_attachments
            WHERE google_account_id = ? AND gmail_message_id = ?
            """,
            (account_id, message_id),
        )
        return {
            "data": [
                {
                    "attachmentId": r["gmail_attachment_id"],
                    "filename": r["filename"],
                    "mimeType": r["mime_type"],
                    "size": r["size"],
                    "contentId": r["content_id"],
                    "isInline": bool(r["is_inline"]),
                }
                for r in rows
            ],
            "sync": self._sync_meta(account_id),
            "note": "Metadata only; bytes are not downloaded until explicitly requested.",
        }

    def get_email_sync_status(self, account_id: str) -> dict[str, Any]:
        state = self.db.fetchone(
            "SELECT * FROM gmail_sync_state WHERE google_account_id = ?",
            (account_id,),
        )
        conn = self.db.get_connection(account_id)
        counts = self.db.fetchone(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_unread = 1 AND is_deleted = 0 THEN 1 ELSE 0 END) AS unread,
                SUM(CASE WHEN body_cached = 1 THEN 1 ELSE 0 END) AS bodies_cached
            FROM gmail_messages
            WHERE google_account_id = ? AND is_deleted = 0
            """,
            (account_id,),
        )
        return {
            "data": {
                "accountId": account_id,
                "accountAlias": conn["account_alias"] if conn else None,
                "email": conn["email"] if conn else None,
                "reconnectRequired": bool(conn["reconnect_required"]) if conn else None,
                "messageCount": counts["total"] if counts else 0,
                "unreadCount": counts["unread"] if counts else 0,
                "bodiesCached": counts["bodies_cached"] if counts else 0,
                "state": dict(state) if state else None,
            },
            "sync": self._sync_meta(account_id),
        }

    def refresh_email_on_demand(self, account_id: str) -> dict[str, Any]:
        job_id = self.db.enqueue_job(
            job_type="gmail_incremental",
            google_account_id=account_id,
            dedupe_key=f"gmail_incremental:{account_id}",
            payload={"trigger": "on_demand", "requested_at": utc_now_iso()},
            max_attempts=self.config.max_job_attempts,
        )
        return {
            "data": {"jobId": job_id, "enqueued": job_id is not None},
            "sync": self._sync_meta(account_id),
        }
