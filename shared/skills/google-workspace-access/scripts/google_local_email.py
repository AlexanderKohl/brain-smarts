#!/usr/bin/env python3
"""Read Gmail from the local sync index (not live Google, unless body miss)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _cli_common import add_account_arg, print_json
from google_sync.factory import build_stack, ensure_connection, resolve_account_from_env


def _account(args: argparse.Namespace):
    stack = build_stack()
    account_id, alias, email = resolve_account_from_env(args.account)
    ensure_connection(stack["db"], alias, email)
    return stack, account_id


def cmd_list_recent(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].list_recent_emails(
            account_id, limit=args.limit, unread_only=args.unread_only
        )
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].search_emails(
            account_id, query=args.query, limit=args.limit
        )
    )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].get_email_metadata(account_id, args.message_id)
    )
    return 0


def cmd_thread(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].get_email_thread(account_id, args.thread_id)
    )
    return 0


def cmd_body(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].get_email_body(
            account_id, args.message_id, include_html=args.include_html
        )
    )
    return 0


def cmd_attachments(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(
        stack["email_service"].get_email_attachments(account_id, args.message_id)
    )
    return 0


def cmd_sync_status(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(stack["email_service"].get_email_sync_status(account_id))
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    stack, account_id = _account(args)
    print_json(stack["email_service"].refresh_email_on_demand(account_id))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    recent = sub.add_parser("list-recent")
    add_account_arg(recent)
    recent.add_argument("--limit", type=int, default=50)
    recent.add_argument("--unread-only", action="store_true")
    recent.set_defaults(func=cmd_list_recent)

    search = sub.add_parser("search")
    add_account_arg(search)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=50)
    search.set_defaults(func=cmd_search)

    get_p = sub.add_parser("get")
    add_account_arg(get_p)
    get_p.add_argument("--message-id", required=True)
    get_p.set_defaults(func=cmd_get)

    thread = sub.add_parser("thread")
    add_account_arg(thread)
    thread.add_argument("--thread-id", required=True)
    thread.set_defaults(func=cmd_thread)

    body = sub.add_parser("body")
    add_account_arg(body)
    body.add_argument("--message-id", required=True)
    body.add_argument("--include-html", action="store_true")
    body.set_defaults(func=cmd_body)

    atts = sub.add_parser("attachments")
    add_account_arg(atts)
    atts.add_argument("--message-id", required=True)
    atts.set_defaults(func=cmd_attachments)

    status = sub.add_parser("sync-status")
    add_account_arg(status)
    status.set_defaults(func=cmd_sync_status)

    refresh = sub.add_parser("refresh")
    add_account_arg(refresh)
    refresh.set_defaults(func=cmd_refresh)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"google_local_email error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
