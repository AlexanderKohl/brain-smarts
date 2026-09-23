"""Gmail watch renewal and Pub/Sub pull notification handling."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import SyncConfig
from .db import Database
from .errors import classify_google_error, safe_error_message
from .gmail_sync import GmailSyncService, decode_pubsub_push_data
from .observability import emit_event, utc_now_iso


PubsubPuller = Callable[[str, int], list[dict[str, Any]]]
PubsubAcker = Callable[[str, list[str]], None]


class GmailWatchService:
    """Renew watches and pull Pub/Sub notifications into sync jobs."""

    def __init__(
        self,
        db: Database,
        config: SyncConfig,
        gmail_sync: GmailSyncService,
        *,
        puller: PubsubPuller | None = None,
        acker: PubsubAcker | None = None,
    ):
        self.db = db
        self.config = config
        self.gmail_sync = gmail_sync
        self.puller = puller
        self.acker = acker

    def renew_due_watches(self) -> list[dict[str, Any]]:
        if not self.config.gmail_local_sync_enabled:
            return []
        if not self.config.gmail_pubsub_topic:
            return []
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        renew_before = now + timedelta(hours=12)
        rows = self.db.fetchall(
            """
            SELECT s.*, c.account_alias, c.reconnect_required
            FROM gmail_sync_state s
            JOIN google_connections c ON c.id = s.google_account_id
            WHERE c.reconnect_required = 0 AND c.status = 'active'
            """
        )
        for row in rows:
            should = False
            if not row["watch_expiration"]:
                should = True
            else:
                exp = datetime.fromisoformat(
                    row["watch_expiration"].replace("Z", "+00:00")
                )
                if exp <= renew_before:
                    should = True
            last = row["last_watch_renewed_at"]
            if last:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                age = (now - last_dt).total_seconds()
                if age >= self.config.gmail_watch_renewal_interval:
                    should = True
            if not should:
                continue
            try:
                result = self.gmail_sync.renew_watch(row["google_account_id"])
                results.append(
                    {
                        "account_id": row["google_account_id"],
                        "ok": True,
                        **result,
                    }
                )
            except Exception as exc:
                sync_exc = classify_google_error(exc)
                emit_event(
                    "gmail_watch_renew_failed",
                    account_id=row["google_account_id"],
                    error_category=sync_exc.category.value,
                    error=safe_error_message(exc),
                )
                results.append(
                    {
                        "account_id": row["google_account_id"],
                        "ok": False,
                        "error": safe_error_message(exc),
                    }
                )
        return results

    def process_pubsub_notification(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a decoded Pub/Sub message body.

        Accepts either:
        - Gmail notification dict: {emailAddress, historyId}
        - Full Pub/Sub push envelope with message.data
        """
        data = payload
        if "message" in payload and isinstance(payload["message"], dict):
            msg = payload["message"]
            raw_data = msg.get("data")
            if raw_data:
                data = decode_pubsub_push_data(raw_data)
        email_address = data.get("emailAddress") or data.get("email")
        history_id = data.get("historyId")
        if history_id is not None:
            history_id = str(history_id)
        if not email_address:
            return {"ok": False, "error": "missing_emailAddress"}
        conn = self.db.get_connection_by_email(str(email_address))
        if conn is None:
            emit_event(
                "gmail_pubsub_unknown_account",
                email=str(email_address),
            )
            return {"ok": False, "error": "unknown_account", "email": email_address}
        job_id = self.gmail_sync.record_push_history(conn["id"], history_id)
        return {
            "ok": True,
            "account_id": conn["id"],
            "email": email_address,
            "history_id": history_id,
            "job_id": job_id,
            "coalesced": job_id is None,
        }

    def pull_and_enqueue(self, max_messages: int = 10) -> list[dict[str, Any]]:
        if not self.config.gmail_local_sync_enabled:
            return []
        if not self.config.pubsub_configured:
            return []
        if self.puller is None:
            self.puller = default_pubsub_puller
        if self.acker is None:
            self.acker = default_pubsub_acker

        messages = self.puller(
            self.config.gmail_pubsub_subscription, max_messages
        )
        results: list[dict[str, Any]] = []
        ack_ids: list[str] = []
        for msg in messages:
            ack_id = msg.get("ackId")
            try:
                data_b64 = msg.get("data") or ""
                if isinstance(data_b64, bytes):
                    data_b64 = base64.urlsafe_b64encode(data_b64).decode("ascii")
                payload = decode_pubsub_push_data(data_b64) if data_b64 else {}
                result = self.process_pubsub_notification(payload)
                results.append(result)
                if ack_id:
                    ack_ids.append(ack_id)
            except Exception as exc:
                emit_event(
                    "gmail_pubsub_message_failed",
                    error=safe_error_message(exc),
                )
                # Still ack malformed messages to avoid poison loops.
                if ack_id:
                    ack_ids.append(ack_id)
                results.append({"ok": False, "error": safe_error_message(exc)})
        if ack_ids:
            self.acker(self.config.gmail_pubsub_subscription, ack_ids)
        return results

    def reconcile_stale_accounts(self) -> list[str]:
        if not self.config.gmail_local_sync_enabled:
            return []
        now = datetime.now(timezone.utc)
        enqueued: list[str] = []
        rows = self.db.fetchall(
            """
            SELECT s.*, c.reconnect_required
            FROM gmail_sync_state s
            JOIN google_connections c ON c.id = s.google_account_id
            WHERE c.reconnect_required = 0
              AND s.initial_sync_completed_at IS NOT NULL
            """
        )
        for row in rows:
            last = row["last_successful_sync_at"] or row["last_reconciliation_at"]
            if last:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if (now - last_dt).total_seconds() < self.config.gmail_reconciliation_interval:
                    continue
            job_id = self.gmail_sync.enqueue_reconciliation(row["google_account_id"])
            self.db.execute(
                """
                UPDATE gmail_sync_state
                SET last_reconciliation_at = ?, updated_at = ?
                WHERE google_account_id = ?
                """,
                (utc_now_iso(), utc_now_iso(), row["google_account_id"]),
            )
            if job_id:
                enqueued.append(row["google_account_id"])
        return enqueued


def default_pubsub_puller(subscription: str, max_messages: int) -> list[dict[str, Any]]:
    """Pull messages using google-cloud-pubsub if installed; else empty."""
    try:
        from google.cloud import pubsub_v1  # type: ignore
    except ImportError:
        emit_event(
            "gmail_pubsub_pull_unavailable",
            reason="google-cloud-pubsub not installed",
        )
        return []
    subscriber = pubsub_v1.SubscriberClient()
    response = subscriber.pull(
        request={
            "subscription": subscription,
            "max_messages": max_messages,
            "return_immediately": True,
        },
        timeout=30,
    )
    out: list[dict[str, Any]] = []
    for received in response.received_messages:
        data = received.message.data
        out.append(
            {
                "ackId": received.ack_id,
                "data": base64.urlsafe_b64encode(data).decode("ascii"),
                "messageId": received.message.message_id,
            }
        )
    return out


def default_pubsub_acker(subscription: str, ack_ids: list[str]) -> None:
    if not ack_ids:
        return
    try:
        from google.cloud import pubsub_v1  # type: ignore
    except ImportError:
        return
    subscriber = pubsub_v1.SubscriberClient()
    subscriber.acknowledge(
        request={"subscription": subscription, "ack_ids": ack_ids}
    )
