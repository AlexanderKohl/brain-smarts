"""The tombstone transaction of the synced secrets store (design synced-secrets-repository.md,
section 7): one administrator commit deleting an entry. A rotating sign-in is deleted whole: the
tombstones of its oauth and grant objects, both index names removed, its refresher mapping removed
and both ids retired, so the policy never holds half a sign-in."""

from __future__ import annotations

from typing import Any

from .errors import SecretStoreError
from .policy import INDEX_PREFIX, Policy, object_hash
from .store_ops import next_policy, seal_object


def _path(oid: str) -> str:
    return f"objects/{oid}.json"


def targets(policy: Policy, index: dict[str, str], name: str) -> set[str]:
    """Object ids deleting name removes: the entry the name maps to (a sign-in's oauth or grant
    name brings its pair), and every sign-in stored under name (index names name#field)."""
    ids: set[str] = set()

    def add(oid: str) -> None:
        grant = oid if oid in policy.doc["refreshers"] else policy.oauth_refresher.get(oid)
        ids.update({oid} if grant is None else {grant, policy.doc["refreshers"][grant]["oauth"]})

    if name in index:
        add(index[name])
    for key, oid in index.items():
        if key.startswith(name + "#") and policy.assignment(oid)[1] in ("oauth", "grant"):
            add(oid)
    if not ids:
        raise SecretStoreError(f"there is no entry {name}")
    return ids


def build_delete(policy: Policy, entries: dict, index: dict[str, str], name: str,
                 signer: Any) -> tuple[dict, str]:
    """(files, message): the empty final revision of every target signed by the administrator,
    the policy change retiring each id with that revision's hash (and dropping a deleted grant's
    refresher), and the index without the deleted names."""
    ids = targets(policy, index, name)
    groups = {policy.assignment(oid)[0] for oid in ids}
    if len(groups) != 1:
        raise SecretStoreError(f"entry {name} spans more than one group; nothing was deleted")
    index_id = INDEX_PREFIX + groups.pop()
    tombstones = {oid: seal_object(policy, oid, "tombstone", {}, signer, entries.get(oid),
                                   epoch=policy.epoch + 1, readers=policy.readers_for(oid)) for oid in sorted(ids)}

    def retire(doc: dict) -> None:
        for oid, tombstone in tombstones.items():
            del doc["assignments"][oid]
            doc["refreshers"].pop(oid, None)
            doc["retired"][oid] = object_hash(tombstone)

    new_doc = next_policy(policy, signer, retire)
    result = Policy(new_doc)
    names = {k: v for k, v in index.items() if v not in ids}
    files: dict = {"policy.json": new_doc}
    files.update({_path(oid): tombstone for oid, tombstone in tombstones.items()})
    files[_path(index_id)] = seal_object(result, index_id, "index", {"entries": names}, signer, entries.get(index_id))
    return files, "policy"
