"""Google Tasks local mirror unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from google_sync.tests.fakes import FakeGmailApi, FakeTasksApi
from google_sync.tests.helpers import ACCOUNT_ID, SyncTestCase


class TasksSyncTests(SyncTestCase):
    def test_creating_internal_task_creates_one_sync_operation(self) -> None:
        _, task_service = self.build_tasks_stack(FakeTasksApi())
        result = task_service.create_task(
            title="Follow up",
            google_account_id=ACCOUNT_ID,
            description="Notes",
            due_at="2026-08-07T15:30:00+10:00",
        )
        task_id = result["data"]["id"]
        outbox = self.db.fetchall(
            "SELECT * FROM sync_outbox WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["operation"], "create_task")
        self.assertEqual(result["data"]["dueAt"], "2026-08-07T15:30:00+10:00")

    def test_successful_google_creation_stores_mapping(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        created = task_service.create_task(
            title="Do thing", google_account_id=ACCOUNT_ID
        )
        task_id = created["data"]["id"]
        worker, _, _, _ = self.build_worker(FakeGmailApi(), fake)
        worker.drain_outbox()
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["google_task_id"], "gt-1")
        self.assertEqual(len(fake.inserted), 1)
        self.assertIn(task_id, fake.inserted[0]["body"]["notes"])

    def test_retrying_create_does_not_create_duplicate(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        created = task_service.create_task(
            title="Once", google_account_id=ACCOUNT_ID
        )
        task_id = created["data"]["id"]
        tasks_sync.create_external_task(task_id)
        tasks_sync.create_external_task(task_id)
        self.assertEqual(len(fake.inserted), 1)

    def test_poll_uses_updated_min_and_flags(self) -> None:
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
        tasks_sync, _ = self.build_tasks_stack(fake)
        result = tasks_sync.poll_external_changes(ACCOUNT_ID)
        self.assertFalse(result.get("skipped"))
        self.assertTrue(result["showCompleted"])
        self.assertTrue(result["showHidden"])
        self.assertTrue(result["showDeleted"])
        call = fake.list_calls[0]
        self.assertEqual(call["showCompleted"], True)
        self.assertEqual(call["showHidden"], True)
        self.assertEqual(call["showDeleted"], True)
        self.assertIsNotNone(call["updatedMin"])
        # Overlap of 180s from 10:00:00 → 09:57:00
        self.assertEqual(call["updatedMin"], "2026-08-06T09:57:00Z")

    def test_poll_handles_pagination(self) -> None:
        fake = FakeTasksApi()
        list_id = fake.create_task_list("Portable AI Brain")["id"]
        # page size 1 forces pagination
        from dataclasses import replace

        self.config = replace(self.config, google_tasks_page_size=1)
        tasks_sync, task_service = self.build_tasks_stack(fake)
        t1 = task_service.create_task(title="A", google_account_id=ACCOUNT_ID)[
            "data"
        ]["id"]
        t2 = task_service.create_task(title="B", google_account_id=ACCOUNT_ID)[
            "data"
        ]["id"]
        tasks_sync.create_external_task(t1)
        tasks_sync.create_external_task(t2)
        # Clear list_calls from ensure/create
        fake.list_calls.clear()
        result = tasks_sync.poll_external_changes(ACCOUNT_ID)
        self.assertGreaterEqual(result["page_count"], 2)

    def test_google_completion_marks_internal_completed(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Done soon", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        # Mutate Google task to completed
        for item in fake.tasks[mapping["google_task_list_id"]]:
            if item["id"] == mapping["google_task_id"]:
                item["status"] = "completed"
                item["completed"] = "2026-08-06T12:00:00.000Z"
                item["updated"] = "2026-08-06T12:00:00.000Z"
        result = tasks_sync.poll_external_changes(ACCOUNT_ID)
        self.assertEqual(result["completed_from_google"], 1)
        internal = task_service.get_task(task_id)["data"]
        self.assertEqual(internal["status"], "completed")
        self.assertEqual(internal["completedSource"], "google_tasks")

    def test_google_completion_does_not_create_update_loop(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Loop", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        for item in fake.tasks[mapping["google_task_list_id"]]:
            if item["id"] == mapping["google_task_id"]:
                item["status"] = "completed"
                item["updated"] = "2026-08-06T12:00:00.000Z"
        # Clear pending create outbox
        self.db.execute("UPDATE sync_outbox SET status = 'completed'")
        tasks_sync.poll_external_changes(ACCOUNT_ID)
        pending = self.db.fetchone(
            """
            SELECT COUNT(*) AS n FROM sync_outbox
            WHERE internal_task_id = ? AND status = 'pending'
            """,
            (task_id,),
        )["n"]
        self.assertEqual(pending, 0)
        self.assertEqual(len(fake.patched), 0)

    def test_internal_completion_enqueues_google_update(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Finish", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        self.db.execute("DELETE FROM sync_outbox")
        task_service.complete_task(task_id, source="internal")
        outbox = self.db.fetchall(
            "SELECT * FROM sync_outbox WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["operation"], "complete_task")

    def test_stale_needs_action_does_not_reopen(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Stay done", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        task_service.complete_task(task_id, source="internal")
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        for item in fake.tasks[mapping["google_task_list_id"]]:
            if item["id"] == mapping["google_task_id"]:
                item["status"] = "needsAction"
                item["updated"] = "2026-08-06T13:00:00.000Z"
        tasks_sync.poll_external_changes(ACCOUNT_ID)
        internal = task_service.get_task(task_id)["data"]
        self.assertEqual(internal["status"], "completed")

    def test_google_deletion_does_not_delete_internal(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        task_id = task_service.create_task(
            title="Keep me", google_account_id=ACCOUNT_ID
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        for item in fake.tasks[mapping["google_task_list_id"]]:
            if item["id"] == mapping["google_task_id"]:
                item["deleted"] = True
                item["updated"] = "2026-08-06T14:00:00.000Z"
        tasks_sync.poll_external_changes(ACCOUNT_ID)
        internal = task_service.get_task(task_id)["data"]
        self.assertIsNotNone(internal)
        self.assertEqual(internal["status"], "open")
        mapping2 = self.db.fetchone(
            "SELECT mapping_status FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        self.assertEqual(mapping2["mapping_status"], "externally_deleted")

    def test_due_time_not_lost_internally(self) -> None:
        fake = FakeTasksApi()
        tasks_sync, task_service = self.build_tasks_stack(fake)
        due = "2026-08-07T15:30:00+10:00"
        task_id = task_service.create_task(
            title="Timed",
            google_account_id=ACCOUNT_ID,
            due_at=due,
        )["data"]["id"]
        tasks_sync.create_external_task(task_id)
        # Google stores date-only; poll should not wipe internal due_at
        mapping = self.db.fetchone(
            "SELECT * FROM google_task_mappings WHERE internal_task_id = ?",
            (task_id,),
        )
        for item in fake.tasks[mapping["google_task_list_id"]]:
            if item["id"] == mapping["google_task_id"]:
                item["due"] = "2026-08-07T00:00:00.000Z"
                item["updated"] = "2026-08-06T15:00:00.000Z"
        tasks_sync.poll_external_changes(ACCOUNT_ID)
        internal = task_service.get_task(task_id)["data"]
        self.assertEqual(internal["dueAt"], due)

    def test_poll_checkpoint_advances_only_after_success(self) -> None:
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
                "id": "orphan",
                "status": "needsAction",
                "updated": "2026-08-06T11:00:00.000Z",
            }
        ]
        tasks_sync, _ = self.build_tasks_stack(fake)
        # Force failure after list by breaking apply via DB closed mid-flight:
        # Instead: raise on second list page by patching list_tasks.
        original = fake.list_tasks

        def flaky(**kwargs):
            if fake.list_calls:
                raise RuntimeError("transient boom")
            return original(**kwargs)

        # Simpler: poll succeeds with orphan ignored; checkpoint advances to newest
        result = tasks_sync.poll_external_changes(ACCOUNT_ID)
        self.assertEqual(result["checkpoint"], "2026-08-06T11:00:00.000Z")
        state = self.db.fetchone(
            "SELECT last_updated_min, last_successful_poll_at FROM google_task_sync_state WHERE google_account_id = ?",
            (ACCOUNT_ID,),
        )
        self.assertEqual(state["last_updated_min"], "2026-08-06T11:00:00.000Z")
        self.assertIsNotNone(state["last_successful_poll_at"])

        # Failure path: checkpoint unchanged
        self.db.execute(
            """
            UPDATE google_task_sync_state
            SET last_updated_min = '2026-08-06T11:00:00.000Z'
            WHERE google_account_id = ?
            """,
            (ACCOUNT_ID,),
        )

        def boom(**_kwargs):
            raise RuntimeError("503 unavailable")

        fake.list_tasks = boom  # type: ignore[method-assign]
        with self.assertRaises(Exception):
            tasks_sync.poll_external_changes(ACCOUNT_ID)
        state2 = self.db.fetchone(
            "SELECT last_updated_min FROM google_task_sync_state WHERE google_account_id = ?",
            (ACCOUNT_ID,),
        )
        self.assertEqual(state2["last_updated_min"], "2026-08-06T11:00:00.000Z")

    def test_overlapping_polls_prevented(self) -> None:
        fake = FakeTasksApi()
        fake.create_task_list("Portable AI Brain")
        tasks_sync, _ = self.build_tasks_stack(fake)
        acquired = self.db.try_acquire_lock(
            f"google_tasks_poll:{ACCOUNT_ID}", "other", ttl_seconds=60
        )
        self.assertTrue(acquired)
        result = tasks_sync.poll_external_changes(ACCOUNT_ID)
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("reason"), "lock_held")


if __name__ == "__main__":
    unittest.main()
