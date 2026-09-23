"""Start the Portable AI Brain Xero OAuth connection manager."""

import sys

from xero_oauth import XeroOAuthError
from xero_oauth.server import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except XeroOAuthError as exc:
        print(f"Xero connection error: {exc}", file=sys.stderr)
        raise SystemExit(2)
