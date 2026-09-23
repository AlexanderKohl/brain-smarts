"""Thin Gmail API helpers used by sync orchestration."""

from __future__ import annotations

import base64
import email.utils
import html
import re
from typing import Any, Callable, Iterator


METADATA_HEADERS = [
    "From",
    "To",
    "Cc",
    "Subject",
    "Date",
    "Message-ID",
]


class GmailApiClient:
    """Wraps a googleapiclient gmail service (or a test double with same shape)."""

    def __init__(self, service: Any):
        self.service = service

    def profile(self) -> dict[str, Any]:
        return self.service.users().getProfile(userId="me").execute()

    def list_message_ids(
        self,
        *,
        query: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "userId": "me",
            "q": query,
            "maxResults": page_size,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        return self.service.users().messages().list(**kwargs).execute()

    def iter_message_ids(
        self, *, query: str, page_size: int = 100
    ) -> Iterator[tuple[str, str | None]]:
        """Yield (message_id, thread_id) across all pages."""
        page_token: str | None = None
        while True:
            response = self.list_message_ids(
                query=query, page_size=page_size, page_token=page_token
            )
            for item in response.get("messages") or []:
                yield item["id"], item.get("threadId")
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def get_metadata(self, message_id: str) -> dict[str, Any]:
        return (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=METADATA_HEADERS,
            )
            .execute()
        )

    def get_full(self, message_id: str) -> dict[str, Any]:
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def list_history(
        self,
        *,
        start_history_id: str,
        page_token: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "maxResults": page_size,
            "historyTypes": [
                "messageAdded",
                "messageDeleted",
                "labelAdded",
                "labelRemoved",
            ],
        }
        if page_token:
            kwargs["pageToken"] = page_token
        return self.service.users().history().list(**kwargs).execute()

    def watch(self, *, topic_name: str, label_ids: list[str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "topicName": topic_name,
            "labelIds": label_ids or ["INBOX"],
            "labelFilterBehavior": "include",
        }
        return self.service.users().watch(userId="me", body=body).execute()

    def stop_watch(self) -> None:
        self.service.users().stop(userId="me").execute()

    def list_labels(self) -> list[dict[str, Any]]:
        response = self.service.users().labels().list(userId="me").execute()
        return list(response.get("labels") or [])


def parse_address(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    name, addr = email.utils.parseaddr(value)
    name = name.strip() or None
    addr = addr.strip().lower() or None
    return name, addr


def parse_address_list(value: str | None) -> list[dict[str, str | None]]:
    if not value:
        return []
    out: list[dict[str, str | None]] = []
    for name, addr in email.utils.getaddresses([value]):
        if not name and not addr:
            continue
        out.append(
            {
                "name": (name.strip() or None),
                "email": (addr.strip().lower() or None),
            }
        )
    return out


def header_map(payload: dict[str, Any] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in (payload or {}).get("headers") or []:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            headers[name] = value
    return headers


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _decode_part_body(part: dict[str, Any]) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    try:
        return _b64url_decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def collect_mime_parts(
    payload: dict[str, Any] | None,
    *,
    plain_parts: list[str],
    html_parts: list[str],
    attachments: list[dict[str, Any]],
) -> None:
    if not payload:
        return
    mime = (payload.get("mimeType") or "").split(";", 1)[0].strip().lower()
    filename = payload.get("filename") or ""
    body = payload.get("body") or {}
    attachment_id = body.get("attachmentId")
    if filename or attachment_id:
        attachments.append(
            {
                "gmail_attachment_id": attachment_id,
                "filename": filename or None,
                "mime_type": mime or None,
                "size": body.get("size"),
                "content_id": None,
                "is_inline": 0,
            }
        )
    body_text = _decode_part_body(payload)
    if body_text and not attachment_id:
        if mime == "text/plain":
            plain_parts.append(body_text)
        elif mime == "text/html":
            html_parts.append(body_text)
    for child in payload.get("parts") or []:
        collect_mime_parts(
            child,
            plain_parts=plain_parts,
            html_parts=html_parts,
            attachments=attachments,
        )


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)</div\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def decode_message_bodies(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload") or {}
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []
    collect_mime_parts(
        payload,
        plain_parts=plain_parts,
        html_parts=html_parts,
        attachments=attachments,
    )
    html_body = "\n\n".join(part.strip() for part in html_parts if part.strip())
    if plain_parts:
        text = "\n\n".join(part.strip() for part in plain_parts if part.strip())
    elif html_body:
        text = html_to_text(html_body)
    else:
        text = ""
    return {"text": text, "html": html_body, "attachments": attachments}


def metadata_attachment_flag(message: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Infer attachment presence from metadata payload parts (no download)."""
    attachments: list[dict[str, Any]] = []
    plain: list[str] = []
    html_parts: list[str] = []
    collect_mime_parts(
        message.get("payload") or {},
        plain_parts=plain,
        html_parts=html_parts,
        attachments=attachments,
    )
    # Metadata format often omits nested parts; also check filename on payload.
    has = bool(attachments)
    return has, attachments


def normalise_metadata(message: dict[str, Any]) -> dict[str, Any]:
    headers = header_map(message.get("payload"))
    sender_name, sender_email = parse_address(headers.get("From"))
    recipients = parse_address_list(headers.get("To"))
    cc = parse_address_list(headers.get("Cc"))
    label_ids = list(message.get("labelIds") or [])
    has_attachments, attachment_meta = metadata_attachment_flag(message)
    return {
        "gmail_message_id": message.get("id"),
        "gmail_thread_id": message.get("threadId"),
        "history_id": str(message["historyId"]) if message.get("historyId") is not None else None,
        "internal_date": int(message["internalDate"])
        if message.get("internalDate") is not None
        else None,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "recipients": recipients,
        "cc": cc,
        "subject": headers.get("Subject"),
        "snippet": message.get("snippet"),
        "label_ids": label_ids,
        "is_unread": 1 if "UNREAD" in label_ids else 0,
        "is_starred": 1 if "STARRED" in label_ids else 0,
        "is_important": 1 if "IMPORTANT" in label_ids else 0,
        "has_attachments": 1 if has_attachments else 0,
        "attachments": attachment_meta,
        "size_estimate": message.get("sizeEstimate"),
        "mime_type": (message.get("payload") or {}).get("mimeType"),
    }


def build_gmail_client_from_connection(
    connection_factory: Callable[[], Any],
) -> GmailApiClient:
    return GmailApiClient(connection_factory())
