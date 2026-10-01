"""Per-login Vault Agent tray app: broker + unlock prompt + grey/red status icon."""

from __future__ import annotations

import argparse
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Any

from portable_vault import CredentialError, default_vault_path
from vault_agent import VaultAgent
from vault_agent_runtime import prepare_runtime_dir

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 MessageBox / dialog constants
_MB_OK = 0x00000000
_MB_YESNO = 0x00000004
_MB_ICONERROR = 0x00000010
_MB_ICONQUESTION = 0x00000020
_MB_ICONINFORMATION = 0x00000040
_MB_TOPMOST = 0x00040000
_IDYES = 6
_IDOK = 1
_IDCANCEL = 2

_WM_DESTROY = 0x0002
_WM_CLOSE = 0x0010
_WM_COMMAND = 0x0111
_WM_SETFOCUS = 0x0007
_BS_DEFPUSHBUTTON = 0x00000001
_BS_PUSHBUTTON = 0x00000000
_ES_PASSWORD = 0x0020
_ES_AUTOHSCROLL = 0x0080
_ES_LEFT = 0x0000
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_TABSTOP = 0x00010000
_WS_CAPTION = 0x00C00000
_WS_SYSMENU = 0x00080000
_WS_POPUP = 0x80000000
_WS_BORDER = 0x00800000
_DS_MODALFRAME = 0x00000080
_WS_EX_DLGMODALFRAME = 0x00000001
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080
_SWP_NOZORDER = 0x0004
_SWP_SHOWWINDOW = 0x0040
_SW_SHOW = 5
_SPI_GETWORKAREA = 0x0030
_WHITE_BRUSH = 0
_IDC_EDIT = 1001
_IDC_OK = 1002
_IDC_CANCEL = 1003

_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(
    _LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)
# Without these, ctypes passes a 64-bit LPARAM (a pointer, for example during window creation) as a
# 32-bit int, and the call fails with "OverflowError: int too long to convert".
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = _LRESULT


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _require_tray_deps() -> tuple[Any, Any, Any]:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit(
            "Missing tray dependencies. From the repo root run:\n"
            "  cd <brain root>   (the folder holding CONTRACT.md)\n"
            "  python -m pip install -r shared/skills/manage-credentials/requirements.txt"
        ) from exc
    return pystray, Image, ImageDraw


def _work_area() -> _RECT:
    rect = _RECT()
    user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect


def _position_near_tray(width: int, height: int, margin: int = 12) -> tuple[int, int]:
    area = _work_area()
    x = int(area.right - width - margin)
    y = int(area.bottom - height - margin)
    return max(int(area.left), x), max(int(area.top), y)


def _create_tray_anchor() -> wintypes.HWND:
    """Tiny owner window near the notification area so MessageBox appears by the tray."""
    x, y = _position_near_tray(8, 8, margin=24)
    hwnd = user32.CreateWindowExW(
        _WS_EX_TOOLWINDOW | _WS_EX_TOPMOST,
        "STATIC",
        "",
        _WS_POPUP,
        x,
        y,
        8,
        8,
        None,
        None,
        kernel32.GetModuleHandleW(None),
        None,
    )
    if hwnd:
        user32.SetWindowPos(hwnd, None, x, y, 8, 8, _SWP_NOZORDER | _SWP_SHOWWINDOW)
    return hwnd


def _win_message(text: str, *, title: str = "Portable Vault", flags: int) -> int:
    owner = _create_tray_anchor()
    try:
        return int(
            user32.MessageBoxW(
                owner,
                str(text),
                title,
                flags | _MB_TOPMOST,
            )
        )
    finally:
        if owner:
            user32.DestroyWindow(owner)


def _show_info(message: str) -> None:
    _win_message(message, flags=_MB_OK | _MB_ICONINFORMATION)


def _show_error(message: str) -> None:
    _win_message(message, flags=_MB_OK | _MB_ICONERROR)


def _ask_unlock_now() -> bool:
    return (
        _win_message(
            "Unlock the portable credential vault for this Windows login?",
            flags=_MB_YESNO | _MB_ICONQUESTION,
        )
        == _IDYES
    )


def _make_icon(unlocked: bool, Image: Any, ImageDraw: Any) -> Any:
    colour = (200, 40, 40, 255) if unlocked else (140, 140, 140, 255)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=colour)
    draw.rectangle((22, 30, 42, 50), fill=(255, 255, 255, 230))
    draw.arc((24, 16, 40, 36), start=0, end=180, fill=(255, 255, 255, 230), width=4)
    return image


def _prompt_passphrase(title: str = "Unlock Portable Vault") -> str | None:
    """Modal Win32 password dialog anchored near the system tray (closes on OK/Cancel)."""
    result: dict[str, str | None] = {"value": None}
    done = threading.Event()

    def ui() -> None:
        try:
            result["value"] = _win_password_dialog(title)
        finally:
            done.set()

    thread = threading.Thread(target=ui, name="vault-passphrase-ui", daemon=True)
    thread.start()
    if not done.wait(timeout=600):
        return None
    value = result["value"]
    if value is None:
        return None
    value = value.strip()
    return value or None


def _win_password_dialog(title: str) -> str | None:
    width, height = 380, 150
    x, y = _position_near_tray(width, height, margin=16)
    hinstance = kernel32.GetModuleHandleW(None)
    class_name = "PortableVaultUnlockDialog"
    state: dict[str, Any] = {
        "hwnd": None,
        "edit": None,
        "result": None,
        "finished": False,
    }

    @_WNDPROC
    def wndproc(hwnd, msg, wparam, lparam):  # type: ignore[no-untyped-def]
        if msg == _WM_SETFOCUS and state["edit"]:
            user32.SetFocus(state["edit"])
            return 0
        if msg == _WM_COMMAND:
            control_id = int(wparam & 0xFFFF)
            if control_id == _IDC_OK:
                length = user32.GetWindowTextLengthW(state["edit"]) + 1
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(state["edit"], buf, length)
                state["result"] = buf.value
                state["finished"] = True
                user32.DestroyWindow(hwnd)
                return 0
            if control_id == _IDC_CANCEL:
                state["result"] = None
                state["finished"] = True
                user32.DestroyWindow(hwnd)
                return 0
        if msg == _WM_CLOSE:
            state["result"] = None
            state["finished"] = True
            user32.DestroyWindow(hwnd)
            return 0
        if msg == _WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # Keep callback alive for the class lifetime.
    state["wndproc"] = wndproc

    wc = _WNDCLASSW()
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinstance
    wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
    wc.hbrBackground = ctypes.c_void_p(6)  # COLOR_WINDOW + 1
    wc.lpszClassName = class_name
    user32.RegisterClassW(ctypes.byref(wc))  # fails harmlessly if already registered

    style = _WS_POPUP | _WS_CAPTION | _WS_SYSMENU | _DS_MODALFRAME
    ex_style = _WS_EX_DLGMODALFRAME | _WS_EX_TOPMOST
    hwnd = user32.CreateWindowExW(
        ex_style,
        class_name,
        title,
        style,
        x,
        y,
        width,
        height,
        None,
        None,
        hinstance,
        None,
    )
    if not hwnd:
        return None
    state["hwnd"] = hwnd

    user32.CreateWindowExW(
        0,
        "STATIC",
        "Vault recovery passphrase:",
        _WS_CHILD | _WS_VISIBLE,
        16,
        16,
        340,
        20,
        hwnd,
        None,
        hinstance,
        None,
    )
    edit = user32.CreateWindowExW(
        0,
        "EDIT",
        "",
        _WS_CHILD | _WS_VISIBLE | _WS_TABSTOP | _WS_BORDER | _ES_LEFT | _ES_PASSWORD | _ES_AUTOHSCROLL,
        16,
        44,
        340,
        26,
        hwnd,
        _IDC_EDIT,
        hinstance,
        None,
    )
    state["edit"] = edit
    user32.CreateWindowExW(
        0,
        "BUTTON",
        "OK",
        _WS_CHILD | _WS_VISIBLE | _WS_TABSTOP | _BS_DEFPUSHBUTTON,
        180,
        88,
        80,
        28,
        hwnd,
        _IDC_OK,
        hinstance,
        None,
    )
    user32.CreateWindowExW(
        0,
        "BUTTON",
        "Cancel",
        _WS_CHILD | _WS_VISIBLE | _WS_TABSTOP | _BS_PUSHBUTTON,
        276,
        88,
        80,
        28,
        hwnd,
        _IDC_CANCEL,
        hinstance,
        None,
    )

    user32.SetWindowPos(hwnd, None, x, y, width, height, _SWP_SHOWWINDOW)
    user32.ShowWindow(hwnd, _SW_SHOW)
    user32.UpdateWindow(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(edit)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if not user32.IsDialogMessageW(hwnd, ctypes.byref(msg)):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if state["finished"]:
            break

    return state["result"]


class VaultTrayApp:
    def __init__(self, vault_path: str | None = None) -> None:
        self.pystray, self.Image, self.ImageDraw = _require_tray_deps()
        self.agent = VaultAgent(vault_path or default_vault_path())
        self._serve_thread: threading.Thread | None = None
        self._icon: Any = None
        self._stop = threading.Event()

    def _unlocked(self) -> bool:
        return bool(self.agent.status().get("unlocked"))

    def _title(self) -> str:
        state = "unlocked (red)" if self._unlocked() else "locked (grey)"
        return f"Portable Vault — {state}"

    def _refresh_icon(self) -> None:
        if self._icon is None:
            return
        self._icon.icon = _make_icon(self._unlocked(), self.Image, self.ImageDraw)
        self._icon.title = self._title()

    def _start_broker(self) -> None:
        def run() -> None:
            try:
                self.agent.serve_forever()
            except CredentialError as exc:
                _show_error(str(exc))
                self._stop.set()
                if self._icon is not None:
                    self._icon.stop()
            except Exception as exc:  # noqa: BLE001
                _show_error(f"Vault Agent stopped unexpectedly: {exc}")
                self._stop.set()
                if self._icon is not None:
                    self._icon.stop()

        self._serve_thread = threading.Thread(target=run, name="vault-agent", daemon=True)
        self._serve_thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._stop.is_set():
                raise CredentialError("Vault Agent failed to start.")
            try:
                import os

                from vault_agent_runtime import read_state

                state = read_state()
                if state and int(state.get("pid") or 0) == os.getpid():
                    return
            except Exception:
                pass
            time.sleep(0.1)

    def _do_unlock(self, _icon: Any = None, _item: Any = None) -> None:
        if self._unlocked():
            _show_info("Vault is already unlocked.")
            self._refresh_icon()
            return
        passphrase = _prompt_passphrase()
        if passphrase is None:
            return
        try:
            self.agent.unlock(passphrase)
        except CredentialError as exc:
            _show_error(str(exc))
            return
        self._refresh_icon()

    def _do_lock(self, _icon: Any = None, _item: Any = None) -> None:
        self.agent.lock()
        self._refresh_icon()

    def _do_status(self, _icon: Any = None, _item: Any = None) -> None:
        status = self.agent.status()
        state = "unlocked" if status.get("unlocked") else "locked"
        _show_info(
            f"Vault Agent is {state}.\n"
            f"PID: {status.get('pid')}\n"
            f"Vault: {status.get('vault_path')}"
        )

    def _do_quit(self, icon: Any, _item: Any = None) -> None:
        try:
            self.agent.lock()
            self.agent.shutdown()
        except Exception:
            pass
        self._stop.set()
        icon.stop()

    def _menu(self) -> Any:
        return self.pystray.Menu(
            self.pystray.MenuItem(
                "Unlock…",
                self._do_unlock,
                enabled=lambda _item: not self._unlocked(),
            ),
            self.pystray.MenuItem(
                "Lock",
                self._do_lock,
                enabled=lambda _item: self._unlocked(),
            ),
            self.pystray.MenuItem("Status…", self._do_status),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem("Quit", self._do_quit),
        )

    def run(self, *, prompt_on_start: bool = True) -> int:
        prepare_runtime_dir()
        try:
            self._start_broker()
        except CredentialError as exc:
            _show_error(
                f"{exc}\n\n"
                "If another Vault Agent is still running, quit it from the tray "
                "(or close the old PowerShell serve window), then start again."
            )
            return 2

        if prompt_on_start and not self._unlocked():
            if _ask_unlock_now():
                self._do_unlock()

        self._icon = self.pystray.Icon(
            "PortableAIBrainVault",
            _make_icon(self._unlocked(), self.Image, self.ImageDraw),
            self._title(),
            self._menu(),
        )
        self._icon.run()
        try:
            self.agent.lock()
            self.agent.shutdown()
        except Exception:
            pass
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", help="Override the portable vault path")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Start locked without asking to unlock",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    app = VaultTrayApp(args.vault)
    return app.run(prompt_on_start=not args.no_prompt)


if __name__ == "__main__":
    raise SystemExit(main())
