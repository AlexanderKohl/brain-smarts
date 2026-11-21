"""The migration lock beside the vault (round-9 plan, row M5).

migrate_to_store.py holds it while a migration or rollback runs: created exclusively, it names the
command's process and start time, and is removed when the command ends. The Vault Agent answers
its scrub, restore-static and migration-marker operations, and opens the old vault while the store
is on, only while a live lock is there. An absent, unreadable or stale lock (its process gone, or
older than MAX_AGE_SECONDS) refuses.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from portable_vault import CredentialError
from vault_agent_runtime import _pid_is_running

MAX_AGE_SECONDS = 6 * 3600.0
REFUSED_MESSAGE = ("{operation} runs only while migrate_to_store.py holds the migration lock beside the vault; "
                   "nothing was changed")


def lock_path(vault_path: Path | str) -> Path:
    path = Path(vault_path)
    return path.with_name(path.name + ".migration.lock")


def _read(path: Path) -> dict[str, Any] | None:
    try:
        held = json.loads(path.read_text("utf-8"))
        pid, started = int(held["pid"]), float(held["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {"pid": pid, "started": started, "command": str(held.get("command") or "")}


def holder(vault_path: Path | str) -> dict[str, Any] | None:
    """The live lock's holder, or None when the lock is absent, unreadable or stale."""
    held = _read(lock_path(vault_path))
    if held is None:
        return None
    age = time.time() - held["started"]
    if age > MAX_AGE_SECONDS or age < -60 or not _pid_is_running(held["pid"]):
        return None
    return held


def require(vault_path: Path | str, operation: str) -> None:
    if holder(vault_path) is None:
        raise CredentialError(REFUSED_MESSAGE.format(operation=operation))


class MigrationLock:
    """with MigrationLock(vault_path, "migrate"): ... – exclusive; a stale lock is replaced."""

    def __init__(self, vault_path: Path | str, command: str) -> None:
        self.path = lock_path(vault_path)
        self.command = command
        self.mine: dict[str, Any] | None = None

    def _create(self) -> bool:
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        self.mine = {"pid": os.getpid(), "started": time.time(), "command": self.command}
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(self.mine) + "\n")
        return True

    def __enter__(self) -> "MigrationLock":
        if self._create():
            return self
        held = holder(self.path.with_name(self.path.name[: -len(".migration.lock")]))
        if held is not None:
            raise CredentialError(f"a {held['command'] or 'migration'} is already running (process {held['pid']}); "
                                  "nothing was changed")
        self.path.unlink(missing_ok=True)  # stale: its process ended or it is too old
        if not self._create():
            raise CredentialError("another migration took the migration lock first; nothing was changed")
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self.mine is not None and _read(self.path) == self.mine:
            self.path.unlink(missing_ok=True)
        self.mine = None
