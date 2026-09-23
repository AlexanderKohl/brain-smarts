"""Initialise, update, unlock and use the portable encrypted credential vault."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import warnings

from portable_vault import CredentialError, PortableVault


ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _passphrase(
    prompt: str = "Vault recovery passphrase: ",
    *,
    allow_session: bool = True,
) -> str:
    if allow_session:
        session_passphrase = os.getenv("PORTABLE_VAULT_PASSPHRASE")
        if session_passphrase:
            return session_passphrase
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", getpass.GetPassWarning)
        value = getpass.getpass(prompt)
        if any(issubclass(item.category, getpass.GetPassWarning) for item in caught):
            raise CredentialError(
                "Hidden passphrase entry is unavailable; refusing echoed input."
            )
    return value


def _new_passphrase() -> str:
    first = _passphrase("New vault recovery passphrase: ", allow_session=False)
    second = _passphrase("Repeat new vault recovery passphrase: ", allow_session=False)
    if first != second:
        raise CredentialError("The new passphrases do not match.")
    return first


def _secret_value(use_stdin: bool, field: str) -> str:
    value = sys.stdin.read().rstrip("\r\n") if use_stdin else getpass.getpass(f"Value for {field}: ")
    if not value:
        raise CredentialError("Empty credential values are not accepted.")
    return value


def _mapping(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError("Mappings must use ENVIRONMENT_VARIABLE=vault_field.")
    environment_name, field = value.split("=", 1)
    if not ENVIRONMENT_NAME.fullmatch(environment_name):
        raise ValueError(f"Invalid environment variable name: {environment_name}")
    if not field:
        raise ValueError("Vault field names cannot be empty.")
    return environment_name, field


def _try_broker_fields(entry: str, fields: list[str]) -> dict[str, object] | None:
    try:
        from vault_broker_client import broker_request, broker_unlocked
    except ImportError:
        return None
    try:
        if not broker_unlocked():
            return None
        values = broker_request("get_fields", entry=entry, fields=fields)
    except CredentialError:
        return None
    return values if isinstance(values, dict) else None


def _credential_environment(
    vault: PortableVault,
    entry: str,
    raw_mappings: list[str],
    passphrase: str | None,
) -> dict[str, str]:
    mappings = [_mapping(mapping) for mapping in raw_mappings]
    field_names = [field for _, field in mappings]
    values = _try_broker_fields(entry, field_names)
    if values is None:
        if not passphrase:
            raise CredentialError(
                "Vault Agent is locked/unavailable. "
                "Start the Portable Vault tray app and unlock it from the tray menu, "
                "or provide an interactive passphrase for this one-shot run."
            )
        values = vault.get_fields(entry, field_names, passphrase)
    environment = os.environ.copy()
    # Never place the master passphrase or vault path into child environments.
    environment.pop("PORTABLE_VAULT_PASSPHRASE", None)
    for environment_name, field in mappings:
        value = values[field]
        if not isinstance(value, str):
            raise CredentialError(f"Only text fields can be mapped: {field}")
        environment[environment_name] = value
    return environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", help="Override the portable vault path")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("init", help="Create a new empty encrypted vault")
    commands.add_parser("check", help="Verify the passphrase and vault integrity")
    commands.add_parser("change-passphrase", help="Re-encrypt with a new passphrase")

    delete_entry = commands.add_parser(
        "delete-entry",
        help="Permanently delete one complete encrypted credential entry",
    )
    delete_entry.add_argument("--entry", required=True)

    put = commands.add_parser("put", help="Store one secret field")
    put.add_argument("--entry", required=True)
    put.add_argument("--field", required=True)
    put.add_argument("--stdin", action="store_true")

    put_entry = commands.add_parser(
        "put-entry",
        help="Unlock once, prompt for every secret, and atomically update one entry",
    )
    put_entry.add_argument("--entry", required=True)
    put_entry.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="FIELD",
        help="Text credential field to request through a hidden prompt; repeat as needed",
    )
    put_entry.add_argument(
        "--empty-json",
        action="append",
        default=[],
        metavar="FIELD",
        help="JSON field to initialise as an empty object; repeat as needed",
    )

    initialise = commands.add_parser("init-json", help="Store an empty JSON object")
    initialise.add_argument("--entry", required=True)
    initialise.add_argument("--field", default="oauth_token_json")

    run = commands.add_parser(
        "run",
        help="Inject mapped text fields and run an authorised child (prefers Vault Agent)",
    )
    run.add_argument("--entry", required=True)
    run.add_argument("--map", action="append", required=True, metavar="ENV=FIELD")
    run.add_argument("command", nargs=argparse.REMAINDER)

    session = commands.add_parser(
        "session",
        help="DEPRECATED emergency shell with mapped fields only (no master passphrase export)",
    )
    session.add_argument("--entry", required=True)
    session.add_argument("--map", action="append", required=True, metavar="ENV=FIELD")
    session.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Optional shell command after --; defaults to PowerShell -NoProfile on Windows",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    vault = PortableVault(args.vault)
    try:
        if args.operation == "init":
            vault.initialize(_new_passphrase())
            print(f"Initialised encrypted credential vault: {vault.path}")
            return 0
        if args.operation == "check":
            vault.load(_passphrase())
            print("Credential vault unlocked and authenticated successfully.")
            return 0
        if args.operation == "change-passphrase":
            old_passphrase = _passphrase("Current vault recovery passphrase: ")
            vault.change_passphrase(old_passphrase, _new_passphrase())
            print("Credential vault recovery passphrase changed.")
            return 0
        if args.operation == "delete-entry":
            confirmation = input(
                f"Type {args.entry} to permanently delete this credential entry: "
            )
            if confirmation != args.entry:
                raise CredentialError("Credential entry deletion was not confirmed.")
            vault.delete_entry(args.entry, _passphrase())
            print(f"Deleted encrypted credential entry: {args.entry}")
            return 0
        if args.operation == "put":
            try:
                from vault_broker_client import broker_request, broker_unlocked

                if broker_unlocked():
                    broker_request(
                        "set_text",
                        entry=args.entry,
                        field=args.field,
                        value=_secret_value(args.stdin, args.field),
                    )
                    print(f"Stored encrypted credential field: {args.entry}#{args.field}")
                    return 0
            except CredentialError:
                pass
            passphrase = _passphrase()
            vault.set(
                args.entry,
                args.field,
                _secret_value(args.stdin, args.field),
                "text",
                passphrase,
            )
            print(f"Stored encrypted credential field: {args.entry}#{args.field}")
            return 0
        if args.operation == "put-entry":
            field_names = [*args.secret, *args.empty_json]
            if not field_names:
                parser.error("Provide at least one --secret or --empty-json field.")
            duplicates = sorted(
                field for field in set(field_names) if field_names.count(field) > 1
            )
            if duplicates:
                parser.error(
                    "Each field may be provided only once: " + ", ".join(duplicates)
                )
            passphrase = _passphrase()
            values = {
                field: (_secret_value(False, field), "text")
                for field in args.secret
            }
            values.update({field: ({}, "json") for field in args.empty_json})
            vault.set_fields(args.entry, values, passphrase)
            print(
                f"Stored encrypted credential entry: {args.entry} "
                f"({len(values)} fields)"
            )
            return 0
        if args.operation == "init-json":
            vault.set(args.entry, args.field, {}, "json", _passphrase())
            print(f"Initialised encrypted JSON field: {args.entry}#{args.field}")
            return 0
        if args.operation == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("A child command is required after --.")
            broker_values = _try_broker_fields(
                args.entry,
                [field for _, field in (_mapping(item) for item in args.map)],
            )
            passphrase = None if broker_values is not None else _passphrase()
            environment = _credential_environment(
                vault,
                args.entry,
                args.map,
                passphrase,
            )
            return subprocess.run(command, env=environment, check=False).returncode
        if args.operation == "session":
            print(
                "WARNING: vault_credentials.py session is deprecated. "
                "Prefer the unlocked Portable Vault tray app (RULE-2026-0012).",
                file=sys.stderr,
            )
            broker_values = _try_broker_fields(
                args.entry,
                [field for _, field in (_mapping(item) for item in args.map)],
            )
            passphrase = None if broker_values is not None else _passphrase()
            environment = _credential_environment(
                vault,
                args.entry,
                args.map,
                passphrase,
            )
            shell_command = (
                args.command[1:] if args.command[:1] == ["--"] else args.command
            )
            if not shell_command:
                if os.name == "nt":
                    shell_command = [
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-NoExit",
                    ]
                else:
                    shell_command = [os.getenv("SHELL", "/bin/sh")]
            if not shell_command:
                raise CredentialError("The session shell command is empty.")
            print(
                "Deprecated mapped-field shell open. Master passphrase is NOT exported. "
                "OAuth refresh requires the Vault Agent. Close this shell when finished."
            )
            return_code = subprocess.run(
                shell_command,
                env=environment,
                check=False,
            ).returncode
            print("Deprecated session shell closed.")
            return return_code
    except (CredentialError, ValueError, OSError) as exc:
        print(f"Credential operation failed: {exc}", file=sys.stderr)
        return 2
    parser.error("Unsupported operation.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
