#!/usr/bin/env python3
"""Operational tasks backed by the local sync DB (async Google Tasks mirror)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _cli_common import add_account_arg, print_json
from google_sync.factory import build_stack, ensure_connection, resolve_account_from_env


def _stack_account(args: argparse.Namespace):
    stack = build_stack()
    account_id, alias, email = resolve_account_from_env(args.account)
    ensure_connection(stack["db"], alias, email)
    return stack, account_id


def cmd_list(args: argparse.Namespace) -> int:
    stack, account_id = _stack_account(args)
    print_json(
        stack["task_service"].list_tasks(
            account_id, status=args.status, limit=args.limit
        )
    )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    stack, _ = _stack_account(args)
    print_json(stack["task_service"].get_task(args.task_id))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    stack, account_id = _stack_account(args)
    print_json(
        stack["task_service"].search_tasks(
            args.query, account_id=account_id, limit=args.limit
        )
    )
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    stack, account_id = _stack_account(args)
    print_json(
        stack["task_service"].create_task(
            title=args.title,
            google_account_id=account_id,
            description=args.description,
            due_at=args.due,
        )
    )
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    stack, _ = _stack_account(args)
    print_json(
        stack["task_service"].update_task(
            args.task_id,
            title=args.title,
            description=args.description,
            due_at=args.due,
        )
    )
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    stack, _ = _stack_account(args)
    print_json(stack["task_service"].complete_task(args.task_id, source="internal"))
    return 0


def cmd_sync_status(args: argparse.Namespace) -> int:
    stack, account_id = _stack_account(args)
    print_json(stack["task_service"].get_task_sync_status(account_id))
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    stack, account_id = _stack_account(args)
    print_json(stack["task_service"].refresh_tasks_on_demand(account_id))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list")
    add_account_arg(list_p)
    list_p.add_argument("--status", choices=["open", "completed"])
    list_p.add_argument("--limit", type=int, default=100)
    list_p.set_defaults(func=cmd_list)

    get_p = sub.add_parser("get")
    add_account_arg(get_p)
    get_p.add_argument("--task-id", required=True)
    get_p.set_defaults(func=cmd_get)

    search = sub.add_parser("search")
    add_account_arg(search)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=50)
    search.set_defaults(func=cmd_search)

    create = sub.add_parser("create")
    add_account_arg(create)
    create.add_argument("--title", required=True)
    create.add_argument("--description")
    create.add_argument("--due", help="Internal due datetime (ISO-8601); time preserved locally")
    create.set_defaults(func=cmd_create)

    update = sub.add_parser("update")
    add_account_arg(update)
    update.add_argument("--task-id", required=True)
    update.add_argument("--title")
    update.add_argument("--description")
    update.add_argument("--due")
    update.set_defaults(func=cmd_update)

    complete = sub.add_parser("complete")
    add_account_arg(complete)
    complete.add_argument("--task-id", required=True)
    complete.set_defaults(func=cmd_complete)

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
        print(f"google_local_tasks error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
