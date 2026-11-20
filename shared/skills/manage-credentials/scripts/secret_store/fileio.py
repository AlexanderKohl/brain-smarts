"""Local file primitives shared by the refresh journal and the portable vault: an exclusive lock
taken by a non-blocking retry loop with a deadline (a plain message on timeout, never an endless
wait or a platform error), and a durable atomic write.

Durability (design synced-secrets-repository.md, section 9: each journal state is flushed before
the next step). The data goes to a temporary file, which is flushed and fsynced, then replaces
the target atomically. On POSIX the containing folder is then fsynced, so the rename itself
survives a power loss. On Windows the replacement is MoveFileExW with MOVEFILE_WRITE_THROUGH,
which returns only once the move is flushed to disk. The limit: Windows offers no folder fsync
to Python, so the folder entry relies on that write-through flag and on NTFS metadata
journalling; a file system without them (FAT on a USB stick) may lose the last rename."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

POLL_SECONDS = 0.05
_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8


def _try_lock(handle: Any) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked(path: Path, timeout: float, error: Callable[[], Exception]) -> Iterator[None]:
    """Hold an exclusive lock on path; error() is raised when it is not free within timeout."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise error()
            time.sleep(POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(handle)


def _replace_write_through(source: Path, target: Path) -> None:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move = kernel32.MoveFileExW
    move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move.restype = wintypes.BOOL
    if not move(str(source), str(target), _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH):
        raise ctypes.WinError(ctypes.get_last_error())


def _sync_folder(folder: Path) -> None:
    descriptor = os.open(str(folder), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_durable(path: Path, data: bytes) -> None:
    """Write data to path so that either the old or the new content survives a power loss."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "nt":
        _replace_write_through(temporary, path)
    else:
        os.replace(temporary, path)
        _sync_folder(path.parent)


def remove_durable(path) -> None:
    """Remove a file and, on POSIX, flush its folder so the removal survives a power cut."""
    path = Path(path)
    path.unlink(missing_ok=True)
    if os.name != "nt" and path.parent.is_dir():
        handle = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
