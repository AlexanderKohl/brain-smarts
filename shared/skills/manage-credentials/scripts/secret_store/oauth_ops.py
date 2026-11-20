"""Rotating sign-ins in the secrets store (design synced-secrets-repository.md, sections 7 and 9).

A sign-in is two objects: an oauth object the group reads (access token, expiry, token type,
scope and shared settings) and a grant object only the refresher computer and the recovery key
read ({"token": refresh token and other grant fields, "fields": grant text fields such as the
client secret}). The computer that stores a sign-in becomes its refresher. Index names:
"<entry>#<field>" for the oauth object and "<entry>#<field>#grant" for the grant. The store's
own helpers (store.py) are used as they are; messages never carry values."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any

from . import envelope, provider_profiles, signing
from .errors import SecretStoreError
from .keys import key_id
from .policy import Policy
from .store_ops import GROUP, INDEX_ID, new_object_id, next_policy

GRANT_SUFFIX = "#grant"
SIGNIN_MARKERS = ("access_token", "refresh_token", "accessToken", "refreshToken")


class _Unchanged(Exception):
    pass


@dataclass(frozen=True)
class SignIn:
    entry: str
    field: str
    oauth_id: str
    grant_id: str
    refresher: tuple
    mine: bool
    provider: str | None

    @property
    def journal_key(self) -> str:
        return f"{self.entry}#{self.field}"


def signin_names(entry: str, field: str) -> tuple[str, str]:
    base = f"{entry}#{field}"
    return base, base + GRANT_SUFFIX


def looks_like_signin(value: Any) -> bool:
    return isinstance(value, dict) and any(k in value for k in SIGNIN_MARKERS)


def new_operation() -> str:
    return secrets.token_hex(16)


def plain_numbers(value: Any) -> Any:
    """Canonical JSON refuses floats: a float becomes the whole number below it (an expiry read
    up to one second early is harmless)."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SecretStoreError("a sign-in record holds a number that is not finite")
        return math.floor(value)
    if isinstance(value, dict):
        return {k: plain_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain_numbers(v) for v in value]
    return value


def split_record(record: dict, provider: str | None) -> tuple[dict, dict]:
    """(shared part for the oauth object, grant part) of a token record."""
    grant_keys = provider_profiles.grant_fields(provider)
    clean = plain_numbers(dict(record))
    return ({k: v for k, v in clean.items() if k not in grant_keys},
            {k: v for k, v in clean.items() if k in grant_keys})


def merge(shared: dict, grant: dict) -> dict:
    out = dict(shared)
    out.update(grant.get("token", {}))
    return out


def seal_revision(policy: Policy, oid: str, kind: str, payload: dict, signer: Any, entry: dict | None,
                  operation: str | None = None) -> dict:
    """store_ops.seal_object with an operation id (section 9, step 6)."""
    header = {"repository": policy.repository, "group": GROUP, "id": oid, "kind": kind,
              "revision": 1 if entry is None else entry["revision"] + 1,
              "previous": None if entry is None else entry["hash"], "policy_epoch": policy.epoch,
              "writer": key_id(signer.public_key()), "operation": operation}
    readers = [(rid, policy.enc_keys[rid]) for rid in policy.readers_for(oid)]
    return signing.sign(envelope.seal(payload, readers, header), signer)


def _path(oid: str) -> str:
    return f"objects/{oid}.json"


def _me(store: Any) -> tuple[str, str]:
    return store.config["person"], store.config["computer"]


def find(store: Any, entry: str, field: str) -> SignIn | None:
    index = store._index()
    oname, gname = signin_names(entry, field)
    if oname not in index:
        return None
    oauth_id, grant_id = index[oname], index.get(gname)
    who = store.policy.refresher(oauth_id)
    if grant_id is None or who is None:
        raise SecretStoreError(f"sign-in {entry}#{field} has no grant or refresher in the policy")
    return SignIn(entry, field, oauth_id, grant_id, who, who == _me(store), provider_profiles.provider_for(entry))


def signin_fields(store: Any, entry: str) -> list[str]:
    prefix = entry + "#"
    return sorted(n[len(prefix):] for n in store._index() if n.startswith(prefix) and "#" not in n[len(prefix):])


def refuse_other(signin: SignIn) -> None:
    raise SecretStoreError(f"this sign-in refreshes on {signin.refresher[1]}")


def _open(store: Any, oid: str) -> dict:
    return store._open_object(store._tree_object(oid, store.checkpoint))


def read_shared(store: Any, signin: SignIn) -> dict:
    return _open(store, signin.oauth_id)


def read_grant(store: Any, signin: SignIn) -> dict:
    if not signin.mine:
        refuse_other(signin)
    return _open(store, signin.grant_id)


def read(store: Any, signin: SignIn) -> dict:
    """The merged record on the refresher; the access token and shared settings elsewhere."""
    shared = read_shared(store, signin)
    return merge(shared, read_grant(store, signin)) if signin.mine else shared


def _revision_files(store: Any, signin: SignIn, shared: dict | None, grant: dict | None,
                    operation: str | None) -> dict:
    signer, cp = store._identity().ed25519, store.checkpoint.objects
    files = {}
    if shared is not None:
        files[_path(signin.oauth_id)] = seal_revision(store.policy, signin.oauth_id, "oauth", shared, signer,
                                                      cp.get(signin.oauth_id), operation)
    if grant is not None:
        files[_path(signin.grant_id)] = seal_revision(store.policy, signin.grant_id, "grant", grant, signer,
                                                      cp.get(signin.grant_id), operation)
    return files


def _new_signin_files(store: Any, entry: str, field: str, shared: dict, grant: dict) -> dict:
    policy, signer, index = store.policy, store._identity().ed25519, store._index()
    oname, gname = signin_names(entry, field)
    if gname in index:
        raise SecretStoreError(f"the store already holds a grant named {gname}")
    oauth_id = new_object_id(policy)
    grant_id = new_object_id(policy)
    while grant_id == oauth_id:
        grant_id = new_object_id(policy)
    person, computer = _me(store)

    def change(doc: dict) -> None:
        doc["assignments"][oauth_id] = {"group": GROUP, "kind": "oauth"}
        doc["assignments"][grant_id] = {"group": GROUP, "kind": "grant"}
        doc["refreshers"][grant_id] = {"person": person, "computer": computer, "oauth": oauth_id}

    doc = next_policy(policy, signer, change)
    result = Policy(doc)
    names = dict(index)
    names[oname], names[gname] = oauth_id, grant_id
    return {"policy.json": doc,
            _path(oauth_id): seal_revision(result, oauth_id, "oauth", shared, signer, None),
            _path(grant_id): seal_revision(result, grant_id, "grant", grant, signer, None),
            _path(INDEX_ID): seal_revision(result, INDEX_ID, "index", {"entries": names}, signer,
                                           store.checkpoint.objects.get(INDEX_ID))}


def put_signin(store: Any, entry: str, field: str, record: dict, grant_fields: dict | None = None,
               replace: bool = False) -> None:
    """Store a rotating sign-in with this computer as its refresher (one commit)."""
    provider = provider_profiles.provider_for(entry)
    shared, token = split_record(record, provider)
    grant = {"token": token, "fields": dict(grant_fields or {})}
    if not all(isinstance(v, str) and v for v in grant["fields"].values()):
        raise SecretStoreError("grant fields must be non-empty text")

    def build() -> tuple[dict, str]:
        signin = find(store, entry, field)
        if signin is None:
            return _new_signin_files(store, entry, field, shared, grant), "policy"
        if not replace:
            raise SecretStoreError(f"the store already holds {entry}#{field}; use replace to overwrite it")
        if not signin.mine:
            refuse_other(signin)
        return _revision_files(store, signin, shared, grant, new_operation()), "update"
    store._write(build)


def publish(store: Any, signin: SignIn, answer: dict, operation: str) -> None:
    """Section 9 step 6: one revision of the oauth and grant objects carrying the operation id.
    Fields the answer carries replace the latest record's; everything else is kept."""
    if not signin.mine:
        refuse_other(signin)
    new_shared, new_token = split_record(answer, signin.provider)

    def build() -> tuple[dict, str]:
        shared = read_shared(store, signin)
        shared.update(new_shared)
        grant = dict(_open(store, signin.grant_id))
        token = dict(grant.get("token", {}))
        token.update(new_token)
        grant["token"] = token
        return _revision_files(store, signin, shared, grant, operation), "update"
    store._write(build)


def is_published(store: Any, signin: SignIn, operation: str, answer: dict) -> bool:
    """Whether the store already shows this refresh: the latest oauth revision carries the
    operation id from this computer, or its access-token fields equal the answer's."""
    obj = store._tree_object(signin.oauth_id, store.checkpoint)
    if obj["operation"] == operation and obj["writer"] == key_id(store._identity().ed25519.public_key()):
        return True
    shared, _token = split_record(answer, signin.provider)
    keys = [k for k in provider_profiles.token_fields(signin.provider) if k in shared]
    latest = read_shared(store, signin)
    return bool(keys) and all(latest.get(k) == shared[k] for k in keys)


def save_settings(store: Any, signin: SignIn, value: dict) -> bool:
    """A settings save (section 7 field rules): applied to the latest record, token and grant
    fields preserved. Off the refresher a grant field is refused. Returns whether it wrote."""
    grant_keys = provider_profiles.grant_fields(signin.provider)
    if not signin.mine and set(value) & grant_keys:
        refuse_other(signin)
    protected = grant_keys | provider_profiles.token_fields(signin.provider)
    changes = {k: v for k, v in plain_numbers(value).items() if k not in protected}

    def build() -> tuple[dict, str]:
        current = read_shared(store, signin)
        new = dict(current)
        new.update(changes)
        if new == current:
            raise _Unchanged()
        return _revision_files(store, signin, new, None, None), "update"
    try:
        store._write(build)
    except _Unchanged:
        return False
    return True


def set_grant_fields(store: Any, signin: SignIn, fields: dict) -> None:
    """Grant text fields such as the client secret: the refresher only."""
    if not signin.mine:
        refuse_other(signin)

    def build() -> tuple[dict, str]:
        grant = dict(_open(store, signin.grant_id))
        grant["fields"] = {**grant.get("fields", {}), **fields}
        return _revision_files(store, signin, None, grant, None), "update"
    store._write(build)
