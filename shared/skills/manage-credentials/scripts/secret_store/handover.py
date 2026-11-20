"""Cooperative handover of a rotating sign-in's refresher (design synced-secrets-repository.md,
section 9, Handing over item 1).

release (on the old refresher): under the per-entry journal lock, set and persist the local
disabled flag, finish a pending publication (an uncertain record refuses: that needs item 2),
prepare the next grant revision encrypted to the new refresher and the recovery key, and sign a
release binding the repository, the grant id, the source policy epoch, the new refresher's key and
the prepared revision's hash. Both travel to the administrator in one request file,
requests/<first 16 characters of the grant id>.handover.json, which acceptance ignores like an
enrolment request.

accept (on an administrator's computer): one commit holding the policy change that names the new
refresher and cites the release, the release in releases/, the prepared grant revision, and the
request file's removal. accept.py checks the transition: the grant revision is signed by the source
policy's refresher and exactly bound by the cited release. Messages never carry values."""

from __future__ import annotations

import secrets
from typing import Any

from . import oauth_ops, signing
from .errors import SecretStoreError
from .journal import Journal, uncertain_message
from .keys import key_id
from .policy import object_hash
from .store_ops import build_policy_change, seal_object

REQUEST_FIELDS = frozenset({"schema", "type", "release", "revision"})


def request_path(grant_id: str) -> str:
    return f"requests/{grant_id[:16]}.handover.json"


def _find(store: Any, entry: str, group: str | None, field: str) -> oauth_ops.SignIn:
    store.open()  # the latest verified state: the release or the policy may have moved on
    signin = oauth_ops.find(store, entry, field, group)
    if signin is None:
        raise SecretStoreError(f"there is no sign-in {entry}#{field}")
    return signin


def _target(store: Any, to: str) -> tuple[str, str]:
    person, _sep, computer = str(to).partition("/")
    target = (person, computer)
    if not person or not computer or target not in store.policy.computers:
        raise SecretStoreError(f"{to} is not an enrolled computer; name it as PERSON/COMPUTER")
    if computer in store.policy.doc["people"][person]["disabled_refresher"]:
        raise SecretStoreError(f"{to} may not refresh sign-ins: the policy disables it")
    return target


def release(store: Any, entry: str, to: str, group: str | None = None, field: str = oauth_ops.DEFAULT_FIELD,
            journal: Journal | None = None) -> str:
    """The old refresher's half. Returns the request path the administrator's accept reads."""
    signin = _find(store, entry, group, field)
    if not signin.mine:
        oauth_ops.refuse_other(signin)
    target = _target(store, to)
    if target == signin.refresher:
        raise SecretStoreError(f"{to} already refreshes {entry}")
    journal = journal or Journal(store.config["checkpoint_dir"], store._identity().x25519)
    key, signer = signin.journal_key, store._identity().ed25519
    me = key_id(signer.public_key())
    with journal.lock(key):
        journal.set_disabled(key)  # persisted first: no refresh starts here from now on
        record = journal.read(key)
        if record is not None and record["state"] == "calling":
            raise SecretStoreError(uncertain_message(key, signin.provider))
        if record is not None and record["state"] == "answered":
            journal._finish(key, record, lambda op, answer: oauth_ops.publish(store, signin, answer, op),
                            lambda op, answer: oauth_ops.is_published(store, signin, op, answer))
        path = request_path(signin.grant_id)

        def build() -> tuple[dict, str]:
            policy, cp = store.policy, store.checkpoint
            if policy.refresher(signin.grant_id) != signin.refresher:
                raise SecretStoreError(f"the refresher of {entry} changed meanwhile; nothing was released")
            readers = sorted({policy.computers[target][0], policy.recovery[0]})
            revision = seal_object(policy, signin.grant_id, "grant", oauth_ops._open_grant(store, signin.grant_id), signer,
                                   cp.objects.get(signin.grant_id), epoch=policy.epoch + 1, readers=readers)
            body = {"schema": 1, "type": "release", "repository": policy.repository, "grant": signin.grant_id,
                    "source_epoch": policy.epoch, "new_refresher": policy.computers[target][1],
                    "revision_hash": object_hash(revision), "writer": me}
            req = {"schema": 1, "type": "handover", "release": signing.sign(body, signer), "revision": revision}
            return {path: req}, "update"
        store._write(build)
    return path


def _read_request(store: Any, path: str) -> dict | None:
    try:
        return store.repo.read(path)
    except (OSError, ValueError):
        return None


def accept(store: Any, entry: str, group: str | None = None, field: str = oauth_ops.DEFAULT_FIELD) -> tuple:
    """The administrator's half: one commit moving the refresher. Returns the new refresher."""
    signin = _find(store, entry, group, field)
    path, moved = request_path(signin.grant_id), {}
    signer = store._identity().ed25519

    def build() -> tuple[dict, str]:
        policy, cp = store.policy, store.checkpoint
        if not policy.is_admin_key(key_id(signer.public_key())):
            raise SecretStoreError("only an administrator may move a refresher")
        req = _read_request(store, path)
        if req is None:
            raise SecretStoreError(f"no release for {entry}: run handover-release on "
                                   f"{policy.refresher(signin.grant_id)[1]} first")
        if not isinstance(req, dict) or set(req) != REQUEST_FIELDS or req["type"] != "handover" \
                or not isinstance(req["release"], dict) or not isinstance(req["revision"], dict):
            raise SecretStoreError(f"the handover request for {entry} is malformed")
        rel = req["release"]
        if rel.get("grant") != signin.grant_id:
            raise SecretStoreError(f"the handover request for {entry} names another grant")
        if rel.get("source_epoch") != policy.epoch:
            raise SecretStoreError(f"the release of {entry} is for an older policy; run handover-release again")
        if rel.get("writer") != policy.refresher_sign_id(signin.grant_id):
            raise SecretStoreError(f"the release of {entry} is not signed by its refresher")
        policy.verify(rel, rel["writer"])
        who = policy.signers.get(rel.get("new_refresher"))
        if not isinstance(who, tuple) or who not in policy.computers:
            raise SecretStoreError(f"the release of {entry} names an unknown computer")
        moved["to"] = who

        def change(doc: dict) -> None:
            doc["refreshers"][signin.grant_id].update(person=who[0], computer=who[1])
            doc["cites"].append(object_hash(rel))
        others = {oid: e for oid, e in cp.objects.items() if oid != signin.grant_id}
        files = build_policy_change(policy, others, change, signer,
                                    lambda oid: store._open_object(store._tree_object(oid, cp)))
        files[f"releases/{secrets.token_hex(16)}.json"] = rel
        files[f"objects/{signin.grant_id}.json"] = req["revision"]
        files[path] = None
        return files, "policy"
    store._write(build)
    return moved["to"]
