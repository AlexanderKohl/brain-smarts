"""Gmail initial and incremental synchronisation orchestration."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import SyncConfig
from .db import Database
from .errors import ErrorCategory, SyncError, classify_google_error, safe_error_message
from .gmail_api import GmailApiClient, decode_message_bodies, normalise_metadata
from .gmail_repo import (
    get_cached_body,
    mark_message_deleted,
    store_message_body,
    update_message_labels,
    upsert_message,
)
from .observability import emit_event, timed_event, utc_now_iso


ClientFactory = Callable[[str], GmailApiClient]


class GmailSyncService:
    """Implements EmailProvider-shaped Gmail sync against local SQLite."""

    def __init__(
        self,
        db: Database,
        config: SyncConfig,
        client_factory: ClientFactory,
    ):
        self.db = db
        self.config = config
        self.client_factory = client_factory

    def _client(self, account_id: str) -> GmailApiClient:
        return self.client_factory(account_id)

    def _set_status(self, account_id: str, status: str, error: str | None = None) -> None:
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET sync_status = ?, last_sync_error = ?, updated_at = ?
            WHERE google_account_id = ?
            """,
            (status, error, utc_now_iso(), account_id),
        )

    def ensure_profile_history_seed(self, account_id: str, client: GmailApiClient) -> str:
        profile = client.profile()
        history_id = str(profile.get("historyId") or "")
        if not history_id:
            raise SyncError(
                "Gmail profile missing historyId",
                ErrorCategory.INVALID_REQUEST,
            )
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET last_history_id = COALESCE(last_history_id, ?),
                updated_at = ?
            WHERE google_account_id = ?
            """,
            (history_id, utc_now_iso(), account_id),
        )
        return history_id

    def _queries_for_initial(self) -> list[str]:
        queries = [self.config.gmail_initial_sync_query]
        if self.config.gmail_import_important_history:
            queries.append(self.config.gmail_important_history_query)
        return queries

    def _import_query(
        self,
        account_id: str,
        client: GmailApiClient,
        query: str,
    ) -> tuple[int, int, int]:
        """Import message metadata for one query. Returns (added, updated, pages)."""
        added = 0
        updated = 0
        pages = 0
        page_token: str | None = None
        seen_ids: set[str] = set()
        batch: list[str] = []

        def flush_batch() -> None:
            nonlocal added, updated
            for message_id in batch:
                meta_raw = client.get_metadata(message_id)
                meta = normalise_metadata(meta_raw)
                existing = self.db.fetchone(
                    """
                    SELECT id FROM gmail_messages
                    WHERE google_account_id = ? AND gmail_message_id = ?
                    """,
                    (account_id, message_id),
                )
                upsert_message(self.db, account_id, meta)
                if existing:
                    updated += 1
                else:
                    added += 1
            batch.clear()

        while True:
            response = client.list_message_ids(
                query=query,
                page_size=self.config.gmail_list_page_size,
                page_token=page_token,
            )
            pages += 1
            for item in response.get("messages") or []:
                mid = item["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                batch.append(mid)
                if len(batch) >= self.config.gmail_metadata_batch_size:
                    flush_batch()
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        if batch:
            flush_batch()
        return added, updated, pages

    def start_initial_sync(self, account_id: str) -> dict[str, Any]:
        holder = f"initial:{uuid.uuid4()}"
        lock_key = f"gmail_sync:{account_id}"
        with self.db.account_lock(lock_key, holder, ttl_seconds=3600) as acquired:
            if not acquired:
                emit_event(
                    "gmail_initial_sync_skipped_lock",
                    account_id=account_id,
                )
                return {"skipped": True, "reason": "lock_held"}
            return self._run_initial_sync(account_id)

    def _run_initial_sync(self, account_id: str) -> dict[str, Any]:
        client = self._client(account_id)
        with timed_event(
            "gmail_initial_sync_started",
            "gmail_initial_sync_completed",
            "gmail_sync_failed",
            account_id=account_id,
            sync_kind="initial",
        ) as op:
            self._set_status(account_id, "initial_syncing")
            try:
                history_id = self.ensure_profile_history_seed(account_id, client)
                total_added = 0
                total_updated = 0
                total_pages = 0
                queries = self._queries_for_initial()
                for query in queries:
                    added, updated, pages = self._import_query(
                        account_id, client, query
                    )
                    total_added += added
                    total_updated += updated
                    total_pages += pages
                now = utc_now_iso()
                self.db.execute(
                    """
                    UPDATE gmail_sync_state
                    SET last_history_id = ?,
                        initial_sync_completed_at = ?,
                        last_successful_sync_at = ?,
                        sync_status = 'idle',
                        last_sync_error = NULL,
                        updated_at = ?
                    WHERE google_account_id = ?
                    """,
                    (history_id, now, now, now, account_id),
                )
                result = {
                    "messages_added": total_added,
                    "messages_updated": total_updated,
                    "page_count": total_pages,
                    "checkpoint": history_id,
                    "queries": queries,
                }
                op.complete(**result)
                emit_event(
                    "gmail_messages_added",
                    account_id=account_id,
                    record_count=total_added,
                )
                if total_updated:
                    emit_event(
                        "gmail_messages_updated",
                        account_id=account_id,
                        record_count=total_updated,
                    )
                return result
            except Exception as exc:
                sync_exc = classify_google_error(exc)
                self._handle_auth_failure(account_id, sync_exc)
                self._set_status(
                    account_id, "error", safe_error_message(sync_exc)
                )
                raise

    def process_incremental_sync(self, account_id: str) -> dict[str, Any]:
        holder = f"incremental:{uuid.uuid4()}"
        lock_key = f"gmail_sync:{account_id}"
        with self.db.account_lock(lock_key, holder, ttl_seconds=900) as acquired:
            if not acquired:
                emit_event(
                    "gmail_incremental_sync_skipped_lock",
                    account_id=account_id,
                )
                return {"skipped": True, "reason": "lock_held"}
            return self._run_incremental_sync(account_id)

    def _run_incremental_sync(self, account_id: str) -> dict[str, Any]:
        state = self.db.fetchone(
            "SELECT * FROM gmail_sync_state WHERE google_account_id = ?",
            (account_id,),
        )
        if state is None:
            raise SyncError(
                f"No gmail_sync_state for {account_id}",
                ErrorCategory.DATA_MAPPING,
            )
        if not state["initial_sync_completed_at"]:
            return self._run_initial_sync(account_id)

        start_history = state["last_history_id"]
        if not start_history:
            emit_event(
                "gmail_history_checkpoint_expired",
                account_id=account_id,
                reason="missing_checkpoint",
            )
            return self._run_initial_sync(account_id)

        client = self._client(account_id)
        with timed_event(
            "gmail_incremental_sync_started",
            "gmail_incremental_sync_completed",
            "gmail_sync_failed",
            account_id=account_id,
            sync_kind="incremental",
            checkpoint=start_history,
        ) as op:
            now = utc_now_iso()
            self.db.execute(
                """
                UPDATE gmail_sync_state
                SET sync_status = 'incremental_syncing',
                    last_incremental_sync_started_at = ?,
                    updated_at = ?
                WHERE google_account_id = ?
                """,
                (now, now, account_id),
            )
            try:
                result = self._apply_history(account_id, client, start_history)
                completed = utc_now_iso()
                self.db.execute(
                    """
                    UPDATE gmail_sync_state
                    SET last_history_id = ?,
                        last_incremental_sync_completed_at = ?,
                        last_successful_sync_at = ?,
                        sync_status = 'idle',
                        last_sync_error = NULL,
                        updated_at = ?
                    WHERE google_account_id = ?
                    """,
                    (
                        result["checkpoint"],
                        completed,
                        completed,
                        completed,
                        account_id,
                    ),
                )
                op.complete(**result)
                return result
            except SyncError as exc:
                if exc.category == ErrorCategory.EXPIRED_CHECKPOINT:
                    emit_event(
                        "gmail_history_checkpoint_expired",
                        account_id=account_id,
                        checkpoint=start_history,
                    )
                    return self._run_initial_sync(account_id)
                self._handle_auth_failure(account_id, exc)
                self._set_status(account_id, "error", safe_error_message(exc))
                raise
            except Exception as exc:
                sync_exc = classify_google_error(exc)
                if sync_exc.category == ErrorCategory.EXPIRED_CHECKPOINT:
                    emit_event(
                        "gmail_history_checkpoint_expired",
                        account_id=account_id,
                        checkpoint=start_history,
                    )
                    return self._run_initial_sync(account_id)
                self._handle_auth_failure(account_id, sync_exc)
                self._set_status(
                    account_id, "error", safe_error_message(sync_exc)
                )
                raise

    def _apply_history(
        self,
        account_id: str,
        client: GmailApiClient,
        start_history_id: str,
    ) -> dict[str, Any]:
        page_token: str | None = None
        pages = 0
        added = 0
        updated = 0
        deleted = 0
        label_changes = 0
        newest_history = start_history_id
        messages_to_refresh: set[str] = set()
        labels_to_add: list[tuple[str, list[str]]] = []
        labels_to_remove: list[tuple[str, list[str]]] = []

        while True:
            try:
                response = client.list_history(
                    start_history_id=start_history_id,
                    page_token=page_token,
                    page_size=100,
                )
            except Exception as exc:
                raise classify_google_error(exc) from exc

            pages += 1
            if response.get("historyId") is not None:
                newest_history = str(response["historyId"])

            for record in response.get("history") or []:
                if record.get("id") is not None:
                    newest_history = str(record["id"])
                for item in record.get("messagesAdded") or []:
                    msg = item.get("message") or {}
                    mid = msg.get("id")
                    if mid:
                        messages_to_refresh.add(mid)
                for item in record.get("messagesDeleted") or []:
                    msg = item.get("message") or {}
                    mid = msg.get("id")
                    if mid:
                        mark_message_deleted(self.db, account_id, mid)
                        deleted += 1
                for item in record.get("labelsAdded") or []:
                    msg = item.get("message") or {}
                    mid = msg.get("id")
                    labels = list(item.get("labelIds") or [])
                    if mid and labels:
                        labels_to_add.append((mid, labels))
                for item in record.get("labelsRemoved") or []:
                    msg = item.get("message") or {}
                    mid = msg.get("id")
                    labels = list(item.get("labelIds") or [])
                    if mid and labels:
                        labels_to_remove.append((mid, labels))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Refresh metadata first, then apply label deltas so later label events win.
        for mid in messages_to_refresh:
            existing = self.db.fetchone(
                """
                SELECT id FROM gmail_messages
                WHERE google_account_id = ? AND gmail_message_id = ?
                """,
                (account_id, mid),
            )
            meta = normalise_metadata(client.get_metadata(mid))
            upsert_message(self.db, account_id, meta)
            if existing:
                updated += 1
            else:
                added += 1

        for mid, labels in labels_to_add:
            update_message_labels(self.db, account_id, mid, add=labels)
            label_changes += 1
        for mid, labels in labels_to_remove:
            update_message_labels(self.db, account_id, mid, remove=labels)
            label_changes += 1

        if added:
            emit_event(
                "gmail_messages_added",
                account_id=account_id,
                record_count=added,
            )
        if updated:
            emit_event(
                "gmail_messages_updated",
                account_id=account_id,
                record_count=updated,
            )

        return {
            "messages_added": added,
            "messages_updated": updated,
            "messages_deleted": deleted,
            "label_changes": label_changes,
            "page_count": pages,
            "checkpoint": newest_history,
        }

    def renew_watch(self, account_id: str) -> dict[str, Any]:
        if not self.config.gmail_pubsub_topic:
            return {"skipped": True, "reason": "topic_not_configured"}
        client = self._client(account_id)
        try:
            result = client.watch(topic_name=self.config.gmail_pubsub_topic)
        except Exception as exc:
            sync_exc = classify_google_error(exc)
            self._handle_auth_failure(account_id, sync_exc)
            raise
        expiration_ms = result.get("expiration")
        expiration = None
        if expiration_ms is not None:
            expiration = datetime.fromtimestamp(
                int(expiration_ms) / 1000.0, tz=timezone.utc
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        history_id = (
            str(result["historyId"]) if result.get("historyId") is not None else None
        )
        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET watch_expiration = ?,
                last_history_id = COALESCE(?, last_history_id),
                last_watch_renewed_at = ?,
                updated_at = ?
            WHERE google_account_id = ?
            """,
            (expiration, history_id, now, now, account_id),
        )
        emit_event(
            "gmail_watch_renewed",
            account_id=account_id,
            watch_expiration=expiration,
            checkpoint=history_id,
        )
        return {
            "watch_expiration": expiration,
            "history_id": history_id,
            "raw_expiration_ms": expiration_ms,
        }

    def fetch_message_body(
        self, account_id: str, message_id: str
    ) -> dict[str, Any]:
        cached = get_cached_body(self.db, account_id, message_id)
        if cached is not None:
            return {
                "text": cached["text_body"],
                "html": cached["html_body"],
                "cached": True,
                "fetched_at": cached["fetched_at"],
            }

        holder = f"body:{uuid.uuid4()}"
        # Deduplicate concurrent body downloads via DB lock row.
        if not self._try_body_lock(account_id, message_id, holder):
            # Wait briefly for the other fetcher to finish.
            for _ in range(40):
                time.sleep(0.05)
                cached = get_cached_body(self.db, account_id, message_id)
                if cached is not None:
                    return {
                        "text": cached["text_body"],
                        "html": cached["html_body"],
                        "cached": True,
                        "fetched_at": cached["fetched_at"],
                        "deduped": True,
                    }
            # Lock holder may have failed; steal if expired and fetch.
            self._try_body_lock(account_id, message_id, holder, force_expired=True)

        try:
            # Re-check after acquiring lock.
            cached = get_cached_body(self.db, account_id, message_id)
            if cached is not None:
                return {
                    "text": cached["text_body"],
                    "html": cached["html_body"],
                    "cached": True,
                    "fetched_at": cached["fetched_at"],
                    "deduped": True,
                }
            client = self._client(account_id)
            raw = client.get_full(message_id)
            decoded = decode_message_bodies(raw)
            # Ensure metadata row exists for FK.
            meta = normalise_metadata(raw)
            upsert_message(self.db, account_id, meta)
            store_message_body(
                self.db,
                account_id,
                message_id,
                text_body=decoded["text"],
                html_body=decoded["html"],
                attachments=decoded.get("attachments"),
            )
            return {
                "text": decoded["text"],
                "html": decoded["html"],
                "cached": False,
                "fetched_at": utc_now_iso(),
            }
        finally:
            self._release_body_lock(account_id, message_id, holder)

    def _try_body_lock(
        self,
        account_id: str,
        message_id: str,
        holder: str,
        *,
        force_expired: bool = False,
    ) -> bool:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self.config.body_fetch_lock_ttl_seconds)
        now_s = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        exp_s = expires.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT holder, expires_at FROM body_fetch_locks
                WHERE google_account_id = ? AND gmail_message_id = ?
                """,
                (account_id, message_id),
            ).fetchone()
            if row is not None:
                exp = row["expires_at"]
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if exp_dt > now and row["holder"] != holder and not force_expired:
                    return False
                if exp_dt > now and not force_expired:
                    return False
            conn.execute(
                """
                INSERT INTO body_fetch_locks (
                    google_account_id, gmail_message_id, holder,
                    acquired_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(google_account_id, gmail_message_id) DO UPDATE SET
                    holder = excluded.holder,
                    acquired_at = excluded.acquired_at,
                    expires_at = excluded.expires_at
                """,
                (account_id, message_id, holder, now_s, exp_s),
            )
        return True

    def _release_body_lock(
        self, account_id: str, message_id: str, holder: str
    ) -> None:
        self.db.execute(
            """
            DELETE FROM body_fetch_locks
            WHERE google_account_id = ? AND gmail_message_id = ? AND holder = ?
            """,
            (account_id, message_id, holder),
        )

    def record_push_history(
        self, account_id: str, history_id: str | None
    ) -> str | None:
        """Record a Pub/Sub notification and enqueue coalesced incremental sync."""
        now = utc_now_iso()
        if history_id:
            self.db.execute(
                """
                UPDATE gmail_sync_state
                SET received_history_id = ?, updated_at = ?
                WHERE google_account_id = ?
                """,
                (history_id, now, account_id),
            )
        job_id = self.db.enqueue_job(
            job_type="gmail_incremental",
            google_account_id=account_id,
            dedupe_key=f"gmail_incremental:{account_id}",
            payload={"trigger": "pubsub", "history_id": history_id},
            max_attempts=self.config.max_job_attempts,
        )
        return job_id

    def enqueue_reconciliation(self, account_id: str) -> str | None:
        return self.db.enqueue_job(
            job_type="gmail_incremental",
            google_account_id=account_id,
            dedupe_key=f"gmail_incremental:{account_id}",
            payload={"trigger": "reconciliation"},
            max_attempts=self.config.max_job_attempts,
        )

    def _handle_auth_failure(self, account_id: str, exc: SyncError) -> None:
        if exc.category == ErrorCategory.AUTHENTICATION:
            self.db.mark_reconnect_required(account_id, safe_error_message(exc))
            # Cancel pending sync jobs for this account to avoid hammering.
            self.db.execute(
                """
                UPDATE sync_jobs
                SET status = 'failed',
                    last_error = ?,
                    last_error_category = ?,
                    updated_at = ?
                WHERE google_account_id = ?
                  AND status IN ('pending', 'running')
                  AND job_type LIKE 'gmail_%'
                """,
                (
                    "authentication failure; reconnect required",
                    ErrorCategory.AUTHENTICATION.value,
                    utc_now_iso(),
                    account_id,
                ),
            )


def decode_pubsub_push_data(data_b64: str) -> dict[str, Any]:
    """Decode Gmail Pub/Sub notification data field (base64 JSON)."""
    import base64

    padded = data_b64 + "=" * (-len(data_b64) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))
