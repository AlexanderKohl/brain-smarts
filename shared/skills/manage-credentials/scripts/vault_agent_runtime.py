"""Runtime paths and helpers for the per-login Vault Agent."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


AGENT_PROTOCOL_VERSION = 1
AGENT_NAME = "PortableAIBrainVaultAgent"


def runtime_base() -> Path:
    """Where the agent keeps its state file and singleton lock.

    On Windows this is outside AppData: a packaged app (MSIX, such as the Claude desktop app) gives
    the processes it starts its own view of AppData, which hides the running tray's state file from
    them, so sessions there could never reach the agent. The user profile outside AppData is shared.
    """
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE") or Path.home()) / ".portable-ai-brain" / "vault-agent"
    return Path(os.environ.get("XDG_RUNTIME_DIR") or (Path.home() / ".cache")) / "PortableAIBrain" / "vault-agent"


def runtime_dir() -> Path:
    path = runtime_base()
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return runtime_dir() / "agent-state.json"


def singleton_lock_path() -> Path:
    return runtime_dir() / "agent.singleton"


def tray_log_path() -> Path:
    return runtime_dir() / "tray.log"


def log_tray(message: str) -> None:
    """Append one line to the tray's log. The tray runs without a console, so this is the only
    trace of why a start failed. Never raises, and never receives secret material."""
    try:
        path = tray_log_path()
        # Keep the file small: start again when it passes 64 KiB.
        if path.exists() and path.stat().st_size > 64 * 1024:
            path.unlink()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{stamp} pid={os.getpid()} {message}\n")
    except OSError:
        pass


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
    """Tighten the runtime folder and remove temporary files a dead agent left.

    It never removes the state file or the singleton lock. A state file left by an agent that
    has ended is harmless: clients refuse it because its process is gone, and the next agent
    overwrites it. Removing it here once let a second start, or a test, take away the state
    file of an agent that was running or just starting.
    """
    directory = runtime_dir()
    restrict_to_current_user(directory)
    cutoff = time.time() - 60
    for leftover in directory.glob("agent-state*.tmp"):
        try:
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink()
        except OSError:
            pass


def icacls_arguments(path: Path, user: str, is_dir: bool) -> list[str]:
    """The icacls command that leaves only `user` and SYSTEM with access to `path`.

    On a folder the grants carry `(OI)(CI)`, so files and folders created in it afterwards – the
    vault's `.lock` file, a README – inherit the same two grants. Without them, `/inheritance:r`
    leaves every later child with an empty access list that nobody, not even the user, can open.
    """
    rights = "(OI)(CI)(F)" if is_dir else "(F)"
    return ["icacls", str(path), "/inheritance:r",
            "/grant:r", f"{user}:{rights}", "/grant:r", f"SYSTEM:{rights}"]


def restrict_to_current_user(path: Path) -> None:
    """Best-effort ACL tightening so only the current user (and SYSTEM on Windows) can read."""
    path = Path(path)
    if not path.exists():
        return
    if os.name != "nt":
        try:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        except OSError:
            pass
        return
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        return
    try:
        subprocess.run(
            icacls_arguments(path, user, path.is_dir()),
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
        # Tighten the file before it takes the published name, so the keys in it are never
        # readable under the folder's earlier access list.
        restrict_to_current_user(temporary)
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
    except (OSError, ValueError):
        # Unreadable, not UTF-8 or not JSON: the same as no state file.
        return None
    return payload if isinstance(payload, dict) else None


def clear_state(only_pid: int | None = None) -> None:
    """Remove the state file; with `only_pid`, only when it names that process.

    An agent that stops passes its own process id, so it can never remove the state file of
    another, running agent.
    """
    path = state_path()
    if only_pid is not None:
        state = read_state()
        if state is not None and state.get("pid") != only_pid:
            return
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
