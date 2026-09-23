#!/usr/bin/env python3
"""Lookup ABN or ACN via ABR JSON web services. Requires ABR_AUTHENTICATION_GUID."""

from __future__ import annotations

import argparse
import json
import sys

from abr_client import AbrError, lookup_abn, lookup_acn


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Look up an Australian Business Number (ABN) or Company Number (ACN)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--abn", help="11-digit ABN (spaces/hyphens allowed)")
    group.add_argument("--acn", help="9-digit ACN (spaces/hyphens allowed)")
    parser.add_argument(
        "--history",
        action="store_true",
        help="Include historical details for ABN lookup when supported",
    )
    args = parser.parse_args()
    try:
        if args.abn:
            payload = lookup_abn(args.abn, include_historical=args.history)
        else:
            payload = lookup_acn(args.acn)
    except AbrError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **payload}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
