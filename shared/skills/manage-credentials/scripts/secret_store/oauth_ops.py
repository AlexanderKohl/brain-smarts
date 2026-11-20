"""Rotating sign-ins in the secrets store (design synced-secrets-repository.md, sections 7 and 9).

A sign-in is two objects: an oauth object the group reads (access token, expiry, token type,
scope and shared settings) and a grant object only the refresher computer and the recovery key
read ({"token": refresh token and other grant fields, "fields": grant text fields such as the
client secret}). The computer that stores a sign-in becomes its refresher. Index names:
"<entry>#<field>" for the oauth object and "<entry>#<field>#grant" for the grant. Which fields are
grant fields never depends on the entry's name (provider_profiles.grant_fields); the provider is
recorded in the oauth object's shared settings under PROVIDER_KEY and decides the token fields.
Every revision carries the group of its policy assignment. The store's own helpers (store.py)
are used as they are; messages never carry values."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any

from . import envelope, provider_profiles, signing
from .errors import SecretStoreError
from .keys import key_id
from .policy import INDEX_PREFIX, Policy, object_hash
from .store_ops import GROUP, new_object_id, next_policy

GRANT_SUFFIX = "#grant"
DEFAULT_FIELD = "oauth_token_json"
PROVIDER_KEY = "provider"
SIGNIN_MARKERS = ("access_token", "refresh_token", "accessToken", "refreshToken", "user_token")


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
    group: str = GROUP
    repository: str = ""

    @property
    def journal_key(self) -> str:
        """Entry and field (for messages), then the repository id and the grant object id."""
        return f"{self.entry}#{self.field} @ {self.repository}/{self.grant_id}"


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
    """(shared part for the oauth object, grant part) of a token record. The recorded provider is
    never taken from a record handed in: only the sign-in's creation sets it."""
    grant_keys = provider_profiles.grant_fields(provider)
    clean = plain_numbers({k: v for k, v in dict(record).items() if k != PROVIDER_KEY})
    return ({k: v for k, v in clean.items() if k not in grant_keys},
            {k: v for k, v in clean.items() if k in grant_keys})


def merge(shared: dict, grant: dict) -> dict:
    out = dict(shared)
    out.update(grant.get("token", {}))
    return out


def seal_revision(policy: Policy, oid: str, kind: str, payload: dict, signer: Any, entry: dict | None,
                  operation: str | None = None) -> dict:
    """store_ops.seal_object with an operation id (section 9, step 6), in the object's own group."""
    group, _kind = policy.assignment(oid)
    header = {"repository": policy.repository, "group": group, "id": oid, "kind": kind,
              "revision": 1 if entry is None else entry["revision"] + 1,
              "previous": None if entry is None else entry["hash"], "policy_epoch": policy.epoch,
              "writer": key_id(signer.public_key()), "operation": operation}
    readers = [(rid, policy.enc_keys[rid]) for rid in policy.readers_for(oid)]
    return signing.sign(envelope.seal(payload, readers, header), signer)


def _path(oid: str) -> str:
    return f"objects/{oid}.json"


def _me(store: Any) -> tuple[str, str]:
    return store.config["person"], store.config["computer"]


def _open(store: Any, oid: str) -> dict:
    return store._open_object(store._tree_object(oid, store.checkpoint))


def _open_grant(store: Any, grant_id: str) -> dict:
    """The grant's payload. A grant this computer refreshes but cannot read was superseded (design
    section 9): it reads as empty until the new refresher writes its first revision."""
    obj = store._tree_object(grant_id, store.checkpoint)
    if (not any(r["key"] in store._identity().my_keys() for r in obj["readers"])
            and store.policy.refresher(grant_id) == _me(store)):
        return {}
    return store._open_object(obj)


def find(store: Any, entry: str, field: str, group: str | None = None) -> SignIn | None:
    index = store._index(group)
    oname, gname = signin_names(entry, field)
    if oname not in index:
        return None
    oauth_id, grant_id = index[oname], index.get(gname)
    who = store.policy.refresher(oauth_id)
    if grant_id is None or who is None:
        raise SecretStoreError(f"sign-in {entry}#{field} has no grant or refresher in the policy")
    provider = _open(store, oauth_id).get(PROVIDER_KEY) or provider_profiles.provider_for(entry)
    return SignIn(entry, field, oauth_id, grant_id, who, who == _me(store), provider, store._group(group),
                  store.policy.repository)


def signin_fields(store: Any, entry: str, group: str | None = None) -> list[str]:
    prefix = entry + "#"
    return sorted(n[len(prefix):] for n in store._index(group)
                  if n.startswith(prefix) and "#" not in n[len(prefix):])


def refuse_other(signin: SignIn) -> None:
    raise SecretStoreError(f"this sign-in refreshes on {signin.refresher[1]}")


def read_shared(store: Any, signin: SignIn) -> dict:
    return _open(store, signin.oauth_id)


def read_grant(store: Any, signin: SignIn) -> dict:
    if not signin.mine:
        refuse_other(signin)
    return _open_grant(store, signin.grant_id)


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


def _static_plan(store: Any, entry: str, group: str, names: set) -> tuple | None:
    """(object id, fields kept, grant fields moved) when the entry's static object holds one of
    names or any grant field, which leave it in the same commit; else None."""
    oid = store._index(group).get(entry)
    if oid is None or store.policy.assignment(oid)[1] != "static":
        return None
    record = store.get_record(entry, group)
    grant_keys = provider_profiles.grant_fields()
    drop = {k for k in record if k in names or k in grant_keys}
    if not drop:
        return None
    return (oid, {k: v for k, v in record.items() if k not in drop},
            {k: v for k, v in record.items() if k in grant_keys})


def _static_files(store: Any, policy: Policy, plan: tuple | None) -> dict:
    if plan is None:
        return {}
    oid, kept, _moved = plan
    return {_path(oid): seal_revision(policy, oid, "static", kept, store._identity().ed25519,
                                      store.checkpoint.objects.get(oid))}


def _new_signin_files(store: Any, entry: str, field: str, shared: dict, grant: dict,
                      group: str, provider: str | None = None) -> tuple[Policy, dict]:
    policy, signer, index = store.policy, store._identity().ed25519, store._index(group)
    oname, gname = signin_names(entry, field)
    if gname in index:
        raise SecretStoreError(f"the store already holds a grant named {gname}")
    oauth_id = new_object_id(policy)
    grant_id = new_object_id(policy)
    while grant_id == oauth_id:
        grant_id = new_object_id(policy)
    person, computer = _me(store)

    def change(doc: dict) -> None:
        # The provider is bound in the policy (immutable) so a supersession can be checked
        # against it.
        bound = {"provider": provider} if provider else {}
        doc["assignments"][oauth_id] = {"group": group, "kind": "oauth", **bound}
        doc["assignments"][grant_id] = {"group": group, "kind": "grant", **bound}
        doc["refreshers"][grant_id] = {"person": person, "computer": computer, "oauth": oauth_id}

    doc = next_policy(policy, signer, change)
    result = Policy(doc)
    names = dict(index)
    names[oname], names[gname] = oauth_id, grant_id
    index_id = INDEX_PREFIX + group
    return result, {"policy.json": doc,
                    _path(oauth_id): seal_revision(result, oauth_id, "oauth", shared, signer, None),
                    _path(grant_id): seal_revision(result, grant_id, "grant", grant, signer, None),
                    _path(index_id): seal_revision(result, index_id, "index", {"entries": names}, signer,
                                                   store.checkpoint.objects.get(index_id))}


def put_signin(store: Any, entry: str, field: str, record: dict, grant_fields: dict | None = None,
               replace: bool = False, group: str | None = None) -> None:
    """Store a rotating sign-in with this computer as its refresher (one commit). A static field
    of the same name (a placeholder) and every grant field of the entry's static object leave the
    static object in that commit; the grant fields move into the grant."""
    group = store._group(group)
    provider = provider_profiles.provider_for(entry)
    shared, token = split_record(record, provider)
    shared[PROVIDER_KEY] = provider
    extra = dict(grant_fields or {})
    if not all(isinstance(v, str) and v for v in extra.values()):
        raise SecretStoreError("grant fields must be non-empty text")

    def build() -> tuple[dict, str]:
        plan = _static_plan(store, entry, group, {field})
        moved = {**(plan[2] if plan else {}), **extra}
        signin = find(store, entry, field, group)
        if signin is None:
            grant = {"token": token, "fields": moved}
            result, files = _new_signin_files(store, entry, field, shared, grant, group, provider)
            return {**files, **_static_files(store, result, plan)}, "policy"
        if not replace:
            raise SecretStoreError(f"the store already holds {entry}#{field}; use replace to overwrite it")
        if not signin.mine:
            refuse_other(signin)
        kept = _open_grant(store, signin.grant_id).get("fields", {})  # replace keeps them; new ones merge in
        grant = {"token": token, "fields": {**kept, **moved}}
        files = _revision_files(store, signin, shared, grant, new_operation())
        return {**files, **_static_files(store, store.policy, plan)}, "update"
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
        grant = dict(_open_grant(store, signin.grant_id))
        token = dict(grant.get("token", {}))
        token.update(new_token)
        grant["token"] = token
        return _revision_files(store, signin, shared, grant, operation), "update"
    store._write(build)


def is_published(store: Any, signin: SignIn, operation: str, answer: dict) -> bool:
    """Whether the store already shows this refresh (section 9 step 6): the latest oauth and grant
    revisions both carry the operation id and this computer's writer key, and on both the hash of
    the journalled answer's fields equals the hash of the same fields as published."""
    me = key_id(store._identity().ed25519.public_key())
    for oid in (signin.oauth_id, signin.grant_id):
        obj = store._tree_object(oid, store.checkpoint)
        if obj.get("operation") != operation or obj.get("writer") != me:
            return False
    shared, token = split_record(answer, signin.provider)
    latest_shared = read_shared(store, signin)
    latest_token = read_grant(store, signin).get("token", {})
    return (object_hash(shared) == object_hash({k: latest_shared.get(k) for k in shared})
            and object_hash(token) == object_hash({k: latest_token.get(k) for k in token}))


def save_settings(store: Any, signin: SignIn, value: dict) -> bool:
    """A settings save (section 7 field rules): applied to the latest record, token and grant
    fields and the recorded provider preserved. Off the refresher a grant field is refused.
    Returns whether it wrote."""
    grant_keys = provider_profiles.grant_fields(signin.provider)
    if not signin.mine and set(value) & grant_keys:
        refuse_other(signin)
    protected = grant_keys | provider_profiles.token_fields(signin.provider) | {PROVIDER_KEY}
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
    """Grant text fields such as the client secret: the refresher only. The same fields and any
    grant field left in the entry's static object leave it in the same commit."""
    if not signin.mine:
        refuse_other(signin)

    def build() -> tuple[dict, str]:
        plan = _static_plan(store, signin.entry, signin.group, set(fields))
        grant = dict(_open_grant(store, signin.grant_id))
        grant["fields"] = {**grant.get("fields", {}), **(plan[2] if plan else {}), **fields}
        files = _revision_files(store, signin, None, grant, None)
        return {**files, **_static_files(store, store.policy, plan)}, "update"
    store._write(build)


def clear_tokens(store: Any, signin: SignIn, operation: str) -> None:
    """clear() on a stored sign-in: one revision of both objects without the access-token fields
    and the grant's token; shared settings and grant text fields stay. The refresher only."""
    if not signin.mine:
        raise SecretStoreError(f"this sign-in refreshes on {signin.refresher[1]}; clear it there")

    def build() -> tuple[dict, str]:
        dropped = provider_profiles.token_fields(signin.provider)
        shared = {k: v for k, v in read_shared(store, signin).items() if k not in dropped}
        grant = {**_open_grant(store, signin.grant_id), "token": {}}
        return _revision_files(store, signin, shared, grant, operation), "update"
    store._write(build)
