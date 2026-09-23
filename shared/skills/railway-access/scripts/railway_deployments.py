#!/usr/bin/env python3
"""List Railway deployments and resolve the current/latest deployment ID."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from railway_client import (  # noqa: E402
    RailwayError,
    latest_successful_deployment_id,
    list_deployments,
    resolve_token,
    token_tail,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Railway deployments for a service/environment."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--limit", type=int, default=10, help="How many deployments to list.")
    parser.add_argument(
        "--latest-id-only",
        action="store_true",
        help="Print only the latest successful deployment id (plain text).",
    )
    args = parser.parse_args()

    try:
        token = resolve_token()
        deployments = list_deployments(
            project_id=args.project_id,
            service_id=args.service_id,
            environment_id=args.environment_id,
            first=max(1, min(args.limit, 100)),
        )
        latest_id = latest_successful_deployment_id(
            project_id=args.project_id,
            service_id=args.service_id,
            environment_id=args.environment_id,
            scan=max(args.limit, 20),
        )
    except RailwayError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    if args.latest_id_only:
        print(latest_id)
        return 0

    print(
        json.dumps(
            {
                "ok": True,
                "token_tail": token_tail(token),
                "query": {
                    "project_id": args.project_id,
                    "service_id": args.service_id,
                    "environment_id": args.environment_id,
                    "limit": args.limit,
                },
                "latest_successful_or_newest_id": latest_id,
                "count": len(deployments),
                "deployments": deployments,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
