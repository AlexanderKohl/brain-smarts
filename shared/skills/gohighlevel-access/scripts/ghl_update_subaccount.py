"""Update an existing HighLevel sub-account (Location) under the connected agency.

Run from inside the active credential-aware PowerShell session (see
/shared/skills/gohighlevel-access/SKILL.md and /shared/skills/manage-credentials/SKILL.md):

    python shared/skills/gohighlevel-access/scripts/ghl_update_subaccount.py --name "Example Test Co" --city "Exampletown" --state "Example State" --country AU --postal-code 0000 --timezone Australia/Sydney

Identify the target sub-account with either --location-id or --name (looked
up in the cached, or freshly rediscovered with --refresh-catalog, subaccount
catalogue). Requires the same 'locations.write' scope as sub-account
creation. Prints the exact payload and asks for interactive confirmation
before sending the request, unless --yes is passed. Does not retry
automatically on failure.
"""

from __future__ import annotations

import argparse
import json
import sys

from ghl_oauth import HighLevelConnection, HighLevelOAuthError
from ghl_oauth.client import API_ROOT


def _resolve_location_id(connection: HighLevelConnection, status: dict, args: argparse.Namespace) -> str:
    if args.location_id:
        return args.location_id.strip()

    if not args.name:
        print("Provide either --location-id or --name.", file=sys.stderr)
        raise SystemExit(2)

    if args.refresh_catalog:
        catalog = connection.refresh_location_catalog()
    else:
        catalog = status.get("location_catalog") or []

    matches = [item for item in catalog if item.get("name") == args.name]
    if not matches:
        print(
            f"No cached sub-account named {args.name!r} was found. "
            "Re-run with --refresh-catalog, or pass --location-id directly.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if len(matches) > 1:
        print(
            f"Multiple sub-accounts are named {args.name!r}; pass --location-id "
            "to disambiguate:",
            file=sys.stderr,
        )
        for item in matches:
            print(f"  {item.get('id')}", file=sys.stderr)
        raise SystemExit(2)
    return str(matches[0]["id"])


def _build_payload(args: argparse.Namespace, company_id: str) -> dict:
    payload: dict = {"companyId": company_id}
    optional_fields = {
        "name": args.new_name,
        "phone": args.phone,
        "address": args.address,
        "city": args.city,
        "state": args.state,
        "country": args.country,
        "postalCode": args.postal_code,
        "website": args.website,
        "timezone": args.timezone,
    }
    for key, value in optional_fields.items():
        if value:
            payload[key] = value
    if args.prospect_first_name or args.prospect_last_name or args.prospect_email:
        payload["prospectInfo"] = {
            key: value
            for key, value in {
                "firstName": args.prospect_first_name,
                "lastName": args.prospect_last_name,
                "email": args.prospect_email,
            }.items()
            if value
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location-id", default="", help="Target sub-account ID")
    parser.add_argument("--name", default="", help="Target sub-account name (looked up in the catalogue)")
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--new-name", default="", help="Rename the sub-account")
    parser.add_argument("--phone", default="")
    parser.add_argument("--address", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--country", default="", help="2-letter country code, e.g. AU")
    parser.add_argument("--postal-code", default="")
    parser.add_argument("--website", default="")
    parser.add_argument("--timezone", default="", help="e.g. Australia/Brisbane")
    parser.add_argument("--prospect-first-name", default="")
    parser.add_argument("--prospect-last-name", default="")
    parser.add_argument("--prospect-email", default="")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
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

    granted_scopes = set(str(status.get("scope", "")).split())
    if "locations.write" not in granted_scopes:
        print(
            "The connected HighLevel app grant does not include the "
            "'locations.write' scope, so updating a sub-account would be an "
            "uncertain write. Granted scopes: "
            f"{status.get('scope', '(none)')}",
            file=sys.stderr,
        )
        return 3

    company_id = str(status.get("company_id", "")).strip()
    if not company_id:
        print("Could not determine the connected agency's company ID.", file=sys.stderr)
        return 2

    location_id = _resolve_location_id(connection, status, args)
    payload = _build_payload(args, company_id)
    if len(payload) <= 1:
        print("No fields to update were supplied.", file=sys.stderr)
        return 2

    print(f"About to update sub-account {location_id} with:")
    print(json.dumps(payload, indent=2))
    if not args.yes:
        confirmation = input(f"Type the sub-account ID ({location_id!r}) to confirm: ")
        if confirmation != location_id:
            print("Confirmation did not match; no request was sent.", file=sys.stderr)
            return 1

    try:
        _, data, _ = connection.request(
            "PUT",
            f"{API_ROOT}/locations/{location_id}",
            body=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json"},
            expected=(200,),
        )
    except HighLevelOAuthError as exc:
        print(f"Sub-account update failed: {exc}", file=sys.stderr)
        print(
            "Do not retry automatically; reconcile with the HighLevel agency "
            "dashboard before attempting again.",
            file=sys.stderr,
        )
        return 4

    try:
        updated = json.loads(data)
    except json.JSONDecodeError:
        print("HighLevel returned a non-JSON response for the update.", file=sys.stderr)
        print(data.decode("utf-8", errors="replace"))
        return 4

    location = updated.get("location") if isinstance(updated, dict) else updated
    if isinstance(location, dict):
        print(f"Updated sub-account: {location.get('name', '')} (id={location_id})")
    else:
        print("Sub-account update request succeeded. Raw response:")
        print(json.dumps(updated, indent=2))

    print(
        "Reminder: run 'python shared/skills/gohighlevel-access/scripts/"
        "ghl_subaccounts.py --refresh' to refresh the cached subaccount "
        "catalogue."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
