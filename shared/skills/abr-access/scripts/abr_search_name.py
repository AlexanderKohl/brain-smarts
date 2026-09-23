#!/usr/bin/env python3
"""Search ABR by entity/business name. Requires ABR_AUTHENTICATION_GUID."""

from __future__ import annotations

import argparse
import json
import sys

from abr_client import AbrError, search_name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search the Australian Business Register by name."
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Entity or business name to search (e.g. 'Example Plumbing Pty Ltd')",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum matches to return (1-200, default 20)",
    )
    args = parser.parse_args()
    try:
        payload = search_name(args.name, max_results=args.max_results)
    except AbrError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **payload}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
