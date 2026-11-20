"""Per-file rules of commit acceptance (design sections 7 and 9): commit paths, object shape and
chain, refresher releases, supersession records, and the content rules for oauth and index objects."""

from __future__ import annotations

import re
from typing import Any

from . import envelope
from .errors import SecretStoreError
from .policy import HASH, INDEX_PREFIX, Policy, object_hash

TOKEN_FIELDS = ("access_token", "expires_at", "token_type", "scope")
OBJECT_FIELDS = frozenset({"schema", "suite", "repository", "policy_epoch", "group", "id", "kind", "revision",
                           "previous", "operation", "readers", "nonce", "ciphertext", "writer", "signature"})
RELEASE_FIELDS = frozenset({"schema", "type", "repository", "grant", "source_epoch", "new_refresher",
                            "revision_hash", "writer", "signature"})
SUPERSESSION_FIELDS = frozenset({"schema", "type", "repository", "grant", "person", "computer", "confirmation",
                                 "writer", "signature"})
_OBJECT_PATH = re.compile(r"objects/([A-Za-z0-9_-]{1,140})\.json")
_RECORD_PATH = re.compile(r"releases/([A-Za-z0-9_-]{1,140})\.json")
_MISSING = object()


def _refuse(message: str) -> None:
    raise SecretStoreError(message)


def split_files(files: Any) -> tuple[dict | None, dict[str, dict], dict[str, dict]]:
    """Split one commit into (policy document or None, objects by id, records by name)."""
    if not isinstance(files, dict) or not files:
        _refuse("a commit must change at least one file")
    policy_doc, objects, records = None, {}, {}
    for path, value in files.items():
        if not isinstance(path, str) or not isinstance(value, dict):
            _refuse("a commit file is malformed")
        if path == "policy.json":
            policy_doc = value
            continue
        match = _OBJECT_PATH.fullmatch(path)
        if match:
            if value.get("id") != match.group(1):
                _refuse(f"{path}: the object id does not match its path")
            objects[match.group(1)] = value
            continue
        match = _RECORD_PATH.fullmatch(path)
        if match:
            records[match.group(1)] = value
            continue
        _refuse(f"unexpected path in commit: {path}")
    return policy_doc, objects, records


def check_object_shape(obj: dict[str, Any], oid: str) -> None:
    if set(obj) != OBJECT_FIELDS:
        _refuse(f"object {oid}: unexpected or missing fields")
    try:
        envelope._check_header(obj)  # schema, suite, kind, id fields, revision, operation
    except SecretStoreError as error:
        raise SecretStoreError(f"object {oid}: {error}") from None
    epoch = obj["policy_epoch"]
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        _refuse(f"object {oid}: policy_epoch malformed")
    if obj["previous"] is not None and not (isinstance(obj["previous"], str) and HASH.fullmatch(obj["previous"])):
        _refuse(f"object {oid}: previous hash malformed")
    if not isinstance(obj["writer"], str):
        _refuse(f"object {oid}: writer malformed")
    readers = obj["readers"]
    if not isinstance(readers, list) or not all(
            isinstance(r, dict) and set(r) == {"key", "enc", "wrapped"} and isinstance(r["key"], str) for r in readers):
        _refuse(f"object {oid}: readers malformed")


def check_readers(obj: dict[str, Any], oid: str, expected: list[str]) -> None:
    keys = [r["key"] for r in obj["readers"]]
    if len(keys) != len(set(keys)) or sorted(keys) != expected:
        _refuse(f"object {oid}: readers are not exactly the readers the policy gives it")


def check_chain(obj: dict[str, Any], oid: str, entry: dict | None) -> None:
    """Revision exactly one higher than the checkpoint and previous equal to its hash."""
    if obj["revision"] != (1 if entry is None else entry["revision"] + 1):
        _refuse(f"object {oid}: revision is not one higher than the checkpoint")
    if obj["previous"] != (None if entry is None else entry["hash"]):
        _refuse(f"object {oid}: previous hash does not match the checkpoint")


def _record_shape(record: dict[str, Any], fields: frozenset, kind: str) -> None:
    if set(record) != fields or record.get("schema") != 1 or record.get("type") != kind:
        _refuse(f"{kind} record malformed")
    if not all(isinstance(record[name], str) for name in fields - {"schema", "source_epoch"}):
        _refuse(f"{kind} record malformed")


def check_release(record: dict[str, Any], prior: Policy, result: Policy, objects: dict[str, dict]) -> str:
    """Section 9, cooperative handover: signed by the grant's refresher in the source (prior)
    policy, naming the new refresher, bound to the grant revision in this commit by its hash and
    cited by the resulting policy. Returns the grant id."""
    _record_shape(record, RELEASE_FIELDS, "release")
    grant = record["grant"]
    if record["repository"] != prior.repository or record["source_epoch"] != prior.epoch:
        _refuse("release is not for this repository and source policy epoch")
    old = prior.refresher_sign_id(grant)
    if old is None or record["writer"] != old:
        _refuse("release is not signed by the grant's refresher in the source policy")
    prior.verify(record, old)
    if record["new_refresher"] != result.refresher_sign_id(grant):
        _refuse("release names a different new refresher from the resulting policy")
    obj = objects.get(grant)
    if obj is None or record["revision_hash"] != object_hash(obj):
        _refuse("release is not bound to the grant revision in this commit")
    if object_hash(record) not in result.doc["cites"]:
        _refuse("the resulting policy does not cite the release")
    return grant


def check_supersession(record: dict[str, Any], prior: Policy, result: Policy) -> str:
    """Section 9, old refresher unreachable: an administrator's record naming the old computer,
    which the resulting policy disables, and the grant whose refresher moves. Returns the grant id."""
    _record_shape(record, SUPERSESSION_FIELDS, "supersession")
    if record["repository"] != result.repository:
        _refuse("supersession record is for another repository")
    if not result.is_admin_key(record["writer"]):
        _refuse("supersession record is not signed by an administrator")
    result.verify(record, record["writer"])
    grant, old = record["grant"], (record["person"], record["computer"])
    if not record["confirmation"].strip():
        _refuse("supersession record has no revocation confirmation")
    if prior.refresher(grant) != old:
        _refuse("supersession record does not name the grant's previous refresher")
    if record["computer"] not in result.doc["people"].get(record["person"], {}).get("disabled_refresher", []):
        _refuse("supersession record names a computer the policy does not disable")
    if result.refresher(grant) in (None, old):
        _refuse("supersession record without a new refresher in the policy")
    return grant


def check_oauth_payload(payload: dict, previous: dict | None, obj: dict, token_writer: bool, admin_writer: bool) -> bool:
    """Section 7 field rules. Returns whether the object is usable; raises when a revision changes
    access-token fields without the refresher's operation id."""
    if token_writer:
        return True
    if previous is None:
        # No verified baseline on this computer: the first revision, or an administrator's
        # re-key (a newly admitted reader's baseline), is taken as it is; anything else waits.
        return obj["revision"] == 1 or admin_writer
    for name in TOKEN_FIELDS:
        if payload.get(name, _MISSING) != previous.get(name, _MISSING):
            _refuse(f"object {obj['id']}: access-token fields changed without the refresher's operation")
    return True


def check_index_payload(payload: dict, oid: str, result: Policy) -> None:
    entries = payload.get("entries")
    if not isinstance(entries, dict) or not all(isinstance(v, str) for v in entries.values()):
        _refuse(f"index {oid}: entries malformed")
    ids = list(entries.values())
    if len(ids) != len(set(ids)) or sorted(ids) != result.assigned_ids(oid[len(INDEX_PREFIX):]):
        _refuse(f"index {oid}: its ids are not exactly the policy's assignments for the group")
