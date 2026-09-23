"""Gmail search/read and draft create/update. Send is gated behind explicit approval."""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from email.message import EmailMessage
from typing import Any

from _cli_common import (
    add_account_arg,
    add_crm_args,
    print_json,
    require_side_effect_confirmation,
)
from google_oauth import GoogleConnection, GoogleOAuthError
from google_oauth.crm import GoogleCrmError, resolve_for_side_effect


def _service(account: str | None) -> Any:
    return GoogleConnection.from_environment(account).build_service("gmail", "v1")


def _b64url_decode(data: str) -> bytes:
    """Decode Gmail API body.data (URL-safe base64, padding optional)."""
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


def _collect_mime_parts(
    payload: dict[str, Any] | None,
    *,
    plain_parts: list[str],
    html_parts: list[str],
) -> None:
    if not payload:
        return
    mime = (payload.get("mimeType") or "").split(";", 1)[0].strip().lower()
    body_text = _decode_part_body(payload)
    if body_text:
        if mime == "text/plain":
            plain_parts.append(body_text)
        elif mime == "text/html":
            html_parts.append(body_text)
        elif not mime.startswith("multipart/") and not mime:
            # Rare: top-level body without a useful mimeType
            plain_parts.append(body_text)
    for child in payload.get("parts") or []:
        _collect_mime_parts(child, plain_parts=plain_parts, html_parts=html_parts)


def _html_to_text(raw: str) -> str:
    """Light HTML → text: drop scripts/styles/tags; keep readable whitespace."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)</div\s*>", "\n", text)
    text = re.sub(r"(?is)</tr\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _header_map(payload: dict[str, Any] | None) -> dict[str, str]:
    headers = {}
    for item in (payload or {}).get("headers") or []:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            headers[name] = value
    return headers


def _decoded_message(
    message: dict[str, Any], *, include_html: bool
) -> dict[str, Any]:
    payload = message.get("payload") or {}
    headers = _header_map(payload)
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_mime_parts(payload, plain_parts=plain_parts, html_parts=html_parts)

    html_body = "\n\n".join(part.strip() for part in html_parts if part.strip())
    if plain_parts:
        text = "\n\n".join(part.strip() for part in plain_parts if part.strip())
    elif html_body:
        text = _html_to_text(html_body)
    else:
        text = ""

    out: dict[str, Any] = {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "Date": headers.get("Date"),
        "From": headers.get("From"),
        "To": headers.get("To"),
        "Subject": headers.get("Subject"),
        "labelIds": message.get("labelIds") or [],
        "snippet": message.get("snippet"),
        "text": text,
    }
    if include_html:
        out["html"] = html_body
    return out


# Owner rule: paginate until exhausted; stop at 1000 and ask before continuing.
OWNER_ASK_THRESHOLD = 1000
GMAIL_PAGE_SIZE_MAX = 500


def _search_max_total(args: argparse.Namespace) -> int | None:
    """Resolve total message cap. None means fetch until exhausted (subject to owner gate)."""
    if args.max_total is not None:
        return args.max_total
    if args.max is not None:
        # Legacy --max was a single-page maxResults; treat as total cap for callers.
        return args.max
    return None


def _search_effective_limit(
    *,
    max_total: int | None,
    approve_more_than_1000: bool,
) -> tuple[int | None, str | None]:
    """
    Returns (effective_limit, refusal_error).

    effective_limit None = no cap (fetch until Gmail has no nextPageToken).
    Without owner approval, never auto-fetch past OWNER_ASK_THRESHOLD.
    """
    if max_total is not None and max_total < 1:
        return None, "--max-total / --max must be >= 1"
    if max_total is not None and max_total > OWNER_ASK_THRESHOLD and not approve_more_than_1000:
        return None, (
            f"Refusing --max-total {max_total}: fetching more than "
            f"{OWNER_ASK_THRESHOLD} messages requires owner approval via "
            f"--i-approve-more-than-1000 (after the owner says to continue)."
        )
    if max_total is not None:
        return max_total, None
    if approve_more_than_1000:
        return None, None
    return OWNER_ASK_THRESHOLD, None


def cmd_search(args: argparse.Namespace) -> int:
    page_size = args.page_size
    if page_size < 1 or page_size > GMAIL_PAGE_SIZE_MAX:
        print(
            f"--page-size must be between 1 and {GMAIL_PAGE_SIZE_MAX} "
            f"(Gmail API maxResults).",
            file=sys.stderr,
        )
        return 2

    max_total = _search_max_total(args)
    effective_limit, refusal = _search_effective_limit(
        max_total=max_total,
        approve_more_than_1000=args.i_approve_more_than_1000,
    )
    if refusal:
        print(refusal, file=sys.stderr)
        return 3

    service = _service(args.account)
    details: list[dict[str, Any]] = []
    page_token: str | None = None
    result_size_estimate: int | None = None
    next_page_token: str | None = None
    pages_fetched = 0
    stopped_early_in_page = False

    while True:
        remaining = (
            None
            if effective_limit is None
            else max(0, effective_limit - len(details))
        )
        if remaining is not None and remaining == 0:
            break

        list_kwargs: dict[str, Any] = {
            "userId": "me",
            "q": args.query,
            "maxResults": page_size
            if remaining is None
            else min(page_size, remaining),
        }
        if page_token:
            list_kwargs["pageToken"] = page_token

        response = service.users().messages().list(**list_kwargs).execute()
        pages_fetched += 1
        if result_size_estimate is None and "resultSizeEstimate" in response:
            result_size_estimate = response.get("resultSizeEstimate")

        batch = response.get("messages") or []
        for index, item in enumerate(batch):
            meta = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                )
                .execute()
            )
            headers = {
                h["name"]: h["value"]
                for h in (meta.get("payload") or {}).get("headers") or []
            }
            details.append(
                {
                    "id": meta.get("id"),
                    "threadId": meta.get("threadId"),
                    "snippet": meta.get("snippet"),
                    "headers": headers,
                }
            )
            if effective_limit is not None and len(details) >= effective_limit:
                # Requested fewer than this page returned; unread siblings remain.
                if index + 1 < len(batch):
                    stopped_early_in_page = True
                break

        next_page_token = response.get("nextPageToken") or None
        hit_limit = effective_limit is not None and len(details) >= effective_limit
        if hit_limit or not next_page_token or not batch:
            break
        page_token = next_page_token

    # More matches exist if Gmail has another page, or we cut mid-page via --max-total.
    # Note: when maxResults equals remaining, Gmail may omit unrequested ids from this
    # page; nextPageToken then indicates further matches.
    more_remain = bool(next_page_token) or stopped_early_in_page
    # Default (no --max-total): hard-stop at 1000 and ask the owner before continuing.
    stopped_at_owner_threshold = (
        more_remain
        and not args.i_approve_more_than_1000
        and max_total is None
        and len(details) >= OWNER_ASK_THRESHOLD
    )

    note = None
    if stopped_at_owner_threshold:
        note = (
            f"Stopped at owner threshold ({OWNER_ASK_THRESHOLD} messages). "
            "Ask the owner whether to continue. If yes, re-run with "
            "--i-approve-more-than-1000 (optionally --max-total N with N>1000)."
        )
    elif more_remain and max_total is not None:
        note = (
            f"Stopped at --max-total {max_total}; more messages may match. "
            "Raise --max-total (and --i-approve-more-than-1000 if above "
            f"{OWNER_ASK_THRESHOLD}) to continue."
        )

    print_json(
        {
            "query": args.query,
            "messages": details,
            "count": len(details),
            "page_size": page_size,
            "pages_fetched": pages_fetched,
            "max_total": max_total,
            "effective_limit": effective_limit,
            "resultSizeEstimate": result_size_estimate,
            "nextPageToken": next_page_token if more_remain else None,
            "complete": not more_remain,
            "more_remain": more_remain,
            "stopped_at_owner_threshold": stopped_at_owner_threshold,
            "owner_threshold": OWNER_ASK_THRESHOLD,
            "needs_owner_approval_to_continue": stopped_at_owner_threshold,
            "note": note,
        }
    )
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    service = _service(args.account)
    message = (
        service.users()
        .messages()
        .get(userId="me", id=args.message_id, format="full")
        .execute()
    )
    if args.format == "raw":
        print_json(message)
        return 0
    print_json(_decoded_message(message, include_html=args.include_html))
    return 0


def _build_raw_message(
    *,
    to: str,
    subject: str,
    body: str,
    from_address: str | None,
    cc: str | None,
    bcc: str | None,
) -> str:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if from_address:
        message["From"] = from_address
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _resolve_crm(args: argparse.Namespace):
    return resolve_for_side_effect(
        contact_id=args.contact_id,
        email=args.contact_email or getattr(args, "to", None),
        name=args.contact_name,
        persona_key=args.persona,
        account_alias=args.account,
        allow_missing_contact=bool(args.persona or args.account),
    )


def cmd_create_draft(args: argparse.Namespace) -> int:
    resolution = _resolve_crm(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    from_address = args.from_address
    if not from_address and resolution.persona:
        from_address = resolution.persona.primary_from_email
    service = _service(account_alias)
    raw = _build_raw_message(
        to=args.to,
        subject=args.subject,
        body=args.body,
        from_address=from_address,
        cc=args.cc,
        bcc=args.bcc,
    )
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    print_json(
        {
            "action": "create_draft",
            "draft": draft,
            "crm": resolution.as_dict(),
            "note": "Draft only. Send requires explicit owner approval of this draft id.",
        }
    )
    return 0


def cmd_update_draft(args: argparse.Namespace) -> int:
    resolution = _resolve_crm(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    from_address = args.from_address
    if not from_address and resolution.persona:
        from_address = resolution.persona.primary_from_email
    service = _service(account_alias)
    raw = _build_raw_message(
        to=args.to,
        subject=args.subject,
        body=args.body,
        from_address=from_address,
        cc=args.cc,
        bcc=args.bcc,
    )
    draft = (
        service.users()
        .drafts()
        .update(
            userId="me",
            id=args.draft_id,
            body={"message": {"raw": raw}},
        )
        .execute()
    )
    print_json(
        {
            "action": "update_draft",
            "draft": draft,
            "crm": resolution.as_dict(),
        }
    )
    return 0


def cmd_list_drafts(args: argparse.Namespace) -> int:
    service = _service(args.account)
    response = (
        service.users().drafts().list(userId="me", maxResults=args.max).execute()
    )
    print_json(response)
    return 0


def cmd_send_draft(args: argparse.Namespace) -> int:
    if not args.i_approve_send:
        print(
            "Refusing to send. Re-run with --i-approve-send after the owner "
            "explicitly approves this specific draft id.",
            file=sys.stderr,
        )
        return 3
    if args.approve_draft_id != args.draft_id:
        print(
            "Refusing to send: --approve-draft-id must exactly match --draft-id.",
            file=sys.stderr,
        )
        return 3
    resolution = _resolve_crm(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    service = _service(account_alias)
    existing = (
        service.users().drafts().get(userId="me", id=args.draft_id).execute()
    )
    sent = (
        service.users()
        .drafts()
        .send(userId="me", body={"id": args.draft_id})
        .execute()
    )
    print_json(
        {
            "action": "send_draft",
            "approved_draft_id": args.draft_id,
            "draft_before_send": existing,
            "sent": sent,
            "crm": resolution.as_dict(),
        }
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser(
        "search",
        help=(
            "Search Gmail messages (paginates until exhausted; stops at "
            f"{OWNER_ASK_THRESHOLD} unless owner approves continuing)"
        ),
    )
    add_account_arg(search)
    search.add_argument("--query", required=True)
    search.add_argument(
        "--page-size",
        type=int,
        default=100,
        help=f"Gmail list maxResults per page (1-{GMAIL_PAGE_SIZE_MAX}; default 100)",
    )
    search.add_argument(
        "--max-total",
        type=int,
        default=None,
        help=(
            "Optional cap on total messages returned. Omit to fetch all matches "
            f"(still stops at {OWNER_ASK_THRESHOLD} without "
            "--i-approve-more-than-1000)."
        ),
    )
    search.add_argument(
        "--max",
        type=int,
        default=None,
        help="Deprecated alias for --max-total (legacy single-page callers)",
    )
    search.add_argument(
        "--i-approve-more-than-1000",
        action="store_true",
        help=(
            f"Owner explicitly approved fetching more than {OWNER_ASK_THRESHOLD} "
            "messages. Required for --max-total N with N>1000, or to continue "
            "past the default owner threshold until exhausted."
        ),
    )
    search.set_defaults(func=cmd_search)

    read = sub.add_parser(
        "read",
        help="Read one Gmail message by id (default: decoded plain text)",
    )
    add_account_arg(read)
    read.add_argument("--message-id", required=True)
    read.add_argument(
        "--format",
        choices=("decoded", "raw"),
        default="decoded",
        help="decoded (default): headers + plain text; raw: full Gmail API JSON",
    )
    read.add_argument(
        "--include-html",
        action="store_true",
        help="With --format decoded, also include decoded text/html as html",
    )
    read.set_defaults(func=cmd_read)

    drafts = sub.add_parser("list-drafts", help="List Gmail drafts")
    add_account_arg(drafts)
    drafts.add_argument("--max", type=int, default=20)
    drafts.set_defaults(func=cmd_list_drafts)

    create = sub.add_parser("create-draft", help="Create a Gmail draft")
    add_account_arg(create)
    add_crm_args(create)
    create.add_argument("--to", required=True)
    create.add_argument("--subject", required=True)
    create.add_argument("--body", required=True)
    create.add_argument("--from-address")
    create.add_argument("--cc")
    create.add_argument("--bcc")
    create.set_defaults(func=cmd_create_draft)

    update = sub.add_parser("update-draft", help="Replace a Gmail draft body")
    add_account_arg(update)
    add_crm_args(update)
    update.add_argument("--draft-id", required=True)
    update.add_argument("--to", required=True)
    update.add_argument("--subject", required=True)
    update.add_argument("--body", required=True)
    update.add_argument("--from-address")
    update.add_argument("--cc")
    update.add_argument("--bcc")
    update.set_defaults(func=cmd_update_draft)

    send = sub.add_parser(
        "send-draft",
        help="Send an approved draft (requires explicit draft-id approval flags)",
    )
    add_account_arg(send)
    add_crm_args(send)
    send.add_argument("--draft-id", required=True)
    send.add_argument(
        "--approve-draft-id",
        required=True,
        help="Must exactly equal --draft-id; proves owner approved this draft",
    )
    send.add_argument(
        "--i-approve-send",
        action="store_true",
        help="Required. Owner explicitly approved sending this draft.",
    )
    send.set_defaults(func=cmd_send_draft)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (GoogleOAuthError, GoogleCrmError) as exc:
        print(f"Gmail error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
