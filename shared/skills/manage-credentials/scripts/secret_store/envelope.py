"""Seal and open store objects (design section 7), without signature or policy logic."""

from __future__ import annotations

import base64
import binascii
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import canonical, hpke
from .errors import SecretStoreError
from .keys import key_id

SCHEMA = 1
SUITE = "hpke-x25519-sha256-aes256gcm/ed25519"
KINDS = frozenset({"static", "oauth", "grant", "index", "tombstone"})
REQUIRED_HEADER = ("repository", "group", "id", "kind", "revision")
OPTIONAL_HEADER = ("operation", "policy_epoch", "previous", "writer")
AAD_FIELDS = ("schema", "suite", "repository", "group", "id", "kind", "revision", "operation")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: Any, field: str) -> bytes:
    if not isinstance(value, str):
        raise SecretStoreError(f"field {field} must be base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise SecretStoreError(f"field {field} is not valid base64") from None


def associated_data(obj: dict[str, Any]) -> bytes:
    return canonical.dumps({name: obj.get(name) for name in AAD_FIELDS})


def wrap_info(obj: dict[str, Any], reader_key_id: str) -> bytes:
    return canonical.dumps({"repository": obj["repository"], "id": obj["id"],
                            "revision": obj["revision"], "reader": reader_key_id})


def _check_header(obj: dict[str, Any]) -> None:
    if obj.get("schema") != SCHEMA or obj.get("suite") != SUITE:
        raise SecretStoreError("unknown schema or suite")
    if obj.get("kind") not in KINDS:
        raise SecretStoreError("unknown object kind")
    for name in ("repository", "group", "id"):
        if not isinstance(obj.get(name), str) or not obj[name]:
            raise SecretStoreError(f"field {name} must be non-empty text")
    revision = obj.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise SecretStoreError("revision must be a positive integer")
    if obj.get("operation") is not None and not isinstance(obj["operation"], str):
        raise SecretStoreError("operation must be text or null")


def seal(payload: dict[str, Any], readers: list[tuple[str, X25519PublicKey]],
         header: dict[str, Any]) -> dict[str, Any]:
    """Encrypt payload for readers. header: repository, group, id, kind, revision; optionally
    operation (default null), policy_epoch, previous and writer, which are copied through."""
    if not isinstance(payload, dict):
        raise SecretStoreError("payload must be an object")
    unknown = set(header) - set(REQUIRED_HEADER) - set(OPTIONAL_HEADER)
    if unknown:
        raise SecretStoreError("unknown header fields: " + ", ".join(sorted(unknown)))
    obj: dict[str, Any] = {"schema": SCHEMA, "suite": SUITE, "operation": None}
    for name in REQUIRED_HEADER:
        if name not in header:
            raise SecretStoreError(f"header field {name} is missing")
    obj.update(header)
    _check_header(obj)
    if not readers:
        raise SecretStoreError("an object needs at least one reader")
    seen: set[str] = set()
    for reader_id, public_key in readers:
        if reader_id in seen:
            raise SecretStoreError("duplicate reader key id")
        if key_id(public_key) != reader_id:
            raise SecretStoreError("reader key id does not match its public key")
        hpke.load_public_key(hpke.public_bytes(public_key))
        seen.add(reader_id)
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, canonical.dumps(payload), associated_data(obj))
    wrapped_readers = []
    for reader_id, public_key in readers:
        enc, wrapped = hpke.seal(public_key, wrap_info(obj, reader_id), b"", data_key, hpke.AES_256_GCM)
        wrapped_readers.append({"key": reader_id, "enc": _b64(enc), "wrapped": _b64(wrapped)})
    obj["readers"] = wrapped_readers
    obj["nonce"] = _b64(nonce)
    obj["ciphertext"] = _b64(ciphertext)
    return obj


def open_(obj: dict[str, Any], my_key_id: str, my_x25519_private: X25519PrivateKey) -> dict[str, Any]:
    """Decrypt obj as the reader my_key_id; refuse anything tampered with."""
    if not isinstance(obj, dict):
        raise SecretStoreError("object must be a JSON object")
    _check_header(obj)
    if key_id(my_x25519_private.public_key()) != my_key_id:
        raise SecretStoreError("my key id does not match my private key")
    readers = obj.get("readers")
    if not isinstance(readers, list) or not all(isinstance(r, dict) for r in readers):
        raise SecretStoreError("readers must be a list of objects")
    ids = [r.get("key") for r in readers]
    if len(ids) != len(set(ids)):
        raise SecretStoreError("duplicate reader key id")
    mine = [r for r in readers if r.get("key") == my_key_id]
    if not mine:
        raise SecretStoreError("this key is not a reader of the object")
    enc = _unb64(mine[0].get("enc"), "enc")
    wrapped = _unb64(mine[0].get("wrapped"), "wrapped")
    data_key = hpke.open_(enc, my_x25519_private, wrap_info(obj, my_key_id), b"", wrapped, hpke.AES_256_GCM)
    if len(data_key) != 32:
        raise SecretStoreError("unwrapped data key has the wrong length")
    nonce = _unb64(obj.get("nonce"), "nonce")
    if len(nonce) != 12:
        raise SecretStoreError("nonce must be 12 bytes")
    try:
        plaintext = AESGCM(data_key).decrypt(nonce, _unb64(obj.get("ciphertext"), "ciphertext"),
                                             associated_data(obj))
    except InvalidTag:
        raise SecretStoreError("object authentication refused") from None
    payload = canonical.loads(plaintext)
    if not isinstance(payload, dict):
        raise SecretStoreError("payload must be an object")
    return payload
