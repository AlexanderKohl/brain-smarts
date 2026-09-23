"""Start the brain's HighLevel agency connection manager."""

import sys

from ghl_oauth import HighLevelOAuthError
from ghl_oauth.server import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HighLevelOAuthError as exc:
        print(f"HighLevel connection error: {exc}", file=sys.stderr)
        raise SystemExit(2)
