"""Thin Google Tasks API helpers."""

from __future__ import annotations

from typing import Any, Iterator


class TasksApiClient:
    def __init__(self, service: Any):
        self.service = service

    def list_task_lists(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"maxResults": page_size}
            if page_token:
                kwargs["pageToken"] = page_token
            response = self.service.tasklists().list(**kwargs).execute()
            items.extend(response.get("items") or [])
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def create_task_list(self, title: str) -> dict[str, Any]:
        return self.service.tasklists().insert(body={"title": title}).execute()

    def list_tasks(
        self,
        *,
        tasklist: str,
        updated_min: str | None = None,
        page_token: str | None = None,
        page_size: int = 100,
        show_completed: bool = True,
        show_hidden: bool = True,
        show_deleted: bool = True,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "tasklist": tasklist,
            "maxResults": page_size,
            "showCompleted": show_completed,
            "showHidden": show_hidden,
            "showDeleted": show_deleted,
        }
        if updated_min:
            kwargs["updatedMin"] = updated_min
        if page_token:
            kwargs["pageToken"] = page_token
        return self.service.tasks().list(**kwargs).execute()

    def iter_tasks(
        self,
        *,
        tasklist: str,
        updated_min: str | None = None,
        page_size: int = 100,
    ) -> Iterator[dict[str, Any]]:
        page_token: str | None = None
        while True:
            response = self.list_tasks(
                tasklist=tasklist,
                updated_min=updated_min,
                page_token=page_token,
                page_size=page_size,
            )
            for item in response.get("items") or []:
                yield item
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def insert_task(self, *, tasklist: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.service.tasks().insert(tasklist=tasklist, body=body).execute()

    def patch_task(
        self, *, tasklist: str, task_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return (
            self.service.tasks()
            .patch(tasklist=tasklist, task=task_id, body=body)
            .execute()
        )

    def get_task(self, *, tasklist: str, task_id: str) -> dict[str, Any]:
        return self.service.tasks().get(tasklist=tasklist, task=task_id).execute()
