"""List the connected HighLevel agency and its cached approved subaccounts.

Run from inside the active credential-aware PowerShell session:

    python shared/skills/gohighlevel-access/scripts/ghl_subaccounts.py

Reads the existing cached ``location_catalog`` on the stored agency token.
Does not call HighLevel or refresh the catalogue; pass --refresh to
rediscover subaccounts live instead.
"""

from __future__ import annotations

import argparse
import sys

from ghl_oauth import HighLevelConnection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rediscover approved subaccounts live instead of using the cache",
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

    if args.refresh:
        catalog = connection.refresh_location_catalog()
        refreshed_at = "just now"
    else:
        catalog = status.get("location_catalog") or []
        refreshed_at = status.get("location_catalog_refreshed_at") or "never"

    company = status.get("company_profile") or {}
    print(
        f"Agency: {company.get('name', '(unknown name)')} "
        f"(company_id={status.get('company_id')})"
    )
    print(f"Subaccount catalogue last refreshed: {refreshed_at}")
    warning = status.get("location_discovery_warning")
    if warning:
        print(f"Discovery warning: {warning}")
    print(f"\n{len(catalog)} approved subaccount(s):\n")
    for location in sorted(catalog, key=lambda item: item.get("name", "")):
        print(f"  {location.get('name', '(unnamed)'):<40} {location.get('id', '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
