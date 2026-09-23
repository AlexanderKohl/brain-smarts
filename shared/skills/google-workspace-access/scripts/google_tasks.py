"""Google Tasks list and create/update (no delete)."""

from __future__ import annotations

import argparse
import sys
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
    return GoogleConnection.from_environment(account).build_service("tasks", "v1")


def cmd_list_lists(args: argparse.Namespace) -> int:
    service = _service(args.account)
    print_json(service.tasklists().list(maxResults=args.max).execute())
    return 0


def cmd_list_tasks(args: argparse.Namespace) -> int:
    service = _service(args.account)
    print_json(
        service.tasks()
        .list(tasklist=args.tasklist, maxResults=args.max, showCompleted=args.show_completed)
        .execute()
    )
    return 0


def _resolve(args: argparse.Namespace):
    return resolve_for_side_effect(
        contact_id=args.contact_id,
        email=args.contact_email,
        name=args.contact_name,
        persona_key=args.persona,
        account_alias=args.account,
        allow_missing_contact=True,
    )


def cmd_create_task(args: argparse.Namespace) -> int:
    resolution = _resolve(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    service = _service(account_alias)
    body: dict[str, Any] = {"title": args.title}
    if args.notes:
        body["notes"] = args.notes
    if args.due:
        body["due"] = args.due
    created = service.tasks().insert(tasklist=args.tasklist, body=body).execute()
    print_json(
        {"action": "create_task", "task": created, "crm": resolution.as_dict()}
    )
    return 0


def cmd_update_task(args: argparse.Namespace) -> int:
    resolution = _resolve(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    service = _service(account_alias)
    body: dict[str, Any] = {}
    if args.title:
        body["title"] = args.title
    if args.notes is not None:
        body["notes"] = args.notes
    if args.due:
        body["due"] = args.due
    if args.status:
        body["status"] = args.status
    updated = (
        service.tasks()
        .patch(tasklist=args.tasklist, task=args.task_id, body=body)
        .execute()
    )
    print_json(
        {"action": "update_task", "task": updated, "crm": resolution.as_dict()}
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    lists = sub.add_parser("list-lists")
    add_account_arg(lists)
    lists.add_argument("--max", type=int, default=20)
    lists.set_defaults(func=cmd_list_lists)

    tasks = sub.add_parser("list-tasks")
    add_account_arg(tasks)
    tasks.add_argument("--tasklist", default="@default")
    tasks.add_argument("--max", type=int, default=50)
    tasks.add_argument("--show-completed", action="store_true")
    tasks.set_defaults(func=cmd_list_tasks)

    create = sub.add_parser("create-task")
    add_account_arg(create)
    add_crm_args(create)
    create.add_argument("--tasklist", default="@default")
    create.add_argument("--title", required=True)
    create.add_argument("--notes")
    create.add_argument("--due", help="RFC3339 due datetime")
    create.set_defaults(func=cmd_create_task)

    update = sub.add_parser("update-task")
    add_account_arg(update)
    add_crm_args(update)
    update.add_argument("--tasklist", default="@default")
    update.add_argument("--task-id", required=True)
    update.add_argument("--title")
    update.add_argument("--notes")
    update.add_argument("--due")
    update.add_argument("--status", choices=["needsAction", "completed"])
    update.set_defaults(func=cmd_update_task)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (GoogleOAuthError, GoogleCrmError) as exc:
        print(f"Tasks error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
