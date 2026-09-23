"""HighLevel agency OAuth token management and authenticated API access."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API_ROOT = "https://services.leadconnectorhq.com"
TOKEN_URL = f"{API_ROOT}/oauth/token"
INSTALLED_LOCATIONS_URL = f"{API_ROOT}/oauth/installed-locations"
LOCATION_TOKEN_URL = f"{API_ROOT}/oauth/location-token"
DEFAULT_REDIRECT_URI = "http://localhost:8766/oauth/callback"
DEFAULT_INSTALLATION_URL = ""
DEFAULT_RESOURCE_VERSION = "2021-07-28"
DEFAULT_OAUTH_VERSION = "v3"
DEFAULT_RATE_LIMIT_RETRIES = 3
DEFAULT_USER_AGENT = "Brain-HighLevel-Access/1.0"


class HighLevelOAuthError(RuntimeError):
    """Raised when HighLevel authentication or an API request fails."""


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, bytes, dict[str, str]]:
    retries = max(
        0,
        int(os.getenv("GHL_RATE_LIMIT_RETRIES", str(DEFAULT_RATE_LIMIT_RETRIES))),
    )
    for attempt in range(retries + 1):
        request_headers = {"User-Agent": DEFAULT_USER_AGENT}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url,
            method=method,
            data=body,
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                data = response.read()
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            error_body = exc.read()
            detail = error_body.decode("utf-8", errors="replace")[:1000]
            if exc.code == 429 and attempt < retries:
                retry_after_value = exc.headers.get("Retry-After", "10")
                try:
                    retry_after = max(0.0, min(60.0, float(retry_after_value)))
                except ValueError:
                    retry_after = 10.0
                time.sleep(retry_after)
                continue
            # urllib raises on every 4xx and 5xx, so a caller that named an error
            # status in `expected` never saw it: the answer it asked for arrived as
            # an exception instead. A named status is an answer, not a failure - it
            # is how "no such record" and "no such object" are read (index readers
            # and its 404-tolerant callers). An unnamed one still raises.
            if exc.code in expected:
                return exc.code, error_body, dict(exc.headers.items())
            raise HighLevelOAuthError(
                f"HighLevel returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise HighLevelOAuthError(
                f"Could not reach HighLevel: {exc.reason}"
            ) from exc
        if status not in expected:
            snippet = data.decode("utf-8", errors="replace")[:300] if data else ""
            detail = f"HighLevel returned unexpected HTTP {status} for {method} {url}."
            if snippet:
                detail = f"{detail} Body: {snippet}"
            raise HighLevelOAuthError(detail)
        return status, data, response_headers
    raise HighLevelOAuthError("HighLevel request retry loop ended unexpectedly.")


def _credential_scripts_path() -> Path:
    return Path(__file__).resolve().parents[3] / "manage-credentials" / "scripts"


def _credential_modules() -> tuple[Any, Any, Any]:
    path = _credential_scripts_path()
    if not path.exists():
        raise HighLevelOAuthError(
            "The shared manage-credentials skill is unavailable."
        )
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        from portable_vault import (
            CredentialError,
            PortableVault,
            PortableVaultJsonStore,
        )
    except ImportError as exc:
        raise HighLevelOAuthError(
            "Could not load the shared portable-vault credential provider."
        ) from exc
    return CredentialError, PortableVault, PortableVaultJsonStore


def _vault_static_fields(entry: str, fields: list[str]) -> dict[str, Any]:
    CredentialError, PortableVault, _ = _credential_modules()
    scripts = Path(__file__).resolve().parents[3] / "manage-credentials" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from vault_broker_client import broker_request, broker_unlocked

        if broker_unlocked():
            values = broker_request("get_fields", entry=entry, fields=fields)
            if isinstance(values, dict):
                return values
    except Exception:
        pass
    passphrase = os.getenv("PORTABLE_VAULT_PASSPHRASE", "")
    if not passphrase:
        raise HighLevelOAuthError(
            "Vault Agent is locked/unavailable. "
            "Start the Portable Vault tray app and unlock it from the tray menu."
        )
    try:
        vault = PortableVault(os.getenv("PORTABLE_VAULT_PATH") or None)
        return vault.get_fields(entry, fields, passphrase)
    except CredentialError as exc:
        raise HighLevelOAuthError(str(exc)) from exc


def _portable_vault_token_store(entry: str, field: str) -> Any:
    CredentialError, _, PortableVaultJsonStore = _credential_modules()

    class HighLevelPortableVaultStore:
        def __init__(self) -> None:
            try:
                self.backend = PortableVaultJsonStore(
                    entry=entry,
                    field=field,
                    path=os.getenv("PORTABLE_VAULT_PATH") or None,
                )
            except CredentialError as exc:
                raise HighLevelOAuthError(str(exc)) from exc
            self.path = self.backend.path

        def load(self) -> dict[str, Any]:
            try:
                return self.backend.load()
            except CredentialError as exc:
                raise HighLevelOAuthError(str(exc)) from exc

        def save(self, value: dict[str, Any]) -> None:
            try:
                self.backend.save(value)
            except CredentialError as exc:
                raise HighLevelOAuthError(str(exc)) from exc

        def clear(self) -> None:
            try:
                self.backend.clear()
            except CredentialError as exc:
                raise HighLevelOAuthError(str(exc)) from exc

        def rotation_lock(self) -> Any:
            return self.backend.rotation_lock()

    return HighLevelPortableVaultStore()


def _rotation_lock(store: Any) -> Any:
    factory = getattr(store, "rotation_lock", None)
    return factory() if callable(factory) else nullcontext()


def _first(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def _normalise_token(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HighLevelOAuthError("HighLevel returned a malformed token response.")
    aliases = {
        "access_token": ("access_token", "accessToken"),
        "refresh_token": ("refresh_token", "refreshToken"),
        "token_type": ("token_type", "tokenType"),
        "expires_in": ("expires_in", "expiresIn"),
        "refresh_token_id": ("refreshTokenId", "refresh_token_id"),
        "user_type": ("userType", "user_type"),
        "company_id": ("companyId", "company_id"),
        "location_id": ("locationId", "location_id"),
        "user_id": ("userId", "user_id"),
        "approved_locations": ("approvedLocations", "approved_locations"),
        "install_to_future_locations": (
            "installToFutureLocations",
            "install_to_future_locations",
        ),
        "approve_all_locations": ("approveAllLocations", "approve_all_locations"),
        "is_bulk_installation": ("isBulkInstallation", "is_bulk_installation"),
    }
    consumed = {name for names in aliases.values() for name in names}
    token = {key: value for key, value in raw.items() if key not in consumed}
    for canonical, names in aliases.items():
        value = _first(raw, *names)
        if value is not None:
            token[canonical] = value
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    token["obtained_at"] = now
    try:
        expires_in = int(token.get("expires_in", 86400))
    except (TypeError, ValueError) as exc:
        raise HighLevelOAuthError(
            "HighLevel returned an invalid token expiry."
        ) from exc
    token["expires_in"] = expires_in
    token["expires_at"] = now + expires_in
    return token


def _validate_company_token(
    token: dict[str, Any],
    *,
    expected_company_id: str | None = None,
) -> None:
    if not token.get("access_token") or not token.get("refresh_token"):
        raise HighLevelOAuthError(
            "HighLevel did not return both access and refresh tokens."
        )
    if str(token.get("user_type", "")).casefold() != "company":
        raise HighLevelOAuthError(
            "HighLevel did not return a Company agency token. "
            "Verify that the app targets Agency users."
        )
    company_id = str(token.get("company_id", "")).strip()
    if not company_id:
        raise HighLevelOAuthError("HighLevel did not return a company ID.")
    if expected_company_id and company_id != expected_company_id:
        raise HighLevelOAuthError(
            "The refreshed HighLevel token belongs to a different agency."
        )


def _validate_api_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "services.leadconnectorhq.com"
        or parsed.username
        or parsed.password
    ):
        raise HighLevelOAuthError(
            "Authenticated HighLevel requests must use "
            "https://services.leadconnectorhq.com/."
        )


@dataclass
class HighLevelConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = DEFAULT_REDIRECT_URI
    installation_url: str = DEFAULT_INSTALLATION_URL
    resource_version: str = DEFAULT_RESOURCE_VERSION
    oauth_version: str = DEFAULT_OAUTH_VERSION
    vault_entry: str = "ghl-agency-oauth"
    vault_field: str = "oauth_token_json"

    @classmethod
    def from_environment(cls) -> "HighLevelConfig":
        entry = os.getenv("GHL_VAULT_ENTRY", "ghl-agency-oauth").strip()
        field = os.getenv("GHL_VAULT_FIELD", "oauth_token_json").strip()
        client_id = os.getenv("GHL_CLIENT_ID", "").strip()
        client_secret = os.getenv("GHL_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            values = _vault_static_fields(entry, ["client_id", "client_secret"])
            client_id = client_id or str(values["client_id"]).strip()
            client_secret = client_secret or str(values["client_secret"]).strip()
        if not client_id or not client_secret:
            raise HighLevelOAuthError(
                "The HighLevel client ID or client secret is empty."
            )
        redirect_uri = os.getenv(
            "GHL_REDIRECT_URI", DEFAULT_REDIRECT_URI
        ).strip()
        parsed_redirect = urllib.parse.urlparse(redirect_uri)
        if (
            parsed_redirect.scheme != "http"
            or parsed_redirect.hostname not in {"localhost", "127.0.0.1"}
            or parsed_redirect.path != "/oauth/callback"
            or parsed_redirect.query
            or parsed_redirect.fragment
        ):
            raise HighLevelOAuthError(
                "GHL_REDIRECT_URI must be a plain HTTP localhost callback "
                "ending in /oauth/callback."
            )
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            installation_url=os.getenv(
                "GHL_INSTALLATION_URL", DEFAULT_INSTALLATION_URL
            ).strip(),
            resource_version=os.getenv(
                "GHL_API_VERSION", DEFAULT_RESOURCE_VERSION
            ).strip(),
            oauth_version=os.getenv(
                "GHL_OAUTH_VERSION", DEFAULT_OAUTH_VERSION
            ).strip(),
            vault_entry=entry,
            vault_field=field,
        )


class HighLevelConnection:
    """Reusable, auto-refreshing HighLevel agency connection."""

    def __init__(self, config: HighLevelConfig, store: Any | None = None):
        self.config = config
        self.store = store or _portable_vault_token_store(
            config.vault_entry, config.vault_field
        )
        self._location_tokens: dict[str, dict[str, Any]] = {}
        # One minting at a time. A cache miss reaches the vault broker, and the broker's
        # Windows listener accepts one pending connection at a time, so callers that start
        # together - the test runner opens twenty checks at once - all miss, all connect, and
        # most are refused with "Vault Agent request failed". With this the first thread mints
        # and the rest wait a moment and find the token already there. The lock is here, in the
        # caller that stampedes, rather than in the credential broker.
        self._location_token_lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "HighLevelConnection":
        config = HighLevelConfig.from_environment()
        return cls(config)

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        # HighLevel OAuth token endpoints may return 201 Created.
        _, data, _ = _request(
            "POST",
            TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Version": self.config.oauth_version,
            },
            body=urllib.parse.urlencode(fields).encode(),
            expected=(200, 201),
        )
        try:
            return _normalise_token(json.loads(data))
        except json.JSONDecodeError as exc:
            raise HighLevelOAuthError(
                "HighLevel returned a non-JSON token response."
            ) from exc

    def exchange_code(self, code: str) -> dict[str, Any]:
        token = self._token_request(
            {
                "clientId": self.config.client_id,
                "clientSecret": self.config.client_secret,
                "grantType": "authorization_code",
                "code": code,
                "userType": "Company",
                "redirectUri": self.config.redirect_uri,
            }
        )
        _validate_company_token(token)
        with _rotation_lock(self.store):
            self.store.save(token)
        self._location_tokens.clear()
        return token

    def refresh(self) -> dict[str, Any]:
        with _rotation_lock(self.store):
            current = self.store.load()
            refresh_token = str(current.get("refresh_token", "")).strip()
            if not refresh_token:
                raise HighLevelOAuthError(
                    "No HighLevel refresh token is stored. Connect the agency first."
                )
            company_id = str(current.get("company_id", "")).strip()
            updated = self._token_request(
                {
                    "clientId": self.config.client_id,
                    "clientSecret": self.config.client_secret,
                    "grantType": "refresh_token",
                    "refreshToken": refresh_token,
                    "userType": "Company",
                    "redirectUri": self.config.redirect_uri,
                }
            )
            _validate_company_token(updated, expected_company_id=company_id)
            for field in (
                "approved_locations",
                "approve_all_locations",
                "install_to_future_locations",
                "is_bulk_installation",
                "location_catalog",
                "location_catalog_refreshed_at",
                "location_discovery_warning",
            ):
                if field not in updated and field in current:
                    updated[field] = current[field]
            self.store.save(updated)
        self._location_tokens.clear()
        return updated

    def company_access_token(self, leeway_seconds: int = 90) -> str:
        token = self.store.load()
        if not token.get("access_token"):
            raise HighLevelOAuthError("HighLevel agency access is not connected.")
        _validate_company_token(token)
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if float(token.get("expires_at", 0)) <= now + leeway_seconds:
            token = self.refresh()
        return str(token["access_token"])

    def _agency_request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
        oauth_endpoint: bool = False,
    ) -> tuple[int, bytes, dict[str, str]]:
        _validate_api_url(url)
        request_headers = {
            "Authorization": f"Bearer {self.company_access_token()}",
            "Accept": "application/json",
            "Version": (
                self.config.oauth_version
                if oauth_endpoint
                else self.config.resource_version
            ),
        }
        request_headers.update(headers or {})
        return _request(
            method,
            url,
            headers=request_headers,
            body=body,
            expected=expected,
        )

    @staticmethod
    def _location_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("locations", "installedLocations", "installed_locations", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = HighLevelConnection._location_records(value)
                if nested:
                    return nested
        return []

    @staticmethod
    def _location_id(record: dict[str, Any]) -> str:
        return str(
            _first(record, "id", "locationId", "location_id") or ""
        ).strip()

    def refresh_location_catalog(self) -> list[dict[str, Any]]:
        token = self.store.load()
        _validate_company_token(token)
        granted_scopes = set(str(token.get("scope", "")).split())
        records: dict[str, dict[str, Any]] = {}
        company_profile: dict[str, Any] = {}
        approved = token.get("approved_locations") or []
        if isinstance(approved, list):
            for location_id in approved:
                clean_id = str(location_id).strip()
                if clean_id:
                    records[clean_id] = {"id": clean_id}

        warnings: list[str] = []
        if "companies.readonly" in granted_scopes:
            try:
                company_id = urllib.parse.quote(str(token["company_id"]))
                _, data, _ = self._agency_request(
                    "GET",
                    f"{API_ROOT}/companies/{company_id}",
                    headers={"Version": self.config.oauth_version},
                )
                company_payload = json.loads(data)
                company = (
                    company_payload.get("company")
                    if isinstance(company_payload, dict)
                    else None
                )
                if isinstance(company, dict):
                    company_profile = company
            except (HighLevelOAuthError, json.JSONDecodeError) as exc:
                warnings.append(f"Company lookup: {exc}")

        if "locations.readonly" in granted_scopes:
            skip = 0
            limit = 100
            for _ in range(1000):
                query = urllib.parse.urlencode(
                    {
                        "companyId": token["company_id"],
                        "skip": skip,
                        "limit": limit,
                    }
                )
                try:
                    _, data, _ = self._agency_request(
                        "GET",
                        f"{API_ROOT}/locations/search?{query}",
                        headers={"Version": self.config.oauth_version},
                    )
                    discovered = self._location_records(json.loads(data))
                except (HighLevelOAuthError, json.JSONDecodeError) as exc:
                    warnings.append(f"Subaccount search: {exc}")
                    break
                if not discovered:
                    break
                new_ids = 0
                for record in discovered:
                    location_id = self._location_id(record)
                    if location_id:
                        if location_id not in records:
                            new_ids += 1
                        records[location_id] = {
                            **records.get(location_id, {}),
                            **record,
                        }
                if len(discovered) < limit:
                    break
                if not new_ids:
                    warnings.append(
                        "Subaccount search pagination repeated a page; "
                        "the catalogue may be partial."
                    )
                    break
                skip += len(discovered)
            else:
                warnings.append(
                    "Subaccount search exceeded the pagination safety limit."
                )

        if "oauth.readonly" in granted_scopes:
            try:
                installed_query = urllib.parse.urlencode(
                    {"companyId": token["company_id"], "limit": 100}
                )
                _, data, _ = self._agency_request(
                    "GET",
                    f"{INSTALLED_LOCATIONS_URL}?{installed_query}",
                    oauth_endpoint=True,
                )
                discovered = self._location_records(json.loads(data))
                for record in discovered:
                    location_id = self._location_id(record)
                    if location_id:
                        records[location_id] = {**records.get(location_id, {}), **record}
            except (HighLevelOAuthError, json.JSONDecodeError) as exc:
                warnings.append(str(exc))

        if "locations.readonly" in granted_scopes:
            for location_id in list(records):
                try:
                    _, data, _ = self._agency_request(
                        "GET",
                        f"{API_ROOT}/locations/{urllib.parse.quote(location_id)}",
                    )
                    detail_payload = json.loads(data)
                    detail = (
                        detail_payload.get("location")
                        if isinstance(detail_payload, dict)
                        else None
                    )
                    if isinstance(detail, dict):
                        records[location_id] = {
                            **records.get(location_id, {}),
                            **detail,
                        }
                except (HighLevelOAuthError, json.JSONDecodeError) as exc:
                    warnings.append(f"{location_id}: {exc}")

        catalog = []
        for location_id, record in sorted(records.items()):
            catalog.append(
                {
                    "id": location_id,
                    "name": str(
                        _first(record, "name", "locationName", "location_name") or ""
                    ),
                    "company_id": str(
                        _first(record, "companyId", "company_id")
                        or token.get("company_id", "")
                    ),
                }
            )
        with _rotation_lock(self.store):
            latest = self.store.load()
            if company_profile:
                latest["company_profile"] = company_profile
            latest["location_catalog"] = catalog
            latest["location_catalog_refreshed_at"] = (
                dt.datetime.now(dt.timezone.utc).isoformat()
            )
            if warnings:
                latest["location_discovery_warning"] = "; ".join(warnings)[:2000]
            else:
                latest.pop("location_discovery_warning", None)
            self.store.save(latest)
        return catalog

    def location_access_token(
        self,
        location_id: str,
        *,
        leeway_seconds: int = 90,
    ) -> str:
        location_id = location_id.strip()
        if not location_id:
            raise HighLevelOAuthError("A HighLevel location ID is required.")
        def fresh() -> str | None:
            cached = self._location_tokens.get(location_id)
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            if cached and float(cached.get("expires_at", 0)) > now + leeway_seconds:
                return str(cached["access_token"])
            return None

        hit = fresh()
        if hit is not None:
            return hit
        with self._location_token_lock:
            # Checked again inside the lock: while this thread waited, the one holding it
            # probably minted the very token being asked for.
            hit = fresh()
            if hit is not None:
                return hit
            return self._mint_location_token(location_id)

    def _mint_location_token(self, location_id: str) -> str:
        company = self.store.load()
        _validate_company_token(company)
        payload = json.dumps(
            {
                "companyId": company["company_id"],
                "locationId": location_id,
            },
            separators=(",", ":"),
        ).encode()
        # Location-token mint is a create-style POST; HighLevel has been
        # observed returning HTTP 201 here. That status was previously
        # rejected (default expected=200 only) and surfaced to callers as
        # "Could not list existing Custom Values: ... unexpected HTTP 201"
        # because list_* helpers request with location_id and mint first.
        _, data, _ = self._agency_request(
            "POST",
            LOCATION_TOKEN_URL,
            body=payload,
            headers={"Content-Type": "application/json"},
            oauth_endpoint=True,
            expected=(200, 201),
        )
        try:
            token = _normalise_token(json.loads(data))
        except json.JSONDecodeError as exc:
            raise HighLevelOAuthError(
                "HighLevel returned a non-JSON location-token response."
            ) from exc
        if str(token.get("user_type", "")).casefold() != "location":
            raise HighLevelOAuthError(
                "HighLevel did not return a Location token."
            )
        if str(token.get("location_id", "")) != location_id:
            raise HighLevelOAuthError(
                "HighLevel returned a token for a different location."
            )
        if str(token.get("company_id", "")) != str(company["company_id"]):
            raise HighLevelOAuthError(
                "HighLevel returned a location token for a different agency."
            )
        if not token.get("access_token"):
            raise HighLevelOAuthError(
                "HighLevel did not return a location access token."
            )
        self._location_tokens[location_id] = token
        return str(token["access_token"])

    def request(
        self,
        method: str,
        url: str,
        *,
        location_id: str | None = None,
        accept: str = "application/json",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes, dict[str, str]]:
        _validate_api_url(url)
        token = (
            self.location_access_token(location_id)
            if location_id
            else self.company_access_token()
        )
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "Version": self.config.resource_version,
        }
        request_headers.update(headers or {})
        return _request(
            method,
            url,
            headers=request_headers,
            body=body,
            expected=expected,
        )

    def status(self) -> dict[str, Any]:
        token = self.store.load()
        if not token.get("access_token"):
            return {
                "connected": False,
                "redirect_uri": self.config.redirect_uri,
                "token_store": str(self.store.path),
            }
        try:
            _validate_company_token(token)
            self.company_access_token()
            token = self.store.load()
            return {
                "connected": True,
                "company_id": token.get("company_id"),
                "company_profile": token.get("company_profile") or {},
                "user_type": token.get("user_type"),
                "scope": token.get("scope", ""),
                "approved_locations": token.get("approved_locations") or [],
                "approve_all_locations": token.get("approve_all_locations"),
                "install_to_future_locations": token.get(
                    "install_to_future_locations"
                ),
                "is_bulk_installation": token.get("is_bulk_installation"),
                "location_catalog": token.get("location_catalog") or [],
                "location_catalog_refreshed_at": token.get(
                    "location_catalog_refreshed_at"
                ),
                "location_discovery_warning": token.get(
                    "location_discovery_warning"
                ),
                "expires_at": token.get("expires_at"),
                "redirect_uri": self.config.redirect_uri,
                "token_store": str(self.store.path),
            }
        except HighLevelOAuthError as exc:
            return {
                "connected": False,
                "error": str(exc),
                "redirect_uri": self.config.redirect_uri,
                "token_store": str(self.store.path),
            }

    def clear_local_authorisation(self) -> None:
        self.store.clear()
        self._location_tokens.clear()
