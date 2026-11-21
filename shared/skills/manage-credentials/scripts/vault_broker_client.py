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


RESERVED_REQUEST_KEYS = frozenset({"v", "id", "token", "op"})


def broker_request(operation: str, /, **payload: Any) -> Any:
    """One request to the Vault Agent. operation is positional only: a refresh passes the journal's
    operation id as the payload key "operation". A payload may not name the request's own fields."""
    clash = sorted(RESERVED_REQUEST_KEYS & payload.keys())
    if clash:
        raise TypeError(f"a Vault Agent request cannot carry the payload key {clash[0]!r}")
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
def _expiry(value: Any) -> float:
    """expires_at as epoch seconds: a number, or an ISO-8601 time (LinkedIn); else ValueError."""
    if isinstance(value, str) and not value.strip().replace(".", "", 1).isdigit():
        import datetime as dt
        moment = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt.timezone.utc)
        return moment.timestamp()
    return float(value)


def _expiring(record: dict, leeway: Any) -> bool:
    try:
        return _expiry(record.get("expires_at")) <= time.time() + float(leeway or 0)
    except (TypeError, ValueError):
        return True


def _load_or_empty(store: Any) -> dict:
    try:
        return store.load()
    except CredentialError:
        return {}


def _wait_for_refresher(store: Any, begun: dict, leeway: Any, before: dict | None = None) -> None:
    """Another computer never calls the provider: pull until the refresher publishes a newer
    access token, or stop in plain words. A token newer than the one this computer held before
    begin_refresh (before), and not expired, is that newer token: the refresher published it
    just before, so it is returned at once instead of waiting for another refresh."""
    baseline = begun.get("record") or {}
    if leeway is not None and not _expiring(baseline, leeway):
        return
    token = baseline.get("access_token")
    if (before is not None and token and token != before.get("access_token")
            and not _expiring(baseline, leeway or 0)):
        return
    deadline = time.monotonic() + REFRESH_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(max(0.0, min(REFRESH_POLL_SECONDS, deadline - time.monotonic())))
        record = store._broker_request("poll_refresh", entry=store.entry, field=store.field)
        token = record.get("access_token")
        if token and token != baseline.get("access_token") and (leeway is None or not _expiring(record, leeway)):
            return
    raise CredentialError(f"this sign-in refreshes on {begun.get('computer')}; it has not refreshed it yet")


def unsaved_message(entry: str, new_authorisation: bool = False) -> str:
    if new_authorisation:
        return (f"The sign-in of {entry} ended without saving the provider's answer; nothing was recorded. "
                "Sign in again in the browser.")
    return (f"The refresh of {entry} ended without saving the provider's answer, so it is held as uncertain: "
            "the provider may have been called. A connector that certainly sent nothing raises "
            "ProviderNotCalled instead.")


@contextmanager
def store_refresh(store: Any, local_lock: Any, *, refresh: bool = False, leeway_seconds: Any = None,
                  new_authorisation: bool = False) -> Any:
    """Every rotation_lock on a sign-in when the agent serves the secrets store. A refresh is
    begun only when a provider call is due: refresh=True, new_authorisation=True (a code
    exchange, also a first sign-in) or a token expiring within leeway_seconds. Otherwise the block
    runs under the lock and nothing is written; a token change saved there is refused. On the
    refresher, begin_refresh opens the journal record and the save inside carries its operation
    id. Only ProviderNotCalled and ProviderRefused remove the record; any other exception, and a normal exit without
    a save, leave it in calling (uncertain) and release the lock (the latter with a plain
    message). A new authorisation writes no calling record, so it leaves nothing uncertain. A
    connector raises portable_vault.ProviderNotCalled for any failure before its provider request
    (token_endpoint.post_token raises it and ProviderRefused for its token-endpoint call). Elsewhere a refresh runs once the refresher has published a newer access token."""
    from secret_store.journal import ProviderNotCalled, ProviderRefused

    with local_lock():
        before = _load_or_empty(store) if (refresh or leeway_seconds is not None) and not new_authorisation else {}
        due = refresh or new_authorisation or (
            leeway_seconds is not None and _expiring(before, leeway_seconds))
        if not due:
            yield
            return
        begun = store._broker_request("begin_refresh", entry=store.entry, field=store.field,
                                      new_authorisation=new_authorisation)
        if not begun.get("operation"):
            if begun.get("signin"):  # another computer refreshes this sign-in
                if new_authorisation:
                    raise CredentialError(f"this sign-in refreshes on {begun.get('computer')}; sign in again there")
                _wait_for_refresher(store, begun, None if refresh else leeway_seconds, before)
            yield
            return
        operation = begun["operation"]
        store._operation, store._saved = operation, False

        def end(how: str) -> None:
            store._operation = None
            if not store._saved:
                store._broker_request(how, entry=store.entry, field=store.field, operation=operation)
        try:
            yield
        except (ProviderNotCalled, ProviderRefused):  # no token can have been issued
            end("abort_refresh")
            raise
        except BaseException:
            end("release_refresh")
            raise
        end("release_refresh")
        if not store._saved:
            raise CredentialError(unsaved_message(store.entry, new_authorisation))
