"""Create a new HighLevel sub-account (Location) under the connected agency.

Run from inside the active credential-aware PowerShell session (see
/shared/skills/gohighlevel-access/SKILL.md and /shared/skills/manage-credentials/SKILL.md):

    python shared/skills/gohighlevel-access/scripts/ghl_create_subaccount.py --name "Test Creation"

This is an explicit, owner-authorised CRM write per the skill's permissions.
The HighLevel API only strictly requires ``name`` and ``companyId`` to create
a sub-account (``companyId`` is taken from the connected agency token
automatically); every other field below is optional. Requires the agency
app grant to include the ``locations.write`` scope and an Agency Pro plan;
the script fails closed with a clear message if the scope is missing rather
than attempting an uncertain write.
"""

from __future__ import annotations

import argparse
import json
import sys

from ghl_oauth import HighLevelConnection, HighLevelOAuthError
from ghl_oauth.client import API_ROOT


def _build_payload(args: argparse.Namespace, company_id: str) -> dict:
    payload: dict = {"name": args.name, "companyId": company_id}
    optional_fields = {
        "phone": args.phone,
        "address": args.address,
        "city": args.city,
        "state": args.state,
        "country": args.country,
        "postalCode": args.postal_code,
        "website": args.website,
        "timezone": args.timezone,
        "snapshotId": args.snapshot_id,
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
    parser.add_argument("--name", required=True, help="Sub-account name (required)")
    parser.add_argument("--phone", default="", help="Phone number with country code")
    parser.add_argument("--address", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--country", default="", help="2-letter country code, e.g. AU")
    parser.add_argument("--postal-code", default="")
    parser.add_argument("--website", default="")
    parser.add_argument("--timezone", default="", help="e.g. Australia/Brisbane")
    parser.add_argument("--snapshot-id", default="", help="Snapshot to load into the new sub-account")
    parser.add_argument("--prospect-first-name", default="")
    parser.add_argument("--prospect-last-name", default="")
    parser.add_argument("--prospect-email", default="")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt",
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

    granted_scopes = set(str(status.get("scope", "")).split())
    if "locations.write" not in granted_scopes:
        print(
            "The connected HighLevel app grant does not include the "
            "'locations.write' scope, so creating a sub-account would be an "
            "uncertain write. Add 'locations.write' in the Marketplace app's "
            "Auth pane and reconnect the agency (see SKILL.md 'Connect the "
            "agency'), then re-run this script. Granted scopes: "
            f"{status.get('scope', '(none)')}",
            file=sys.stderr,
        )
        return 3

    company_id = str(status.get("company_id", "")).strip()
    if not company_id:
        print("Could not determine the connected agency's company ID.", file=sys.stderr)
        return 2

    payload = _build_payload(args, company_id)

    print("About to create a new HighLevel sub-account with:")
    print(json.dumps(payload, indent=2))
    if not args.yes:
        confirmation = input(f"Type the sub-account name ({args.name!r}) to confirm: ")
        if confirmation != args.name:
            print("Confirmation did not match; no request was sent.", file=sys.stderr)
            return 1

    try:
        _, data, _ = connection.request(
            "POST",
            f"{API_ROOT}/locations/",
            body=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json"},
            expected=(200, 201),
        )
    except HighLevelOAuthError as exc:
        print(f"Sub-account creation failed: {exc}", file=sys.stderr)
        print(
            "Do not retry automatically; reconcile with the HighLevel agency "
            "dashboard before attempting again.",
            file=sys.stderr,
        )
        return 4

    try:
        created = json.loads(data)
    except json.JSONDecodeError:
        print("HighLevel returned a non-JSON response for the new sub-account.", file=sys.stderr)
        print(data.decode("utf-8", errors="replace"))
        return 4

    location = created.get("location") if isinstance(created, dict) else created
    if isinstance(location, dict):
        print(
            "Created sub-account: "
            f"{location.get('name', args.name)} (id={location.get('id', '(unknown)')})"
        )
    else:
        print("Sub-account creation request succeeded. Raw response:")
        print(json.dumps(created, indent=2))

    print(
        "Reminder: run 'python shared/skills/gohighlevel-access/scripts/"
        "ghl_subaccounts.py --refresh' to refresh the cached subaccount "
        "catalogue so this new sub-account appears in future listings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
