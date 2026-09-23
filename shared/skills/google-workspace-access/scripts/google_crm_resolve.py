"""Resolve Personal CRM contact → persona → google_account_alias."""

from __future__ import annotations

import argparse
import sys

from _cli_common import add_crm_args, print_json
from google_oauth.crm import GoogleCrmError, resolve_for_side_effect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_crm_args(parser)
    parser.add_argument(
        "--account",
        help="Optional explicit Google account alias to cross-check against persona",
    )
    parser.add_argument(
        "--allow-missing-contact",
        action="store_true",
        help="Allow resolution without a contact match (persona/account only)",
    )
    args = parser.parse_args()
    try:
        resolution = resolve_for_side_effect(
            contact_id=args.contact_id,
            email=args.contact_email,
            name=args.contact_name,
            persona_key=args.persona,
            account_alias=args.account,
            allow_missing_contact=args.allow_missing_contact,
        )
    except GoogleCrmError as exc:
        print(f"CRM resolve error: {exc}", file=sys.stderr)
        return 2
    print_json(resolution.as_dict())
    return 3 if resolution.confirmation_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
