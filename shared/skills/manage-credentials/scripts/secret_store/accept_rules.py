"""Per-file rules of commit acceptance (design sections 7 and 9): commit paths, object shape and
chain, refresher releases, supersession records, and the content rules for oauth and index objects."""

from __future__ import annotations

import re
from typing import Any

from . import envelope, provider_profiles
from .errors import SecretStoreError
from .policy import HASH, INDEX_PREFIX, Policy, object_hash

TOKEN_FIELDS = frozenset({"access_token", "accessToken", "expires_at", "expiresAt", "expires_in", "id_token",
                          "token_type", "scope"})
OBJECT_FIELDS = frozenset({"schema", "suite", "repository", "policy_epoch", "group", "id", "kind", "revision",
                           "previous", "operation", "readers", "nonce", "ciphertext", "writer", "signature"})
RELEASE_FIELDS = frozenset({"schema", "type", "repository", "grant", "source_epoch", "new_refresher",
                            "revision_hash", "writer", "signature"})
SUPERSESSION_FIELDS = frozenset({"schema", "type", "repository", "grant", "provider", "person", "computer",
                                 "confirmation", "writer", "signature"})
_OBJECT_PATH = re.compile(r"objects/([A-Za-z0-9_-]{1,140})\.json")
_RECORD_PATH = re.compile(r"releases/([A-Za-z0-9_-]{1,140})\.json")
_REQUEST_PATH = re.compile(r"requests/[0-9a-f]{16}(\.answer|\.proof|\.handover|\.share)?\.json")
_MISSING = object()

# Plan section L (Sol round 10, low): a refused commit is named outside this module by one of these
# fixed codes and its fixed text only, never by a message that could carry text from the commit.
REFUSAL_CODES = {
    "commit-shape": "the commit has more than one parent or a subject outside the allowed set",
    "commit-attributes": "the commit changes .gitattributes",
    "commit-empty": "a commit must change at least one file",
    "commit-file": "a commit file is malformed",
    "commit-path": "the commit holds a path outside the store's layout",
    "object-id-path": "an object's id does not match its path",
    "object-shape": "an object has unexpected, missing or malformed fields",
    "object-repository": "an object belongs to another repository or policy epoch",
    "object-chain": "an object's revision or previous hash does not follow the checkpoint",
    "object-retired": "an object reuses a retired id",
    "object-tombstone": "a tombstone does not match the policy or is not an administrator's",
    "object-assignment": "an object's group or kind does not match the policy",
    "object-readers": "an object's readers are not the readers the policy gives it",
    "object-authority": "the writer has no authority for the object or its signature does not verify",
    "object-content": "an object's content could not be opened or breaks a content rule",
    "oauth-fields": "a sign-in object breaks the sign-in field rules",
    "index-content": "an index does not list exactly the policy's assignments",
    "record-shape": "a release or supersession record is malformed or has no policy change with it",
    "release": "a release record does not meet the handover rules",
    "supersession": "a supersession record does not meet the supersession rules",
    "refresher-move": "a grant whose refresher moves lacks exactly one release or supersession",
    "completeness": "a policy change lacks a file it obliges the same commit to carry",
    "policy-checkpoint": "the trusted policy does not match the checkpoint",
    "policy-transition": "the policy change is not an allowed transition",
    "checkpoint-chain": "the commit does not advance the checkpoint",
    "trust-root": "the first commit is not a trust root this computer can pin",
    "unclassified": "a rule outside the list of codes refused it",
}


class RuleRefusal(SecretStoreError):
    """A refusal of commit acceptance with its fixed code and, when the rule is about one object,
    the object id as the commit gave it (oid: never shown until the store has checked it is its own)."""

    def __init__(self, message: str, code: str, oid: str | None = None) -> None:
        super().__init__(message)
        self.code, self.oid = (code if code in REFUSAL_CODES else "unclassified"), oid


def coded(code: str, oid: str | None = None):
    """Context manager: a refusal raised without a code inside it gets this code (the message stays)."""
    import contextlib

    @contextlib.contextmanager
    def scope():
        try:
            yield
        except RuleRefusal:
            raise
        except SecretStoreError as error:
            raise RuleRefusal(str(error), code, oid) from None
    return scope()


def _refuse(message: str, code: str = "unclassified", oid: str | None = None) -> None:
    raise RuleRefusal(message, code, oid)


def split_files(files: Any) -> tuple[dict | None, dict[str, dict], dict[str, dict]]:
    """Split one commit into (policy document or None, objects by id, records by name)."""
    if not isinstance(files, dict) or not files:
        _refuse("a commit must change at least one file", "commit-empty")
    policy_doc, objects, records = None, {}, {}
    for path, value in files.items():
        if isinstance(path, str) and _REQUEST_PATH.fullmatch(path):
            # Enrolment exchange (section 8): public keys and challenges only, added or removed;
            # never part of the policy or the checkpoint. enrol.py verifies these files itself; a
            # .handover file carries a release to the administrator, and accept.py judges it when cited;
            # a .share file carries one member's login to another (share.py checks it when accepted).
            if value is not None and not isinstance(value, dict):
                _refuse("a commit file is malformed", "commit-file")
            continue
        if not isinstance(path, str) or not isinstance(value, dict):
            _refuse("a commit file is malformed", "commit-file")
        if path == "policy.json":
            policy_doc = value
            continue
        match = _OBJECT_PATH.fullmatch(path)
        if match:
            if value.get("id") != match.group(1):
                _refuse("an object's id does not match its path", "object-id-path")
            objects[match.group(1)] = value
            continue
        match = _RECORD_PATH.fullmatch(path)
        if match:
            records[match.group(1)] = value
            continue
        _refuse("unexpected path in commit", "commit-path")
    return policy_doc, objects, records


def check_object_shape(obj: dict[str, Any], oid: str) -> None:
    if set(obj) != OBJECT_FIELDS:
        _refuse(f"object {oid}: unexpected or missing fields", "object-shape", oid)
    try:
        envelope._check_header(obj)  # schema, suite, kind, id fields, revision, operation
    except SecretStoreError as error:
        raise RuleRefusal(f"object {oid}: {error}", "object-shape", oid) from None
    epoch = obj["policy_epoch"]
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        _refuse(f"object {oid}: policy_epoch malformed", "object-shape", oid)
    if obj["previous"] is not None and not (isinstance(obj["previous"], str) and HASH.fullmatch(obj["previous"])):
        _refuse(f"object {oid}: previous hash malformed", "object-shape", oid)
    if not isinstance(obj["writer"], str):
        _refuse(f"object {oid}: writer malformed", "object-shape", oid)
    readers = obj["readers"]
    if not isinstance(readers, list) or not all(
            isinstance(r, dict) and set(r) == {"key", "enc", "wrapped"} and isinstance(r["key"], str) for r in readers):
        _refuse(f"object {oid}: readers malformed", "object-shape", oid)


def check_readers(obj: dict[str, Any], oid: str, expected: list[str]) -> None:
    keys = [r["key"] for r in obj["readers"]]
    if len(keys) != len(set(keys)) or sorted(keys) != expected:
        _refuse(f"object {oid}: readers are not exactly the readers the policy gives it", "object-readers", oid)


def check_chain(obj: dict[str, Any], oid: str, entry: dict | None) -> None:
    """Revision exactly one higher than the checkpoint and previous equal to its hash."""
    if obj["revision"] != (1 if entry is None else entry["revision"] + 1):
        _refuse(f"object {oid}: revision is not one higher than the checkpoint", "object-chain", oid)
    if obj["previous"] != (None if entry is None else entry["hash"]):
        _refuse(f"object {oid}: previous hash does not match the checkpoint", "object-chain", oid)


def _record_shape(record: dict[str, Any], fields: frozenset, kind: str) -> None:
    if set(record) != fields or record.get("schema") != 1 or record.get("type") != kind:
        _refuse(f"{kind} record malformed", "record-shape")
    if not all(isinstance(record[name], str) for name in fields - {"schema", "source_epoch"}):
        _refuse(f"{kind} record malformed", "record-shape")


def check_release(record: dict[str, Any], prior: Policy, result: Policy, objects: dict[str, dict]) -> str:
    """Section 9, cooperative handover: signed by the grant's refresher in the source (prior)
    policy, naming the new refresher, bound to the grant revision in this commit by its hash and
    cited by the resulting policy. Returns the grant id."""
    _record_shape(record, RELEASE_FIELDS, "release")
    grant = record["grant"]
    if record["repository"] != prior.repository or record["source_epoch"] != prior.epoch:
        _refuse("release is not for this repository and source policy epoch", "release")
    old = prior.refresher_sign_id(grant)
    if old is None or record["writer"] != old:
        _refuse("release is not signed by the grant's refresher in the source policy", "release")
    with coded("release"):
        prior.verify(record, old)
    if record["new_refresher"] != result.refresher_sign_id(grant):
        _refuse("release names a different new refresher from the resulting policy", "release")
    obj = objects.get(grant)
    if obj is None or record["revision_hash"] != object_hash(obj):
        _refuse("release is not bound to the grant revision in this commit", "release")
    if object_hash(record) not in result.doc["cites"]:
        _refuse("the resulting policy does not cite the release", "release")
    return grant


def check_supersession(record: dict[str, Any], prior: Policy, result: Policy) -> str:
    """Section 9, old refresher unreachable: an administrator's record naming the old computer,
    which the resulting policy disables, and the grant whose refresher moves. Returns the grant id."""
    _record_shape(record, SUPERSESSION_FIELDS, "supersession")
    if record["repository"] != result.repository:
        _refuse("supersession record is for another repository", "supersession")
    if not result.is_admin_key(record["writer"]):
        _refuse("supersession record is not signed by an administrator", "supersession")
    with coded("supersession"):
        result.verify(record, record["writer"])
    grant, old = record["grant"], (record["person"], record["computer"])
    recorded = prior.provider(grant)
    if recorded is None or record["provider"] != recorded:
        _refuse("supersession record's provider is not the provider recorded for the sign-in", "supersession")
    refusal = provider_profiles.recovery_refusal(record["provider"])
    if refusal is not None:  # fail closed (design section 9): no supersession without a verified profile
        _refuse("supersession refused: " + refusal, "supersession")
    if not record["confirmation"].strip():
        _refuse("supersession record has no revocation confirmation", "supersession")
    if prior.refresher(grant) != old:
        _refuse("supersession record does not name the grant's previous refresher", "supersession")
    if record["computer"] not in result.doc["people"].get(record["person"], {}).get("disabled_refresher", []):
        _refuse("supersession record names a computer the policy does not disable", "supersession")
    if result.refresher(grant) in (None, old):
        _refuse("supersession record without a new refresher in the policy", "supersession")
    return grant


def protected_fields(payload: dict, previous: dict | None) -> frozenset:
    """Token fields only the refresher changes: the conservative default set, every grant-field
    spelling (which never belongs in an oauth object), every provider profile's token fields
    whatever the provider (recognised or not), and the provider name itself."""
    return frozenset(set(TOKEN_FIELDS) | provider_profiles.token_fields() | provider_profiles.grant_fields()
                     | {"provider"})


def check_oauth_payload(payload: dict, previous: dict | None, obj: dict, token_writer: bool, admin_writer: bool,
                        recorded_provider: str | None = None) -> bool:
    """Section 7 field rules. Raises when an oauth payload carries any grant-field spelling, whoever
    signs it (the refresher included); when any revision names another provider than the policy
    records for the oauth id; when a revision changes token fields without the
    refresher's operation id; or when there is no verified baseline and the writer is neither the
    refresher with an operation id (revision 1 included) nor an administrator. A sign-in whose policy assignment records no provider (created before providers
    were recorded) has no provider to compare."""
    exposed = sorted(set(payload) & provider_profiles.grant_fields())
    if exposed:
        _refuse(f"object {obj['id']}: an oauth object never carries a grant field ({', '.join(exposed)})",
                "oauth-fields", obj["id"])
    if recorded_provider is not None and payload.get("provider") != recorded_provider:
        _refuse(f"object {obj['id']}: the provider is not the provider the policy records for the sign-in",
                "oauth-fields", obj["id"])
    if token_writer:
        return True
    if previous is None:
        # No verified baseline on this computer: only the refresher's operation (a first
        # authorisation is revision 1 with an operation id, taken above) or an administrator's
        # re-key (a newly admitted reader's baseline) is taken as it is. Any other revision 1 is
        # refused: a member could otherwise set an access token in a rewritten fork.
        if admin_writer:
            return True
        _refuse(f"object {obj['id']}: no verified baseline here and the writer is neither an administrator "
                "nor the refresher's operation", "oauth-fields", obj["id"])
    for name in protected_fields(payload, previous):
        if payload.get(name, _MISSING) != previous.get(name, _MISSING):
            _refuse(f"object {obj['id']}: access-token fields changed without the refresher's operation",
                    "oauth-fields", obj["id"])
    return True


def check_index_payload(payload: dict, oid: str, result: Policy) -> None:
    entries = payload.get("entries")
    if not isinstance(entries, dict) or not all(isinstance(v, str) for v in entries.values()):
        _refuse(f"index {oid}: entries malformed", "index-content", oid)
    ids = list(entries.values())
    if len(ids) != len(set(ids)) or sorted(ids) != result.assigned_ids(oid[len(INDEX_PREFIX):]):
        _refuse(f"index {oid}: its ids are not exactly the policy's assignments for the group", "index-content", oid)
