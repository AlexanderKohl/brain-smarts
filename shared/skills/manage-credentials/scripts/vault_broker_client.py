"""Client for the local Vault Agent broker."""

from __future__ import annotations

import secrets
from multiprocessing.connection import Client
from typing import Any

from portable_vault import CredentialError
from vault_agent_runtime import AGENT_PROTOCOL_VERSION, ipc_address, read_state


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
