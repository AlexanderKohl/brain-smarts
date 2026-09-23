"""Gmail local sync unit tests."""

from __future__ import annotations

import base64
import json
import sys
import threading
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from google_sync.errors import ErrorCategory, SyncError
from google_sync.gmail_sync import decode_pubsub_push_data
from google_sync.observability import emit_event
from google_sync.tests.fakes import (
    FakeGmailApi,
    FakeHttpError,
    encode_pubsub_data,
    make_message,
)
from google_sync.tests.helpers import ACCOUNT_ID, EMAIL, SyncTestCase


class GmailSyncTests(SyncTestCase):
    def test_initial_sync_uses_one_year_query(self) -> None:
        fake = FakeGmailApi()
        fake.list_pages["newer_than:1y"] = [[{"id": "m1", "threadId": "t1"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        fake.messages["m1"] = make_message("m1")
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        result = gmail_sync.start_initial_sync(ACCOUNT_ID)
        self.assertIn("newer_than:1y", fake.list_queries)
        self.assertEqual(result["messages_added"], 1)
        self.assertFalse(result.get("skipped"))

    def test_initial_sync_handles_pagination(self) -> None:
        fake = FakeGmailApi()
        fake.list_pages["newer_than:1y"] = [
            [{"id": "m1", "threadId": "t1"}],
            [{"id": "m2", "threadId": "t2"}],
        ]
        fake.list_pages["is:starred OR is:important"] = [[]]
        fake.messages["m1"] = make_message("m1", thread_id="t1")
        fake.messages["m2"] = make_message("m2", thread_id="t2", subject="Two")
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        result = gmail_sync.start_initial_sync(ACCOUNT_ID)
        self.assertEqual(result["messages_added"], 2)
        self.assertGreaterEqual(result["page_count"], 2)

    def test_metadata_stored_without_attachments_download(self) -> None:
        fake = FakeGmailApi()
        fake.list_pages["newer_than:1y"] = [
            [{"id": "m1", "threadId": "t1"}]
        ]
        fake.list_pages["is:starred OR is:important"] = [[]]
        fake.messages["m1"] = make_message("m1", with_attachment=True)
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        self.assertEqual(fake.full_calls, [])
        meta = email_service.get_email_metadata(ACCOUNT_ID, "m1")
        self.assertTrue(meta["data"]["hasAttachments"])
        atts = email_service.get_email_attachments(ACCOUNT_ID, "m1")
        self.assertEqual(len(atts["data"]), 1)
        self.assertEqual(atts["data"][0]["filename"], "file.pdf")

    def test_duplicate_messages_upserted(self) -> None:
        fake = FakeGmailApi()
        fake.list_pages["newer_than:1y"] = [
            [{"id": "m1", "threadId": "t1"}]
        ]
        fake.list_pages["is:starred OR is:important"] = [
            [{"id": "m1", "threadId": "t1"}]
        ]
        fake.messages["m1"] = make_message("m1")
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        count = self.db.fetchone(
            "SELECT COUNT(*) AS n FROM gmail_messages WHERE google_account_id = ?",
            (ACCOUNT_ID,),
        )["n"]
        self.assertEqual(count, 1)

    def test_pubsub_notification_decoded(self) -> None:
        payload = {"emailAddress": EMAIL, "historyId": "555"}
        encoded = encode_pubsub_data(payload)
        decoded = decode_pubsub_push_data(encoded)
        self.assertEqual(decoded["emailAddress"], EMAIL)
        self.assertEqual(str(decoded["historyId"]), "555")

    def test_duplicate_notifications_do_not_duplicate_work(self) -> None:
        fake = FakeGmailApi()
        gmail_sync, _, watch = self.build_gmail_stack(fake)
        # Mark initial complete so incremental is enqueued
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET initial_sync_completed_at = '2026-08-01T00:00:00Z',
                last_history_id = '100'
            WHERE google_account_id = ?
            """,
            (ACCOUNT_ID,),
        )
        r1 = watch.process_pubsub_notification(
            {"emailAddress": EMAIL, "historyId": "101"}
        )
        r2 = watch.process_pubsub_notification(
            {"emailAddress": EMAIL, "historyId": "102"}
        )
        self.assertTrue(r1["ok"])
        self.assertIsNotNone(r1["job_id"])
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["coalesced"])
        self.assertIsNone(r2["job_id"])
        pending = self.db.fetchone(
            """
            SELECT COUNT(*) AS n FROM sync_jobs
            WHERE dedupe_key = ? AND status = 'pending'
            """,
            (f"gmail_incremental:{ACCOUNT_ID}",),
        )["n"]
        self.assertEqual(pending, 1)

    def test_incremental_history_pagination(self) -> None:
        fake = FakeGmailApi()
        fake.messages["m2"] = make_message("m2", history_id="120")
        fake.history_pages = [
            {
                "historyId": "110",
                "history": [
                    {
                        "id": "110",
                        "messagesAdded": [
                            {"message": {"id": "m2", "threadId": "t2"}}
                        ],
                    }
                ],
            },
            {
                "historyId": "120",
                "history": [
                    {
                        "id": "120",
                        "labelsAdded": [
                            {
                                "message": {"id": "m2"},
                                "labelIds": ["STARRED"],
                            }
                        ],
                    }
                ],
            },
        ]
        # Seed message m2 absence then sync
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET initial_sync_completed_at = '2026-08-01T00:00:00Z',
                last_history_id = '100'
            WHERE google_account_id = ?
            """,
            (ACCOUNT_ID,),
        )
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        result = gmail_sync.process_incremental_sync(ACCOUNT_ID)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["messages_added"], 1)
        meta = email_service.get_email_metadata(ACCOUNT_ID, "m2")
        self.assertTrue(meta["data"]["isStarred"])

    def test_label_changes_update_local_state(self) -> None:
        fake = FakeGmailApi()
        fake.messages["m1"] = make_message("m1", labels=["INBOX", "UNREAD"])
        fake.list_pages["newer_than:1y"] = [[{"id": "m1", "threadId": "t1"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        fake.history_pages = [
            {
                "historyId": "150",
                "history": [
                    {
                        "id": "150",
                        "labelsRemoved": [
                            {"message": {"id": "m1"}, "labelIds": ["UNREAD"]}
                        ],
                        "labelsAdded": [
                            {"message": {"id": "m1"}, "labelIds": ["STARRED"]}
                        ],
                    }
                ],
            }
        ]
        gmail_sync.process_incremental_sync(ACCOUNT_ID)
        meta = email_service.get_email_metadata(ACCOUNT_ID, "m1")
        self.assertFalse(meta["data"]["isUnread"])
        self.assertTrue(meta["data"]["isStarred"])

    def test_deleted_messages_handled(self) -> None:
        fake = FakeGmailApi()
        fake.messages["m1"] = make_message("m1")
        fake.list_pages["newer_than:1y"] = [[{"id": "m1", "threadId": "t1"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        fake.history_pages = [
            {
                "historyId": "160",
                "history": [
                    {
                        "id": "160",
                        "messagesDeleted": [{"message": {"id": "m1"}}],
                    }
                ],
            }
        ]
        gmail_sync.process_incremental_sync(ACCOUNT_ID)
        row = self.db.fetchone(
            """
            SELECT is_deleted FROM gmail_messages
            WHERE gmail_message_id = ?
            """,
            ("m1",),
        )
        self.assertEqual(row["is_deleted"], 1)
        recent = email_service.list_recent_emails(ACCOUNT_ID)
        self.assertEqual(recent["data"], [])

    def test_history_404_triggers_bounded_resync(self) -> None:
        fake = FakeGmailApi()
        fake.history_error = FakeHttpError(404, "historyId startHistoryId not found")
        fake.list_pages["newer_than:1y"] = [[{"id": "m9", "threadId": "t9"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        fake.messages["m9"] = make_message("m9", thread_id="t9")
        self.db.execute(
            """
            UPDATE gmail_sync_state
            SET initial_sync_completed_at = '2026-08-01T00:00:00Z',
                last_history_id = '1'
            WHERE google_account_id = ?
            """,
            (ACCOUNT_ID,),
        )
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        result = gmail_sync.process_incremental_sync(ACCOUNT_ID)
        self.assertIn("queries", result)
        self.assertEqual(result["messages_added"], 1)

    def test_watch_renewal_updates_expiration(self) -> None:
        fake = FakeGmailApi()
        fake.watch_result = {
            "historyId": "999",
            "expiration": "1893456000000",
        }
        gmail_sync, _, _ = self.build_gmail_stack(fake)
        result = gmail_sync.renew_watch(ACCOUNT_ID)
        self.assertIsNotNone(result["watch_expiration"])
        state = self.db.fetchone(
            "SELECT watch_expiration, last_watch_renewed_at FROM gmail_sync_state WHERE google_account_id = ?",
            (ACCOUNT_ID,),
        )
        self.assertEqual(state["watch_expiration"], result["watch_expiration"])
        self.assertIsNotNone(state["last_watch_renewed_at"])

    def test_cached_body_avoids_another_google_request(self) -> None:
        fake = FakeGmailApi()
        fake.messages["m1"] = make_message("m1", body_text="Secret body")
        fake.list_pages["newer_than:1y"] = [[{"id": "m1", "threadId": "t1"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        first = email_service.get_email_body(ACCOUNT_ID, "m1")
        self.assertEqual(first["data"]["text"], "Secret body")
        self.assertFalse(first["data"]["cached"])
        second = email_service.get_email_body(ACCOUNT_ID, "m1")
        self.assertTrue(second["data"]["cached"])
        self.assertEqual(fake.full_calls.count("m1"), 1)

    def test_concurrent_body_requests_deduplicated(self) -> None:
        fake = FakeGmailApi()
        fake.messages["m1"] = make_message("m1", body_text="Once")
        # Ensure metadata row exists
        fake.list_pages["newer_than:1y"] = [[{"id": "m1", "threadId": "t1"}]]
        fake.list_pages["is:starred OR is:important"] = [[]]
        gmail_sync, email_service, _ = self.build_gmail_stack(fake)
        gmail_sync.start_initial_sync(ACCOUNT_ID)
        fake.full_calls.clear()

        results: list[dict] = []

        def worker() -> None:
            results.append(email_service.get_email_body(ACCOUNT_ID, "m1"))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 4)
        self.assertEqual(fake.full_calls.count("m1"), 1)
        self.assertTrue(all(r["data"]["text"] == "Once" for r in results))


if __name__ == "__main__":
    unittest.main()
