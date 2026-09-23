"""Xero OAuth token management and authenticated HTTP access."""

from __future__ import annotations

import base64
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


AUTHORISE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
REVOCATION_URL = "https://identity.xero.com/connect/revocation"
CONNECTIONS_URL = "https://api.xero.com/connections"
ACCOUNTING_SCOPES = (
    "offline_access",
    "accounting.invoices",
    "accounting.payments",
    "accounting.banktransactions",
    "accounting.manualjournals",
    "accounting.reports.aged.read",
    "accounting.reports.balancesheet.read",
    "accounting.reports.banksummary.read",
    "accounting.reports.budgetsummary.read",
    "accounting.reports.executivesummary.read",
    "accounting.reports.profitandloss.read",
    "accounting.reports.trialbalance.read",
    "accounting.reports.taxreports.read",
    "accounting.reports.tenninetynine.read",
    "accounting.settings",
    "accounting.contacts",
    "accounting.attachments",
    "accounting.budgets.read",
)
IDENTITY_SCOPES = ("offline_access", "openid", "profile", "email")
PAYROLL_SCOPES = (
    "offline_access",
    "payroll.employees",
    "payroll.payruns",
    "payroll.payslip",
    "payroll.timesheets",
    "payroll.settings",
)
SCOPE_PROFILES = {
    "accounting": ACCOUNTING_SCOPES,
    "identity": IDENTITY_SCOPES,
    "payroll": PAYROLL_SCOPES,
    "files": ("offline_access", "files"),
    "assets": ("offline_access", "assets"),
    "projects": ("offline_access", "projects"),
    "einvoicing": ("offline_access", "einvoicing"),
}
STANDARD_ORGANISATION_SCOPES = tuple(
    dict.fromkeys(scope for profile in SCOPE_PROFILES.values() for scope in profile)
)
DEFAULT_SCOPES = " ".join(ACCOUNTING_SCOPES)
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.005
DEFAULT_RATE_LIMIT_RETRIES = 5


class XeroOAuthError(RuntimeError):
    """Raised when Xero authentication or an authenticated request fails."""


def default_token_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "CodexIntegrations" / "xero-oauth" / "tokens.json"
    return Path.home() / ".local" / "share" / "xero-oauth" / "tokens.json"


def _rate_limit_path() -> Path:
    token_path = Path(os.getenv("XERO_TOKEN_FILE") or default_token_path())
    return token_path.parent / "xero-request-rate-limit.lock"


def _acquire_file_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_file_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _wait_for_request_slot() -> None:
    interval = max(
        DEFAULT_REQUEST_INTERVAL_SECONDS,
        float(
            os.getenv(
                "XERO_REQUEST_INTERVAL_SECONDS",
                str(DEFAULT_REQUEST_INTERVAL_SECONDS),
            )
        ),
    )
    path = _rate_limit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        _acquire_file_lock(handle)
        try:
            handle.seek(0)
            try:
                last_request = float(handle.read().decode("ascii") or "0")
            except ValueError:
                last_request = 0
            wait_seconds = interval - (time.time() - last_request)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            handle.seek(0)
            handle.truncate()
            handle.write(f"{time.time():.6f}".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            _release_file_lock(handle)


def _announce_rate_limit_wait(wait_seconds: float, problem: str = "") -> None:
    resume_at = dt.datetime.now().astimezone() + dt.timedelta(seconds=wait_seconds)
    problem_text = f" ({problem} limit)" if problem else ""
    message = (
        f"Xero rate limit wait{problem_text}: pausing for "
        f"{wait_seconds:g} seconds; continuing at "
        f"{resume_at.strftime('%d %b %Y %H:%M:%S %Z')}."
    )
    print(message, flush=True)
    status_file = os.getenv("XERO_WAIT_STATUS_FILE", "").strip()
    if status_file:
        path = Path(status_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
            handle.flush()


def _request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, bytes, dict[str, str]]:
    max_retries = max(
        0,
        int(os.getenv("XERO_RATE_LIMIT_RETRIES", str(DEFAULT_RATE_LIMIT_RETRIES))),
    )
    for attempt in range(max_retries + 1):
        _wait_for_request_slot()
        request = urllib.request.Request(
            url, method=method, data=body, headers=headers or {}
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, data = response.status, response.read()
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code == 429 and attempt < max_retries:
                retry_after_value = exc.headers.get("Retry-After", "60")
                rate_problem = exc.headers.get("X-Rate-Limit-Problem", "")
                try:
                    retry_after = max(0.0, float(retry_after_value))
                except ValueError:
                    retry_after = 60.0
                _announce_rate_limit_wait(retry_after, rate_problem)
                time.sleep(retry_after)
                continue
            rate_problem = exc.headers.get("X-Rate-Limit-Problem", "")
            rate_note = f" ({rate_problem} limit)" if rate_problem else ""
            raise XeroOAuthError(
                f"Xero returned HTTP {exc.code}{rate_note}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise XeroOAuthError(f"Could not reach Xero: {exc.reason}") from exc
        if status not in expected:
            raise XeroOAuthError(f"Xero returned unexpected HTTP {status}.")
        return status, data, response_headers
    raise XeroOAuthError("Xero request retry loop ended unexpectedly.")


class JsonTokenStore:
    """Atomic JSON token storage outside the source tree by default."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.getenv("XERO_TOKEN_FILE") or default_token_path())

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise XeroOAuthError(f"Cannot read Xero token store {self.path}: {exc}") from exc

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix="xero-token-", suffix=".json", dir=self.path.parent
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


def _portable_vault_token_store() -> Any:
    entry = os.getenv("XERO_VAULT_ENTRY", "xero-oauth").strip()
    field = os.getenv("XERO_VAULT_FIELD", "oauth_token_json").strip()
    path = os.getenv("PORTABLE_VAULT_PATH", "").strip() or None
    credential_scripts = (
        Path(__file__).resolve().parents[3] / "manage-credentials" / "scripts"
    )
    if not credential_scripts.exists():
        raise XeroOAuthError(
            "The shared manage-credentials skill is unavailable."
        )
    if str(credential_scripts) not in sys.path:
        sys.path.insert(0, str(credential_scripts))
    try:
        from portable_vault import (
            CredentialError,
            PortableVaultJsonStore,
        )
    except ImportError as exc:
        raise XeroOAuthError(
            "Could not load the shared portable-vault credential provider."
        ) from exc

    class XeroPortableVaultStore:
        def __init__(self) -> None:
            try:
                self.backend = PortableVaultJsonStore(
                    entry=entry,
                    field=field,
                    path=path,
                )
            except CredentialError as exc:
                raise XeroOAuthError(str(exc)) from exc
            self.path = self.backend.path

        def load(self) -> dict[str, Any]:
            try:
                return self.backend.load()
            except CredentialError as exc:
                raise XeroOAuthError(str(exc)) from exc

        def save(self, value: dict[str, Any]) -> None:
            try:
                self.backend.save(value)
            except CredentialError as exc:
                raise XeroOAuthError(str(exc)) from exc

        def clear(self) -> None:
            try:
                self.backend.clear()
            except CredentialError as exc:
                raise XeroOAuthError(str(exc)) from exc

        def rotation_lock(self) -> Any:
            return self.backend.rotation_lock()

    return XeroPortableVaultStore()


def _token_store_from_environment() -> Any:
    backend = os.getenv("XERO_TOKEN_STORE", "file").strip().lower()
    if backend == "file":
        return JsonTokenStore()
    if backend == "vault":
        return _portable_vault_token_store()
    raise XeroOAuthError(
        "XERO_TOKEN_STORE must be either 'file' or 'vault'."
    )


def _rotation_lock(store: Any) -> Any:
    factory = getattr(store, "rotation_lock", None)
    return factory() if callable(factory) else nullcontext()


@dataclass
class XeroConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str = DEFAULT_SCOPES

    @classmethod
    def from_environment(cls) -> "XeroConfig":
        client_id = os.getenv("XERO_CLIENT_ID", "").strip()
        client_secret = os.getenv("XERO_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv(
            "XERO_REDIRECT_URI", "http://localhost:8765/oauth/callback"
        ).strip()
        missing = [
            name
            for name, value in (
                ("XERO_CLIENT_ID", client_id),
                ("XERO_CLIENT_SECRET", client_secret),
            )
            if not value
        ]
        if missing:
            raise XeroOAuthError(f"Missing environment variable(s): {', '.join(missing)}")
        return cls(
            client_id,
            client_secret,
            redirect_uri,
            os.getenv("XERO_SCOPES", DEFAULT_SCOPES).strip(),
        )


class XeroConnection:
    """A reusable, auto-refreshing Xero OAuth connection."""

    def __init__(self, config: XeroConfig, store: Any | None = None):
        self.config = config
        self.store = store or _token_store_from_environment()

    @classmethod
    def from_environment(cls) -> "XeroConnection":
        return cls(
            XeroConfig.from_environment(),
            _token_store_from_environment(),
        )

    def authorisation_url(self, state: str, scopes: str | None = None) -> str:
        return AUTHORISE_URL + "?" + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "scope": scopes or self.config.scopes,
                "state": state,
            }
        )

    def _basic_auth(self) -> str:
        value = f"{self.config.client_id}:{self.config.client_secret}".encode()
        return "Basic " + base64.b64encode(value).decode()

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        _, data, _ = _request(
            "POST",
            TOKEN_URL,
            {
                "Authorization": self._basic_auth(),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            urllib.parse.urlencode(fields).encode(),
        )
        token = json.loads(data)
        token["obtained_at"] = dt.datetime.now(dt.timezone.utc).timestamp()
        token["expires_at"] = token["obtained_at"] + int(token.get("expires_in", 1800))
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
            token["selected_tenant_id"] = current.get("selected_tenant_id")
            self.store.save(token)
        return token

    def refresh(self) -> dict[str, Any]:
        with _rotation_lock(self.store):
            current = self.store.load()
            refresh_token = current.get("refresh_token")
            if not refresh_token:
                raise XeroOAuthError("No refresh token is stored. Connect to Xero first.")
            updated = self._token_request(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
            updated["selected_tenant_id"] = current.get("selected_tenant_id")
            self.store.save(updated)
        return updated

    def access_token(self, leeway_seconds: int = 90) -> str:
        token = self.store.load()
        if not token.get("access_token"):
            raise XeroOAuthError("Xero is not connected.")
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if float(token.get("expires_at", 0)) <= now + leeway_seconds:
            token = self.refresh()
        return str(token["access_token"])

    def connections(self) -> list[dict[str, Any]]:
        _, data, _ = _request(
            "GET",
            CONNECTIONS_URL,
            {"Authorization": f"Bearer {self.access_token()}", "Accept": "application/json"},
        )
        return json.loads(data)

    def select_tenant(self, tenant_id: str) -> None:
        available = {item.get("tenantId") for item in self.connections()}
        if tenant_id not in available:
            raise XeroOAuthError("The selected tenant is not connected to this Xero app.")
        with _rotation_lock(self.store):
            token = self.store.load()
            token["selected_tenant_id"] = tenant_id
            self.store.save(token)

    def tenant_id(self) -> str:
        tenant_id = self.store.load().get("selected_tenant_id")
        if tenant_id:
            return str(tenant_id)
        connections = self.connections()
        if len(connections) == 1:
            tenant_id = str(connections[0]["tenantId"])
            self.select_tenant(tenant_id)
            return tenant_id
        raise XeroOAuthError("Select a Xero organisation in the connection manager.")

    def request(
        self,
        method: str,
        url: str,
        *,
        accept: str = "application/json",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes, dict[str, str]]:
        request_headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "Xero-tenant-id": self.tenant_id(),
            "Accept": accept,
        }
        request_headers.update(headers or {})
        return _request(method, url, request_headers, body, expected)

    def status(self) -> dict[str, Any]:
        token = self.store.load()
        if not token.get("access_token"):
            return {
                "connected": False,
                "requested_scopes": self.config.scopes,
                "token_file": str(self.store.path),
            }
        try:
            connections = self.connections()
            granted_scopes = str(token.get("scope", "")).split()
            requested_scopes = self.config.scopes.split()
            return {
                "connected": True,
                "selected_tenant_id": token.get("selected_tenant_id"),
                "connections": connections,
                "scopes": token.get("scope", ""),
                "requested_scopes": self.config.scopes,
                "missing_scopes": [
                    scope for scope in requested_scopes if scope not in granted_scopes
                ],
                "expires_at": token.get("expires_at"),
                "token_file": str(self.store.path),
            }
        except XeroOAuthError as exc:
            return {
                "connected": False,
                "error": str(exc),
                "requested_scopes": self.config.scopes,
                "token_file": str(self.store.path),
            }

    def revoke(self) -> None:
        token = self.store.load().get("refresh_token")
        if token:
            _request(
                "POST",
                REVOCATION_URL,
                {
                    "Authorization": self._basic_auth(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                urllib.parse.urlencode({"token": token}).encode(),
            )
        self.store.clear()
