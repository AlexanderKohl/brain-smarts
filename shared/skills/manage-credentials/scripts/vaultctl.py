"""Operator CLI for the per-login Vault Agent and scoped credential use."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import warnings

from portable_vault import CredentialError
from vault_broker_client import (
    BrokerLocked,
    BrokerUnavailable,
    broker_request,
    broker_status,
    broker_unlocked,
)


ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _hidden_passphrase(prompt: str = "Vault recovery passphrase: ") -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", getpass.GetPassWarning)
        value = getpass.getpass(prompt)
        if any(issubclass(item.category, getpass.GetPassWarning) for item in caught):
            raise CredentialError(
                "Hidden passphrase entry is unavailable; refusing echoed input."
            )
    if not value:
        raise CredentialError("The vault passphrase is required.")
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


def _mapped_environment(entry: str, raw_mappings: list[str]) -> dict[str, str]:
    mappings = [_mapping(item) for item in raw_mappings]
    fields = [field for _, field in mappings]
    values = broker_request("get_fields", entry=entry, fields=fields)
    if not isinstance(values, dict):
        raise CredentialError("Broker returned malformed field values.")
    environment = os.environ.copy()
    # Never propagate a leftover master passphrase into children.
    environment.pop("PORTABLE_VAULT_PASSPHRASE", None)
    for environment_name, field in mappings:
        value = values.get(field)
        if not isinstance(value, str):
            raise CredentialError(f"Only text fields can be mapped: {field}")
        environment[environment_name] = value
    return environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)

    commands.add_parser("status", help="Show Vault Agent lock state")
    commands.add_parser("unlock", help="Unlock the running Vault Agent once")
    commands.add_parser("lock", help="Lock the running Vault Agent")

    access = commands.add_parser(
        "access-token",
        help="Return the stored OAuth access token for one entry (no refresh)",
    )
    access.add_argument("--entry", required=True)
    access.add_argument("--field", default="oauth_token_json")

    put = commands.add_parser("secret-put", help="Store one text secret through the agent")
    put.add_argument("--entry", required=True)
    put.add_argument("--field", required=True)

    run = commands.add_parser(
        "run",
        help="Inject mapped text fields from the unlocked agent and run a child command",
    )
    run.add_argument("--entry", required=True)
    run.add_argument("--map", action="append", required=True, metavar="ENV=FIELD")
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.operation == "status":
            status = broker_status()
            state = "unlocked" if status.get("unlocked") else "locked"
            print(f"Vault Agent {state} (pid {status.get('pid')})")
            print(f"Vault: {status.get('vault_path')}")
            return 0
        if args.operation == "unlock":
            if broker_unlocked():
                print("Vault Agent already unlocked.")
                return 0
            broker_request("unlock", passphrase=_hidden_passphrase())
            print("Vault Agent unlocked for this login session.")
            return 0
        if args.operation == "lock":
            broker_request("lock")
            print("Vault Agent locked.")
            return 0
        if args.operation == "access-token":
            result = broker_request(
                "get_access_token",
                entry=args.entry,
                field=args.field,
            )
            token = result.get("access_token") if isinstance(result, dict) else None
            if not isinstance(token, str):
                raise CredentialError("No access token returned.")
            # Print only the token value for piping; never print refresh material.
            print(token)
            return 0
        if args.operation == "secret-put":
            value = _hidden_passphrase(f"Value for {args.field}: ")
            broker_request(
                "set_text",
                entry=args.entry,
                field=args.field,
                value=value,
            )
            print(f"Stored encrypted credential field: {args.entry}#{args.field}")
            return 0
        if args.operation == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("A child command is required after --.")
            if not broker_unlocked():
                raise BrokerLocked(
                    "Vault Agent is locked. Run vaultctl unlock first."
                )
            environment = _mapped_environment(args.entry, args.map)
            return subprocess.run(command, env=environment, check=False).returncode
    except BrokerUnavailable as exc:
        print(f"Vault Agent unavailable: {exc}", file=sys.stderr)
        return 3
    except (BrokerLocked, CredentialError, ValueError, OSError) as exc:
        print(f"Credential operation failed: {exc}", file=sys.stderr)
        return 2
    parser.error("Unsupported operation.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
