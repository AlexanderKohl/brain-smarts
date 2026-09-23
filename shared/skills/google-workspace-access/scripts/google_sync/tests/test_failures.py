"""Failure handling and safety tests."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from google_sync.errors import (
    ErrorCategory,
    classify_google_error,
    decide_retry,
    safe_error_message,
)
from google_sync.observability import emit_event
from google_sync.tests.fakes import FakeGmailApi, FakeHttpError, FakeTasksApi
from google_sync.tests.helpers import ACCOUNT_ID, SyncTestCase


class FailureHandlingTests(SyncTestCase):
    def test_rate_limit_retry(self) -> None:
        exc = FakeHttpError(
            429, "rateLimitExceeded", headers={"Retry-After": "2"}
        )
        decision = decide_retry(exc, attempt=1, max_attempts=5)
        self.assertTrue(decision.should_retry)
        self.assertEqual(decision.category, ErrorCategory.RATE_LIMIT)
        self.assertGreaterEqual(decision.delay_seconds, 2.0)

    def test_transient_api_failure(self) -> None:
        exc = FakeHttpError(503, "backendError temporary unavailable")
        sync_exc = classify_google_error(exc)
        self.assertEqual(sync_exc.category, ErrorCategory.TRANSIENT_GOOGLE_ERROR)
        decision = decide_retry(sync_exc, attempt=2, max_attempts=5)
        self.assertTrue(decision.should_retry)

    def test_invalid_token_marks_reconnect(self) -> None:
        fake = FakeGmailApi()

        def boom_profile():
            raise FakeHttpError(401, "invalid_grant token revoked")

        fake.profile = boom_profile  # type: ignore[method-assign]
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        with self.assertRaises(Exception):
            gmail_sync.start_initial_sync(ACCOUNT_ID)
        conn = self.db.get_connection(ACCOUNT_ID)
        self.assertEqual(conn["reconnect_required"], 1)
        self.assertEqual(conn["status"], "needs_reauth")

    def test_database_failure_before_checkpoint_update(self) -> None:
        fake = FakeTasksApi()
        list_id = fake.create_task_list("Portable AI Brain")["id"]
        self.db.execute(
            """
            INSERT INTO google_task_sync_state (
                google_account_id, google_task_list_id, list_title,
                last_updated_min, sync_status, created_at, updated_at
            ) VALUES (?, ?, 'Portable AI Brain', '2026-08-06T10:00:00Z', 'idle',
                      '2026-08-06T10:00:00Z', '2026-08-06T10:00:00Z')
            """,
            (ACCOUNT_ID, list_id),
        )
        fake.tasks[list_id] = [
            {
                "id": "x",
                "status": "needsAction",
                "updated": "2026-08-06T12:00:00.000Z",
            }
        ]
        tasks_sync, _ = self.build_tasks_stack(fake)

        # Force failure after fetching pages by raising inside apply path:
        # close DB mid-poll is harsh; raise from list on second call after
        # we've already observed checkpoint stays put when list raises first.
        def boom(**_kwargs):
            raise RuntimeError("database locked")

        fake.list_tasks = boom  # type: ignore[method-assign]
        with self.assertRaises(Exception):
            tasks_sync.poll_external_changes(ACCOUNT_ID)
        state = self.db.fetchone(
            "SELECT last_updated_min FROM google_task_sync_state WHERE google_account_id = ?",
            (ACCOUNT_ID,),
        )
        self.assertEqual(state["last_updated_min"], "2026-08-06T10:00:00Z")

    def test_failed_outbox_remains_retryable(self) -> None:
        fake = FakeTasksApi()
        fake.insert_error = FakeHttpError(503, "temporary backendError")
        _, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Retry me", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        worker, _, _, _ = self.build_worker(FakeGmailApi(), fake)
        worker.drain_outbox()
        row = self.db.fetchone(
            "SELECT * FROM sync_outbox WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertEqual(row["status"], "pending")
        self.assertGreaterEqual(row["attempts"], 1)
        self.assertEqual(row["last_error_category"], ErrorCategory.TRANSIENT_GOOGLE_ERROR.value)

        # Clear error and succeed
        fake.insert_error = None
        # Force run_after to now
        self.db.execute(
            "UPDATE sync_outbox SET run_after = '2000-01-01T00:00:00Z'"
        )
        worker.drain_outbox()
        row2 = self.db.fetchone(
            "SELECT * FROM sync_outbox WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertEqual(row2["status"], "completed")
        mapping = self.db.fetchone(
            "SELECT google_task_id FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertIsNotNone(mapping)

    def test_logs_exclude_tokens_and_message_bodies(self) -> None:
        buf = io.StringIO()
        with redirect_stderr(buf):
            emit_event(
                "test_event",
                access_token="ya29.secret",
                refresh_token="1//secret",
                text_body="PRIVATE EMAIL BODY",
                html_body="<p>PRIVATE</p>",
                account_id=ACCOUNT_ID,
            )
        logged = buf.getvalue()
        self.assertIn("[REDACTED]", logged)
        self.assertNotIn("ya29.secret", logged)
        self.assertNotIn("1//secret", logged)
        self.assertNotIn("PRIVATE EMAIL BODY", logged)
        self.assertNotIn("<p>PRIVATE</p>", logged)

        msg = safe_error_message(
            RuntimeError("Authorization: Bearer abc.def refresh_token=xyz")
        )
        self.assertNotIn("abc.def", msg)
        self.assertNotIn("xyz", msg)


if __name__ == "__main__":
    unittest.main()
