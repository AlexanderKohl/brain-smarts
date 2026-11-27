"""Each computer's relay signing key (design 8.1): an Ed25519 key pair made beside the store's keys
and kept in the same allowlisted keychain, under a service of its own. The public key reaches the
relay document through a relay enrolment: a small file naming the person, the computer and the
public key, signed by that computer's store key, so an administrator can check it against the team
policy whatever way it travelled."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from secret_store import canonical, keys, signing
from secret_store.errors import SecretStoreError

SERVICE = "brain-relay"
STORED_FORMAT = 1
ENROLMENT_FIELDS = frozenset({"schema", "type", "repository", "person", "computer", "relay_key", "writer", "signature"})


def public_text(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return base64.b64encode(keys.raw_public(public)).decode("ascii")


def _read(person: str, computer: str) -> str | None:
    backend = keys._backend()
    try:
        return backend.get_password(SERVICE, keys.username(person, computer))
    except Exception as error:  # noqa: BLE001 - any keychain failure fails closed
        raise SecretStoreError(f"keychain read failed ({type(error).__name__})") from None


def create_relay_key(person: str, computer: str) -> Ed25519PrivateKey:
    """Make and store this computer's relay key; refused when one is already stored."""
    if _read(person, computer) is not None:
        raise SecretStoreError("this computer already has a relay key; it is never replaced silently")
    key = Ed25519PrivateKey.generate()
    record = canonical.dumps({"format": STORED_FORMAT,
                              "ed25519": base64.b64encode(keys.raw_private(key)).decode("ascii")}).decode("ascii")
    try:
        keys._backend().set_password(SERVICE, keys.username(person, computer), record)
    except Exception as error:  # noqa: BLE001
        raise SecretStoreError(f"keychain write failed ({type(error).__name__})") from None
    return key


def load(person: str, computer: str) -> Ed25519PrivateKey:
    stored = _read(person, computer)
    if stored is None:
        raise SecretStoreError("this computer has no relay key yet; run brain_secrets.py relay-enrol")
    try:
        record = canonical.loads(stored)
        if record.get("format") != STORED_FORMAT:
            raise ValueError("format")
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(record["ed25519"], validate=True))
    except Exception:  # noqa: BLE001 - never echo the stored value
        raise SecretStoreError("the stored relay key is malformed") from None


def enrolment(repository: str, person: str, computer: str, relay_key: Ed25519PrivateKey,
              store_signer: Ed25519PrivateKey) -> dict:
    """The signed enrolment an administrator admits with relay-admit."""
    body = {"schema": 1, "type": "relay-enrolment", "repository": repository, "person": person,
            "computer": computer, "relay_key": public_text(relay_key),
            "writer": keys.key_id(store_signer.public_key())}
    return signing.sign(body, store_signer)


def verify_enrolment(doc: Any, policy: Any) -> tuple[str, str, str]:
    """(person, computer, relay public key) of an enrolment signed by that computer's store key in
    the team policy."""
    if not isinstance(doc, dict) or set(doc) != ENROLMENT_FIELDS or doc["type"] != "relay-enrolment" \
            or doc["schema"] != 1:
        raise SecretStoreError("the relay enrolment is malformed")
    if doc["repository"] != policy.repository:
        raise SecretStoreError("the relay enrolment belongs to another team store")
    who = (doc["person"], doc["computer"])
    if who not in policy.computers or policy.computers[who][1] != doc["writer"]:
        raise SecretStoreError("the relay enrolment is not signed by that computer's key in the team policy")
    policy.verify(doc, doc["writer"])
    try:
        raw = base64.b64decode(doc["relay_key"], validate=True)
        Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError, TypeError):
        raise SecretStoreError("the relay enrolment's key is malformed") from None
    return doc["person"], doc["computer"], doc["relay_key"]
