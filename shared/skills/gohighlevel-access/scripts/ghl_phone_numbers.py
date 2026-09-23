"""Report phone-system numbers for every cached HighLevel subaccount.

Run from inside the active credential-aware PowerShell session (see
/shared/skills/gohighlevel-access/SKILL.md and /shared/skills/manage-credentials/SKILL.md):

    python shared/skills/gohighlevel-access/scripts/ghl_phone_numbers.py

Uses the reusable, cached ``location_catalog`` on the stored agency token
rather than refreshing subaccounts, per the skill's catalogue-refresh
policy. Pass --refresh-catalog to force a subaccount rediscovery first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse

from ghl_oauth import HighLevelConnection, HighLevelOAuthError
from ghl_oauth.client import API_ROOT


def _fetch_location_numbers(
    connection: HighLevelConnection, location_id: str
) -> list[dict]:
    numbers: list[dict] = []
    page = 0
    while True:
        query = urllib.parse.urlencode(
            {"pageSize": 100, "page": page, "skipNumberPool": "false"}
        )
        url = (
            f"{API_ROOT}/phone-system/numbers/location/"
            f"{urllib.parse.quote(location_id)}?{query}"
        )
        _, data, _ = connection.request("GET", url, location_id=location_id)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise HighLevelOAuthError(
                "HighLevel returned a non-JSON phone-number response."
            ) from exc
        if isinstance(payload, list):
            batch = payload
        elif isinstance(payload, dict):
            batch = payload.get("numbers")
            if batch is None:
                batch = payload.get("data")
            batch = batch if isinstance(batch, list) else []
        else:
            batch = []
        numbers.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100 or page > 50:
            break
        page += 1
    return numbers


def _number_status(record: dict) -> str:
    for key in ("active", "isActive", "status", "enabled"):
        if key in record:
            return str(record[key])
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Rediscover approved subaccounts before checking phone numbers",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to also write the full result as JSON",
    )
    args = parser.parse_args()

    connection = HighLevelConnection.from_environment()
    status = connection.status()
    if not status.get("connected"):
        print(
            "HighLevel agency is not connected: "
            f"{status.get('error', 'no token stored')}",
            file=sys.stderr,
        )
        return 2

    if args.refresh_catalog:
        catalog = connection.refresh_location_catalog()
    else:
        catalog = status.get("location_catalog") or []
        if not catalog:
            print(
                "No cached subaccount catalogue is stored. "
                "Re-run with --refresh-catalog.",
                file=sys.stderr,
            )
            return 2

    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
    results = []
    for location in sorted(catalog, key=lambda item: item.get("name", "")):
        location_id = str(location.get("id", "")).strip()
        name = location.get("name") or "(unnamed)"
        if not location_id:
            continue
        try:
            numbers = _fetch_location_numbers(connection, location_id)
            results.append(
                {
                    "location_id": location_id,
                    "location_name": name,
                    "coverage": "live",
                    "error": None,
                    "phone_numbers": [
                        {
                            "phone_number": item.get("phoneNumber")
                            or item.get("number")
                            or "",
                            "friendly_name": item.get("friendlyName")
                            or item.get("name")
                            or "",
                            "type": item.get("type") or item.get("numberType") or "",
                            "provider": item.get("provider") or "",
                            "status": _number_status(item),
                            "raw": item,
                        }
                        for item in numbers
                    ],
                }
            )
        except HighLevelOAuthError as exc:
            results.append(
                {
                    "location_id": location_id,
                    "location_name": name,
                    "coverage": "error",
                    "error": str(exc),
                    "phone_numbers": [],
                }
            )

    print(f"HighLevel phone-number status ({retrieved_at})")
    print(f"Company: {status.get('company_id')}\n")
    for entry in results:
        print(f"== {entry['location_name']} ({entry['location_id']}) ==")
        if entry["error"]:
            print(f"  ERROR: {entry['error']}")
            continue
        if not entry["phone_numbers"]:
            print("  No phone numbers found.")
            continue
        for number in entry["phone_numbers"]:
            label = number["friendly_name"] or number["type"] or "number"
            print(
                f"  {number['phone_number']:<16} "
                f"status={number['status']:<10} "
                f"provider={number['provider']:<10} "
                f"({label})"
            )
    print()

    if args.out:
        report = {
            "source_system": "HighLevel",
            "retrieved_at": retrieved_at,
            "company_id": status.get("company_id"),
            "endpoint": "/phone-system/numbers/location/{locationId}",
            "coverage": "partial" if any(item["error"] for item in results) else "live",
            "locations": results,
        }
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(f"Full result written to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
