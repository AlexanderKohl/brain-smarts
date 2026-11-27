"""Step 2 of design 10.1: the old secret revoked at the provider, and shown dead, before the relay
serves the new one. The revocation call is sorted as a refresh is (section 9): not sent, the old
secret still works; refused or proved dead, the state moves on; uncertain, the probe decides and the
old refresh token is never sent again. The old values are held in this process's memory only.

Google: the revocation endpoint is called with the old refresh token, which also ends every access
token made from it; an answer of success counts as the proof, and so does the token endpoint's own
`invalid_token` (already dead). The probe uses the old sign-in's own access token, read from the
store with the grant and only while it has not expired (no refresh is made for it, so the old
refresh token goes out only once, to the revocation endpoint), and asks Google's token information
endpoint about it; HTTP 400 there means dead. Other providers: the
command names the step to take in the provider's own pages, then probes where it can."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from secret_store.journal import ProviderNotCalled, ProviderRefused
from token_endpoint import post_token

GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
MANUAL_STEPS = {
    "highlevel": "uninstall the old installation of the app in HighLevel (Marketplace, installed apps)",
    "meta": "remove the old user token's access to the app in Business Settings (System users / Apps)",
    "wordpress": "delete the old application password in the site's admin (Users, Profile, Application Passwords)",
}


@dataclass
class Outcome:
    state: str  # "dead", "alive" (not sent) or "uncertain"
    detail: str


def find_token(record: Any, name: str) -> str | None:
    """The first text value of name in a sign-in record, at any depth (records nest the token JSON)."""
    if isinstance(record, dict):
        value = record.get(name)
        if isinstance(value, str) and value:
            return value
        for item in record.values():
            if isinstance(item, str) and item.startswith("{"):
                try:
                    item = json.loads(item)
                except ValueError:
                    continue
            found = find_token(item, name)
            if found:
                return found
    return None


def google_revoke(refresh_token: str, post: Callable = post_token) -> Outcome:
    try:
        post(GOOGLE_REVOKE, {}, {"token": refresh_token})
    except ProviderNotCalled:
        return Outcome("alive", "the revocation was not sent (no connection); the old sign-in still works")
    except ProviderRefused as refused:
        if refused.error in ("invalid_token", "invalid_grant"):
            return Outcome("dead", "Google refused the old token as already invalid")
        return Outcome("uncertain", f"Google refused the revocation ({refused.error[:60]})")
    except Exception:  # noqa: BLE001 - an answer that may or may not have revoked it
        return Outcome("uncertain", "the revocation's answer was lost or unclear")
    return Outcome("dead", "Google confirmed the revocation")


def google_probe(access_token: str | None, get: Callable[[str], int]) -> Outcome:
    """Ask Google about an old access token: HTTP 400 means it, and the grant it came from, are dead."""
    if not access_token:
        return Outcome("uncertain", "no old access token was kept to probe with")
    status = get(GOOGLE_TOKENINFO + "?" + urllib.parse.urlencode({"access_token": access_token}))
    if status == 400:
        return Outcome("dead", "Google no longer knows the old access token")
    if status == 200:
        return Outcome("alive", "the old access token still works; the revocation did not take")
    return Outcome("uncertain", f"the probe answered HTTP {status}")


def http_status(url: str) -> int:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - a fixed Google https address
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return 0
