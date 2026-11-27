"""The relay-* commands of brain_secrets.py (design 8.1, 8.5, 10.1 to 10.6). Values are typed only
into the masked window; output names credentials, fields, states, people and computers, never a
value. Every command that changes the relay or its document is an administrator's.

  relay-enrol [--out FILE]                     this computer: make its relay key, write the enrolment
  relay-admit (--enrolment FILE | --this-computer)   administrator: add a computer to relay.json
  relay-init --url URL --relay-key PUBLIC      administrator: the first relay.json
  relay-keygen --recovery-file FILE --railway-project ID --railway-environment ID --railway-service ID
                                               administrator: the relay's key pair (6.1, 6.3)
  relay-record --credential C (--file RECORD.json | --remove)   administrator: a credential's record
  relay-put --credential C --secret FIELD [...]   administrator: fields typed straight to the relay
  relay-connect --credential C                 administrator: the relay's own browser sign-in
  relay-revoke --credential C (--old-entry E [--old-field F] [--group G] | --no-old-secret)
  relay-serve --credential C                   administrator: serve, once the store copy is deleted
  relay-status | relay-log [--person L] [--credential C] [--since DATE]
  relay-disable | relay-enable (--credential C | --person L)
  relay-delete --credential C                  administrator: remove a credential from the relay"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable

from secret_store import canonical
from secret_store.errors import SecretStoreError

COMMANDS = ("relay-admit", "relay-connect", "relay-delete", "relay-disable", "relay-enable", "relay-enrol",
            "relay-init", "relay-keygen", "relay-log", "relay-put", "relay-record", "relay-revoke", "relay-serve",
            "relay-status")
CONNECT_WAIT = 300


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brain_secrets.py", description="The team credential relay.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("relay-enrol").add_argument("--out")
    admit = sub.add_parser("relay-admit").add_mutually_exclusive_group(required=True)
    admit.add_argument("--enrolment")
    admit.add_argument("--this-computer", action="store_true")
    init = sub.add_parser("relay-init")
    init.add_argument("--url", required=True)
    init.add_argument("--relay-key", required=True, help="the relay's public key, as relay-keygen printed it")
    keygen = sub.add_parser("relay-keygen")
    for name in ("--recovery-file", "--railway-project", "--railway-environment", "--railway-service"):
        keygen.add_argument(name, required=True)
    record = sub.add_parser("relay-record")
    record.add_argument("--credential", required=True)
    what = record.add_mutually_exclusive_group(required=True)
    what.add_argument("--file")
    what.add_argument("--remove", action="store_true")
    put = sub.add_parser("relay-put")
    put.add_argument("--credential", required=True)
    put.add_argument("--secret", action="append", required=True, metavar="FIELD")
    sub.add_parser("relay-connect").add_argument("--credential", required=True)
    sub.add_parser("relay-delete").add_argument("--credential", required=True)
    sub.add_parser("relay-serve").add_argument("--credential", required=True)
    revoke = sub.add_parser("relay-revoke")
    revoke.add_argument("--credential", required=True)
    old = revoke.add_mutually_exclusive_group(required=True)
    old.add_argument("--old-entry")
    old.add_argument("--no-old-secret", action="store_true")
    revoke.add_argument("--old-field", default="oauth_token_json")
    revoke.add_argument("--group")
    sub.add_parser("relay-status")
    log = sub.add_parser("relay-log")
    for name in ("--person", "--credential", "--since"):
        log.add_argument(name)
    for switch in (sub.add_parser("relay-disable").add_mutually_exclusive_group(required=True),
                   sub.add_parser("relay-enable").add_mutually_exclusive_group(required=True)):
        switch.add_argument("--credential")
        switch.add_argument("--person")
    return p


# ---------------------------------------------------------------- the relay document

def _team_and_document():
    from secret_store.team import TeamStore

    from . import document
    store = TeamStore().open()
    clone = document.clone_path()
    document.pull(clone)
    return store, clone, document.read(clone)


def _change_document(client_check: Callable[[dict], dict] | None, change: Callable[[dict], None],
                     message: str) -> str:
    """Sign, check at the relay where it can be reached, commit and push the next relay.json."""
    from . import document
    store, clone, current = _team_and_document()
    if current is None:
        raise SecretStoreError("brain-team-relay has no relay.json yet; run relay-init first")
    document.verify(current, store.policy)
    new = document.next_version(current, store.policy, store._identity().ed25519, change)
    if client_check is not None:
        answer = client_check(new)
        if not answer.get("ok"):
            raise SecretStoreError("the relay would refuse this relay.json: " + str(answer.get("error", "unknown")))
    return document.write(clone, new, message)


def _check_with(client: Any) -> Callable[[dict], dict]:
    return lambda doc: client.admin("check", {"document": doc})


def _admin_client():
    from .client import for_this_computer
    client, _context = for_this_computer(admin=True)
    return client


def relay_enrol(out: str | None) -> int:
    from secret_store.team import TeamStore

    from . import keys
    store = TeamStore().open()
    me = store._identity()
    try:
        relay_key = keys.load(me.person, me.computer)
    except SecretStoreError:
        relay_key = keys.create_relay_key(me.person, me.computer)
    doc = keys.enrolment(store.policy.repository, me.person, me.computer, relay_key, me.ed25519)
    path = Path(out or f"relay-enrolment-{me.person}-{me.computer}.json").resolve()
    path.write_bytes(canonical.dumps(doc))
    print(f"Relay key ready for {me.person}/{me.computer}. Enrolment written to {path}; it holds a public key "
          "only. Send it to an administrator, who runs: brain_secrets.py relay-admit --enrolment FILE")
    return 0


def relay_admit(enrolment: str | None, this_computer: bool) -> int:
    from secret_store.team import TeamStore

    from . import keys
    if this_computer:
        store = TeamStore().open()
        me = store._identity()
        try:
            relay_key = keys.load(me.person, me.computer)
        except SecretStoreError:
            relay_key = keys.create_relay_key(me.person, me.computer)
        doc = keys.enrolment(store.policy.repository, me.person, me.computer, relay_key, me.ed25519)
    else:
        doc = canonical.loads(Path(enrolment).read_bytes())
    person, computer, public = keys.verify_enrolment(doc, TeamStore().open().policy)

    def change(relay_doc: dict) -> None:
        relay_doc["computers"].setdefault(person, {})[computer] = public
    commit = _change_document(None, change, f"Admit {person}/{computer} to the relay")
    print(f"{person}/{computer} is in relay.json (commit {commit[:12]}); the relay serves it from its next pull.")
    return 0


def relay_init(url: str, relay_key: str) -> int:
    from . import document
    store, clone, current = _team_and_document()
    if current is not None:
        raise SecretStoreError("brain-team-relay already has a relay.json")
    me = store._identity()
    if me.person not in store.policy.doc["administrators"]:
        raise SecretStoreError("only an administrator of the team store starts the relay document")
    doc = document.first(store.policy, me.ed25519, url, relay_key, me.person)
    document.verify(doc, store.policy)
    commit = document.write(clone, doc, "The relay document: address, key and first administrator")
    print(f"relay.json written (commit {commit[:12]}). Next: relay-admit --this-computer, then relay-record.")
    return 0


def relay_record(credential: str, file: str | None, remove: bool) -> int:
    record = None if remove else json.loads(Path(file).read_text("utf-8"))

    def change(doc: dict) -> None:
        if remove:
            doc["credentials"].pop(credential, None)
        else:
            doc["credentials"][credential] = record
    client = _admin_client()
    commit = _change_document(_check_with(client), change,
                              f"{'Remove' if remove else 'Set'} the relay record of {credential}")
    print(f"The record of {credential} is {'removed' if remove else 'set'} in relay.json (commit {commit[:12]}).")
    return 0


# ---------------------------------------------------------------- credentials at the relay

def _row(client: Any, credential: str) -> dict | None:
    return next((c for c in client.admin("status")["credentials"] if c["name"] == credential), None)


def relay_put(credential: str, fields: list[str], ask: Callable | None) -> int:
    from . import envelope
    from .client import for_this_computer
    client, (_store, view, _clone) = for_this_computer(admin=True)
    if credential not in view.records:
        raise SecretStoreError(f"relay.json has no record for {credential}; run relay-record first")
    answer = (ask or _ask_window)(f"Relay {credential}", list(fields))
    if answer is None:
        print("Cancelled; nothing was sent.")
        return 1
    row = _row(client, credential)
    revision = (row["revision"] if row else 0) + 1
    sealed = envelope.seal(view.relay_public, credential, revision, dict(answer[0]))
    result = client.admin("put", {"credential": credential, "revision": revision, "envelope": sealed})
    print(f"Sent {', '.join(sorted(fields))} of {credential} to the relay. Test: {result['test']}; "
          f"state: {result['state']}.")
    return 0 if result["test"] != "failed" else 1


def _ask_window(title: str, fields: list[str]):
    from secret_window import ask_secrets
    return ask_secrets(title, fields, False)


def relay_connect(credential: str, opener: Callable[[str], Any] = webbrowser.open,
                  sleep: Callable[[float], None] = time.sleep) -> int:
    client = _admin_client()
    before = _row(client, credential)
    start = client.admin("connect", {"credential": credential})
    print("Opening the browser at the relay's sign-in. Sign in with the account the record names.")
    opener(start["start"])
    waited = 0
    while waited < CONNECT_WAIT:
        sleep(5)
        waited += 5
        row = _row(client, credential)
        if row and before and row["revision"] >= before["revision"] + 2 and row["state"] == before["state"]:
            print("The sign-in finished but the relay's test call failed, so it was dropped; nothing else changed.")
            return 1
        if row and before and row["revision"] != before["revision"] and row["state"] != "pending-test":
            print(f"Signed in at the relay; {credential} is now {row['state']}.")
            if row["state"] == "pending-revoke":
                print(f"Next: brain_secrets.py relay-revoke --credential {credential} --old-entry ENTRY "
                      "(or --no-old-secret when there is none)")
            return 0
    print("No finished sign-in was seen in five minutes; run relay-status, or relay-connect again.")
    return 1


def _old_signin(entry: str, field: str, group: str | None) -> dict:
    from secret_store import oauth_ops
    from secret_store.store import SecretStore
    from secret_store.team import TeamStore
    store = (TeamStore() if group else SecretStore()).open()
    signin = oauth_ops.find(store, entry, field, group)
    if signin is None:
        raise SecretStoreError(f"there is no sign-in {entry} {field}")
    return oauth_ops.read(store, signin)


def relay_revoke(credential: str, old_entry: str | None, old_field: str, group: str | None,
                 no_old_secret: bool, confirm: Callable[[str], str] | None = None) -> int:
    from . import revoke
    client = _admin_client()
    row = _row(client, credential)
    if row is None or row["state"] != "pending-revoke":
        raise SecretStoreError(f"{credential} is not waiting for its old secret to be revoked")
    if no_old_secret:
        client.admin("advance", {"credential": credential, "to": "pending-delete"})
        print(f"{credential} had no old secret; next: brain_secrets.py relay-serve --credential {credential}")
        return 0
    record = _old_signin(old_entry, old_field, group)
    refresh_token = revoke.find_token(record, "refresh_token")
    if not refresh_token:
        raise SecretStoreError(f"{old_entry} holds no refresh token to revoke")
    if (confirm or input)(f"Type {credential} to revoke the old sign-in {old_entry} at Google now: ").strip() != credential:
        print("Nothing was revoked.")
        return 1
    outcome = revoke.google_revoke(refresh_token)
    if outcome.state == "uncertain":
        expires = revoke.find_token(record, "expires_at")
        access = revoke.find_token(record, "access_token")
        fresh = access if expires is None or str(expires) > str(int(time.time()) + 60) else None
        outcome = revoke.google_probe(fresh, revoke.http_status)
    print(f"Revocation: {outcome.detail}.")
    if outcome.state != "dead":
        print("The relay stays in pending-revoke and does not serve. "
              + ("Run relay-revoke again." if outcome.state == "alive" else
                 "Check the Google account's third-party access page and remove the old app's access there, "
                 "then run relay-revoke again."))
        return 1
    client.admin("advance", {"credential": credential, "to": "pending-delete"})
    flag = f" --group {group}" if group else ""
    print(f"Next: brain_secrets.py delete --entry {old_entry} --field {old_field}{flag}, then "
          f"brain_secrets.py relay-serve --credential {credential}")
    return 0


def relay_serve(credential: str) -> int:
    client = _admin_client()
    row = _row(client, credential)
    if row is None or row["state"] != "pending-delete":
        raise SecretStoreError(f"{credential} is not ready to serve (it must be pending-delete)")
    client.admin("advance", {"credential": credential, "to": "serving"})
    print(f"The relay now serves {credential}. Connectors use it through the relay from now on.")
    return 0


def relay_status() -> int:
    client = _admin_client()
    status = client.admin("status")
    print(f"Policy epoch {status['policy_epoch']}, relay document epoch {status['relay_epoch']}.")
    for c in status["credentials"]:
        flags = [f for f, on in (("ended", c["ended"]), ("uncertain refresh", c["uncertain"])) if on]
        print(f"{c['name']}: {c['state']}, revision {c['revision']}, fields: {', '.join(c['fields']) or 'none'}"
              + (f" ({', '.join(flags)})" if flags else ""))
    waiting = sorted(set(status["records"]) - {c["name"] for c in status["credentials"]})
    if waiting:
        print("Records with no credential at the relay yet: " + ", ".join(waiting))
    for kind, name in status["switches"]:
        print(f"Switched off: {kind} {name}")
    return 0


def relay_log(person: str | None, credential: str | None, since: str | None) -> int:
    rows = _admin_client().admin("log", {k: v for k, v in (("person", person), ("credential", credential),
                                                            ("since", since)) if v is not None})["rows"]
    for r in rows:
        print(f"{r['at']}  {r['person'] or '-'}/{r['computer'] or '-'}  {r['credential'] or '-'}  "
              f"{r['method'] or '-'} {r['host'] or ''}{r['path'] or ''}  {r['status'] or ''} {r['code'] or ''}")
    if not rows:
        print("No use in that window.")
    return 0


def relay_switch(on: bool, credential: str | None, person: str | None) -> int:
    kind, name = ("credential", credential) if credential else ("person", person)
    _admin_client().admin("enable" if on else "disable", {"kind": kind, "name": name})
    print(f"{kind} {name} is switched {'on' if on else 'off'} at the relay.")
    return 0


def relay_delete(credential: str, confirm: Callable[[str], str] | None = None) -> int:
    if (confirm or input)(f"Type {credential} to remove it from the relay: ").strip() != credential:
        print("Nothing was removed.")
        return 1
    _admin_client().admin("delete", {"credential": credential})
    print(f"{credential} is removed from the relay.")
    return 0


def main(argv: list[str], ask: Callable | None = None, confirm: Callable | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "relay-enrol":
            return relay_enrol(args.out)
        if args.command == "relay-admit":
            return relay_admit(args.enrolment, args.this_computer)
        if args.command == "relay-init":
            return relay_init(args.url, args.relay_key)
        if args.command == "relay-keygen":
            from .keygen import relay_keygen
            return relay_keygen(args.recovery_file, args.railway_project, args.railway_environment,
                                args.railway_service)
        if args.command == "relay-record":
            return relay_record(args.credential, args.file, args.remove)
        if args.command == "relay-put":
            return relay_put(args.credential, args.secret, ask)
        if args.command == "relay-connect":
            return relay_connect(args.credential)
        if args.command == "relay-revoke":
            return relay_revoke(args.credential, args.old_entry, args.old_field, args.group, args.no_old_secret,
                                confirm)
        if args.command == "relay-serve":
            return relay_serve(args.credential)
        if args.command == "relay-status":
            return relay_status()
        if args.command == "relay-log":
            return relay_log(args.person, args.credential, args.since)
        if args.command in ("relay-disable", "relay-enable"):
            return relay_switch(args.command == "relay-enable", args.credential, args.person)
        if args.command == "relay-delete":
            return relay_delete(args.credential, confirm)
    except (SecretStoreError, OSError, ValueError) as error:
        print(f"Team credential relay: {error}", file=sys.stderr)
        return 1
    return 2

