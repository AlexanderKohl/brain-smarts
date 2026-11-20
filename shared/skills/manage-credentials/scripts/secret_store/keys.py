"""Computer key pairs: generation, key ids, and private-key storage in an allowlisted keychain."""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from . import canonical
from .errors import SecretStoreError

SERVICE = "brain-secrets"
STORED_FORMAT = 1
ALLOWED_BACKENDS = frozenset({
    "keyring.backends.Windows.WinVaultKeyring",
    "keyring.backends.macOS.Keyring",
    "keyring.backends.SecretService.Keyring",
})


def generate_key_pairs() -> tuple[X25519PrivateKey, Ed25519PrivateKey]:
    return X25519PrivateKey.generate(), Ed25519PrivateKey.generate()


def raw_public(public_key: X25519PublicKey | Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def raw_private(private_key: X25519PrivateKey | Ed25519PrivateKey) -> bytes:
    return private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def key_id(public_key: X25519PublicKey | Ed25519PublicKey) -> str:
    """First 16 bytes of SHA-256 of the raw public key, as hex."""
    return hashlib.sha256(raw_public(public_key)).digest()[:16].hex()


def username(person: str, computer: str) -> str:
    for label, value in (("person", person), ("computer", computer)):
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "@\r\n\t"):
            raise SecretStoreError(f"{label} name must be non-empty text without '@' or control characters")
    return f"{person.strip()}@{computer.strip()}"


def _backend():
    try:
        import keyring
    except ImportError:
        raise SecretStoreError("the keyring package is not installed") from None
    try:
        backend = keyring.get_keyring()
    except Exception as error:  # noqa: BLE001 - any keyring failure fails closed
        raise SecretStoreError(f"keychain unavailable ({type(error).__name__})") from None
    name = f"{type(backend).__module__}.{type(backend).__qualname__}"
    if name not in ALLOWED_BACKENDS:
        raise SecretStoreError(f"keychain backend {name} is not on the allowlist; refusing to use it")
    return backend


def store_private_keys(person: str, computer: str, x25519: X25519PrivateKey, ed25519: Ed25519PrivateKey,
                       *, replace: bool = False) -> None:
    """Store both private keys as one keychain item. Refuses to overwrite unless replace=True."""
    user = username(person, computer)
    backend = _backend()
    record = canonical.dumps({
        "format": STORED_FORMAT,
        "x25519": base64.b64encode(raw_private(x25519)).decode("ascii"),
        "ed25519": base64.b64encode(raw_private(ed25519)).decode("ascii"),
    }).decode("ascii")
    try:
        existing = backend.get_password(SERVICE, user)
    except Exception as error:  # noqa: BLE001
        raise SecretStoreError(f"keychain read failed ({type(error).__name__})") from None
    if existing is not None and not replace:
        raise SecretStoreError("keys for this person and computer already exist; refusing to overwrite")
    try:
        backend.set_password(SERVICE, user, record)
    except Exception as error:  # noqa: BLE001
        raise SecretStoreError(f"keychain write failed ({type(error).__name__})") from None


def load_private_keys(person: str, computer: str) -> tuple[X25519PrivateKey, Ed25519PrivateKey]:
    user = username(person, computer)
    backend = _backend()
    try:
        stored = backend.get_password(SERVICE, user)
    except Exception as error:  # noqa: BLE001
        raise SecretStoreError(f"keychain read failed ({type(error).__name__})") from None
    if stored is None:
        raise SecretStoreError("no keys stored for this person and computer")
    try:
        record = canonical.loads(stored)
        if record.get("format") != STORED_FORMAT:
            raise ValueError("format")
        x_raw = base64.b64decode(record["x25519"], validate=True)
        e_raw = base64.b64decode(record["ed25519"], validate=True)
        return X25519PrivateKey.from_private_bytes(x_raw), Ed25519PrivateKey.from_private_bytes(e_raw)
    except Exception:  # noqa: BLE001 - never echo the stored value
        raise SecretStoreError("stored keys are malformed") from None
