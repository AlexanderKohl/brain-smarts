#!/usr/bin/env python3
"""Command line of the synced secrets store, personal repository (design
synced-secrets-repository.md, sections 8 and 9).

  secrets.py init | status | list | recovery-package
  secrets.py put --entry E --secret FIELD [--secret FIELD ...] [--empty-json FIELD ...]
  secrets.py get-check --entry E
  secrets.py delete --entry E

Values are typed only into the masked window, never given on the command line. All output names
entries and fields only.

This file shares its name with the standard library module "secrets". When the scripts folder is
on sys.path and some module runs "import secrets", the block below hands that importer the
standard library module instead, so nothing else in this folder is affected."""

from __future__ import annotations

import sys as _sys

if __name__ == "secrets":
    import importlib.machinery as _machinery
    import importlib.util as _util
    import os as _os

    _here = _os.path.dirname(_os.path.abspath(__file__))
    _spec = _machinery.PathFinder.find_spec(
        "secrets", [p for p in _sys.path if _os.path.abspath(p or ".") != _here])
    _real = _util.module_from_spec(_spec)
    _sys.modules["secrets"] = _real
    _spec.loader.exec_module(_real)
    globals().update({k: v for k, v in vars(_real).items() if not k.startswith("__")})
else:
    import argparse
    from pathlib import Path

    _sys.path.insert(0, str(Path(__file__).resolve().parent))

    def _parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="secrets.py", description="Personal synced secrets store.")
        sub = parser.add_subparsers(dest="command", required=True)
        sub.add_parser("init", help="first computer: keys, recovery words, private repository")
        sub.add_parser("status", help="plain-words state of the store")
        sub.add_parser("list", help="entry names")
        sub.add_parser("recovery-package", help="write a fresh recovery package")
        put = sub.add_parser("put", help="store fields typed into the masked window")
        put.add_argument("--entry", required=True)
        put.add_argument("--secret", action="append", default=[], metavar="FIELD")
        put.add_argument("--empty-json", action="append", default=[], metavar="FIELD")
        check = sub.add_parser("get-check", help="names of the fields an entry holds")
        check.add_argument("--entry", required=True)
        delete = sub.add_parser("delete", help="delete an entry (type its name to confirm)")
        delete.add_argument("--entry", required=True)
        return parser

    def _ask_window(title: str, fields: list[str]):
        from secret_window import ask_secrets
        return ask_secrets(title, fields, False)

    def main(argv=None, store_factory=None, ask=None, confirm=None) -> int:
        from secret_store import SecretStoreError
        from secret_store.store import EMPTY_JSON, SecretStore
        try:
            from portable_vault import CredentialError
        except ImportError:  # pragma: no cover - the vault ships beside this script
            CredentialError = SecretStoreError
        args = _parser().parse_args(argv)
        store = (store_factory or SecretStore)()
        try:
            if args.command == "status":
                print(store.status())
            elif args.command == "init":
                pinned = store.init_personal()
                print("The personal secrets store is set up.")
                print("Trust root fingerprint (compare it on screen when another computer joins):")
                print(pinned)
            elif args.command == "list":
                names = store.open().list_entries()
                print("\n".join(names) if names else "No entries.")
            elif args.command == "recovery-package":
                print(f"Recovery package written: {store.open().refresh_recovery_package(force=True)}")
            elif args.command == "put":
                if not args.secret and not args.empty_json:
                    print("Name at least one --secret or --empty-json field.", file=_sys.stderr)
                    return 2
                fields: dict[str, str] = {}
                if args.secret:
                    answer = (ask or _ask_window)(f"Store {args.entry}", list(args.secret))
                    if answer is None:
                        print("Cancelled; nothing was stored.")
                        return 1
                    fields.update(answer[0])
                fields.update({name: EMPTY_JSON for name in args.empty_json})
                store.open().put_entry(args.entry, fields)
                print(f"Stored {args.entry}: " + ", ".join(sorted(fields)))
            elif args.command == "get-check":
                record = store.open().get_record(args.entry)
                print(f"{args.entry} has fields: " + ", ".join(sorted(record)))
            elif args.command == "delete":
                typed = (confirm or input)(f"Type the entry name {args.entry} to delete it: ")
                if typed.strip() != args.entry:
                    print("The name did not match; nothing was deleted.")
                    return 1
                store.open().delete_entry(args.entry)
                print(f"Deleted {args.entry}.")
            return 0
        except (SecretStoreError, CredentialError) as error:
            print(f"Secrets store: {error}", file=_sys.stderr)
            return 1

    if __name__ == "__main__":
        _sys.exit(main())
