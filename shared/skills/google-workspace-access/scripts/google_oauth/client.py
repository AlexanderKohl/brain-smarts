"""Google Workspace OAuth token management and authenticated API access."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .accounts import (
    GoogleAccount,
    GoogleAccountError,
    get_account,
    resolve_alias,
    resolve_vault_entry,
)


AUTHORISE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
DEFAULT_REDIRECT_URI = "http://localhost:8767/oauth/callback"
DEFAULT_USER_AGENT = "Portable-AI-Brain-GoogleWorkspace/1.0"

# First-cut scopes: draft-capable Gmail, Calendar/Tasks writes, Drive read +
# app-created file writes, Contacts read/write. Send is gated in CLI even though
# gmail.modify includes API send capability. No delete/trash helpers shipped.
# `contacts` includes read; do not also request `contacts.readonly`.
DEFAULT_SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/contacts",
)

# Google may return OIDC shorthand or full userinfo URLs interchangeably.
_SCOPE_ALIASES: dict[str, frozenset[str]] = {
    "email": frozenset(
        {"email", "https://www.googleapis.com/auth/userinfo.email"}
    ),
    "https://www.googleapis.com/auth/userinfo.email": frozenset(
        {"email", "https://www.googleapis.com/auth/userinfo.email"}
    ),
    "profile": frozenset(
        {"profile", "https://www.googleapis.com/auth/userinfo.profile"}
    ),
    "https://www.googleapis.com/auth/userinfo.profile": frozenset(
        {"profile", "https://www.googleapis.com/auth/userinfo.profile"}
    ),
}


def _scope_granted(required: str, granted: set[str]) -> bool:
    """Return True if required scope is present, including OIDC userinfo aliases."""
    aliases = _SCOPE_ALIASES.get(required)
    if aliases is not None:
        return bool(granted & aliases)
    return required in granted


def missing_scopes(requested: list[str] | tuple[str, ...], granted: list[str] | tuple[str, ...]) -> list[str]:
    """List requested scopes not satisfied by granted scopes (alias-aware)."""
    granted_set = {scope for scope in granted if scope}
    return [scope for scope in requested if scope and not _scope_granted(scope, granted_set)]


class GoogleOAuthError(RuntimeError):
    """Raised when Google authentication or an authenticated request fails."""


def default_token_path(alias: str) -> Path:
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in alias.strip()
    ) or "default"
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "CodexIntegrations" / "google-workspace-oauth" / f"{safe}.json"
    return Path.home() / ".local" / "share" / "google-workspace-oauth" / f"{safe}.json"


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, bytes, dict[str, str]]:
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, method=method, data=body, headers=request_headers
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            data = response.read()
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise GoogleOAuthError(f"Google returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GoogleOAuthError(f"Could not reach Google: {exc.reason}") from exc
    if status not in expected:
        snippet = data.decode("utf-8", errors="replace")[:300] if data else ""
        detail = f"Google returned unexpected HTTP {status} for {method} {url}."
        if snippet:
            detail = f"{detail} Body: {snippet}"
        raise GoogleOAuthError(detail)
    return status, data, response_headers


class JsonTokenStore:
    """Atomic JSON token storage outside the source tree by default."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoogleOAuthError(
                f"Cannot read Google token store {self.path}: {exc}"
            ) from exc

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix="google-token-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def _credential_scripts_path() -> Path:
    return Path(__file__).resolve().parents[3] / "manage-credentials" / "scripts"


def _portable_vault_token_store(entry: str, field: str) -> Any:
    path = _credential_scripts_path()
    if not path.exists():
        raise GoogleOAuthError(
            "The shared manage-credentials skill is unavailable."
        )
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        from portable_vault import CredentialError, PortableVaultJsonStore
    except ImportError as exc:
        raise GoogleOAuthError(
            "Could not load the shared portable-vault credential provider."
        ) from exc

    class GooglePortableVaultStore:
        def __init__(self) -> None:
            try:
                self.backend = PortableVaultJsonStore(
                    entry=entry,
                    field=field,
                    path=os.getenv("PORTABLE_VAULT_PATH") or None,
                )
            except CredentialError as exc:
                raise GoogleOAuthError(str(exc)) from exc
            self.path = self.backend.path

        def load(self) -> dict[str, Any]:
            try:
                return self.backend.load()
            except CredentialError as exc:
                raise GoogleOAuthError(str(exc)) from exc

        def save(self, value: dict[str, Any]) -> None:
            try:
                self.backend.save(value)
            except CredentialError as exc:
                raise GoogleOAuthError(str(exc)) from exc

        def clear(self) -> None:
            try:
                self.backend.clear()
            except CredentialError as exc:
                raise GoogleOAuthError(str(exc)) from exc

        def rotation_lock(self) -> Any:
            return self.backend.rotation_lock()

    return GooglePortableVaultStore()


def _rotation_lock(store: Any) -> Any:
    factory = getattr(store, "rotation_lock", None)
    return factory() if callable(factory) else nullcontext()


def _token_store_for_account(account: GoogleAccount) -> Any:
    backend = os.getenv("GOOGLE_TOKEN_STORE", "vault").strip().lower()
    if backend == "file":
        path = os.getenv("GOOGLE_TOKEN_FILE") or str(default_token_path(account.alias))
        return JsonTokenStore(path)
    if backend == "vault":
        entry = resolve_vault_entry(account)
        field = os.getenv("GOOGLE_VAULT_FIELD", "oauth_token_json").strip()
        return _portable_vault_token_store(entry, field)
    raise GoogleOAuthError("GOOGLE_TOKEN_STORE must be either 'file' or 'vault'.")


@dataclass
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    account: GoogleAccount

    @classmethod
    def from_environment(cls, account_alias: str | None = None) -> "GoogleConfig":
        try:
            alias = resolve_alias(account_alias)
            account = get_account(alias)
        except GoogleAccountError as exc:
            raise GoogleOAuthError(str(exc)) from exc

        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI", DEFAULT_REDIRECT_URI
        ).strip()
        scopes = os.getenv("GOOGLE_SCOPES", " ".join(DEFAULT_SCOPES)).strip()
        missing = [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", client_id),
                ("GOOGLE_CLIENT_SECRET", client_secret),
            )
            if not value
        ]
        if missing:
            raise GoogleOAuthError(
                "Missing environment variable(s): "
                + ", ".join(missing)
                + ". Inject them from the vault entry with manage-credentials."
            )
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            account=account,
        )


class GoogleConnection:
    """A reusable, auto-refreshing Google Workspace OAuth connection."""

    def __init__(self, config: GoogleConfig, store: Any | None = None):
        self.config = config
        self.account = config.account
        self.store = store or _token_store_for_account(config.account)

    @classmethod
    def from_environment(cls, account_alias: str | None = None) -> "GoogleConnection":
        config = GoogleConfig.from_environment(account_alias)
        return cls(config, _token_store_for_account(config.account))

    def authorisation_url(self, state: str, scopes: str | None = None) -> str:
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": scopes or self.config.scopes,
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        login_hint = self.account.email
        if login_hint:
            params["login_hint"] = login_hint
        return AUTHORISE_URL + "?" + urllib.parse.urlencode(params)

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        payload = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            **fields,
        }
        _, data, _ = _request(
            "POST",
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urllib.parse.urlencode(payload).encode(),
        )
        token = json.loads(data)
        if "error" in token:
            raise GoogleOAuthError(
                f"Google token error: {token.get('error_description') or token['error']}"
            )
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        token["obtained_at"] = now
        token["expires_at"] = now + int(token.get("expires_in", 3600))
        token["account_alias"] = self.account.alias
        token["account_email"] = self.account.email
        return token

    def exchange_code(self, code: str) -> dict[str, Any]:
        token = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            }
        )
        with _rotation_lock(self.store):
            current = self.store.load()
            if not token.get("refresh_token") and current.get("refresh_token"):
                token["refresh_token"] = current["refresh_token"]
            self.store.save(token)
        return token

    def refresh(self) -> dict[str, Any]:
        with _rotation_lock(self.store):
            current = self.store.load()
            refresh_token = current.get("refresh_token")
            if not refresh_token:
                raise GoogleOAuthError(
                    "No refresh token is stored. Connect the Google account first."
                )
            updated = self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": str(refresh_token),
                }
            )
            if not updated.get("refresh_token"):
                updated["refresh_token"] = refresh_token
            if current.get("scope") and not updated.get("scope"):
                updated["scope"] = current.get("scope")
            self.store.save(updated)
        return updated

    def access_token(self, leeway_seconds: int = 90) -> str:
        token = self.store.load()
        if not token.get("access_token"):
            raise GoogleOAuthError(
                f"Google account {self.account.alias!r} is not connected."
            )
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if float(token.get("expires_at", 0)) <= now + leeway_seconds:
            token = self.refresh()
        return str(token["access_token"])

    def credentials(self) -> Any:
        """Return google.oauth2.credentials.Credentials for API clients."""
        try:
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise GoogleOAuthError(
                "Install google-auth (see requirements.txt) to build API clients."
            ) from exc

        token = self.store.load()
        if not token.get("refresh_token") and not token.get("access_token"):
            raise GoogleOAuthError(
                f"Google account {self.account.alias!r} is not connected."
            )
        # Ensure access token is fresh before handing credentials to google libs.
        access = self.access_token()
        token = self.store.load()
        expiry = None
        if token.get("expires_at"):
            expiry = dt.datetime.fromtimestamp(
                float(token["expires_at"]), tz=dt.timezone.utc
            ).replace(tzinfo=None)
        return Credentials(
            token=access,
            refresh_token=token.get("refresh_token"),
            token_uri=TOKEN_URL,
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            scopes=str(token.get("scope") or self.config.scopes).split(),
            expiry=expiry,
        )

    def build_service(self, api: str, version: str) -> Any:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleOAuthError(
                "Install google-api-python-client (see requirements.txt)."
            ) from exc
        return build(
            api,
            version,
            credentials=self.credentials(),
            cache_discovery=False,
        )

    def userinfo(self) -> dict[str, Any]:
        _, data, _ = _request(
            "GET",
            USERINFO_URL,
            headers={"Authorization": f"Bearer {self.access_token()}"},
        )
        return json.loads(data)

    def status(self) -> dict[str, Any]:
        token = self.store.load()
        base = {
            "account_alias": self.account.alias,
            "registry_email": self.account.email,
            "vault_entry": resolve_vault_entry(self.account),
            "requested_scopes": self.config.scopes,
            "token_store": str(getattr(self.store, "path", "")),
            "registry_status": self.account.status,
        }
        if not token.get("access_token") and not token.get("refresh_token"):
            return {**base, "connected": False}
        try:
            access = self.access_token()
            token = self.store.load()
            info = self.userinfo()
            granted = str(token.get("scope") or "").split()
            requested = self.config.scopes.split()
            return {
                **base,
                "connected": True,
                "access_token_present": bool(access),
                "email": info.get("email"),
                "name": info.get("name"),
                "sub": info.get("sub"),
                "scopes": token.get("scope", ""),
                "missing_scopes": missing_scopes(requested, granted),
                "expires_at": token.get("expires_at"),
            }
        except GoogleOAuthError as exc:
            return {**base, "connected": False, "error": str(exc)}

    def revoke(self) -> None:
        token = self.store.load()
        revoke_value = token.get("refresh_token") or token.get("access_token")
        if revoke_value:
            try:
                _request(
                    "POST",
                    REVOKE_URL,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    body=urllib.parse.urlencode({"token": revoke_value}).encode(),
                    expected=(200,),
                )
            except GoogleOAuthError:
                # Still clear local store if Google rejects an already-revoked token.
                pass
        self.store.clear()

    def request_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "Accept": "application/json",
        }
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        _, data, _ = _request(
            method, url, headers=headers, body=payload, expected=expected
        )
        if not data:
            return {}
        return json.loads(data)
