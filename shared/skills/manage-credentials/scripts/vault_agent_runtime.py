"""Runtime paths and helpers for the per-login Vault Agent."""

from __future__ import annotations

import errno
import functools
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
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


# -- a folder or file private to the current user, proved (follow-up plan R15, fix 1) ---------------
class NotPrivate(RuntimeError):
    """A folder or file could not be made private to the current user, or proved so. Not an
    OSError, so that no `except OSError` swallows it. The message names the path and the reason,
    never a file's content."""

    def __init__(self, path: Path | str, reason: str) -> None:
        super().__init__(f"{path} cannot be proved private to this user: {reason}")
        self.path = str(path)
        self.reason = reason


def make_private(path: Path | str) -> None:
    """Leave only the current user and the operating system's own account with any right on a
    folder or a file, read the access back and prove it; raise NotPrivate when a call fails or
    the proof does not hold.

    Windows: the user is the user SID of the process token (never an environment variable). A
    protected access list of exactly two full-access allow entries, that SID and SYSTEM
    (inherited by children on a folder), is written whole, then the owner is set to that SID.
    The proof reads both back: the list is present, protected, without an inherited entry, every
    entry an allow entry for that SID or SYSTEM, the user's entry full access; the owner is that
    SID and nothing else. POSIX: the path is opened without following a link and changed and
    proved on that descriptor: mode 0700 or 0600, owner the effective user, a folder or a regular
    file as expected; on Linux the POSIX access lists are removed and an NFSv4 list refuses; on
    macOS the extended access list is emptied; any other POSIX system is refused.

    Limits: the proof covers the folder and the file, not the folder's ancestors (the user's
    profile, private by the system's default), and a client does not prove the file again when it
    reads it; both are to be looked at again if the runtime folder ever becomes configurable.
    SYSTEM reads through its entry, members of the Administrators group can take ownership by
    privilege, and root reads on POSIX, by design. A file system without access lists (FAT, some
    network shares) cannot be proved private: the agent refuses to start there, naming the folder.
    The POSIX branches (Linux and macOS) are untested on the computer they were written on.
    """
    path = Path(path)
    if os.name == "nt":
        _windows_set(path)
        _windows_prove(path)
    else:
        _posix(path, change=True)


def is_private(path: Path | str) -> bool:
    """The proof of make_private alone: True only when it holds. Changes nothing."""
    try:
        if os.name == "nt":
            _windows_prove(Path(path))
        else:
            _posix(Path(path), change=False)
    except (NotPrivate, OSError):
        return False
    return True


_SYSTEM_SID = "S-1-5-18"
_SE_FILE_OBJECT = 1
_OWNER_INFO, _DACL_INFO, _PROTECTED_DACL_INFO = 0x1, 0x4, 0x80000000
_SE_DACL_PRESENT, _SE_DACL_PROTECTED = 0x0004, 0x1000
_ALLOW_ACE, _INHERIT_ONLY_ACE, _INHERITED_ACE = 0, 0x08, 0x10
_FILE_ALL_ACCESS = 0x1F01FF
_TOKEN_QUERY, _TOKEN_USER, _ACL_SIZE_INFORMATION = 0x0008, 1, 2
_ERROR_INSUFFICIENT_BUFFER = 122


def _bind(function: Any, restype: Any, *argtypes: Any) -> Any:
    function.restype, function.argtypes = restype, argtypes
    return function


@functools.lru_cache(maxsize=None)
def _win_api() -> SimpleNamespace:
    import ctypes
    from ctypes import wintypes as w

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    p, out = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)

    class AclSize(ctypes.Structure):
        _fields_ = [("AceCount", w.DWORD), ("AclBytesInUse", w.DWORD), ("AclBytesFree", w.DWORD)]

    class AceHead(ctypes.Structure):  # ACE_HEADER and the access mask; the SID starts at byte 8
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte), ("AceSize", ctypes.c_ushort),
                    ("Mask", w.DWORD)]

    return SimpleNamespace(
        AclSize=AclSize, AceHead=AceHead,
        GetCurrentProcess=_bind(kernel32.GetCurrentProcess, w.HANDLE),
        CloseHandle=_bind(kernel32.CloseHandle, w.BOOL, w.HANDLE),
        LocalFree=_bind(kernel32.LocalFree, p, p),
        OpenProcessToken=_bind(advapi32.OpenProcessToken, w.BOOL, w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)),
        GetTokenInformation=_bind(advapi32.GetTokenInformation, w.BOOL, w.HANDLE, ctypes.c_int, p, w.DWORD,
                                  ctypes.POINTER(w.DWORD)),
        ConvertSidToStringSidW=_bind(advapi32.ConvertSidToStringSidW, w.BOOL, p, ctypes.POINTER(w.LPWSTR)),
        ConvertSd=_bind(advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW, w.BOOL, w.LPCWSTR, w.DWORD,
                        out, ctypes.POINTER(w.ULONG)),
        GetSecurityDescriptorDacl=_bind(advapi32.GetSecurityDescriptorDacl, w.BOOL, p, ctypes.POINTER(w.BOOL), out,
                                        ctypes.POINTER(w.BOOL)),
        GetSecurityDescriptorOwner=_bind(advapi32.GetSecurityDescriptorOwner, w.BOOL, p, out, ctypes.POINTER(w.BOOL)),
        GetSecurityDescriptorControl=_bind(advapi32.GetSecurityDescriptorControl, w.BOOL, p, ctypes.POINTER(w.WORD),
                                           ctypes.POINTER(w.DWORD)),
        SetNamedSecurityInfoW=_bind(advapi32.SetNamedSecurityInfoW, w.DWORD, w.LPWSTR, ctypes.c_int, w.DWORD, p, p,
                                    p, p),
        GetNamedSecurityInfoW=_bind(advapi32.GetNamedSecurityInfoW, w.DWORD, w.LPCWSTR, ctypes.c_int, w.DWORD, out,
                                    out, out, out, out),
        GetAclInformation=_bind(advapi32.GetAclInformation, w.BOOL, p, p, w.DWORD, ctypes.c_int),
        GetAce=_bind(advapi32.GetAce, w.BOOL, p, w.DWORD, out),
    )


def _failed(path: Path | str, what: str, code: int) -> NotPrivate:
    return NotPrivate(path, f"{what} failed (Windows error {code})")


def _local_free(api: SimpleNamespace, pointer: Any, path: Path | str) -> None:
    import ctypes

    if api.LocalFree(ctypes.cast(pointer, ctypes.c_void_p)):  # NULL means freed
        raise _failed(path, "LocalFree", ctypes.get_last_error())


def _sid_text(api: SimpleNamespace, sid: Any, path: Path | str) -> str:
    import ctypes
    from ctypes import wintypes

    text = wintypes.LPWSTR()
    if not api.ConvertSidToStringSidW(sid, ctypes.byref(text)) or not text.value:
        raise _failed(path, "ConvertSidToStringSidW", ctypes.get_last_error())
    try:
        return text.value
    finally:
        _local_free(api, text, path)


def _token_user_sid(api: SimpleNamespace, path: Path | str) -> str:
    """The user SID of this process's token, as text."""
    import ctypes
    from ctypes import wintypes

    token = wintypes.HANDLE()
    if not api.OpenProcessToken(api.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        raise _failed(path, "OpenProcessToken", ctypes.get_last_error())
    try:
        needed = wintypes.DWORD(0)
        if api.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed)):
            raise NotPrivate(path, "GetTokenInformation succeeded with no buffer")
        if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER or not needed.value:
            raise _failed(path, "GetTokenInformation (size)", ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(needed.value)
        if not api.GetTokenInformation(token, _TOKEN_USER, buffer, needed, ctypes.byref(needed)):
            raise _failed(path, "GetTokenInformation", ctypes.get_last_error())
        sid = ctypes.c_void_p.from_buffer(buffer).value  # TOKEN_USER begins with the user's PSID
        if not sid:
            raise NotPrivate(path, "the process token names no user")
        return _sid_text(api, sid, path)
    finally:
        if not api.CloseHandle(token):
            raise _failed(path, "CloseHandle", ctypes.get_last_error())


def _windows_set(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    api = _win_api()
    sid = _token_user_sid(api, path)
    flags = "OICI" if path.is_dir() else ""
    descriptor = ctypes.c_void_p()
    if not api.ConvertSd(f"O:{sid}D:P(A;{flags};FA;;;{sid})(A;{flags};FA;;;SY)", 1, ctypes.byref(descriptor), None):
        raise _failed(path, "building the access list", ctypes.get_last_error())
    try:
        present, defaulted, dacl, owner = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p(), ctypes.c_void_p()
        found = api.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl),
                                              ctypes.byref(defaulted))
        if not found or not present.value or not dacl.value:
            raise _failed(path, "GetSecurityDescriptorDacl", ctypes.get_last_error())
        found = api.GetSecurityDescriptorOwner(descriptor, ctypes.byref(owner), ctypes.byref(defaulted))
        if not found or not owner.value:
            raise _failed(path, "GetSecurityDescriptorOwner", ctypes.get_last_error())
        # The list first, written whole: the user's own entry then grants the right to change the owner.
        code = api.SetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT, _DACL_INFO | _PROTECTED_DACL_INFO, None, None,
                                         dacl, None)
        if code != 0:
            raise _failed(path, "writing the access list", code)
        code = api.SetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT, _OWNER_INFO, owner, None, None, None)
        if code != 0:
            raise _failed(path, "setting the owner to this user", code)
    finally:
        _local_free(api, descriptor, path)


def _windows_prove(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    api = _win_api()
    sid = _token_user_sid(api, path)
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    code = api.GetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT, _OWNER_INFO | _DACL_INFO, ctypes.byref(owner), None,
                                     ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if code != 0:
        raise _failed(path, "reading its owner and access list", code)
    try:
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not api.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise _failed(path, "GetSecurityDescriptorControl", ctypes.get_last_error())
        if not control.value & _SE_DACL_PRESENT or not dacl.value:
            raise NotPrivate(path, "it has no access list, which lets everyone in")
        if not control.value & _SE_DACL_PROTECTED:
            raise NotPrivate(path, "its access list is not protected from the folder above")
        if not owner.value or _sid_text(api, owner.value, path) != sid:
            raise NotPrivate(path, "its owner is not this user")
        size = api.AclSize()
        if not api.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), _ACL_SIZE_INFORMATION):
            raise _failed(path, "GetAclInformation", ctypes.get_last_error())
        user_full = False
        for index in range(size.AceCount):
            ace = ctypes.c_void_p()
            if not api.GetAce(dacl, index, ctypes.byref(ace)) or not ace.value:
                raise _failed(path, "GetAce", ctypes.get_last_error())
            head = api.AceHead.from_address(ace.value)
            if head.AceType != _ALLOW_ACE:
                raise NotPrivate(path, "its access list holds an entry that is not an allow entry")
            if head.AceFlags & _INHERITED_ACE:
                raise NotPrivate(path, "its access list holds an inherited entry")
            trustee = _sid_text(api, ace.value + 8, path)
            if trustee not in (sid, _SYSTEM_SID):
                raise NotPrivate(path, f"its access list grants a right to {trustee}")
            if trustee == sid and not head.AceFlags & _INHERIT_ONLY_ACE \
                    and head.Mask & _FILE_ALL_ACCESS == _FILE_ALL_ACCESS:
                user_full = True
        if not user_full:
            raise NotPrivate(path, "this user's entry does not grant full access")
    finally:
        _local_free(api, descriptor, path)


# POSIX: untested on the Windows computer this was written on (follow-up plan R15, amendments).
def _posix(path: Path, change: bool) -> None:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise NotPrivate(path, f"it cannot be read ({exc.strerror})") from exc
    if stat.S_ISLNK(before.st_mode):
        raise NotPrivate(path, "it is a symbolic link")
    folder = stat.S_ISDIR(before.st_mode)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags | (os.O_DIRECTORY if folder else 0))
    except OSError as exc:
        raise NotPrivate(path, f"it cannot be opened without following a link ({exc.strerror})") from exc
    try:
        if change:
            try:
                os.fchmod(descriptor, 0o700 if folder else 0o600)
            except OSError as exc:
                raise NotPrivate(path, f"its mode cannot be set ({exc.strerror})") from exc
        if sys.platform.startswith("linux"):
            _linux_lists(path, descriptor, change)
        elif sys.platform == "darwin":
            _darwin_lists(path, descriptor, change)
        else:
            raise NotPrivate(path, f"access lists on {sys.platform} cannot be proved")
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid():
            raise NotPrivate(path, "its owner is not this user")
        if not (stat.S_ISDIR(info.st_mode) if folder else stat.S_ISREG(info.st_mode)):
            raise NotPrivate(path, "it is not the folder or regular file expected")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise NotPrivate(path, "its group or other users hold a right on it")
    finally:
        os.close(descriptor)


_LINUX_ACLS = ("system.posix_acl_access", "system.posix_acl_default")


def _linux_names(path: Path, descriptor: int) -> list[str]:
    try:
        names = os.listxattr(descriptor)
    except OSError as exc:
        if exc.errno in (errno.ENOTSUP, errno.EOPNOTSUPP):  # no extended attributes, so no access lists
            return []
        raise NotPrivate(path, f"its extended attributes cannot be listed ({exc.strerror})") from exc
    if any(name.startswith("system.nfs4") for name in names):
        raise NotPrivate(path, "it carries an NFSv4 access list, which its mode does not show")
    return [name for name in _LINUX_ACLS if name in names]


def _linux_lists(path: Path, descriptor: int, change: bool) -> None:
    present = _linux_names(path, descriptor)
    if present and change:
        for name in present:
            try:
                os.removexattr(descriptor, name)
            except OSError as exc:
                raise NotPrivate(path, f"its access list {name} cannot be removed ({exc.strerror})") from exc
        present = _linux_names(path, descriptor)
    if present:
        raise NotPrivate(path, "it carries a POSIX access list")


_ACL_TYPE_EXTENDED, _ACL_FIRST_ENTRY = 0x00000100, 0


@functools.lru_cache(maxsize=None)
def _darwin_api() -> SimpleNamespace:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    p, i = ctypes.c_void_p, ctypes.c_int
    return SimpleNamespace(
        get_fd=_bind(libc.acl_get_fd_np, p, i, i),
        get_entry=_bind(libc.acl_get_entry, i, p, i, ctypes.POINTER(p)),
        init=_bind(libc.acl_init, p, i),
        set_fd=_bind(libc.acl_set_fd_np, i, i, p, i),
        free=_bind(libc.acl_free, i, p),
    )


def _darwin_free(api: SimpleNamespace, acl: Any, path: Path) -> None:
    import ctypes

    if api.free(acl) != 0:
        raise NotPrivate(path, f"acl_free failed (error {ctypes.get_errno()})")


def _darwin_has_entry(api: SimpleNamespace, path: Path, descriptor: int) -> bool:
    import ctypes

    acl = api.get_fd(descriptor, _ACL_TYPE_EXTENDED)
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:  # no extended access list
            return False
        raise NotPrivate(path, f"its access list cannot be read (error {ctypes.get_errno()})")
    try:
        entry = ctypes.c_void_p()
        if api.get_entry(acl, _ACL_FIRST_ENTRY, ctypes.byref(entry)) == 0:
            return True
        if ctypes.get_errno() == errno.EINVAL:  # an empty list
            return False
        raise NotPrivate(path, f"its access list cannot be read (error {ctypes.get_errno()})")
    finally:
        _darwin_free(api, acl, path)


def _darwin_lists(path: Path, descriptor: int, change: bool) -> None:
    import ctypes

    api = _darwin_api()
    if not _darwin_has_entry(api, path, descriptor):
        return
    if change:
        empty = api.init(0)
        if not empty:
            raise NotPrivate(path, f"acl_init failed (error {ctypes.get_errno()})")
        try:
            if api.set_fd(descriptor, empty, _ACL_TYPE_EXTENDED) != 0:
                raise NotPrivate(path, f"its access list cannot be emptied (error {ctypes.get_errno()})")
        finally:
            _darwin_free(api, empty, path)
        if not _darwin_has_entry(api, path, descriptor):
            return
    raise NotPrivate(path, "it carries an extended access list")


def prepare_runtime_dir() -> None:
    """Make the runtime folder private, proved, and remove temporary files a dead agent left.

    Raises NotPrivate when the folder cannot be proved private: the agent does not start there.
    It never removes the state file or the singleton lock. A state file left by an agent that
    has ended is harmless: clients refuse it because its process is gone, and the next agent
    overwrites it. Removing it here once let a second start, or a test, take away the state
    file of an agent that was running or just starting.
    """
    directory = runtime_dir()
    make_private(directory)
    cutoff = time.time() - 60
    for leftover in directory.glob("agent-state*.tmp"):
        try:
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink()
        except OSError:
            pass


def restrict_to_current_user(path: Path) -> None:
    """Best effort: make_private for what does not hold the token or the key in the clear (the
    old vault's folder, the singleton lock). A failure is swallowed; nothing is proved."""
    path = Path(path)
    if not path.exists():
        return
    try:
        make_private(path)
    except (NotPrivate, OSError):
        pass


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # Could not remove it: empty it, so no copy of the payload stays.
        try:
            with path.open("w", encoding="utf-8"):
                pass
            path.unlink()
        except OSError:
            pass


def write_state(payload: dict[str, Any]) -> None:
    """Publish the agent's state file, holding its token and pipe key in the clear.

    The order (follow-up plan R15, fix 1, rule 4): the folder is proved private; the temporary
    file is created in it and proved private while it is still empty, its descriptor open
    (Windows accepts a new access list on a file this process holds open); only then the
    payload is written, flushed and synced; the file takes the published name; the published
    path is proved private again. Any failure raises (NotPrivate when a proof fails) and leaves
    no file holding the payload.
    """
    path = state_path()
    folder = path.parent
    make_private(folder)
    # Unique temp name avoids PermissionError on a stale locked agent-state.tmp.
    descriptor, temporary_name = tempfile.mkstemp(prefix="agent-state.", suffix=".tmp", dir=folder)
    temporary = Path(temporary_name)
    published = False
    try:
        try:
            make_private(temporary)
        except BaseException:
            os.close(descriptor)
            raise
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        published = True
        if not is_private(path):
            raise NotPrivate(path, "the published file did not keep its private access")
    except BaseException:
        _remove(temporary)
        if published:
            _remove(path)
        raise


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
