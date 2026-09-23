"""Provider interfaces so Google-specific behaviour stays behind adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EmailProvider(Protocol):
    def start_initial_sync(self, account_id: str) -> None: ...

    def process_incremental_sync(self, account_id: str) -> None: ...

    def renew_watch(self, account_id: str) -> dict[str, Any]: ...

    def fetch_message_body(
        self, account_id: str, message_id: str
    ) -> dict[str, Any]: ...


@runtime_checkable
class TaskProvider(Protocol):
    def ensure_task_list(self, account_id: str) -> str: ...

    def create_external_task(self, internal_task_id: str) -> None: ...

    def update_external_task(self, internal_task_id: str) -> None: ...

    def poll_external_changes(self, account_id: str) -> None: ...
