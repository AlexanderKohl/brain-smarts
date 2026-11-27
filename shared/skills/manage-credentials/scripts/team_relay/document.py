"""The relay document (design 8.2): `relay.json` in the private repository brain-team-relay, checked
out beside the team store's clone. An administrator signs every version with their store key; the
relay verifies the whole chain (brain-relay, relay/authority.py). On a member's computer the
newest version is checked against the team policy the store already verified: signed by an
administrator of that policy who is one of the document's administrators, for this team store."""

from __future__ import annotations

import base64
import binascii
import copy
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

import child_process
from secret_store import canonical, hpke, keys, signing
from secret_store.errors import SecretStoreError
from secret_store.policy import object_hash
from secret_store.store_ops import find_brain_root, project_repos_root

FILE = "relay.json"
FIELDS = frozenset({"schema", "type", "team_repository", "epoch", "previous", "policy_epoch", "relay",
                    "administrators", "computers", "credentials", "writer", "signature"})
RELAYED_MESSAGE = "this credential is used through the team credential relay; ask an administrator"


def clone_path(brain_root: Path | None = None) -> Path:
    root = brain_root or find_brain_root()
    if root is None:
        raise SecretStoreError("the brain root cannot be found")
    return project_repos_root(root) / "brain-team-relay"


def _git(clone: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = child_process.run(["git", "-C", str(clone), *args], capture_output=True)
    if check and result.returncode != 0:
        raise SecretStoreError(f"git {args[0]} in brain-team-relay failed")
    return result


def pull(clone: Path) -> None:
    if not (clone / ".git").is_dir():
        raise SecretStoreError(f"brain-team-relay is not checked out at {clone}")
    _git(clone, "pull", "--ff-only", "-q")


def read(clone: Path) -> dict | None:
    path = clone / FILE
    if not path.is_file():
        return None
    try:
        return canonical.loads(path.read_bytes())
    except SecretStoreError:
        raise SecretStoreError("relay.json is not valid JSON") from None


@dataclass
class RelayView:
    doc: dict
    url: str
    relay_public: X25519PublicKey

    @property
    def records(self) -> dict:
        return self.doc["credentials"]

    def relay_key_of(self, person: str, computer: str) -> str | None:
        return self.doc["computers"].get(person, {}).get(computer)


def verify(doc: Any, policy: Any) -> RelayView:
    """The newest relay document, checked against the team policy this computer verified."""
    if not isinstance(doc, dict) or set(doc) != FIELDS or doc["type"] != "relay" or doc["schema"] != 1:
        raise SecretStoreError("relay.json has unexpected or missing fields")
    if doc["team_repository"] != policy.repository:
        raise SecretStoreError("relay.json belongs to another team store")
    signer = policy.signers.get(doc["writer"]) if isinstance(doc["writer"], str) else None
    if signer is None or signer[0] not in policy.doc["administrators"] or signer[0] not in doc["administrators"]:
        raise SecretStoreError("relay.json is not signed by an administrator of the relay and the team policy")
    policy.verify(doc, doc["writer"])
    try:
        public = hpke.load_public_key(base64.b64decode(doc["relay"]["x25519"], validate=True))
    except (binascii.Error, ValueError, TypeError, KeyError, SecretStoreError):
        raise SecretStoreError("relay.json names a malformed relay key") from None
    return RelayView(doc, str(doc["relay"]["url"]).rstrip("/"), public)


def first(policy: Any, signer: Ed25519PrivateKey, url: str, relay_public: str, administrator: str) -> dict:
    """Epoch 1: the relay's address and public key, its first administrator, nothing granted."""
    doc = {"schema": 1, "type": "relay", "team_repository": policy.repository, "epoch": 1, "previous": None,
           "policy_epoch": policy.epoch, "relay": {"url": url.rstrip("/"), "x25519": relay_public},
           "administrators": [administrator], "computers": {}, "credentials": {}}
    doc["writer"] = keys.key_id(signer.public_key())
    return signing.sign(doc, signer)


def next_version(current: dict, policy: Any, signer: Ed25519PrivateKey, change: Callable[[dict], None]) -> dict:
    """The next version: change applied, epoch one higher, chained to current, signed."""
    doc = copy.deepcopy({k: v for k, v in current.items() if k != "signature"})
    change(doc)
    doc.update({"epoch": current["epoch"] + 1, "previous": object_hash(current), "policy_epoch": policy.epoch,
                "team_repository": policy.repository, "writer": keys.key_id(signer.public_key())})
    signed = signing.sign(doc, signer)
    verify(signed, policy)
    return signed


def write(clone: Path, doc: dict, message: str) -> str:
    """Commit and push one version; returns the commit."""
    (clone / FILE).write_bytes(canonical.dumps(doc))
    _git(clone, "add", FILE)
    _git(clone, "commit", "-q", "-m", message)
    _git(clone, "push", "-q", "origin", "HEAD")
    return _git(clone, "rev-parse", "HEAD").stdout.decode("ascii").strip()


def relayed(credential: str, brain_root: Path | None = None) -> bool:
    """Whether the relay document marks credential as relayed (10.1). Read without verification: the
    answer only ever refuses a local sign-in, so a forged mark can stop one and never start one."""
    try:
        doc = read(clone_path(brain_root))
    except SecretStoreError:
        return False
    record = (doc or {}).get("credentials", {}).get(credential) if isinstance(doc, dict) else None
    return isinstance(record, dict) and record.get("relayed") is True
