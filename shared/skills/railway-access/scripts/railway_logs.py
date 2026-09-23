#!/usr/bin/env python3
"""Fetch Railway deploy/build/HTTP logs for a deployment (timeframe + filter)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from railway_client import (  # noqa: E402
    RailwayError,
    fetch_logs,
    latest_successful_deployment_id,
    parse_time_arg,
    resolve_token,
    token_tail,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch point-in-time Railway logs via GraphQL."
    )
    parser.add_argument("--deployment-id", help="Deployment UUID.")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve latest successful deployment from project/service/environment.",
    )
    parser.add_argument("--project-id")
    parser.add_argument("--service-id")
    parser.add_argument("--environment-id")
    parser.add_argument(
        "--kind",
        choices=("deploy", "build", "http"),
        default="deploy",
        help="Log type (default: deploy).",
    )
    parser.add_argument("--since", help="Relative (1h) or ISO-8601 start bound.")
    parser.add_argument("--until", help="Relative (10m) or ISO-8601 end bound.")
    parser.add_argument(
        "--filter",
        dest="filter_expr",
        help='Railway filter syntax, e.g. @level:error or "rate limit".',
    )
    parser.add_argument("--limit", type=int, default=100, help="Max lines (default 100).")
    args = parser.parse_args()

    try:
        token = resolve_token()
        deployment_id = (args.deployment_id or "").strip()
        if args.latest:
            missing = [
                name
                for name, value in (
                    ("--project-id", args.project_id),
                    ("--service-id", args.service_id),
                    ("--environment-id", args.environment_id),
                )
                if not (value or "").strip()
            ]
            if missing:
                raise RailwayError(
                    f"--latest requires {' '.join(missing)}."
                )
            deployment_id = latest_successful_deployment_id(
                project_id=args.project_id.strip(),
                service_id=args.service_id.strip(),
                environment_id=args.environment_id.strip(),
            )
        if not deployment_id:
            raise RailwayError("Provide --deployment-id or --latest with IDs.")

        start_date = parse_time_arg(args.since, label="--since")
        end_date = parse_time_arg(args.until, label="--until")
        limit = max(1, min(args.limit, 5000))
        logs = fetch_logs(
            deployment_id=deployment_id,
            kind=args.kind,
            limit=limit,
            filter_expr=(args.filter_expr or None),
            start_date=start_date,
            end_date=end_date,
        )
    except RailwayError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "token_tail": token_tail(token),
                "query": {
                    "deployment_id": deployment_id,
                    "kind": args.kind,
                    "since": args.since,
                    "until": args.until,
                    "start_date": start_date,
                    "end_date": end_date,
                    "filter": args.filter_expr,
                    "limit": limit,
                },
                "count": len(logs),
                "logs": logs,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
