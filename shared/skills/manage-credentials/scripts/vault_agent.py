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
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any

import portable_vault
from portable_vault import CredentialError, PortableVault, default_vault_path, refuse_migrated
from vault_agent_runtime import (
    AGENT_PROTOCOL_VERSION,
    NotPrivate,
    clear_state,
    ipc_address,
    log_tray,
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
from secret_store.broker_backend import AGENT_OPS, VAULT_OPS, agent_operation  # noqa: E402

# Requests a vault-backed agent still answers once the store is on: none reads a credential.
ALWAYS_ANSWERED = frozenset({"status", "ping", "lock"})


def build_agent(vault_path: Path | str | None = None, brain_root: Any = None) -> "VaultAgent":
    """The one way vault_agent.py serve and the login tray build their agent (round-9 plan, M2).
    Store on: a store-backed agent. Store off: the vault agent. A malformed configuration raises
    SecretStoreError, so neither starts."""
    from secret_store import broker_backend

    store = broker_backend.backend_if_enabled(brain_root)
    return VaultAgent(vault_path or default_vault_path(), store=store)


def migration_backup_age(vault_path: Path | str) -> str | None:
    """The age of the newest backup in migration-backups beside the vault, or None (row M8)."""
    path = Path(vault_path)
    try:
        times = [p.stat().st_mtime for p in (path.parent / "migration-backups").glob("*" + (path.suffix or ".vault"))
                 if p.is_file()]
    except OSError:
        return None
    if not times:
        return None
    return f"{max(0.0, time.time() - max(times)) / 86400:.1f} days"


STOPPING_MESSAGE = "The Vault Agent is stopping and takes no passphrase. Start it again to unlock."


class AgentAlreadyRunning(CredentialError):
    """The singleton lock stayed held for the whole wait: another agent is running."""


class VaultAgent:
    # How often a running agent checks that its state file is still there (see _keep_state).
    STATE_CHECK_SECONDS = 5.0
    # How long a start waits for a busy singleton lock before it reports another running agent.
    LOCK_WAIT_SECONDS = 10.0
    LOCK_RETRY_SECONDS = 0.25
    # Shutdown waits at most this long for the barrier and for the operations in flight (plan R16).
    DRAIN_SECONDS = 30.0
    # After a failed proof: connections without a key that wake a waiting accept, and the pause after each.
    WAKE_ATTEMPTS = 25
    WAKE_WAIT_SECONDS = 0.2

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
        # Why _keep_state stopped the agent (its state file could not be proved private), or None.
        self._stopped_by: NotPrivate | None = None
        # The shutdown barrier (plan R16, rule 3): under one condition, the open connections, the count
        # of operations in flight and whether the agent is stopping. Lock order: _lock is never taken
        # while the barrier is held, and shutdown never waits while holding _lock.
        self._barrier = threading.Condition(threading.RLock())
        self._connections: set[Any] = set()
        self._in_flight = 0
        self._stopping = False
        self._operation = threading.local()  # .active: this thread runs an admitted operation
        self._serve_ended = threading.Event()  # set when the accept loop of serve_forever has ended
        # The fence visible at once (plan R20): set by the first statement of shutdown, and by _keep_state
        # after a failed proof before it releases _lock. Registration, admission and answering refuse on it.
        self._shutdown_requested = threading.Event()

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
            age = migration_backup_age(self.vault.path)
            if age:
                result["migration_backup_age"] = age
            if self._store is not None:
                result.update(self._store.status(), unlocked=True, vault_unlocked=self._passphrase is not None)
                relay = self._ignored_relay()
                if relay:
                    result["token_relay"] = relay
            return result

    def _ignored_relay(self) -> str | None:
        """A token-relay.json still found while the store is on: reported, never used."""
        try:
            from token_relay import resolve_config

            found, _looked = resolve_config(self.vault.path, use_agent=False)  # never ask itself
        except (CredentialError, OSError):
            return None
        return f"ignored while the secrets store is on ({found})" if found is not None else None

    def _package_timer(self) -> Any:
        """The recovery-package timer when this agent serves the secrets store, else None."""
        if self._store is None or not hasattr(self._store, "package_tick"):
            return None
        from secret_store.broker_backend import PackageTimer

        return PackageTimer(self._store)

    def unlock(self, passphrase: str) -> dict[str, Any]:
        if not passphrase:
            raise CredentialError("The vault passphrase is required.")
        if self._fenced():  # a stopping agent takes no passphrase (plan R21, rule 6)
            raise CredentialError(STOPPING_MESSAGE)
        # Authenticate without retaining a wrong passphrase. In store mode the passphrase is held only
        # for the migration and rollback operations, which open the vault under the migration lock.
        (PortableVault(self.vault.path, migration=True) if self._store is not None else self.vault).load(passphrase)
        with self._lock:
            # Again under _lock: shutdown sets its event before it takes _lock to clear the passphrase.
            if self._fenced():
                raise CredentialError(STOPPING_MESSAGE)
            self._passphrase = passphrase
            # And after the assignment (plan R22): the passphrase is stored before the fence or not at
            # all. A shutdown that set its event between the check and the assignment is seen here.
            if self._fenced():
                self._passphrase = None
                raise CredentialError(STOPPING_MESSAGE)
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
        refuse_migrated(self.vault.path, entry, field)
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
                refuse_migrated(self.vault.path, entry, field)
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
            self._refuse_when_stale(operation)
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

    def _refuse_when_stale(self, operation: Any) -> None:
        """Round-9 plan, row M2: a vault-backed agent checks the store switch on every credential
        request and refuses once it is on; only the migration's own operations pass, under its lock."""
        if self._store is not None or operation in ALWAYS_ANSWERED or not portable_vault.secret_store_enabled():
            return
        if operation in VAULT_OPS:
            import migration_lock

            if migration_lock.holder(self.vault.path) is not None:
                return
        raise CredentialError(portable_vault.STALE_AGENT_MESSAGE)

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
        # A runtime folder that cannot be proved private stops the start here, before the
        # singleton lock and the listener exist (NotPrivate leaves this method).
        prepare_runtime_dir()
        self._acquire_singleton()
        address = ipc_address()
        if isinstance(address, str) and not address.startswith("\\\\.\\pipe\\"):
            sock = Path(address)
            if sock.exists():
                sock.unlink()
        self._listener = Listener(address, authkey=self._authkey)
        try:
            self._serve_with_listener(address)
        except BaseException:
            # Every abnormal end once the listener exists is fenced by the agent itself (plan R21):
            # an accept loop that fails, a worker thread that cannot be started, a failed write_state.
            # shutdown is idempotent, so a path that already fenced itself loses nothing.
            self.shutdown()
            raise

    def _serve_with_listener(self, address: Any) -> None:
        self._state_payload = {
            "pid": os.getpid(),
            "address": address if isinstance(address, str) else list(address),
            "authkey": self._authkey.hex(),
            "token": self._auth_token,
            "vault_path": str(self.vault.path.resolve()),
            "protocol": AGENT_PROTOCOL_VERSION,
        }
        write_state(self._state_payload)  # a failure is fenced by serve_forever
        if self._shutdown_requested.is_set():
            # Shut down while it was starting (a start the tray gave up on): the listener and the state
            # file made after that shutdown are taken away again, and the start fails.
            self.shutdown()
            raise CredentialError("Vault Agent was shut down while it was starting.")
        atexit.register(self.shutdown)
        threading.Thread(target=self._keep_state, name="vault-agent-state", daemon=True).start()
        timer = self._package_timer()
        if timer is not None:  # keeps the recovery package fresh without a credential request
            threading.Thread(target=timer.run, args=(lambda: self._listener is None,),
                             name="vault-agent-package", daemon=True).start()
        print(
            "Vault Agent listening. Unlock once with: "
            "python shared/skills/manage-credentials/scripts/vaultctl.py unlock",
            flush=True,
        )
        print(f"Vault path: {self.vault.path.resolve()}", flush=True)
        try:
            self._accept_loop()
        finally:
            self._serve_ended.set()
        if self._stopped_by is not None:
            raise self._stopped_by

    def _accept_loop(self) -> None:
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
            # The admission of the connection into the register (plan R16, rule 3): one accepted
            # while the agent is stopping is closed and never served, and the loop ends.
            admitted = not self._fenced()
            if admitted:
                with self._barrier:
                    admitted = not self._fenced() and self._listener is not None
                    if admitted:
                        self._connections.add(connection)
            if not admitted:
                _close_quietly(connection)
                break
            thread = threading.Thread(
                target=self._serve_connection,
                args=(connection,),
                daemon=True,
            )
            thread.start()

    def _keep_state(self) -> None:
        """Write the state file again when it has gone missing while this agent still listens.

        Clients find the agent through that file. If another process removes it, the agent
        would run on unreachable until it was restarted; this puts the file back. A rewrite that
        cannot be proved private (NotPrivate) stops the agent: the reason is written to standard
        error and the tray's log and shutdown runs. When shutdown did not drain, the process ends at
        once with exit code 2, before any wake-up (plan R18). Otherwise the waiting accept is woken and
        serve_forever raises the reason; when the accept loop does not end, the process ends itself
        the same way. An agent that could not prove its state file private never stays up.
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
                    continue
                except NotPrivate as exc:
                    self._stopped_by = exc
                    # The fence is visible before _lock is released (plan R20, amendments).
                    self._shutdown_requested.set()
                except OSError:  # a passing failure of reading or replacing
                    continue
            # _lock is released here: shutdown never waits while it is held. The fence comes first,
            # then the reason, best effort; the wake-up or the exit stands in a finally (plan R20).
            drained = False
            try:
                drained = self.shutdown()
            finally:
                try:
                    _diagnose(f"Vault Agent stopped: {self._stopped_by}", f"agent stopped: {self._stopped_by}")
                finally:
                    self._after_the_fence(drained, payload["address"])
            return

    def _after_the_fence(self, drained: bool, address: Any) -> None:
        """After a failed proof and its shutdown: the process ends at once when shutdown did not drain,
        and when the woken accept loop does not end."""
        if not drained:
            _end_process("operations still in flight after shutdown")
            return
        if not self._wake_accept(address):
            _end_process("the accept loop did not end")

    def _wake_accept(self, address: Any) -> bool:
        """End an accept that waits on the pipe after shutdown: closing the listener does not end it
        on Windows. One connection without a key does (its handshake fails); a failed connection is
        retried. True when the accept loop has ended."""
        for _attempt in range(self.WAKE_ATTEMPTS):
            if self._serve_ended.is_set():
                return True
            try:
                Client(address).close()
            except Exception:  # noqa: BLE001 - retried; the loop's end is what counts
                pass
            if self._serve_ended.wait(self.WAKE_WAIT_SECONDS):
                return True
        return self._serve_ended.is_set()

    def _serve_connection(self, connection: Any) -> None:
        try:
            while True:
                try:
                    request = connection.recv()
                except Exception:  # noqa: BLE001 - the client left, or shutdown closed the connection
                    break  # (on Windows a pipe closed under a waiting recv raises RuntimeError)
                if not self._admit():
                    break  # fenced: the request is refused and gets no answer
                try:
                    # Never echo passphrase material in responses.
                    if isinstance(request, dict):
                        response = self.handle(request)
                    else:
                        response = {"ok": False, "error": "Malformed request."}
                    self._answer_ready()
                    # The answer is part of the operation (plan R16, second amendments): it is sent
                    # under the barrier, or suppressed when the agent is stopping, so no answer is
                    # handed to the pipe after stopping began and shutdown never drains during a send.
                    # Fenced (R20): suppressed without waiting for the barrier.
                    sent = not self._fenced()
                    if sent:
                        with self._barrier:
                            sent = not self._fenced()
                            if sent:
                                try:
                                    connection.send(response)
                                except (OSError, ValueError):  # the client left, or the connection was closed
                                    sent = False
                finally:
                    self._finish()
                if not sent or (isinstance(request, dict) and request.get("op") == "shutdown"):
                    break
        finally:
            # Closed first: a refused request's connection closes at once, even while a send holds
            # the barrier (plan R20); it leaves the register when the barrier is free.
            _close_quietly(connection)
            with self._barrier:
                self._connections.discard(connection)

    def _fenced(self) -> bool:
        """Shutdown was requested or has begun: nothing more is registered, admitted or answered."""
        return self._stopping or self._shutdown_requested.is_set()

    def _admit(self) -> bool:
        """Admit one request (plan R16, rule 3; R20): only while the agent is not fenced. The event is
        looked at before the barrier too, so a request is refused while shutdown waits for it."""
        if self._fenced():
            return False
        with self._barrier:
            if self._fenced():
                return False
            self._in_flight += 1
            self._operation.active = True
            return True

    def _answer_ready(self) -> None:
        """The moment an admitted operation's answer is ready, before the barrier is taken: a seam
        the tests use to start shutdown exactly there. It does nothing."""

    def _finish(self) -> None:
        """The operation ended, its answer sent or suppressed: the count falls."""
        with self._barrier:
            self._in_flight -= 1
            self._operation.active = False
            self._barrier.notify_all()

    def shutdown(self) -> bool:
        """Stop the agent (plans R16 to R20); True when it drained.

        The fence comes first, all under one deadline of DRAIN_SECONDS (plan R20):
        - The first statement sets `_shutdown_requested`, so from then on nothing is registered,
          admitted or answered, even while shutdown waits.
        - (a) It takes the barrier.
        - (b) Under the barrier it marks the agent stopping and closes every registered connection
          (an operation still in flight can deliver no answer), then releases the barrier.
        - (c) It takes `_lock` with what is left of the deadline and, under it, takes away the
          passphrase, the listener and the payload.
        - (d) It closes the listener, removes this agent's state file, unregisters from `atexit` and
          releases the singleton.
        - (e) It takes the barrier again and waits until no other operation is in flight.

        `_lock` is never taken while the barrier is held, nor the barrier while `_lock` is held.

        When (a) does not get the barrier (a send that never ends) or (c) does not get `_lock` (an
        operation holds it through work without a bound), it ends the process at once with exit
        code 2, without the clean-up of (c) and (d). A state file left behind names a process that
        is gone, which every client refuses, and the operating system releases the singleton with
        the process. It never returns to its caller then.

        It returns False ("not drained"), with the fence up, in two cases:
        - operations are still in flight at the end of (e) (`_keep_state` then ends the process);
        - it was called from inside an operation, whose own answer is not yet suppressed nor the
          operation finished.
        """
        self._shutdown_requested.set()
        deadline = time.monotonic() + self.DRAIN_SECONDS
        if not self._barrier.acquire(timeout=self.DRAIN_SECONDS):
            _end_process("shutdown could not take the barrier: a send has not ended")
            return False  # only when a test replaced _exit_now
        try:
            self._stopping = True
            for connection in list(self._connections):
                _close_quietly(connection)
        finally:
            self._barrier.release()
        if not self._lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            _end_process("shutdown could not take the agent's lock: an operation holds it")
            return False  # only when a test replaced _exit_now
        try:
            self._passphrase = None
            listener = self._listener
            self._listener = None
            self._state_payload = None
        finally:
            self._lock.release()
        if listener is not None:
            _close_quietly(listener)
        # Only this agent's own state file: never the file of another, running agent.
        clear_state(only_pid=os.getpid())
        try:
            atexit.unregister(self.shutdown)
        except Exception:  # noqa: BLE001
            pass
        self._release_singleton()
        if not self._barrier.acquire(timeout=max(0.0, deadline - time.monotonic())):
            return False  # the fence is up; a send began before it still holds the barrier
        try:
            own = 1 if getattr(self._operation, "active", False) else 0
            others_ended = self._barrier.wait_for(lambda: self._in_flight <= own,
                                                  timeout=max(0.0, deadline - time.monotonic()))
            return others_ended and not own
        finally:
            self._barrier.release()


def _close_quietly(closable: Any) -> None:
    try:
        closable.close()
    except Exception:  # noqa: BLE001
        pass


# How long the diagnostics may hold up whatever follows them (plan R20, rule 3).
DIAGNOSTICS_SECONDS = 2.0


def _diagnose(message: str, tray_line: str) -> None:
    """Say why, best effort and bounded (plans R19, R20). In a daemon thread it writes the message to
    standard error, only when that stream exists (the tray under pythonw has none), then the line to
    the tray's log, each in its own guard that suppresses every Exception. The caller waits for that
    thread at most DIAGNOSTICS_SECONDS. Making, starting and joining the thread are best effort too: it
    never raises an Exception, and a stream that never returns cannot hold up the fence or the exit."""
    def write() -> None:
        stream = sys.stderr
        if stream is not None:
            try:
                print(message, file=stream, flush=True)
            except Exception:  # noqa: BLE001 - a broken stream must not keep the agent up
                pass
        try:
            log_tray(tray_line)
        except Exception:  # noqa: BLE001
            pass

    try:
        thread = threading.Thread(target=write, name="vault-agent-diagnostics", daemon=True)
        thread.start()
        thread.join(DIAGNOSTICS_SECONDS)
    except Exception:  # noqa: BLE001
        pass


def _end_process(reason: str) -> None:
    """The last resort: the reason, best effort, then exit code 2 from a finally, so no failure of the
    diagnostics and no interrupt during them keeps the process alive."""
    try:
        _diagnose(f"Vault Agent ends its process: {reason}", f"agent ends its process: {reason}")
    finally:
        _exit_now(2)


def _exit_now(code: int) -> None:
    """End the process at once (the last resort after a failed proof; tests replace it)."""
    os._exit(code)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", help="Override the portable vault path")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("serve", help="Run the Vault Agent until stopped")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        agent = build_agent(args.vault)
    except SecretStoreError as exc:  # malformed enabled configuration: fatal, never the old vault
        print(f"Vault Agent failed: the secrets-store configuration is not usable: {exc}", file=sys.stderr)
        return 2
    try:
        if args.operation == "serve":
            agent.serve_forever()
            return 0
    except (CredentialError, NotPrivate) as exc:
        print(f"Vault Agent failed: {exc}", file=sys.stderr)
        return 2
    parser.error("Unsupported operation.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
