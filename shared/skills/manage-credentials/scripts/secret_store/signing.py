"""Ed25519 signatures over the canonical bytes of an object minus its 'signature' field."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import canonical
from .errors import SecretStoreError


def signing_bytes(obj: dict[str, Any]) -> bytes:
    if not isinstance(obj, dict):
        raise SecretStoreError("only objects can be signed")
    return canonical.dumps({key: value for key, value in obj.items() if key != "signature"})


def sign(obj: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    """Return a copy of obj carrying a base64 'signature' (any old one is replaced)."""
    signature = private_key.sign(signing_bytes(obj))
    signed = {key: value for key, value in obj.items() if key != "signature"}
    signed["signature"] = base64.b64encode(signature).decode("ascii")
    return signed


def verify(obj: dict[str, Any], public_key: Ed25519PublicKey) -> None:
    """Raise SecretStoreError unless obj carries a valid signature by public_key."""
    encoded = obj.get("signature") if isinstance(obj, dict) else None
    if not isinstance(encoded, str):
        raise SecretStoreError("object has no signature")
    try:
        signature = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise SecretStoreError("signature is not valid base64") from None
    try:
        public_key.verify(signature, signing_bytes(obj))
    except InvalidSignature:
        raise SecretStoreError("signature does not verify") from None
