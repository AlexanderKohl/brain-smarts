"""Small masked windows that ask for the vault passphrase and secrets, so setup never needs a
terminal the person opens. Python standard library only (tkinter); one version for Windows,
macOS and Linux.

Values typed here are returned to the caller and nothing else: never printed, logged, placed in
argv or the environment. Each Entry widget is cleared once read. Python strings cannot be wiped
from memory, so the caller drops its references as soon as the vault has the values.

The checks (length, match, empty) are plain functions the tests call without a display."""

from __future__ import annotations

from typing import Callable

from portable_vault import CredentialError

MIN_PASSPHRASE_LENGTH = 20
MASK = "*"
NO_WINDOW = (
    "No password window can be shown here: tkinter is missing or there is no display. "
    "Install python-tk (on macOS with Homebrew: brew install python-tk), or run the "
    "terminal command without --window."
)


def check_new_passphrase(first: str, second: str) -> str | None:
    """The problem with a new passphrase typed twice, or None when it is acceptable."""
    if len(first) < MIN_PASSPHRASE_LENGTH:
        return f"The passphrase needs at least {MIN_PASSPHRASE_LENGTH} characters."
    if first != second:
        return "The two passphrases do not match."
    return None


def check_secret_values(values: dict[str, str], fields: list[str]) -> str | None:
    """The first field left empty, as a message, or None when every field has a value."""
    for field in fields:
        if not values.get(field):
            return f"Enter a value for {field}."
    return None


def check_passphrase_given(passphrase: str | None) -> str | None:
    if not passphrase:
        return "Enter the vault passphrase."
    return None


def clean_secret(value: str) -> str:
    """A pasted secret without the line break a copy often carries."""
    return value.strip("\r\n")


def _tk():
    try:
        import tkinter
    except ImportError as exc:
        raise CredentialError(NO_WINDOW) from exc
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        raise CredentialError(NO_WINDOW) from exc
    return tkinter, root


def _dialog(
    title: str,
    intro: str,
    labels: list[str],
    validate: Callable[[list[str]], str | None],
    clear_on_error: bool = False,
) -> list[str] | None:
    """Show one masked field per label; the values in order, or None on Cancel, Esc or close."""
    tkinter, root = _tk()
    result: list[list[str]] = []
    try:
        root.title(title)
        root.resizable(False, False)
        frame = tkinter.Frame(root, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        tkinter.Label(frame, text=intro, justify="left", wraplength=380).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        entries = []
        for index, label in enumerate(labels, start=1):
            tkinter.Label(frame, text=label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=2)
            entry = tkinter.Entry(frame, show=MASK, width=36)
            entry.grid(row=index, column=1, sticky="we", pady=2)
            entries.append(entry)
        message = tkinter.Label(frame, text="", fg="#b00020", justify="left", wraplength=380)
        message.grid(row=len(labels) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def clear() -> None:
            for entry in entries:
                entry.delete(0, "end")

        def ok(_event=None) -> None:
            values = [entry.get() for entry in entries]
            problem = validate(values)
            if problem:
                message.configure(text=problem)
                if clear_on_error:
                    clear()
                    entries[0].focus_set()
                return
            result.append(values)
            clear()
            root.destroy()

        def cancel(_event=None) -> None:
            clear()
            root.destroy()

        buttons = tkinter.Frame(frame)
        buttons.grid(row=len(labels) + 2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        tkinter.Button(buttons, text="OK", width=10, command=ok).pack(side="left", padx=4)
        tkinter.Button(buttons, text="Cancel", width=10, command=cancel).pack(side="left")
        root.bind("<Return>", ok)
        root.bind("<KP_Enter>", ok)
        root.bind("<Escape>", cancel)
        root.protocol("WM_DELETE_WINDOW", cancel)
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        if entries:
            entries[0].focus_set()
        root.mainloop()
    except tkinter.TclError as exc:
        raise CredentialError(NO_WINDOW) from exc
    return result[0] if result else None


def ask_new_passphrase() -> str | None:
    """A new vault passphrase typed twice; None when the person cancels."""
    values = _dialog(
        "New vault passphrase",
        f"Choose a vault recovery passphrase of at least {MIN_PASSPHRASE_LENGTH} characters and "
        "type it twice. Keep it safe outside this computer: there is no reset, and losing it "
        "loses everything in the vault.",
        ["Passphrase", "Repeat passphrase"],
        lambda values: check_new_passphrase(values[0], values[1]),
        clear_on_error=True,
    )
    return None if values is None else values[0]


def ask_secrets(
    title: str, fields: list[str], need_passphrase: bool
) -> tuple[dict[str, str], str | None] | None:
    """(values by field, vault passphrase or None) from one window; None when cancelled.
    The passphrase field is shown only when need_passphrase."""
    labels = list(fields) + (["Vault passphrase"] if need_passphrase else [])

    def split(values: list[str]) -> tuple[dict[str, str], str | None]:
        secrets = {field: clean_secret(value) for field, value in zip(fields, values)}
        return secrets, (values[len(fields)] if need_passphrase else None)

    def validate(values: list[str]) -> str | None:
        secrets, passphrase = split(values)
        problem = check_secret_values(secrets, fields)
        if problem is None and need_passphrase:
            problem = check_passphrase_given(passphrase)
        return problem

    intro = "Paste or type each value. Nothing you enter is shown or printed."
    if need_passphrase:
        intro += " The vault is locked, so its passphrase is needed too."
    values = _dialog(title, intro, labels, validate)
    return None if values is None else split(values)
