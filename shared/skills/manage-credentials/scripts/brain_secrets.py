#!/usr/bin/env python3
"""Command line of the synced secrets store (design synced-secrets-repository.md, sections 8 and 9).

  brain_secrets.py init | status | list [--group G] | recovery-package
  brain_secrets.py put --entry E --secret FIELD [--secret FIELD ...] [--empty-json FIELD ...] [--group G]
  brain_secrets.py get-check --entry E [--group G]
  brain_secrets.py delete --entry E [--group G]
  brain_secrets.py enrol-request [--team] --fingerprint F     new computer: write the request
  brain_secrets.py enrol-request [--team] --request ID        new computer: answer the challenge, show words
  brain_secrets.py enrol-approve [--team] --request ID        approver: answer, later compare words and approve
  brain_secrets.py team-init --owner ORG_OR_LOGIN
  brain_secrets.py team-admit --login L --group G [--group G ...]
  brain_secrets.py team-groups --login L --group G [...]  |  team-groups --create G [--create G ...]
  brain_secrets.py team-remove --login L [--computer C]

--group selects the team repository. Values are typed only into the masked window and the
enrolment and recovery words are shown only in a local window, never on the command line or in
the output. All output names entries, fields, groups, people and computers only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_GROUPED = ("list", "put", "get-check", "delete")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain_secrets.py", description="Synced secrets store.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="first computer: keys, recovery words, private repository")
    sub.add_parser("status", help="plain-words state of the store")
    sub.add_parser("list", help="entry names").add_argument("--group")
    sub.add_parser("recovery-package", help="write a fresh recovery package")
    put = sub.add_parser("put", help="store fields typed into the masked window")
    put.add_argument("--entry", required=True)
    put.add_argument("--secret", action="append", default=[], metavar="FIELD")
    put.add_argument("--empty-json", action="append", default=[], metavar="FIELD")
    put.add_argument("--group")
    check = sub.add_parser("get-check", help="names of the fields an entry holds")
    check.add_argument("--entry", required=True)
    check.add_argument("--group")
    delete = sub.add_parser("delete", help="delete an entry (type its name to confirm)")
    delete.add_argument("--entry", required=True)
    delete.add_argument("--group")
    req = sub.add_parser("enrol-request", help="new computer: request enrolment, then answer the challenge")
    req.add_argument("--team", action="store_true")
    step = req.add_mutually_exclusive_group(required=True)
    step.add_argument("--fingerprint", help="the trust root fingerprint, compared on the other screen")
    step.add_argument("--request", help="the request id, once the approver has answered")
    approve = sub.add_parser("enrol-approve", help="approver: answer a request, then compare words and approve")
    approve.add_argument("--team", action="store_true")
    approve.add_argument("--request", required=True)
    sub.add_parser("team-init", help="create the team repository").add_argument("--owner", required=True)
    admit = sub.add_parser("team-admit", help="admit an enrolled person to their first groups")
    admit.add_argument("--login", required=True)
    admit.add_argument("--group", action="append", required=True)
    groups = sub.add_parser("team-groups", help="create groups, or set a person's groups")
    groups.add_argument("--login")
    groups.add_argument("--group", action="append", default=[])
    groups.add_argument("--create", action="append", default=[])
    remove = sub.add_parser("team-remove", help="remove a person or one of their computers")
    remove.add_argument("--login", required=True)
    remove.add_argument("--computer")
    return parser


def _ask_window(title: str, fields: list[str]):
    from secret_window import ask_secrets
    return ask_secrets(title, fields, False)


def main(argv=None, store_factory=None, team_factory=None, ask=None, confirm=None, display=None) -> int:
    from secret_store import SecretStoreError, enrol
    from secret_store import team as team_ops
    from secret_store.store import EMPTY_JSON, SecretStore
    try:
        from portable_vault import CredentialError
    except ImportError:  # pragma: no cover - the vault ships beside this script
        CredentialError = SecretStoreError
    args = _parser().parse_args(argv)
    group = getattr(args, "group", None) if args.command in _GROUPED else None
    use_team = bool(getattr(args, "team", False) or group or args.command.startswith("team-"))
    store = (team_factory or team_ops.TeamStore)() if use_team else (store_factory or SecretStore)()
    try:
        if args.command == "status":
            print(store.status())
        elif args.command == "init":
            print("The personal secrets store is set up.")
            print("Trust root fingerprint (compare it on screen when another computer joins):")
            print(store.init_personal())
        elif args.command == "list":
            names = store.open().list_entries(group)
            print("\n".join(names) if names else "No entries.")
        elif args.command == "recovery-package":
            print(f"Recovery package written: {store.open().refresh_recovery_package(force=True)}")
        elif args.command == "put":
            if not args.secret and not args.empty_json:
                print("Name at least one --secret or --empty-json field.", file=sys.stderr)
                return 2
            fields: dict[str, str] = {}
            if args.secret:
                answer = (ask or _ask_window)(f"Store {args.entry}", list(args.secret))
                if answer is None:
                    print("Cancelled; nothing was stored.")
                    return 1
                fields.update(answer[0])
            fields.update({name: EMPTY_JSON for name in args.empty_json})
            store.open().put_entry(args.entry, fields, group=group)
            print(f"Stored {args.entry}: " + ", ".join(sorted(fields)))
        elif args.command == "get-check":
            record = store.open().get_record(args.entry, group)
            print(f"{args.entry} has fields: " + ", ".join(sorted(record)))
        elif args.command == "delete":
            typed = (confirm or input)(f"Type the entry name {args.entry} to delete it: ")
            if typed.strip() != args.entry:
                print("The name did not match; nothing was deleted.")
                return 1
            store.open().delete_entry(args.entry, group)
            print(f"Deleted {args.entry}.")
        elif args.command == "enrol-request":
            flag = " --team" if args.team else ""
            if args.fingerprint:
                rid = enrol.request(store, args.fingerprint)
                print(f"Enrolment request {rid} written. On an approving computer run: "
                      f"brain_secrets.py enrol-approve{flag} --request {rid}")
            else:
                enrol.prove(store, args.request, display=display)
                print("Challenge answered. Compare the six words in the window with the approver's screen; "
                      f"the approver then runs enrol-approve{flag} --request {args.request} again.")
        elif args.command == "enrol-approve":
            if enrol.approve_step(store, args.request, display=display) == "answered":
                print(f"Request answered. On the new computer run: brain_secrets.py enrol-request "
                      f"{'--team ' if args.team else ''}--request {args.request}")
            else:
                print("The computer is enrolled.")
        elif args.command == "team-init":
            print("The team secrets store is set up.")
            print("Team trust root fingerprint (compare it on screen when a member joins):")
            print(store.init_team(args.owner))
        elif args.command == "team-admit":
            team_ops.admit(store.open(), args.login, args.group)
            print(f"Admitted {args.login} to " + ", ".join(args.group) + ".")
        elif args.command == "team-groups":
            if not args.create and not args.login:
                print("Name --create GROUP, or --login with --group.", file=sys.stderr)
                return 2
            store.open()
            if args.create:
                team_ops.create_groups(store, args.create)
                print("Created " + ", ".join(args.create) + ".")
            if args.login:
                team_ops.set_groups(store, args.login, args.group)
                print(f"{args.login} is now in: " + (", ".join(args.group) or "no group") + ".")
        elif args.command == "team-remove":
            names = team_ops.remove(store.open(), args.login, args.computer)
            print("Removed and re-keyed. Change these provider secrets: " + (", ".join(names) or "none") + ".")
        return 0
    except (SecretStoreError, CredentialError) as error:
        print(f"Secrets store: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
