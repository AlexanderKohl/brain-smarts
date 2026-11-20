"""Client for the local Vault Agent broker."""

from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from multiprocessing.connection import Client
from typing import Any

from portable_vault import CredentialError
from vault_agent_runtime import AGENT_PROTOCOL_VERSION, _pid_is_running, ipc_address, read_state


REFRESH_POLL_SECONDS = 3.0
REFRESH_WAIT_SECONDS = 300.0  # the token relay's default lease, the existing rotation-lock limit


class BrokerUnavailable(CredentialError):
    """Raised when the Vault Agent is not running or not reachable."""


class BrokerLocked(CredentialError):
    """Raised when the Vault Agent is running but the vault is locked."""


def _connect() -> Any:
    state = read_state()
    if not state:
        raise BrokerUnavailable(
            "Vault Agent is not running. Start the Portable Vault tray app "
            "and unlock it from the tray menu."
        )
    authkey = state.get("authkey")
    token = state.get("token")
    if not isinstance(authkey, str) or not isinstance(token, str):
        raise BrokerUnavailable("Vault Agent state is malformed; restart the agent.")
    pid = int(state.get("pid") or 0)
    if not _pid_is_running(pid):
        # Never connect with a key from an agent that has ended: the running agent would refuse it.
        raise BrokerUnavailable(
            f"Vault Agent is not running: its state file names process {pid}, which has ended. "
            "Start the Portable Vault tray app and unlock it. A process started by a packaged app "
            "(such as the Claude desktop app) may see the app's own old copy of the state file; "
            "see the skill's notes on sandboxed access."
        )
    try:
        connection = Client(ipc_address(), authkey=bytes.fromhex(authkey))
    except Exception as exc:  # noqa: BLE001 - surface as broker error
        raise BrokerUnavailable(
            "Vault Agent is not reachable. Restart the Portable Vault tray app "
            "and unlock it from the tray menu."
        ) from exc
    return connection, token


def broker_request(operation: str, **payload: Any) -> Any:
    connection, token = _connect()
    request = {
        "v": AGENT_PROTOCOL_VERSION,
        "id": secrets.token_hex(8),
        "token": token,
        "op": operation,
        **payload,
    }
    try:
        connection.send(request)
        response = connection.recv()
    except Exception as exc:  # noqa: BLE001
        raise BrokerUnavailable("Vault Agent request failed.") from exc
    finally:
        connection.close()
    if not isinstance(response, dict):
        raise BrokerUnavailable("Vault Agent returned a malformed response.")
    if response.get("ok") is True:
        return response.get("result")
    error = response.get("error") or "Vault Agent request failed."
    code = response.get("code")
    if code == "locked":
        raise BrokerLocked(str(error))
    raise CredentialError(str(error))


def broker_status() -> dict[str, Any]:
    result = broker_request("status")
    if not isinstance(result, dict):
        raise BrokerUnavailable("Vault Agent status is malformed.")
    return result


def broker_available() -> bool:
    try:
        broker_status()
        return True
    except (BrokerUnavailable, CredentialError, OSError):
        return False


def broker_unlocked() -> bool:
    try:
        return bool(broker_status().get("unlocked"))
    except (BrokerUnavailable, CredentialError, OSError):
        return False


# -- the secrets store's refresh (design synced-secrets-repository.md, section 9, Consumers) ------
def _expiring(record: dict, leeway: Any) -> bool:
    try:
        return float(record.get("expires_at")) <= time.time() + float(leeway or 0)
    except (TypeError, ValueError):
        return True


def _load_or_empty(store: Any) -> dict:
    try:
        return store.load()
    except CredentialError:
        return {}


def _wait_for_refresher(store: Any, begun: dict, leeway: Any) -> None:
    """Another computer never calls the provider: pull until the refresher publishes a newer
    access token, or stop in plain words."""
    baseline = begun.get("record") or {}
    if leeway is not None and not _expiring(baseline, leeway):
        return
    deadline = time.monotonic() + REFRESH_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(max(0.0, min(REFRESH_POLL_SECONDS, deadline - time.monotonic())))
        record = store._broker_request("poll_refresh", entry=store.entry, field=store.field)
        token = record.get("access_token")
        if token and token != baseline.get("access_token") and (leeway is None or not _expiring(record, leeway)):
            return
    raise CredentialError(f"this sign-in refreshes on {begun.get('computer')}; it has not refreshed it yet")


@contextmanager
def store_refresh(store: Any, local_lock: Any, *, refresh: bool = False, leeway_seconds: Any = None,
                  new_authorisation: bool = False) -> Any:
    """Every rotation_lock on a sign-in when the agent serves the secrets store. A plain lock (no
    refresh, no leeway) takes the refresh path on the refresher too; elsewhere its block runs at
    once (a settings save). On the refresher, begin_refresh opens the journal record and the save
    inside carries its operation id. Leaving the block without a save removes the record only on
    a normal exit (the token was already fresh, nothing was called) or on ProviderNotCalled raised
    before the request; any other exception may follow a provider call, so the record stays in
    calling (uncertain) and only the lock is released. Elsewhere a refresh runs once the refresher
    has published a newer access token."""
    from secret_store.journal import ProviderNotCalled

    plain = not refresh and leeway_seconds is None
    with local_lock():
        if not refresh and not plain and not _expiring(_load_or_empty(store), leeway_seconds):
            yield
            return
        begun = store._broker_request("begin_refresh", entry=store.entry, field=store.field)
        if not begun.get("signin"):
            yield
            return
        if not begun.get("refresher"):
            if new_authorisation:
                raise CredentialError(f"this sign-in refreshes on {begun.get('computer')}; sign in again there")
            if not plain:
                _wait_for_refresher(store, begun, None if refresh else leeway_seconds)
            yield
            return
        store._operation, store._saved = begun["operation"], False
        ending = "abort_refresh"
        try:
            yield
        except ProviderNotCalled:
            raise
        except BaseException:
            ending = "release_refresh"
            raise
        finally:
            operation, store._operation = store._operation, None
            if not store._saved:
                store._broker_request(ending, entry=store.entry, field=store.field, operation=operation)
