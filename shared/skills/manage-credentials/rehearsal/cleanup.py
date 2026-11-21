"""Clean-up and proof (rehearsal plan, step 8). Removes only what the run made, each by its exact
name: the agent processes the run started, the two keychain users of the run (never by service),
the run folder and the run's cloud subfolder. Then it proves each is gone and names what is left."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from names import PCS, RunNames

SERVICE = "brain-secrets"  # scripts/secret_store/keys.py, SERVICE


@dataclass
class Report:
    left: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def safe_user(user: str, n: RunNames) -> bool:
    """Only the run's own two keychain users may be deleted."""
    return bool(user) and user in {n.keychain_user(pc) for pc in PCS}


def safe_folder(folder: Path | None, n: RunNames) -> bool:
    """Only the run folder and the run's own cloud subfolder may be removed."""
    if folder is None:
        return False
    allowed = [n.temp] + ([n.recovery_dir] if n.recovery_dir else [])
    return any(Path(folder) == place and n.run_id in place.name for place in allowed)


def _writable(func: Callable, path: str, _info: Any) -> None:
    os.chmod(path, stat.S_IWRITE)  # Git marks its object files read-only
    func(path)


def _remove(folder: Path, n: RunNames, report: Report) -> None:
    if not safe_folder(folder, n):
        report.left.append(f"folder {folder} (not the run's own; not removed)")
        return
    if folder.exists():
        shutil.rmtree(folder, onexc=_writable)
    if folder.exists():
        report.left.append(f"folder {folder}")
    else:
        report.removed.append(f"folder {folder} removed or never made")


def _default_delete_user(user: str) -> None:
    import keyring
    import keyring.errors
    try:
        keyring.delete_password(SERVICE, user)
    except keyring.errors.PasswordDeleteError:
        pass  # nothing stored for this user


def _default_user_present(user: str) -> bool:
    import keyring
    return keyring.get_password(SERVICE, user) is not None


def _default_pipes() -> list[str]:
    if os.name != "nt":
        return []
    try:
        return os.listdir("\\\\.\\pipe\\")
    except OSError:
        return []


def _default_credential_names() -> list[str]:
    """The target names cmdkey lists (names only; cmdkey never shows a stored value)."""
    if os.name != "nt":
        return []
    out = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="replace").stdout
    return [line.split(":", 1)[1].strip() for line in out.splitlines() if line.strip().lower().startswith("target:")]


def stop_processes(processes: Iterable[Any], report: Report) -> None:
    """Stop the agent processes this run started (Popen objects it holds), and check they ended."""
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        if proc.poll() is None:
            report.left.append(f"process {proc.pid}")
        else:
            report.removed.append(f"process {proc.pid} stopped")


def clean_up(n: RunNames, *, check_mode: bool, processes: Iterable[Any] = (),
             delete_user: Callable[[str], None] = _default_delete_user,
             user_present: Callable[[str], bool] = _default_user_present,
             pipes: Callable[[], list[str]] = _default_pipes,
             credential_names: Callable[[], list[str]] = _default_credential_names) -> Report:
    """Remove what the run made and report what is left, by name. --check made no keychain entry,
    no process and nothing in the cloud folder, so it reads and deletes no keychain entry."""
    report = Report()
    stop_processes(processes, report)
    if not check_mode:
        for pc in PCS:
            user = n.keychain_user(pc)
            if safe_user(user, n):
                delete_user(user)
        for pc in PCS:
            user = n.keychain_user(pc)
            if user_present(user):
                report.left.append(f"keychain entry {user}")
            else:
                report.removed.append(f"keychain entry {user} absent")
        report.left += [f"credential {name}" for name in sorted(credential_names()) if n.run_id in name]
    _remove(n.temp, n, report)
    if n.recovery_dir is not None and not check_mode:  # --check never touches the cloud folder
        _remove(n.recovery_dir, n, report)
    report.left += [f"pipe {name}" for name in sorted(pipes()) if n.run_id in name]
    return report
