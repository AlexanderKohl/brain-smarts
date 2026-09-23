"""Shared argparse and output helpers for Google Workspace CLIs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def add_account_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--account",
        help="Google account alias (or set GOOGLE_ACCOUNT_ALIAS)",
    )


def add_crm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contact-id", help="CRM contact id, e.g. contact-jane-doe")
    parser.add_argument("--contact-email", help="Lookup CRM contact by email")
    parser.add_argument("--contact-name", help="Lookup CRM contact by name")
    parser.add_argument("--persona", help="persona_key override")
    parser.add_argument(
        "--confirm-target",
        action="store_true",
        help="Owner confirmed the CRM persona/account target for this side effect",
    )


def _ensure_utf8_stdout() -> None:
    """Avoid Windows cp1252 UnicodeEncodeError on emoji/non-ASCII JSON."""
    stdout = sys.stdout
    reconfigure = getattr(stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
            return
        except Exception:
            pass
    buffer = getattr(stdout, "buffer", None)
    if buffer is not None:
        import io

        sys.stdout = io.TextIOWrapper(
            buffer, encoding="utf-8", errors="replace", line_buffering=True
        )


def print_json(value: Any) -> None:
    _ensure_utf8_stdout()
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def require_side_effect_confirmation(
    *,
    confirm_target: bool,
    resolution: Any,
) -> None:
    payload = resolution.as_dict()
    if resolution.confirmation_required and not confirm_target:
        print_json(
            {
                "error": "CRM target confirmation required before side effects "
                "(CONTRACT §10.5).",
                "resolution": payload,
            }
        )
        raise SystemExit(3)
    if not confirm_target:
        print(
            "Refusing side effect without --confirm-target after CRM resolution.",
            file=sys.stderr,
        )
        print_json({"resolution": payload})
        raise SystemExit(3)
    if resolution.account is None:
        print_json(
            {
                "error": "No Google account alias resolved from CRM persona.",
                "resolution": payload,
            }
        )
        raise SystemExit(3)


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent
