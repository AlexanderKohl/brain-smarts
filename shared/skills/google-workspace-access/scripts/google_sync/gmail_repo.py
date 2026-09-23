"""Persistence helpers for Gmail local index rows."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import Database, row_to_dict
from .observability import utc_now_iso


def upsert_message(db: Database, account_id: str, meta: dict[str, Any]) -> None:
    now = utc_now_iso()
    db.execute(
        """
        INSERT INTO gmail_messages (
            google_account_id, gmail_message_id, gmail_thread_id, history_id,
            internal_date, sender_name, sender_email, recipients_json, cc_json,
            subject, snippet, label_ids_json, is_unread, is_starred, is_important,
            has_attachments, size_estimate, mime_type, body_cached, is_deleted,
            created_at, updated_at, last_synced_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?
        )
        ON CONFLICT(google_account_id, gmail_message_id) DO UPDATE SET
            gmail_thread_id = excluded.gmail_thread_id,
            history_id = excluded.history_id,
            internal_date = excluded.internal_date,
            sender_name = excluded.sender_name,
            sender_email = excluded.sender_email,
            recipients_json = excluded.recipients_json,
            cc_json = excluded.cc_json,
            subject = excluded.subject,
            snippet = excluded.snippet,
            label_ids_json = excluded.label_ids_json,
            is_unread = excluded.is_unread,
            is_starred = excluded.is_starred,
            is_important = excluded.is_important,
            has_attachments = excluded.has_attachments,
            size_estimate = excluded.size_estimate,
            mime_type = excluded.mime_type,
            is_deleted = 0,
            updated_at = excluded.updated_at,
            last_synced_at = excluded.last_synced_at
        """,
        (
            account_id,
            meta["gmail_message_id"],
            meta["gmail_thread_id"],
            meta.get("history_id"),
            meta.get("internal_date"),
            meta.get("sender_name"),
            meta.get("sender_email"),
            json.dumps(meta.get("recipients") or []),
            json.dumps(meta.get("cc") or []),
            meta.get("subject"),
            meta.get("snippet"),
            json.dumps(meta.get("label_ids") or []),
            meta.get("is_unread", 0),
            meta.get("is_starred", 0),
            meta.get("is_important", 0),
            meta.get("has_attachments", 0),
            meta.get("size_estimate"),
            meta.get("mime_type"),
            now,
            now,
            now,
        ),
    )
    db.execute(
        """
        INSERT INTO gmail_threads (
            google_account_id, gmail_thread_id, subject, snippet,
            last_message_internal_date, message_count, created_at, updated_at,
            last_synced_at
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(google_account_id, gmail_thread_id) DO UPDATE SET
            subject = COALESCE(excluded.subject, gmail_threads.subject),
            snippet = excluded.snippet,
            last_message_internal_date = CASE
                WHEN excluded.last_message_internal_date IS NOT NULL
                     AND (gmail_threads.last_message_internal_date IS NULL
                          OR excluded.last_message_internal_date
                             >= gmail_threads.last_message_internal_date)
                THEN excluded.last_message_internal_date
                ELSE gmail_threads.last_message_internal_date
            END,
            updated_at = excluded.updated_at,
            last_synced_at = excluded.last_synced_at
        """,
        (
            account_id,
            meta["gmail_thread_id"],
            meta.get("subject"),
            meta.get("snippet"),
            meta.get("internal_date"),
            now,
            now,
            now,
        ),
    )
    # Replace label links
    db.execute(
        """
        DELETE FROM gmail_message_labels
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (account_id, meta["gmail_message_id"]),
    )
    for label_id in meta.get("label_ids") or []:
        db.execute(
            """
            INSERT OR IGNORE INTO gmail_labels (
                google_account_id, label_id, name, label_type, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (account_id, label_id, label_id, now, now),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO gmail_message_labels (
                google_account_id, gmail_message_id, label_id
            ) VALUES (?, ?, ?)
            """,
            (account_id, meta["gmail_message_id"], label_id),
        )
    # Attachment metadata (no bytes)
    if meta.get("attachments"):
        db.execute(
            """
            DELETE FROM gmail_attachments
            WHERE google_account_id = ? AND gmail_message_id = ?
            """,
            (account_id, meta["gmail_message_id"]),
        )
        for att in meta["attachments"]:
            db.execute(
                """
                INSERT INTO gmail_attachments (
                    google_account_id, gmail_message_id, gmail_attachment_id,
                    filename, mime_type, size, content_id, is_inline,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    meta["gmail_message_id"],
                    att.get("gmail_attachment_id"),
                    att.get("filename"),
                    att.get("mime_type"),
                    att.get("size"),
                    att.get("content_id"),
                    att.get("is_inline", 0),
                    now,
                    now,
                ),
            )


def mark_message_deleted(db: Database, account_id: str, message_id: str) -> None:
    now = utc_now_iso()
    db.execute(
        """
        UPDATE gmail_messages
        SET is_deleted = 1, updated_at = ?, last_synced_at = ?
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (now, now, account_id, message_id),
    )


def update_message_labels(
    db: Database,
    account_id: str,
    message_id: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> None:
    row = db.fetchone(
        """
        SELECT label_ids_json FROM gmail_messages
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (account_id, message_id),
    )
    if row is None:
        return
    labels = set(json.loads(row["label_ids_json"] or "[]"))
    for label in add or []:
        labels.add(label)
    for label in remove or []:
        labels.discard(label)
    label_list = sorted(labels)
    now = utc_now_iso()
    db.execute(
        """
        UPDATE gmail_messages
        SET label_ids_json = ?,
            is_unread = ?,
            is_starred = ?,
            is_important = ?,
            updated_at = ?,
            last_synced_at = ?
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (
            json.dumps(label_list),
            1 if "UNREAD" in labels else 0,
            1 if "STARRED" in labels else 0,
            1 if "IMPORTANT" in labels else 0,
            now,
            now,
            account_id,
            message_id,
        ),
    )
    db.execute(
        """
        DELETE FROM gmail_message_labels
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (account_id, message_id),
    )
    for label_id in label_list:
        db.execute(
            """
            INSERT OR IGNORE INTO gmail_message_labels (
                google_account_id, gmail_message_id, label_id
            ) VALUES (?, ?, ?)
            """,
            (account_id, message_id, label_id),
        )


def store_message_body(
    db: Database,
    account_id: str,
    message_id: str,
    *,
    text_body: str,
    html_body: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    now = utc_now_iso()
    digest = hashlib.sha256(
        (text_body or "").encode("utf-8") + b"\0" + (html_body or "").encode("utf-8")
    ).hexdigest()
    db.execute(
        """
        INSERT INTO gmail_message_bodies (
            google_account_id, gmail_message_id, text_body, html_body,
            content_hash, fetched_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(google_account_id, gmail_message_id) DO UPDATE SET
            text_body = excluded.text_body,
            html_body = excluded.html_body,
            content_hash = excluded.content_hash,
            fetched_at = excluded.fetched_at,
            updated_at = excluded.updated_at
        """,
        (account_id, message_id, text_body, html_body, digest, now, now),
    )
    db.execute(
        """
        UPDATE gmail_messages
        SET body_cached = 1, updated_at = ?, last_synced_at = ?
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (now, now, account_id, message_id),
    )
    if attachments:
        db.execute(
            """
            DELETE FROM gmail_attachments
            WHERE google_account_id = ? AND gmail_message_id = ?
            """,
            (account_id, message_id),
        )
        for att in attachments:
            db.execute(
                """
                INSERT INTO gmail_attachments (
                    google_account_id, gmail_message_id, gmail_attachment_id,
                    filename, mime_type, size, content_id, is_inline,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    message_id,
                    att.get("gmail_attachment_id"),
                    att.get("filename"),
                    att.get("mime_type"),
                    att.get("size"),
                    att.get("content_id"),
                    att.get("is_inline", 0),
                    now,
                    now,
                ),
            )
        db.execute(
            """
            UPDATE gmail_messages
            SET has_attachments = 1, updated_at = ?
            WHERE google_account_id = ? AND gmail_message_id = ?
            """,
            (now, account_id, message_id),
        )


def get_cached_body(
    db: Database, account_id: str, message_id: str
) -> dict[str, Any] | None:
    row = db.fetchone(
        """
        SELECT text_body, html_body, content_hash, fetched_at
        FROM gmail_message_bodies
        WHERE google_account_id = ? AND gmail_message_id = ?
        """,
        (account_id, message_id),
    )
    return row_to_dict(row)
