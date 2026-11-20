"""RFC 9180 HPKE, base mode, single-shot seal/open.

Suite: DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, AES-128-GCM (tests) or AES-256-GCM (production).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .errors import SecretStoreError

KEM_ID = 0x0020
KDF_ID = 0x0001
N_SECRET = 32
N_PK = 32
N_SK = 32
N_NONCE = 12
MODE_BASE = 0x00
_KEM_SUITE_ID = b"KEM" + KEM_ID.to_bytes(2, "big")
_VERSION_LABEL = b"HPKE-v1"


@dataclass(frozen=True)
class Aead:
    aead_id: int
    key_length: int


AES_128_GCM = Aead(0x0001, 16)
AES_256_GCM = Aead(0x0002, 32)


def _extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt or bytes(32), ikm, hashlib.sha256).digest()


def _expand(prk: bytes, info: bytes, length: int) -> bytes:
    if length > 255 * 32:
        raise SecretStoreError("HKDF expand length too large")
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _labeled_extract(suite_id: bytes, salt: bytes, label: bytes, ikm: bytes) -> bytes:
    return _extract(salt, _VERSION_LABEL + suite_id + label + ikm)


def _labeled_expand(suite_id: bytes, prk: bytes, label: bytes, info: bytes, length: int) -> bytes:
    labeled_info = length.to_bytes(2, "big") + _VERSION_LABEL + suite_id + label + info
    return _expand(prk, labeled_info, length)


def public_bytes(public_key: X25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _dh(private_key: X25519PrivateKey, public_key: X25519PublicKey) -> bytes:
    try:
        shared = private_key.exchange(public_key)
    except ValueError:
        raise SecretStoreError("refused low-order X25519 public key") from None
    if hmac.compare_digest(shared, bytes(len(shared))):
        raise SecretStoreError("refused low-order X25519 public key")
    return shared


def load_public_key(raw: bytes) -> X25519PublicKey:
    """Deserialize and validate an X25519 public key (32 bytes, not a low-order point)."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != N_PK:
        raise SecretStoreError("X25519 public key must be 32 bytes")
    try:
        key = X25519PublicKey.from_public_bytes(bytes(raw))
    except ValueError:
        raise SecretStoreError("invalid X25519 public key") from None
    # A low-order point gives an all-zero shared secret with every private key.
    _dh(X25519PrivateKey.generate(), key)
    return key


def derive_key_pair(ikm: bytes) -> X25519PrivateKey:
    """RFC 9180 DeriveKeyPair for DHKEM(X25519, HKDF-SHA256)."""
    if len(ikm) < N_SK:
        raise SecretStoreError("DeriveKeyPair input keying material too short")
    dkp_prk = _labeled_extract(_KEM_SUITE_ID, b"", b"dkp_prk", ikm)
    sk = _labeled_expand(_KEM_SUITE_ID, dkp_prk, b"sk", b"", N_SK)
    return X25519PrivateKey.from_private_bytes(sk)


def _extract_and_expand(dh: bytes, kem_context: bytes) -> bytes:
    eae_prk = _labeled_extract(_KEM_SUITE_ID, b"", b"eae_prk", dh)
    return _labeled_expand(_KEM_SUITE_ID, eae_prk, b"shared_secret", kem_context, N_SECRET)


def encap(pk_r: X25519PublicKey, sk_e: X25519PrivateKey | None = None) -> tuple[bytes, bytes]:
    """Return (shared_secret, enc). sk_e is fixed only by test vectors."""
    pk_rm = public_bytes(pk_r)
    load_public_key(pk_rm)
    sk_e = sk_e or X25519PrivateKey.generate()
    enc = public_bytes(sk_e.public_key())
    dh = _dh(sk_e, pk_r)
    return _extract_and_expand(dh, enc + pk_rm), enc


def decap(enc: bytes, sk_r: X25519PrivateKey) -> bytes:
    pk_e = load_public_key(enc)
    dh = _dh(sk_r, pk_e)
    return _extract_and_expand(dh, bytes(enc) + public_bytes(sk_r.public_key()))


def _suite_id(aead: Aead) -> bytes:
    return (b"HPKE" + KEM_ID.to_bytes(2, "big") + KDF_ID.to_bytes(2, "big")
            + aead.aead_id.to_bytes(2, "big"))


def key_schedule(shared_secret: bytes, info: bytes, aead: Aead) -> tuple[bytes, bytes]:
    """Base-mode KeySchedule; returns (key, base_nonce)."""
    suite_id = _suite_id(aead)
    psk_id_hash = _labeled_extract(suite_id, b"", b"psk_id_hash", b"")
    info_hash = _labeled_extract(suite_id, b"", b"info_hash", info)
    context = bytes([MODE_BASE]) + psk_id_hash + info_hash
    secret = _labeled_extract(suite_id, shared_secret, b"secret", b"")
    key = _labeled_expand(suite_id, secret, b"key", context, aead.key_length)
    base_nonce = _labeled_expand(suite_id, secret, b"base_nonce", context, N_NONCE)
    return key, base_nonce


def seal(pk_r: X25519PublicKey, info: bytes, aad: bytes, plaintext: bytes, aead: Aead = AES_256_GCM,
         _sk_e: X25519PrivateKey | None = None) -> tuple[bytes, bytes]:
    """Single-shot base-mode seal (sequence number 0). Returns (enc, ciphertext)."""
    shared_secret, enc = encap(pk_r, _sk_e)
    key, nonce = key_schedule(shared_secret, info, aead)
    return enc, AESGCM(key).encrypt(nonce, plaintext, aad)


def open_(enc: bytes, sk_r: X25519PrivateKey, info: bytes, aad: bytes, ciphertext: bytes,
          aead: Aead = AES_256_GCM) -> bytes:
    """Single-shot base-mode open (sequence number 0)."""
    shared_secret = decap(enc, sk_r)
    key, nonce = key_schedule(shared_secret, info, aead)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise SecretStoreError("HPKE open failed: authentication refused") from None
