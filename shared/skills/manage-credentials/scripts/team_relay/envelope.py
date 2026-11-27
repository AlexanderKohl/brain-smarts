"""Credential envelopes of the relay (design 6.1): the fields of one credential, as canonical JSON,
sealed with HPKE to the relay's public key, with the credential's name and revision as associated
data, so an envelope cannot be moved to another credential or revision. The same file is the
brain's team_relay/envelope.py (an administrator seals with it; VENDORED.json pins both copies)."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from secret_store import canonical, hpke
from secret_store.errors import SecretStoreError

INFO = b"brain-relay credential envelope v1"


def associated_data(name: str, revision: int) -> bytes:
    return canonical.dumps({"credential": name, "revision": revision})


def seal(public_key: X25519PublicKey, name: str, revision: int, fields: dict[str, str]) -> dict[str, str]:
    if not isinstance(fields, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items()):
        raise SecretStoreError("credential fields are text names and text values")
    enc, ciphertext = hpke.seal(public_key, INFO, associated_data(name, revision), canonical.dumps(fields))
    return {"enc": base64.b64encode(enc).decode("ascii"), "ct": base64.b64encode(ciphertext).decode("ascii")}


def open_(private_key: X25519PrivateKey, name: str, revision: int, envelope: Any) -> dict[str, str]:
    if not isinstance(envelope, dict) or set(envelope) != {"enc", "ct"}:
        raise SecretStoreError("a credential envelope is malformed")
    try:
        enc = base64.b64decode(envelope["enc"], validate=True)
        ciphertext = base64.b64decode(envelope["ct"], validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise SecretStoreError("a credential envelope is malformed") from None
    fields = canonical.loads(hpke.open_(enc, private_key, INFO, associated_data(name, revision), ciphertext))
    if not isinstance(fields, dict) or not all(isinstance(v, str) for v in fields.values()):
        raise SecretStoreError("a credential envelope holds malformed fields")
    return fields
