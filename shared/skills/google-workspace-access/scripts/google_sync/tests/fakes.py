"""In-memory fake Gmail / Tasks API clients for unit tests."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any


class FakeHttpError(Exception):
    def __init__(self, status: int, message: str, *, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status
        self.resp = type("Resp", (), {"status": status, "headers": headers or {}})()


@dataclass
class FakeGmailApi:
    profile_history_id: str = "100"
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    list_pages: dict[str, list[list[dict[str, str]]]] = field(default_factory=dict)
    history_pages: list[dict[str, Any]] = field(default_factory=list)
    history_error: Exception | None = None
    watch_result: dict[str, Any] = field(
        default_factory=lambda: {
            "historyId": "200",
            "expiration": "1893456000000",
        }
    )
    metadata_calls: list[str] = field(default_factory=list)
    full_calls: list[str] = field(default_factory=list)
    list_queries: list[str] = field(default_factory=list)

    def profile(self) -> dict[str, Any]:
        return {"emailAddress": "user@example.com", "historyId": self.profile_history_id}

    def list_message_ids(
        self,
        *,
        query: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        self.list_queries.append(query)
        pages = self.list_pages.get(query) or [[]]
        index = int(page_token or "0")
        if index >= len(pages):
            return {"messages": []}
        page = pages[index]
        next_token = str(index + 1) if index + 1 < len(pages) else None
        return {
            "messages": page[:page_size],
            "nextPageToken": next_token,
            "resultSizeEstimate": sum(len(p) for p in pages),
        }

    def get_metadata(self, message_id: str) -> dict[str, Any]:
        self.metadata_calls.append(message_id)
        msg = self.messages[message_id]
        # Strip body data for metadata-style response
        payload = dict(msg.get("payload") or {})
        payload = {
            "mimeType": payload.get("mimeType"),
            "headers": payload.get("headers"),
            "parts": [
                {
                    "filename": p.get("filename"),
                    "mimeType": p.get("mimeType"),
                    "body": {
                        "attachmentId": (p.get("body") or {}).get("attachmentId"),
                        "size": (p.get("body") or {}).get("size"),
                    },
                }
                for p in (payload.get("parts") or [])
                if p.get("filename") or (p.get("body") or {}).get("attachmentId")
            ]
            or None,
        }
        return {
            "id": msg["id"],
            "threadId": msg["threadId"],
            "historyId": msg.get("historyId"),
            "internalDate": msg.get("internalDate"),
            "snippet": msg.get("snippet"),
            "labelIds": msg.get("labelIds"),
            "sizeEstimate": msg.get("sizeEstimate"),
            "payload": payload,
        }

    def get_full(self, message_id: str) -> dict[str, Any]:
        self.full_calls.append(message_id)
        return self.messages[message_id]

    def list_history(
        self,
        *,
        start_history_id: str,
        page_token: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        if self.history_error is not None:
            raise self.history_error
        index = int(page_token or "0")
        if index >= len(self.history_pages):
            return {"historyId": self.profile_history_id, "history": []}
        page = self.history_pages[index]
        next_token = str(index + 1) if index + 1 < len(self.history_pages) else None
        out = dict(page)
        if next_token:
            out["nextPageToken"] = next_token
        return out

    def watch(self, *, topic_name: str, label_ids: list[str] | None = None) -> dict[str, Any]:
        return dict(self.watch_result)

    def stop_watch(self) -> None:
        return None

    def list_labels(self) -> list[dict[str, Any]]:
        return [{"id": "INBOX", "name": "INBOX"}]


@dataclass
class FakeTasksApi:
    lists: list[dict[str, Any]] = field(default_factory=list)
    tasks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    inserted: list[dict[str, Any]] = field(default_factory=list)
    patched: list[dict[str, Any]] = field(default_factory=list)
    list_calls: list[dict[str, Any]] = field(default_factory=list)
    insert_error: Exception | None = None
    next_task_id: int = 1

    def list_task_lists(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        return list(self.lists)

    def create_task_list(self, title: str) -> dict[str, Any]:
        item = {"id": f"list-{len(self.lists)+1}", "title": title}
        self.lists.append(item)
        self.tasks.setdefault(item["id"], [])
        return item

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
        self.list_calls.append(
            {
                "tasklist": tasklist,
                "updatedMin": updated_min,
                "pageToken": page_token,
                "showCompleted": show_completed,
                "showHidden": show_hidden,
                "showDeleted": show_deleted,
                "maxResults": page_size,
            }
        )
        items = list(self.tasks.get(tasklist) or [])
        if updated_min:
            items = [t for t in items if (t.get("updated") or "") >= updated_min]
        # Simple pagination by page_token index
        index = int(page_token or "0")
        start = index * page_size
        chunk = items[start : start + page_size]
        next_token = str(index + 1) if start + page_size < len(items) else None
        out: dict[str, Any] = {"items": chunk}
        if next_token:
            out["nextPageToken"] = next_token
        return out

    def insert_task(self, *, tasklist: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.insert_error is not None:
            raise self.insert_error
        task_id = f"gt-{self.next_task_id}"
        self.next_task_id += 1
        created = {
            "id": task_id,
            "etag": f"etag-{task_id}",
            "title": body.get("title"),
            "notes": body.get("notes"),
            "status": body.get("status", "needsAction"),
            "due": body.get("due"),
            "updated": "2026-08-06T00:00:00.000Z",
            "selfLink": f"https://tasks.example/{task_id}",
            "webViewLink": f"https://tasks.example/view/{task_id}",
        }
        self.tasks.setdefault(tasklist, []).append(created)
        self.inserted.append({"tasklist": tasklist, "body": body, "created": created})
        return created

    def patch_task(
        self, *, tasklist: str, task_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        items = self.tasks.get(tasklist) or []
        for item in items:
            if item["id"] == task_id:
                item.update(body)
                item["etag"] = f"etag-{task_id}-patched"
                item["updated"] = "2026-08-06T01:00:00.000Z"
                self.patched.append({"tasklist": tasklist, "task_id": task_id, "body": body})
                return dict(item)
        raise FakeHttpError(404, "task not found")

    def get_task(self, *, tasklist: str, task_id: str) -> dict[str, Any]:
        for item in self.tasks.get(tasklist) or []:
            if item["id"] == task_id:
                return dict(item)
        raise FakeHttpError(404, "task not found")


def make_message(
    message_id: str,
    *,
    thread_id: str = "t1",
    subject: str = "Hello",
    sender: str = "Ada <ada@example.com>",
    to: str = "me@example.com",
    labels: list[str] | None = None,
    internal_date: str = "1700000000000",
    history_id: str = "10",
    with_attachment: bool = False,
    body_text: str = "Body text",
) -> dict[str, Any]:
    parts = [
        {
            "mimeType": "text/plain",
            "body": {
                "data": base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
            },
        }
    ]
    if with_attachment:
        parts.append(
            {
                "filename": "file.pdf",
                "mimeType": "application/pdf",
                "body": {"attachmentId": "att1", "size": 123},
            }
        )
    return {
        "id": message_id,
        "threadId": thread_id,
        "historyId": history_id,
        "internalDate": internal_date,
        "snippet": subject,
        "labelIds": labels or ["INBOX"],
        "sizeEstimate": 100,
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": to},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
            ],
            "parts": parts,
        },
    }


def encode_pubsub_data(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode("ascii")
