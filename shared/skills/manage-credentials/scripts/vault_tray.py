"""Per-login Vault Agent tray app: broker + unlock prompt + grey/red status icon."""

from __future__ import annotations

import argparse
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Any

from portable_vault import CredentialError, default_vault_path
from secret_store.errors import SecretStoreError
from vault_agent import AgentAlreadyRunning, VaultAgent, build_agent
from vault_agent_runtime import NotPrivate, log_tray, prepare_runtime_dir
from vault_broker_client import broker_available

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
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = _LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL


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


def _prompt_passphrase(title: str = "Unlock Portable Vault", cancelled: Any = None) -> str | None:
    """Modal Win32 password dialog anchored near the system tray (closes on OK/Cancel).

    `cancelled` (plan R22): when it returns True the window is not made, or closes itself while open
    (it is looked at every 0.2 seconds), and nothing is returned; it is looked at again after the
    window has returned. The window also closes itself after ten minutes."""
    stopped = cancelled or (lambda: False)
    if stopped():
        return None
    result: dict[str, str | None] = {"value": None}
    window: dict[str, Any] = {"hwnd": None, "cancelled": False}
    done = threading.Event()

    def ui() -> None:
        try:
            result["value"] = _win_password_dialog(title, window)
        finally:
            done.set()

    thread = threading.Thread(target=ui, name="vault-passphrase-ui", daemon=True)
    thread.start()
    deadline = time.monotonic() + 600
    while not done.wait(timeout=0.2):
        if stopped() or time.monotonic() >= deadline:
            window["cancelled"] = True  # a window not yet made closes as soon as it is
            if window["hwnd"]:
                user32.PostMessageW(window["hwnd"], _WM_CLOSE, 0, 0)
            return None
    if stopped():
        return None
    value = result["value"]
    if value is None:
        return None
    value = value.strip()
    return value or None


_WM_KEYDOWN = 0x0100
_VK_RETURN = 0x0D
_VK_ESCAPE = 0x1B
_DIALOG_CLIENT_HEIGHT = 132  # the buttons end at 116; 16 below them, as at the sides


def _dialog_key_command(message: int, key: int) -> int | None:
    """The button a key press stands for: Enter is OK, Esc is Cancel, anything else none."""
    if message != _WM_KEYDOWN:
        return None
    return {_VK_RETURN: _IDC_OK, _VK_ESCAPE: _IDC_CANCEL}.get(int(key))


def _outer_size(client_width: int, client_height: int, style: int, ex_style: int) -> tuple[int, int]:
    """Window size whose inside is the given size, so the title bar never eats the buttons."""
    rect = _RECT(0, 0, client_width, client_height)
    if not user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, ex_style):
        return client_width + 16, client_height + 48
    return rect.right - rect.left, rect.bottom - rect.top


def _win_password_dialog(title: str, window: dict[str, Any] | None = None) -> str | None:
    style = _WS_POPUP | _WS_CAPTION | _WS_SYSMENU | _DS_MODALFRAME
    ex_style = _WS_EX_DLGMODALFRAME | _WS_EX_TOPMOST
    width, height = _outer_size(372, _DIALOG_CLIENT_HEIGHT, style, ex_style)
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
    if window is not None:
        # Published before the cancel flag is read; the waiting side sets the flag before it reads
        # the handle, so either this sees the flag or that side posts WM_CLOSE (plan R22).
        window["hwnd"] = hwnd
        if window.get("cancelled"):
            user32.DestroyWindow(hwnd)
            return None
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
        # This window is not a dialog class, so Enter and Esc reach no default button on
        # their own: turn them into the button's command here. A focused button keeps Enter.
        command = _dialog_key_command(msg.message, msg.wParam)
        if command == _IDC_OK and msg.hWnd != edit:
            command = None
        if command is not None:
            user32.SendMessageW(hwnd, _WM_COMMAND, command, 0)
        elif not user32.IsDialogMessageW(hwnd, ctypes.byref(msg)):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if state["finished"]:
            break

    return state["result"]


class VaultTrayApp:
    def __init__(self, vault_path: str | None = None) -> None:
        self.pystray, self.Image, self.ImageDraw = _require_tray_deps()
        self.agent = build_agent(vault_path or default_vault_path())  # raises for a malformed configuration
        self._serve_thread: threading.Thread | None = None
        self._icon: Any = None
        self._stop = threading.Event()
        self._another_agent = False

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
            except AgentAlreadyRunning as exc:
                # run() decides whether this is worth a dialog: a healthy agent needs none.
                log_tray(f"lock held by another agent: {exc}")
                self._another_agent = True
                self._stop.set()
            except Exception as exc:  # noqa: BLE001
                # Shut down and stop before anything is logged or shown (plan R21): a dialog must
                # never stand in front of an agent that still serves, or of a tray that stays up.
                self._give_up_start()
                self._stop.set()
                if self._icon is not None:
                    self._icon.stop()
                if isinstance(exc, CredentialError):
                    log_tray(f"agent stopped: {exc}")
                    _show_error(str(exc))
                else:
                    log_tray(f"agent stopped unexpectedly: {exc!r}")
                    _show_error(f"Vault Agent stopped unexpectedly: {exc}")

        self._serve_thread = threading.Thread(target=run, name="vault-agent", daemon=True)
        self._serve_thread.start()
        # The agent may wait for a busy lock before it starts, so the window covers that wait.
        window = VaultAgent.LOCK_WAIT_SECONDS + 5
        deadline = time.time() + window
        while time.time() < deadline:
            if self._stop.is_set():
                self._give_up_start()
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
        self._give_up_start()
        raise CredentialError(
            f"Vault Agent did not start within {window:.0f} seconds: its state file was not written."
        )

    def _icon_ready(self, icon: Any) -> None:
        """pystray's setup, once the icon's loop runs: shown, or stopped at once when the agent stopped
        between the check in run and the icon's existence (plan R21)."""
        icon.visible = True
        if self._stop.is_set():
            icon.stop()

    def _give_up_start(self) -> None:
        """A start the tray gives up on may already have its listener: it is shut down before the
        failure is reported (plan R20, amendments)."""
        try:
            self.agent.shutdown()
        except Exception:  # noqa: BLE001
            pass

    def _do_unlock(self, _icon: Any = None, _item: Any = None) -> None:
        if self.agent._store is not None:  # store mode: no unlock window (round-9 plan, M2)
            self._refresh_icon()
            return
        if self._unlocked():
            _show_info("Vault is already unlocked.")
            self._refresh_icon()
            return
        def stopping() -> bool:
            return self._stop.is_set() or self.agent._fenced()

        if stopping():
            # A stopping agent takes no passphrase: no window asks for one (plan R21, rule 6).
            return
        passphrase = _prompt_passphrase(cancelled=stopping)
        if passphrase is None or stopping():  # looked at again before the value is handed over (R22)
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
        # shutdown directly: it takes the passphrase away itself, and lock() would take _lock before
        # the fence (plan R20, amendments).
        try:
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
        log_tray("tray starting")
        try:
            # A runtime folder that cannot be proved private is a failed start like any other.
            prepare_runtime_dir()
            self._start_broker()
        except (CredentialError, NotPrivate) as exc:
            if self._another_agent and broker_available():
                # A healthy agent already serves this login, so there is nothing to start or report.
                log_tray("a healthy agent is already running; this start ends quietly")
                return 0
            log_tray(f"start failed: {exc}")
            _show_error(
                f"{exc}\n\n"
                "If another Vault Agent is still running, quit it from the tray "
                "(or close the old PowerShell serve window), then start again."
            )
            return 2

        if prompt_on_start and self.agent._store is None and not self._unlocked():
            if _ask_unlock_now():
                self._do_unlock()

        if self._stop.is_set():
            # The agent stopped before the icon existed (plan R21): its loop is never entered.
            self._give_up_start()
            return 2
        self._icon = self.pystray.Icon(
            "PortableAIBrainVault",
            _make_icon(self._unlocked(), self.Image, self.ImageDraw),
            self._title(),
            self._menu(),
        )
        self._icon.run(setup=self._icon_ready)
        try:
            self.agent.shutdown()  # directly, as in _do_quit
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
    try:
        app = VaultTrayApp(args.vault)
    except SecretStoreError as exc:  # a malformed configuration: the tray does not start
        log_tray(f"start refused: {exc}")
        _show_error(f"The Vault Agent cannot start: the secrets-store configuration is not usable: {exc}")
        return 2
    return app.run(prompt_on_start=not args.no_prompt)


if __name__ == "__main__":
    raise SystemExit(main())
