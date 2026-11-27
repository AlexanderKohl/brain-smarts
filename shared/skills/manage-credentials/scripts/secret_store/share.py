"""A member shares one of their own logins with another member (design team-credential-relay.md,
8.6): no administrator is needed, because the login is the sharer's own.

The sharer's computer reads the entry from their personal store and seals its values and kinds to
every computer the other member has in the team policy, as a store object (envelope.seal) inside a
file `requests/<id>.share.json` of the team repository, signed by the sharer's computer key. Commit
acceptance ignores request files as it does enrolment and hand-over files, so the policy does not
change. The other member's `share-accept` checks the signature against the team policy, opens the
object with their own key, writes the entry into their own personal store and removes the file. The
team repository's history keeps who shared what with whom, and when (never a value).

A shared login cannot be recalled once it has been read (store rule 3): taking it back means
changing its password at the provider. An entry the relay holds is never shared: those are the
team's app credentials, which only an administrator gives a group the use of (8.5)."""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any, Iterable

from . import canonical, envelope, signing
from .errors import SecretStoreError
from .keys import key_id

FIELDS = frozenset({"schema", "type", "repository", "from", "from_computer", "to", "entry", "object", "writer",
                    "signature"})
_PATH = re.compile(r"requests/([0-9a-f]{16})\.share\.json")


def path_of(share_id: str) -> str:
    return f"requests/{share_id}.share.json"


def share(team: Any, personal: Any, entry: str, to: str, relayed: Iterable[str] = ()) -> str:
    """Seal entry of the caller's personal store to every computer of `to`; returns the file path."""
    if entry in set(relayed):
        raise SecretStoreError(f"{entry} is held by the team credential relay; only an administrator gives its use")
    team.open()
    personal.open()
    me = team._identity()
    if to == me.person:
        raise SecretStoreError("a login is shared with another member, not with oneself")
    computers = sorted(c for (person, c) in team.policy.computers if person == to)
    if not computers:
        raise SecretStoreError(f"{to} has no computer in the team store")
    if entry not in personal.list_entries():
        raise SecretStoreError(f"there is no entry {entry} in your personal store")
    values, kinds = personal.get_typed(entry)
    share_id = secrets.token_hex(8)
    signer = me.ed25519

    def build() -> tuple[dict, str]:
        policy = team.policy
        readers = [(policy.computers[(to, c)][0], policy.enc_keys[policy.computers[(to, c)][0]]) for c in computers]
        obj = envelope.seal({"entry": entry, "values": values, "kinds": kinds}, readers,
                            {"repository": policy.repository, "group": "share", "id": share_id, "kind": "static",
                             "revision": 1, "writer": key_id(signer.public_key())})
        doc = {"schema": 1, "type": "share", "repository": policy.repository, "from": me.person,
               "from_computer": me.computer, "to": to, "entry": entry, "object": obj,
               "writer": key_id(signer.public_key())}
        return {path_of(share_id): signing.sign(doc, signer)}, "update"
    team._write(build)
    return path_of(share_id)


def _check(doc: Any, policy: Any) -> dict:
    if not isinstance(doc, dict) or set(doc) != FIELDS or doc["type"] != "share" or doc["schema"] != 1:
        raise SecretStoreError("a share file is malformed")
    if doc["repository"] != policy.repository:
        raise SecretStoreError("a share file belongs to another team store")
    sender = (doc["from"], doc["from_computer"])
    if sender not in policy.computers or policy.computers[sender][1] != doc["writer"]:
        raise SecretStoreError("a share file is not signed by the sharer's computer in the team policy")
    policy.verify(doc, doc["writer"])
    return doc


def incoming(team: Any) -> list[tuple[str, dict]]:
    """Share files addressed to this computer's person, each checked; sorted by path."""
    team.open()
    me = team._identity()
    found = []
    folder = Path(team.clone) / "requests"
    for path in sorted(folder.glob("*.share.json")) if folder.is_dir() else []:
        rel = f"requests/{path.name}"
        if not _PATH.fullmatch(rel):
            continue
        doc = _check(canonical.loads(path.read_bytes()), team.policy)
        if doc["to"] == me.person:
            found.append((rel, doc))
    return found


def accept(team: Any, personal: Any, rel: str, name: str | None = None) -> str:
    """Write one share into the personal store under its entry name (or name), then remove the file."""
    from .typed_write import write_typed
    matches = [doc for path, doc in incoming(team) if path == rel]
    if not matches:
        raise SecretStoreError(f"there is no share {rel} for you")
    doc = matches[0]
    me = team._identity()
    reader = key_id(me.x25519.public_key())
    payload = envelope.open_(doc["object"], reader, me.x25519)
    if payload.get("entry") != doc["entry"] or not isinstance(payload.get("values"), dict):
        raise SecretStoreError("a share's content does not match its file")
    target = name or doc["entry"]
    personal.open()
    if target in personal.list_entries():
        raise SecretStoreError(f"your personal store already has {target}; accept it under another name with --as")
    write_typed(personal, target, payload["values"], payload.get("kinds"), {}, group=None)
    team._write(lambda: ({rel: None}, "update"))
    return target
