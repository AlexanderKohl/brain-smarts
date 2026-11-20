"""Per-login Vault Agent: holds unlock in-process and serves scoped broker requests."""

from __future__ import annotations

import argparse
import atexit
import errno
import os
import secrets
import sys
import threading
import time
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener
from pathlib import Path
from typing import Any

from portable_vault import CredentialError, PortableVault, default_vault_path
from vault_agent_runtime import (
    AGENT_PROTOCOL_VERSION,
    clear_state,
    ipc_address,
    prepare_runtime_dir,
    read_state,
    restrict_to_current_user,
    singleton_lock_path,
    write_state,
)
from secret_store.errors import SecretStoreError


# The errors a locked file gives on Windows (EACCES, EDEADLOCK) and on POSIX (EACCES, EAGAIN).
LOCK_BUSY_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
# Operations answered in secret_store/broker_backend.py: vault-only ones and the store's refresh ones.
from secret_store.broker_backend import AGENT_OPS, agent_operation  # noqa: E402


class AgentAlreadyRunning(CredentialError):
    """The singleton lock stayed held for the whole wait: another agent is running."""


class VaultAgent:
    # How often a running agent checks that its state file is still there (see _keep_state).
    STATE_CHECK_SECONDS = 5.0
    # How long a start waits for a busy singleton lock before it reports another running agent.
    LOCK_WAIT_SECONDS = 10.0
    LOCK_RETRY_SECONDS = 0.25

    def __init__(self, vault_path: Path | str | None = None, store: Any = None) -> None:
        self.vault = PortableVault(vault_path)
        # broker_backend.StoreBackend when the secrets store is on; None keeps today's vault.
        self._store = store
        self._passphrase: str | None = None
        self._lock = threading.RLock()
        self._entry_locks: dict[str, threading.Lock] = {}
        self._started_at = time.time()
        self._auth_token = secrets.token_hex(32)
        self._authkey = secrets.token_bytes(32)
        self._listener: Listener | None = None
        self._singleton_handle: Any = None
        self._state_payload: dict[str, Any] | None = None

    def _entry_lock(self, entry: str) -> threading.Lock:
        with self._lock:
            lock = self._entry_locks.get(entry)
            if lock is None:
                lock = threading.Lock()
                self._entry_locks[entry] = lock
            return lock

    def status(self) -> dict[str, Any]:
        with self._lock:
            result = {
                "running": True,
                "unlocked": self._passphrase is not None,
                "vault_path": str(self.vault.path.resolve()),
                "pid": os.getpid(),
                "started_at": self._started_at,
                "protocol": AGENT_PROTOCOL_VERSION,
            }
            if self._store is not None:
                result.update(self._store.status(), unlocked=True, vault_unlocked=self._passphrase is not None)
            return result

    def unlock(self, passphrase: str) -> dict[str, Any]:
        if not passphrase:
            raise CredentialError("The vault passphrase is required.")
        # Authenticate without retaining a wrong passphrase.
        self.vault.load(passphrase)
        with self._lock:
            self._passphrase = passphrase
        return {"unlocked": True}

    def lock(self) -> dict[str, Any]:
        with self._lock:
            self._passphrase = None
        return {"unlocked": False}

    def _require_passphrase(self) -> str:
        with self._lock:
            if self._passphrase is None:
                raise CredentialError("Vault Agent is locked. Run: vaultctl unlock")
            return self._passphrase

    def get_fields(self, entry: str, fields: list[str]) -> dict[str, Any]:
        if self._store is not None:
            return self._store.get_fields(entry, fields)
        passphrase = self._require_passphrase()
        return self.vault.get_fields(entry, fields, passphrase)

    def get_json(self, entry: str, field: str) -> dict[str, Any]:
        if self._store is not None:
            return self._store.get_json(entry, field)
        passphrase = self._require_passphrase()
        value = self.vault.get(entry, field, passphrase)
        if not isinstance(value, dict):
            raise CredentialError(f"Vault field must contain a JSON object: {entry}#{field}")
        return value

    def set_json(self, entry: str, field: str, value: dict[str, Any], operation: Any = None) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise CredentialError("JSON credential values must be objects.")
        with self._entry_lock(entry):
            if self._store is not None:
                self._store.set_json(entry, field, value, operation if isinstance(operation, str) else None)
            else:
                self.vault.set(entry, field, value, "json", self._require_passphrase())
        return {"saved": True, "entry": entry, "field": field}

    def set_text(self, entry: str, field: str, value: str) -> dict[str, Any]:
        if not isinstance(value, str) or not value:
            raise CredentialError("Text credential values must be non-empty strings.")
        with self._entry_lock(entry):
            if self._store is not None:
                self._store.set_text(entry, field, value)
            else:
                self.vault.set(entry, field, value, "text", self._require_passphrase())
        return {"saved": True, "entry": entry, "field": field}

    def get_access_token(self, entry: str, field: str = "oauth_token_json") -> dict[str, Any]:
        """Return the stored access token only; refresh remains in the connector."""
        record = self.get_json(entry, field)
        token = record.get("access_token") or record.get("accessToken")
        if not isinstance(token, str) or not token:
            raise CredentialError(f"No access token is stored for {entry}#{field}.")
        result: dict[str, Any] = {"access_token": token}
        for key in ("expires_at", "expires_in", "token_type", "scope", "tenant_id"):
            if key in record:
                result[key] = record[key]
        return result

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            return {"ok": False, "error": "Malformed request."}
        if request.get("v") != AGENT_PROTOCOL_VERSION:
            return {"ok": False, "error": "Unsupported broker protocol version."}
        if request.get("token") != self._auth_token:
            return {"ok": False, "error": "Broker authentication failed."}
        operation = request.get("op")
        request_id = request.get("id")
        try:
            if operation == "status":
                result = self.status()
            elif operation == "unlock":
                result = self.unlock(str(request.get("passphrase") or ""))
            elif operation == "lock":
                result = self.lock()
            elif operation == "get_fields":
                fields = request.get("fields")
                if not isinstance(fields, list) or not all(isinstance(item, str) for item in fields):
                    raise CredentialError("fields must be a list of strings.")
                result = self.get_fields(str(request.get("entry") or ""), fields)
            elif operation == "get_json":
                result = self.get_json(
                    str(request.get("entry") or ""),
                    str(request.get("field") or "oauth_token_json"),
                )
            elif operation == "set_json":
                value = request.get("value")
                if not isinstance(value, dict):
                    raise CredentialError("value must be a JSON object.")
                result = self.set_json(
                    str(request.get("entry") or ""),
                    str(request.get("field") or "oauth_token_json"),
                    value,
                    request.get("operation"),
                )
            elif operation == "set_text":
                result = self.set_text(
                    str(request.get("entry") or ""),
                    str(request.get("field") or ""),
                    str(request.get("value") or ""),
                )
            elif operation == "get_access_token":
                result = self.get_access_token(
                    str(request.get("entry") or ""),
                    str(request.get("field") or "oauth_token_json"),
                )
            elif operation in AGENT_OPS:
                result = agent_operation(self, operation, request)
            elif operation == "ping":
                result = {"pong": True}
            else:
                raise CredentialError(f"Unsupported broker operation: {operation}")
            return {"ok": True, "id": request_id, "result": result}
        except CredentialError as exc:
            message = str(exc)
            code = "locked" if "locked" in message.lower() else "error"
            return {"ok": False, "id": request_id, "error": message, "code": code}
        except SecretStoreError as exc:
            return {"ok": False, "id": request_id, "error": str(exc), "code": "error"}

    @staticmethod
    def _try_lock(handle: Any) -> None:
        """One attempt at the singleton lock; raises OSError when it cannot be taken."""
        if os.name == "nt":
            import msvcrt

            # Measure the file from its end: in append mode a write always lands there, so a
            # start that is about to be refused must not add a byte to the holder's file.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _acquire_singleton(self, wait_seconds: float | None = None) -> None:
        """Take the one-agent lock, retrying while another holder may be about to let go.

        At login an agent can meet a holder that is ending, or a process that touches the lock file
        for a moment, so a busy lock is retried for `LOCK_WAIT_SECONDS` before it is reported as
        another running agent. Any other failure is reported with its own cause.
        """
        wait = self.LOCK_WAIT_SECONDS if wait_seconds is None else wait_seconds
        path = singleton_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + wait
        while True:
            try:
                handle = path.open("a+b")
            except OSError as exc:
                raise CredentialError(f"Vault Agent cannot open its lock file {path}: {exc}") from exc
            try:
                self._try_lock(handle)
                break
            except OSError as exc:
                handle.close()
                if exc.errno not in LOCK_BUSY_ERRNOS:
                    raise CredentialError(f"Vault Agent could not take its lock {path}: {exc}") from exc
                if time.monotonic() >= deadline:
                    raise AgentAlreadyRunning(
                        "Another Vault Agent instance is already running for this user."
                    ) from exc
                time.sleep(self.LOCK_RETRY_SECONDS)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        self._singleton_handle = handle
        restrict_to_current_user(path)

    def _release_singleton(self) -> None:
        handle = self._singleton_handle
        self._singleton_handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass

    def serve_forever(self) -> None:
        prepare_runtime_dir()
        self._acquire_singleton()
        address = ipc_address()
        if isinstance(address, str) and not address.startswith("\\\\.\\pipe\\"):
            sock = Path(address)
            if sock.exists():
                sock.unlink()
        self._listener = Listener(address, authkey=self._authkey)
        self._state_payload = {
            "pid": os.getpid(),
            "address": address if isinstance(address, str) else list(address),
            "authkey": self._authkey.hex(),
            "token": self._auth_token,
            "vault_path": str(self.vault.path.resolve()),
            "protocol": AGENT_PROTOCOL_VERSION,
        }
        write_state(self._state_payload)
        atexit.register(self.shutdown)
        threading.Thread(target=self._keep_state, name="vault-agent-state", daemon=True).start()
        print(
            "Vault Agent listening. Unlock once with: "
            "python shared/skills/manage-credentials/scripts/vaultctl.py unlock",
            flush=True,
        )
        print(f"Vault path: {self.vault.path.resolve()}", flush=True)
        failures = 0
        while True:
            listener = self._listener
            if listener is None:
                break
            try:
                connection = listener.accept()
            except (AuthenticationError, EOFError):
                # A client with the wrong key, or one that left during the handshake, is refused;
                # the agent goes on serving everyone else.
                continue
            except OSError:
                # Closing the listener at shutdown ends the loop; any other error is retried a
                # bounded number of times so a broken pipe cannot spin forever.
                failures += 1
                if self._listener is None:
                    break
                if failures >= 50:
                    # Not a shutdown: say so, so the tray does not go on looking healthy.
                    self.shutdown()
                    raise CredentialError(
                        "Vault Agent stopped listening after repeated connection errors."
                    )
                time.sleep(0.1)
                continue
            failures = 0
            thread = threading.Thread(
                target=self._serve_connection,
                args=(connection,),
                daemon=True,
            )
            thread.start()

    def _keep_state(self) -> None:
        """Write the state file again when it has gone missing while this agent still listens.

        Clients find the agent through that file. If another process removes it, the agent
        would run on unreachable until it was restarted; this puts the file back.
        """
        while self._listener is not None:
            time.sleep(self.STATE_CHECK_SECONDS)
            # Under the agent's lock, which shutdown also takes: a stopping agent never writes
            # its state file back after it has removed it.
            with self._lock:
                payload = self._state_payload
                if self._listener is None or payload is None:
                    return
                try:
                    if read_state() != payload:
                        write_state(payload)
                except OSError:
                    continue

    def _serve_connection(self, connection: Any) -> None:
        try:
            while True:
                try:
                    request = connection.recv()
                except EOFError:
                    break
                # Never echo passphrase material in responses.
                if isinstance(request, dict):
                    response = self.handle(request)
                else:
                    response = {"ok": False, "error": "Malformed request."}
                connection.send(response)
                if isinstance(request, dict) and request.get("op") == "shutdown":
                    break
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    def shutdown(self) -> None:
        with self._lock:
            self._passphrase = None
            listener = self._listener
            self._listener = None
            self._state_payload = None
        # Only this agent's own state file: never the file of another, running agent.
        clear_state(only_pid=os.getpid())
        try:
            atexit.unregister(self.shutdown)
        except Exception:  # noqa: BLE001
            pass
        if listener is not None:
            try:
                listener.close()
            except Exception:  # noqa: BLE001
                pass
        self._release_singleton()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", help="Override the portable vault path")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("serve", help="Run the Vault Agent until stopped")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    from secret_store.broker_backend import backend_if_enabled

    agent = VaultAgent(args.vault or default_vault_path(), store=backend_if_enabled())
    try:
        if args.operation == "serve":
            agent.serve_forever()
            return 0
    except CredentialError as exc:
        print(f"Vault Agent failed: {exc}", file=sys.stderr)
        return 2
    parser.error("Unsupported operation.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
