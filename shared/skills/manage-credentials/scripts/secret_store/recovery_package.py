"""Recovery packages (design: synced-secrets-repository.md, section 9).

A package holds the repository id, the latest checkpoint and a Git bundle of the full history,
encrypted with a fresh AES-256-GCM key that is wrapped to the recovery X25519 key with HPKE.

File layout: MAGIC, 2-byte length of enc, enc, 4-byte length of the wrapped key, wrapped key,
12-byte nonce, ciphertext. The plaintext is three length-prefixed parts: canonical JSON
metadata ({"repository": id, "version": 1}), the checkpoint bytes, the bundle bytes."""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import canonical, hpke
from .errors import SecretStoreError
from .repo import BRANCH, SecretRepo

MAGIC = b"BRAIN-SECRETS-RECOVERY-PACKAGE-1\n"
_INFO = b"brain secrets recovery package v1"
_NONCE = 12


def _parts(*chunks: bytes) -> bytes:
    return b"".join(struct.pack(">Q", len(c)) + c for c in chunks)


def _unparts(data: bytes, count: int) -> list[bytes]:
    out, offset = [], 0
    for _ in range(count):
        if offset + 8 > len(data):
            raise SecretStoreError("recovery package is truncated")
        (size,) = struct.unpack(">Q", data[offset:offset + 8])
        offset += 8
        if offset + size > len(data):
            raise SecretStoreError("recovery package is truncated")
        out.append(data[offset:offset + size])
        offset += size
    if offset != len(data):
        raise SecretStoreError("recovery package has trailing data")
    return out


def repository_id(repo: SecretRepo) -> str:
    """The repository identity from the committed policy.json."""
    result = subprocess.run(["git", "cat-file", "blob", "HEAD:policy.json"], cwd=str(repo.path),
                            capture_output=True)
    if result.returncode != 0:
        raise SecretStoreError("the repository has no committed policy.json")
    identity = canonical.loads(result.stdout).get("repository")
    if not isinstance(identity, str) or not identity:
        raise SecretStoreError("policy.json has no repository id")
    return identity


def _write_atomic(out_path: Path, data: bytes) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=out_path.name + ".", suffix=".tmp", dir=str(out_path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, out_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def build(repo: SecretRepo, checkpoint_bytes: bytes, recovery_public_key: X25519PublicKey,
          out_path: str | os.PathLike) -> Path:
    identity = repository_id(repo)
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "history.bundle"
        result = subprocess.run(["git", "bundle", "create", "--quiet", str(bundle_path), f"refs/heads/{BRANCH}"],
                                cwd=str(repo.path), capture_output=True)
        if result.returncode != 0:
            raise SecretStoreError("git bundle could not be created")
        bundle = bundle_path.read_bytes()
    meta = canonical.dumps({"repository": identity, "version": 1})
    plaintext = _parts(meta, bytes(checkpoint_bytes), bundle)
    data_key = AESGCM.generate_key(bit_length=256)
    enc, wrapped = hpke.seal(recovery_public_key, _INFO, MAGIC, data_key, hpke.AES_256_GCM)
    nonce = os.urandom(_NONCE)
    header = MAGIC + struct.pack(">H", len(enc)) + enc + struct.pack(">I", len(wrapped)) + wrapped + nonce
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, header)
    out = Path(out_path)
    _write_atomic(out, header + ciphertext)
    return out


def _open(package: bytes, recovery_private_key: X25519PrivateKey) -> tuple[str, bytes, bytes]:
    if not package.startswith(MAGIC):
        raise SecretStoreError("not a recovery package")
    try:
        offset = len(MAGIC)
        (enc_len,) = struct.unpack(">H", package[offset:offset + 2])
        enc = package[offset + 2:offset + 2 + enc_len]
        offset += 2 + enc_len
        (wrapped_len,) = struct.unpack(">I", package[offset:offset + 4])
        wrapped = package[offset + 4:offset + 4 + wrapped_len]
        offset += 4 + wrapped_len
        nonce = package[offset:offset + _NONCE]
        offset += _NONCE
    except struct.error:
        raise SecretStoreError("recovery package is truncated") from None
    header, ciphertext = package[:offset], package[offset:]
    data_key = hpke.open_(enc, recovery_private_key, _INFO, MAGIC, wrapped, hpke.AES_256_GCM)
    try:
        plaintext = AESGCM(data_key).decrypt(nonce, ciphertext, header)
    except InvalidTag:
        raise SecretStoreError("recovery package failed authentication") from None
    meta, checkpoint, bundle = _unparts(plaintext, 3)
    identity = canonical.loads(meta).get("repository")
    if not isinstance(identity, str):
        raise SecretStoreError("recovery package has no repository id")
    return identity, checkpoint, bundle


def restore(package_path: str | os.PathLike, recovery_private_key: X25519PrivateKey,
            target_dir: str | os.PathLike) -> bytes:
    """Decrypt the package, clone the repository from its bundle into target_dir and return the
    checkpoint. The clone's repository id must match the package's."""
    identity, checkpoint, bundle = _open(Path(package_path).read_bytes(), recovery_private_key)
    target = Path(target_dir)
    if target.exists() and any(target.iterdir()):
        raise SecretStoreError("restore target is not empty")
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "history.bundle"
        bundle_path.write_bytes(bundle)
        # git clone checks the bundle itself (git bundle verify needs an existing repository).
        clone = subprocess.run(["git", "clone", "--quiet", "-c", "core.autocrlf=false", "--branch", BRANCH,
                                str(bundle_path), str(target)], cwd=tmp, capture_output=True)
        if clone.returncode != 0:
            raise SecretStoreError("git clone of the recovery bundle failed")
    subprocess.run(["git", "remote", "remove", "origin"], cwd=str(target), capture_output=True)
    subprocess.run(["git", "config", "--local", "core.autocrlf", "false"], cwd=str(target), capture_output=True)
    restored = SecretRepo(target, "")
    if repository_id(restored) != identity:
        raise SecretStoreError("the restored repository id does not match the package")
    return checkpoint
