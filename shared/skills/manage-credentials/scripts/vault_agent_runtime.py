"""Runtime paths and helpers for the per-login Vault Agent."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


AGENT_PROTOCOL_VERSION = 1
AGENT_NAME = "PortableAIBrainVaultAgent"


def runtime_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_RUNTIME_DIR") or (Path.home() / ".cache"))
    path = base / "PortableAIBrain" / "vault-agent"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return runtime_dir() / "agent-state.json"


def singleton_lock_path() -> Path:
    return runtime_dir() / "agent.singleton"


def ipc_address() -> str | tuple[str, int]:
    if os.name == "nt":
        return rf"\\.\pipe\{AGENT_NAME}"
    return str(runtime_dir() / "agent.sock")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def prepare_runtime_dir() -> None:
    """Clear stale state/tmp files and a singleton left by a dead process."""
    directory = runtime_dir()
    for path in directory.glob("agent-state*.tmp"):
        try:
            path.unlink()
        except OSError:
            pass
    lock_path = singleton_lock_path()
    if lock_path.exists():
        try:
            raw = lock_path.read_text(encoding="ascii").strip()
            pid = int(raw) if raw.isdigit() else 0
        except (OSError, ValueError):
            pid = 0
        if not _pid_is_running(pid):
            try:
                lock_path.unlink()
            except OSError:
                pass
            clear_state()


def restrict_to_current_user(path: Path) -> None:
    """Best-effort ACL tightening so only the current user (and SYSTEM on Windows) can read."""
    path = Path(path)
    if not path.exists():
        return
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
            if path.is_dir():
                os.chmod(path, 0o700)
        except OSError:
            pass
        return
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        return
    try:
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{user}:(F)",
                "/grant:r",
                "SYSTEM:(F)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        pass


def write_state(payload: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name avoids PermissionError on a stale locked agent-state.tmp.
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="agent-state.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    restrict_to_current_user(path)


def read_state() -> dict[str, Any] | None:
    path = state_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def clear_state() -> None:
    path = state_path()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    for leftover in runtime_dir().glob("agent-state*.tmp"):
        try:
            leftover.unlink()
        except OSError:
            pass
