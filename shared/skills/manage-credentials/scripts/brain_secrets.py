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
  brain_secrets.py handover-release --entry E --to PERSON/COMPUTER [--group G]   old refresher: release
  brain_secrets.py handover-accept --entry E [--group G]                         administrator: move it
  brain_secrets.py supersede --entry E --to PERSON/COMPUTER --confirmation TEXT [--group G]
                                                  administrator, old refresher unreachable
  brain_secrets.py grant-scan [--team]            plain entries holding a grant field (names only)

--group selects the team repository. Values are typed only into the masked window and the
enrolment and recovery words are shown only in a local window, never on the command line or in
the output. All output names entries, fields, groups, people and computers only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_GROUPED = ("list", "put", "get-check", "delete", "handover-release", "handover-accept", "supersede")


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
    release = sub.add_parser("handover-release", help="old refresher: release a sign-in to another computer")
    release.add_argument("--entry", required=True)
    release.add_argument("--to", required=True, metavar="PERSON/COMPUTER")
    release.add_argument("--group")
    take = sub.add_parser("handover-accept", help="administrator: move a released sign-in to its new refresher")
    take.add_argument("--entry", required=True)
    take.add_argument("--group")
    sup = sub.add_parser("supersede", help="administrator: move every sign-in of an unreachable refresher")
    which = sup.add_mutually_exclusive_group(required=True)
    which.add_argument("--entry", help="one sign-in of the lost computer")
    which.add_argument("--all-from", metavar="PERSON/COMPUTER", help="the lost computer")
    sup.add_argument("--to", required=True, metavar="PERSON/COMPUTER")
    sup.add_argument("--confirmation", required=True, help="how the old grant was revoked at the provider")
    sup.add_argument("--group")
    sub.add_parser("grant-scan", help="plain entries holding a grant field").add_argument("--team", action="store_true")
    return parser


def _entries(names: list[str]) -> dict[str, list[str]]:
    """Index names by entry name: a static entry as it is, a sign-in ("<entry>#<field>") under its
    entry with its field; the grant's own name is never shown."""
    from secret_store.oauth_ops import GRANT_SUFFIX
    entries: dict[str, list[str]] = {}
    for name in names:
        if name.endswith(GRANT_SUFFIX):
            continue
        entry, sep, field = name.partition("#")
        entries.setdefault(entry if sep else name, []).extend([field] if sep else [])
    return entries


def _describe(store, entry: str, group) -> list[str]:
    """Field names (never values) of an entry's static record and of each of its sign-ins: the
    shared settings, and the grant's fields on the refresher (elsewhere, where the grant is held)."""
    from secret_store import SecretStoreError, oauth_ops
    lines, fields = [], oauth_ops.signin_fields(store, entry, group)
    if entry in store._index(group) or not fields:
        lines.append(f"{entry} has fields: " + ", ".join(sorted(store.get_record(entry, group))))
    for field in fields:
        signin = oauth_ops.find(store, entry, field, group)
        if signin is None:
            raise SecretStoreError(f"there is no sign-in {entry} {field}")
        shared = ", ".join(sorted(oauth_ops.read_shared(store, signin))) or "none"
        if signin.mine:
            grant = oauth_ops.read_grant(store, signin)
            names = sorted(set(grant.get("token") or {}) | set(grant.get("fields") or {}))
            held = "grant fields: " + (", ".join(names) or "none")
        else:
            held = f"its grant is held on {signin.refresher[0]}/{signin.refresher[1]}"
        lines.append(f"{entry} sign-in {field}: shared fields: {shared}; {held}")
    return lines


def _ask_window(title: str, fields: list[str]):
    from secret_window import ask_secrets
    return ask_secrets(title, fields, False)


def main(argv=None, store_factory=None, team_factory=None, ask=None, confirm=None, display=None) -> int:
    from secret_store import SecretStoreError, enrol, handover
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
            entries = _entries(store.open().list_entries(group))
            print("\n".join(name + (f" (sign-in: {', '.join(fields)})" if fields else "")
                            for name, fields in sorted(entries.items())) if entries else "No entries.")
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
            from secret_store import provider_profiles
            from secret_store.broker_backend import put_grant_fields
            opened = store.open()
            grant = {k: v for k, v in fields.items() if k in provider_profiles.grant_fields()}
            plain = {k: v for k, v in fields.items() if k not in grant}
            if plain and grant:  # one commit: static object, grant, index and policy together
                from secret_store.oauth_ops import put_fields
                put_fields(opened, args.entry, plain, grant, group)
            elif plain:
                opened.put_entry(args.entry, plain, group=group)
            else:  # the same path as the agent's set_text: never into a static object
                put_grant_fields(opened, opened._group(group), args.entry, grant)
            print(f"Stored {args.entry}: " + ", ".join(sorted(fields)))
        elif args.command == "get-check":
            print("\n".join(_describe(store.open(), args.entry, group)))
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
        elif args.command == "handover-release":
            handover.release(store.open(), args.entry, args.to, group)
            print(f"Released {args.entry} to {args.to}; this computer no longer refreshes it. On an administrator's "
                  f"computer run: brain_secrets.py handover-accept --entry {args.entry}" + (f" --group {group}" if group else ""))
        elif args.command == "handover-accept":
            person, computer = handover.accept(store.open(), args.entry, group)
            print(f"{args.entry} now refreshes on {person}/{computer}.")
        elif args.command == "supersede":
            person, computer = handover.supersede(store.open(), args.entry, args.to, args.confirmation, group,
                                                  all_from=args.all_from)
            print(f"Every sign-in of the old computer now refreshes on {person}/{computer}; the old computer may "
                  "no longer refresh.")
        elif args.command == "grant-scan":
            found = store.open().static_grant_exposures()
            print("No plain entry holds a grant field." if not found else
                  "These plain entries hold grant fields every group member could read; move them to the "
                  "sign-in's grant and change them at the provider:\n" + "\n".join(found))
        warning = getattr(store, "package_error", None)
        if warning:  # the operation succeeded; only the recovery package needs attention
            print(f"Warning: {warning}. Run brain_secrets.py recovery-package once the folder is reachable.",
                  file=sys.stderr)
        return 0
    except (SecretStoreError, CredentialError) as error:
        print(f"Secrets store: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
