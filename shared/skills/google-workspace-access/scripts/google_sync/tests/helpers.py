"""Shared test helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from google_sync.config import SyncConfig
from google_sync.db import Database
from google_sync.email_service import EmailService
from google_sync.gmail_sync import GmailSyncService
from google_sync.gmail_watch import GmailWatchService
from google_sync.task_service import TaskService
from google_sync.tasks_sync import TasksSyncService
from google_sync.worker import SyncWorker


ACCOUNT_ID = "google:test"
ALIAS = "test"
EMAIL = "user@example.com"


class SyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "sync.db"
        self.config = replace(
            SyncConfig.from_environment(),
            db_path=self.db_path,
            gmail_local_sync_enabled=True,
            google_tasks_sync_enabled=True,
            gmail_initial_sync_query="newer_than:1y",
            gmail_import_important_history=True,
            gmail_pubsub_topic="projects/p/topics/gmail",
            gmail_pubsub_subscription="projects/p/subscriptions/gmail-pull",
            google_tasks_list_name="Portable AI Brain",
            google_tasks_poll_interval=90,
            google_tasks_updated_min_overlap=180,
            max_job_attempts=3,
        )
        self.db = Database(self.db_path)
        self.db.migrate()
        self.db.upsert_connection(
            account_id=ACCOUNT_ID, alias=ALIAS, email=EMAIL
        )

    def tearDown(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass
        try:
            self._tmpdir.cleanup()
        except Exception:
            pass

    def build_gmail_stack(self, fake_gmail):
        gmail_sync = GmailSyncService(
            self.db, self.config, lambda _aid: fake_gmail
        )
        email_service = EmailService(self.db, self.config, gmail_sync)
        watch = GmailWatchService(self.db, self.config, gmail_sync)
        return gmail_sync, email_service, watch

    def build_tasks_stack(self, fake_tasks):
        tasks_sync = TasksSyncService(
            self.db, self.config, lambda _aid: fake_tasks
        )
        task_service = TaskService(self.db, self.config)
        return tasks_sync, task_service

    def build_worker(self, fake_gmail, fake_tasks, *, puller=None, acker=None):
        gmail_sync = GmailSyncService(
            self.db, self.config, lambda _aid: fake_gmail
        )
        tasks_sync = TasksSyncService(
            self.db, self.config, lambda _aid: fake_tasks
        )
        watch = GmailWatchService(
            self.db,
            self.config,
            gmail_sync,
            puller=puller,
            acker=acker,
        )
        worker = SyncWorker(
            self.db,
            self.config,
            gmail_sync=gmail_sync,
            tasks_sync=tasks_sync,
            watch_service=watch,
        )
        return worker, gmail_sync, tasks_sync, watch
