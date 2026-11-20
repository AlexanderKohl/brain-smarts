"""Per-computer checkpoint (design section 9): the policy epoch and hash and each object's
revision and hash, kept outside the clone and signed by the computer's own signing key."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import canonical, signing
from .errors import SecretStoreError
from .keys import key_id

SCHEMA = 1
_HASH = re.compile(r"[0-9a-f]{64}")
_BODY = {"schema", "type", "repository", "policy_epoch", "policy_hash", "objects"}


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Checkpoint:
    repository: str
    policy_epoch: int
    policy_hash: str
    objects: dict = field(default_factory=dict)  # object id -> {"revision": int, "hash": str}

    def to_doc(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "type": "checkpoint", "repository": self.repository,
                "policy_epoch": self.policy_epoch, "policy_hash": self.policy_hash,
                "objects": {oid: {"revision": e["revision"], "hash": e["hash"]} for oid, e in self.objects.items()}}

    @staticmethod
    def from_doc(doc: Any) -> "Checkpoint":
        ok = (isinstance(doc, dict) and set(doc) == _BODY and doc["schema"] == SCHEMA and doc["type"] == "checkpoint"
              and isinstance(doc["repository"], str) and _int(doc["policy_epoch"])
              and isinstance(doc["policy_hash"], str) and _HASH.fullmatch(doc["policy_hash"])
              and isinstance(doc["objects"], dict))
        if ok:
            for oid, entry in doc["objects"].items():
                ok = ok and isinstance(entry, dict) and set(entry) == {"revision", "hash"} and _int(entry["revision"]) \
                    and isinstance(entry["hash"], str) and _HASH.fullmatch(entry["hash"]) is not None
        if not ok:
            raise SecretStoreError("checkpoint is malformed")
        return Checkpoint(doc["repository"], doc["policy_epoch"], doc["policy_hash"],
                          {oid: {"revision": e["revision"], "hash": e["hash"]} for oid, e in doc["objects"].items()})


def initial(policy: Any) -> Checkpoint:
    """The checkpoint of a freshly pinned trust root: its epoch and hash, no objects."""
    return Checkpoint(policy.repository, policy.epoch, policy.hash, {})


def advance(old: Checkpoint, new: Checkpoint) -> Checkpoint:
    """Return new if it only moves forward from old; refuse anything older or forked."""
    if new.repository != old.repository:
        raise SecretStoreError("checkpoint is for a different repository")
    if new.policy_epoch < old.policy_epoch or (new.policy_epoch == old.policy_epoch
                                               and new.policy_hash != old.policy_hash):
        raise SecretStoreError("checkpoint would move the policy backwards or fork it")
    for oid, entry in old.objects.items():
        later = new.objects.get(oid)
        if later is None or later["revision"] < entry["revision"] or (
                later["revision"] == entry["revision"] and later["hash"] != entry["hash"]):
            raise SecretStoreError(f"checkpoint would move object {oid} backwards or fork it")
    return new


def load(path: str | os.PathLike, public_key: Ed25519PublicKey) -> Checkpoint:
    """Load and verify a checkpoint signed by this computer; a bad signature is refused."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        raise SecretStoreError("checkpoint cannot be read") from None
    doc = canonical.loads(data)
    if not isinstance(doc, dict) or doc.get("writer") != key_id(public_key):
        raise SecretStoreError("checkpoint was not signed by this computer")
    try:
        signing.verify(doc, public_key)
    except SecretStoreError:
        raise SecretStoreError("checkpoint signature does not verify") from None
    return Checkpoint.from_doc({k: v for k, v in doc.items() if k not in ("writer", "signature")})


def save(path: str | os.PathLike, checkpoint: Checkpoint, signing_key: Ed25519PrivateKey,
         clone_root: str | os.PathLike | None = None) -> None:
    """Sign and write the checkpoint atomically; refuses a path inside the clone and any update
    that is not forward of the checkpoint already on disk."""
    target = Path(path).resolve()
    if clone_root is not None:
        root = Path(clone_root).resolve()
        if target == root or root in target.parents:
            raise SecretStoreError("the checkpoint must be kept outside the clone")
    if target.exists():
        advance(load(target, signing_key.public_key()), checkpoint)
    doc = checkpoint.to_doc()
    doc["writer"] = key_id(signing_key.public_key())
    data = canonical.dumps(signing.sign(doc, signing_key))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
