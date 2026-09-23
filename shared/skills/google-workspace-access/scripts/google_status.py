"""Print connection status for a named Google account alias."""

from __future__ import annotations

import argparse
import sys

from _cli_common import add_account_arg, print_json
from google_oauth import GoogleConnection, GoogleOAuthError
from google_oauth.accounts import GoogleAccountError, list_accounts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_account_arg(parser)
    parser.add_argument(
        "--list-accounts",
        action="store_true",
        help="List registry aliases without calling Google",
    )
    args = parser.parse_args()

    try:
        if args.list_accounts:
            print_json(
                [
                    {
                        "alias": item.alias,
                        "email": item.email,
                        "vault_entry": item.vault_entry,
                        "status": item.status,
                        "used_by_personas": item.used_by_personas,
                    }
                    for item in list_accounts()
                ]
            )
            return 0
        connection = GoogleConnection.from_environment(args.account)
        print_json(connection.status())
        return 0
    except (GoogleOAuthError, GoogleAccountError) as exc:
        print(f"Google status error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
