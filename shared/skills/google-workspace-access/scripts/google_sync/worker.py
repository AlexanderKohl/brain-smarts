"""Background worker: jobs, outbox, Pub/Sub pull, polls, watch renew."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .config import SyncConfig
from .db import Database
from .errors import classify_google_error, decide_retry, safe_error_message
from .gmail_sync import GmailSyncService
from .gmail_watch import GmailWatchService
from .observability import emit_event, utc_now_iso
from .tasks_sync import TasksSyncService


class SyncWorker:
    def __init__(
        self,
        db: Database,
        config: SyncConfig,
        *,
        gmail_sync: GmailSyncService,
        tasks_sync: TasksSyncService,
        watch_service: GmailWatchService,
    ):
        self.db = db
        self.config = config
        self.gmail_sync = gmail_sync
        self.tasks_sync = tasks_sync
        self.watch_service = watch_service
        self._last_watch_check = 0.0
        self._last_reconcile_check = 0.0
        self._last_tasks_poll: dict[str, float] = {}

    def run_forever(self, *, once: bool = False) -> None:
        emit_event(
            "google_sync_worker_started",
            gmail_enabled=self.config.gmail_local_sync_enabled,
            tasks_enabled=self.config.google_tasks_sync_enabled,
            db_path=str(self.config.db_path),
        )
        while True:
            self.tick()
            if once:
                break
            time.sleep(self.config.worker_loop_sleep_seconds)

    def tick(self) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "jobs": 0,
            "outbox": 0,
            "pubsub": 0,
            "watches": 0,
            "reconcile": 0,
            "task_polls": 0,
        }
        stats["jobs"] = self.drain_jobs()
        stats["outbox"] = self.drain_outbox()
        if self.config.gmail_local_sync_enabled and self.config.pubsub_configured:
            results = self.watch_service.pull_and_enqueue()
            stats["pubsub"] = len(results)
        now = time.monotonic()
        if (
            self.config.gmail_local_sync_enabled
            and now - self._last_watch_check >= 60
        ):
            renewed = self.watch_service.renew_due_watches()
            stats["watches"] = len(renewed)
            self._last_watch_check = now
        if (
            self.config.gmail_local_sync_enabled
            and now - self._last_reconcile_check >= 60
        ):
            enqueued = self.watch_service.reconcile_stale_accounts()
            stats["reconcile"] = len(enqueued)
            self._last_reconcile_check = now
        if self.config.google_tasks_sync_enabled:
            stats["task_polls"] = self.schedule_task_polls()
        return stats

    def drain_jobs(self, limit: int = 10) -> int:
        jobs = self.db.claim_due_jobs(limit=limit)
        for job in jobs:
            self._run_job(job)
        return len(jobs)

    def _run_job(self, job: Any) -> None:
        job_id = job["id"]
        job_type = job["job_type"]
        account_id = job["google_account_id"]
        payload = json.loads(job["payload_json"] or "{}")
        emit_event(
            "sync_job_started",
            job_id=job_id,
            job_type=job_type,
            account_id=account_id,
            attempt=job["attempts"],
        )
        try:
            if job_type == "gmail_initial":
                if not self.config.gmail_local_sync_enabled:
                    self.db.complete_job(job_id)
                    return
                self.gmail_sync.start_initial_sync(account_id)
            elif job_type == "gmail_incremental":
                if not self.config.gmail_local_sync_enabled:
                    self.db.complete_job(job_id)
                    return
                self.gmail_sync.process_incremental_sync(account_id)
            elif job_type == "gmail_watch_renew":
                self.gmail_sync.renew_watch(account_id)
            elif job_type == "google_tasks_poll":
                if not self.config.google_tasks_sync_enabled:
                    self.db.complete_job(job_id)
                    return
                self.tasks_sync.poll_external_changes(account_id)
            elif job_type == "google_tasks_ensure_list":
                self.tasks_sync.ensure_task_list(account_id)
            else:
                raise RuntimeError(f"unknown job type {job_type}")
            self.db.complete_job(job_id)
            emit_event(
                "sync_job_completed",
                job_id=job_id,
                job_type=job_type,
                account_id=account_id,
            )
        except Exception as exc:
            sync_exc = classify_google_error(exc)
            decision = decide_retry(
                sync_exc,
                attempt=job["attempts"],
                max_attempts=job["max_attempts"],
            )
            self.db.fail_job(
                job_id,
                error=safe_error_message(exc),
                category=decision.category.value,
                retry=decision.should_retry,
                delay_seconds=decision.delay_seconds,
            )
            emit_event(
                "sync_job_failed",
                job_id=job_id,
                job_type=job_type,
                account_id=account_id,
                error_category=decision.category.value,
                error=safe_error_message(exc),
                retry=decision.should_retry,
                retry_count=job["attempts"],
            )

    def drain_outbox(self, limit: int = 20) -> int:
        if not self.config.google_tasks_sync_enabled:
            return 0
        items = self.db.claim_due_outbox(limit=limit)
        for item in items:
            self._run_outbox(item)
        return len(items)

    def _run_outbox(self, item: Any) -> None:
        try:
            self.tasks_sync.process_outbox_item(item)
            self.db.complete_outbox(item["id"])
        except Exception as exc:
            sync_exc = classify_google_error(exc)
            decision = decide_retry(
                sync_exc,
                attempt=item["attempts"],
                max_attempts=item["max_attempts"],
            )
            self.db.fail_outbox(
                item["id"],
                error=safe_error_message(exc),
                category=decision.category.value,
                retry=decision.should_retry,
                delay_seconds=decision.delay_seconds,
            )

    def schedule_task_polls(self) -> int:
        now = time.monotonic()
        count = 0
        rows = self.db.fetchall(
            """
            SELECT id FROM google_connections
            WHERE reconnect_required = 0 AND status = 'active'
            """
        )
        for row in rows:
            account_id = row["id"]
            last = self._last_tasks_poll.get(account_id, 0.0)
            if now - last < self.config.google_tasks_poll_interval:
                continue
            job_id = self.db.enqueue_job(
                job_type="google_tasks_poll",
                google_account_id=account_id,
                dedupe_key=f"google_tasks_poll:{account_id}",
                payload={"trigger": "schedule", "at": utc_now_iso()},
                max_attempts=self.config.max_job_attempts,
            )
            self._last_tasks_poll[account_id] = now
            if job_id:
                count += 1
        return count

    def enqueue_backfill(self, account_id: str) -> dict[str, Any]:
        """Enqueue initial Gmail sync, watch renew, ensure list, and first poll."""
        result: dict[str, Any] = {}
        if self.config.gmail_local_sync_enabled:
            result["gmail_initial"] = self.db.enqueue_job(
                job_type="gmail_initial",
                google_account_id=account_id,
                dedupe_key=f"gmail_initial:{account_id}",
                payload={"trigger": "backfill"},
                max_attempts=self.config.max_job_attempts,
            )
            if self.config.gmail_pubsub_topic:
                result["gmail_watch_renew"] = self.db.enqueue_job(
                    job_type="gmail_watch_renew",
                    google_account_id=account_id,
                    dedupe_key=f"gmail_watch_renew:{account_id}",
                    payload={"trigger": "backfill"},
                    max_attempts=self.config.max_job_attempts,
                )
        if self.config.google_tasks_sync_enabled:
            result["google_tasks_ensure_list"] = self.db.enqueue_job(
                job_type="google_tasks_ensure_list",
                google_account_id=account_id,
                dedupe_key=f"google_tasks_ensure_list:{account_id}",
                payload={"trigger": "backfill"},
                max_attempts=self.config.max_job_attempts,
            )
            result["google_tasks_poll"] = self.db.enqueue_job(
                job_type="google_tasks_poll",
                google_account_id=account_id,
                dedupe_key=f"google_tasks_poll:{account_id}",
                payload={"trigger": "backfill"},
                max_attempts=self.config.max_job_attempts,
            )
        return result
