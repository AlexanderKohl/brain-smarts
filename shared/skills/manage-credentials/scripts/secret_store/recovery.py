"""24-word BIP-39 English recovery mnemonic and the recovery keys derived from its entropy."""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import SecretStoreError

WORDLIST_PATH = Path(__file__).with_name("bip39_english.txt")
WORDLIST_SHA256 = "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"
ENTROPY_BYTES = 32
WORD_COUNT = 24
X25519_INFO = b"brain-secrets recovery x25519 v1"
ED25519_INFO = b"brain-secrets recovery ed25519 v1"


@lru_cache(maxsize=1)
def wordlist() -> tuple[str, ...]:
    # Git on Windows may check the file out with CRLF line endings; the hash is of the LF form.
    data = WORDLIST_PATH.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(data).hexdigest() != WORDLIST_SHA256:
        raise SecretStoreError("BIP-39 word list does not match its expected SHA-256")
    words = tuple(data.decode("ascii").split())
    if len(words) != 2048:
        raise SecretStoreError("BIP-39 word list must have 2048 words")
    return words


def entropy_to_mnemonic(entropy: bytes) -> str:
    if len(entropy) != ENTROPY_BYTES:
        raise SecretStoreError("recovery entropy must be 32 bytes")
    checksum = hashlib.sha256(entropy).digest()[0]
    bits = (int.from_bytes(entropy, "big") << 8) | checksum
    words = wordlist()
    indexes = [(bits >> (11 * (WORD_COUNT - 1 - i))) & 0x7FF for i in range(WORD_COUNT)]
    return " ".join(words[i] for i in indexes)


def generate_mnemonic() -> str:
    return entropy_to_mnemonic(os.urandom(ENTROPY_BYTES))


def mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Validate a 24-word mnemonic and its checksum; return the 32-byte entropy."""
    parts = mnemonic.lower().split() if isinstance(mnemonic, str) else []
    if len(parts) != WORD_COUNT:
        raise SecretStoreError("a recovery phrase has exactly 24 words")
    index = {word: i for i, word in enumerate(wordlist())}
    bits = 0
    for position, word in enumerate(parts, start=1):
        if word not in index:
            raise SecretStoreError(f"word {position} of the recovery phrase is not in the BIP-39 list")
        bits = (bits << 11) | index[word]
    entropy = (bits >> 8).to_bytes(ENTROPY_BYTES, "big")
    if hashlib.sha256(entropy).digest()[0] != bits & 0xFF:
        raise SecretStoreError("recovery phrase checksum does not match")
    return entropy


def _hkdf(entropy: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(entropy)


def derive_recovery_keys(mnemonic: str) -> tuple[X25519PrivateKey, Ed25519PrivateKey]:
    """Validate the phrase, then derive the recovery X25519 and Ed25519 keys from its entropy."""
    entropy = mnemonic_to_entropy(mnemonic)
    return (X25519PrivateKey.from_private_bytes(_hkdf(entropy, X25519_INFO)),
            Ed25519PrivateKey.from_private_bytes(_hkdf(entropy, ED25519_INFO)))
