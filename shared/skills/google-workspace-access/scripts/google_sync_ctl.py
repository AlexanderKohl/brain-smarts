#!/usr/bin/env python3
"""Control plane for local Gmail / Google Tasks synchronisation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script from this directory.
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _cli_common import add_account_arg, print_json
from google_sync.config import SyncConfig
from google_sync.factory import build_stack, ensure_connection, resolve_account_from_env


def cmd_migrate(args: argparse.Namespace) -> int:
    from dataclasses import replace
    from pathlib import Path as P

    config = SyncConfig.from_environment()
    if args.db:
        config = replace(config, db_path=P(args.db))
    stack = build_stack(config)
    applied = stack["db"].migrate()
    print_json(
        {
            "db_path": str(stack["config"].db_path),
            "applied": applied,
            "ok": True,
        }
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    stack = build_stack()
    db = stack["db"]
    connections = [dict(r) for r in db.fetchall("SELECT * FROM google_connections")]
    jobs = [
        dict(r)
        for r in db.fetchall(
            """
            SELECT id, job_type, google_account_id, status, attempts,
                   run_after, last_error_category, updated_at
            FROM sync_jobs
            WHERE status IN ('pending', 'running', 'failed')
            ORDER BY updated_at DESC
            LIMIT 50
            """
        )
    ]
    outbox = [
        dict(r)
        for r in db.fetchall(
            """
            SELECT id, operation, google_account_id, internal_task_id, status,
                   attempts, last_error_category, updated_at
            FROM sync_outbox
            WHERE status IN ('pending', 'running', 'failed')
            ORDER BY updated_at DESC
            LIMIT 50
            """
        )
    ]
    print_json(
        {
            "db_path": str(stack["config"].db_path),
            "config": {
                "gmail_local_sync_enabled": stack["config"].gmail_local_sync_enabled,
                "google_tasks_sync_enabled": stack["config"].google_tasks_sync_enabled,
                "gmail_initial_sync_query": stack["config"].gmail_initial_sync_query,
                "gmail_pubsub_configured": stack["config"].pubsub_configured,
                "google_tasks_list_name": stack["config"].google_tasks_list_name,
            },
            "connections": connections,
            "active_jobs": jobs,
            "active_outbox": outbox,
        }
    )
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    stack = build_stack()
    account_id, alias, email = resolve_account_from_env(args.account)
    ensure_connection(stack["db"], alias, email)
    jobs = stack["worker"].enqueue_backfill(account_id)
    print_json(
        {
            "account_id": account_id,
            "alias": alias,
            "email": email,
            "jobs": jobs,
            "note": "Jobs are queued. Run `worker` (or `worker --once`) to process them.",
        }
    )
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    stack = build_stack()
    stack["worker"].run_forever(once=args.once)
    if args.once:
        print_json({"ok": True, "mode": "once"})
    return 0


def cmd_ensure_connection(args: argparse.Namespace) -> int:
    stack = build_stack()
    account_id, alias, email = resolve_account_from_env(args.account)
    ensure_connection(stack["db"], alias, email)
    print_json({"account_id": account_id, "alias": alias, "email": email})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override GOOGLE_LOCAL_SYNC_DB path")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="Apply SQLite migrations")
    migrate.set_defaults(func=cmd_migrate)

    status = sub.add_parser("status", help="Show sync DB and queue status")
    status.set_defaults(func=cmd_status)

    ensure = sub.add_parser("ensure-connection", help="Register account in sync DB")
    add_account_arg(ensure)
    ensure.set_defaults(func=cmd_ensure_connection)

    backfill = sub.add_parser(
        "backfill",
        help="Enqueue bounded initial sync for an account (does not run at startup)",
    )
    add_account_arg(backfill)
    backfill.set_defaults(func=cmd_backfill)

    worker = sub.add_parser("worker", help="Run background sync worker")
    worker.add_argument(
        "--once",
        action="store_true",
        help="Process one tick then exit",
    )
    worker.set_defaults(func=cmd_worker)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"google_sync_ctl error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
