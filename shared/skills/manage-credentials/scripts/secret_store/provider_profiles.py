"""Provider profiles (design synced-secrets-repository.md, section 9): what is known about each
provider's rotating sign-ins, and which fields of a token record belong in the grant object. A
profile counts only when verified is true (the provider's documentation and a live test); until
then handover and recovery from an uncertain refresh are refused with a plain message."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import SecretStoreError

DATA_FILE = Path(__file__).with_name("provider_profiles.json")
FIXED_GRANT_FIELDS = frozenset({"clientSecret", "client_secret", "id_token", "refreshToken", "refresh_token"})
DEFAULT_GRANT_FIELDS = FIXED_GRANT_FIELDS | frozenset({"refresh_token_expires_at", "refresh_token_expires_in"})
DEFAULT_TOKEN_FIELDS = frozenset({"access_token", "accessToken", "expires_at", "expiresAt", "token_type", "scope",
                                  "expires_in"})


@lru_cache(maxsize=1)
def profiles() -> dict[str, Any]:
    try:
        data = json.loads(DATA_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        raise SecretStoreError("the provider profiles file cannot be read") from None
    found = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(found, dict):
        raise SecretStoreError("the provider profiles file has no profiles")
    return found


def provider_for(entry: str | None) -> str | None:
    """The provider an entry name points to (xero, google, gohighlevel, meta), or None."""
    name = str(entry or "").lower()
    for key, profile in profiles().items():
        if any(word in name for word in profile.get("match", [key])):
            return key
    return None


def profile(provider: str | None) -> dict[str, Any] | None:
    return profiles().get(provider) if provider else None


def grant_fields(provider: str | None = None) -> frozenset:
    """Fields only the refresher computer and the recovery key read: the fixed list plus every
    profile's grant_fields_extra, the same for every entry and provider (conservative: a spelling
    one provider uses is grant-only everywhere, so no entry name can expose it)."""
    extra = frozenset(f for found in profiles().values() for f in found.get("grant_fields_extra", []))
    return DEFAULT_GRANT_FIELDS | extra


def token_fields(provider: str | None) -> frozenset:
    """Access-token fields only the refresher changes (section 7, plus the provider's overrides),
    never a grant field."""
    return (DEFAULT_TOKEN_FIELDS | frozenset((profile(provider) or {}).get("token_fields_extra", []))) - grant_fields()


def verified(provider: str | None) -> bool:
    found = profile(provider)
    return bool(found and found.get("verified") is True)


def recovery_refusal(provider: str | None) -> str | None:
    """None when the provider's profile allows handover and uncertain-refresh recovery, else the
    plain message the agent shows."""
    if verified(provider):
        return None
    found = profile(provider)
    if found is None:
        return ("This sign-in's provider has no provider profile, so there is no handover to another "
                "computer and no recovery from an uncertain refresh: the entry stays blocked.")
    return (f"{found.get('label', provider)} has no verified provider profile, so there is no handover to "
            "another computer and no recovery from an uncertain refresh: the entry stays blocked until a "
            "profile is verified from the provider's documentation and a live test.")


handover_refusal = recovery_refusal
