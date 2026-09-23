"""Start the Portable AI Brain Google Workspace OAuth connection manager."""

import sys

from google_oauth import GoogleOAuthError
from google_oauth.server import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GoogleOAuthError as exc:
        print(f"Google connection error: {exc}", file=sys.stderr)
        raise SystemExit(2)
