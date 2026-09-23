"""Passphrase-encrypted, portable credential storage."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


VAULT_FORMAT = "portable-ai-brain-credential-vault"
VAULT_VERSION = 1
KDF_N = 2**17
KDF_R = 8
KDF_P = 1
KDF_LENGTH = 32
KDF_MAX_MEMORY = 256 * 1024 * 1024
MINIMUM_PASSPHRASE_LENGTH = 20
MAXIMUM_VAULT_BYTES = 16 * 1024 * 1024


class CredentialError(RuntimeError):
    """Raised when a credential operation cannot complete safely."""


def find_brain_root(start: Path | None = None) -> Path:
    """Walk upwards from this script (or ``start``) to the folder holding CONTRACT.md."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    # Fallback for a copy of the skill outside a brain: the historical fixed depth.
    return Path(__file__).resolve().parents[4]


def default_vault_path() -> Path:
    # Owner data lives in the memory checkout: /memory/projects/credential-management/.
    return find_brain_root() / "memory" / "projects" / "credential-management" / "data" / "credentials.vault"


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise CredentialError(f"Vault {label} is malformed.")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise CredentialError(f"Vault {label} is malformed.") from exc


def _validate_name(value: str, label: str) -> str:
    cleaned = value.strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-/ "
    if not cleaned or any(character not in allowed for character in cleaned):
        raise CredentialError(
            f"{label} may contain letters, digits, spaces, underscores, dots, slashes and hyphens only."
        )
    return cleaned


def _validate_passphrase(passphrase: str, *, creating: bool = False) -> bytes:
    if not passphrase:
        raise CredentialError("The vault passphrase is required.")
    if creating and len(passphrase) < MINIMUM_PASSPHRASE_LENGTH:
        raise CredentialError(
            f"Use a recovery passphrase of at least {MINIMUM_PASSPHRASE_LENGTH} characters."
        )
    return passphrase.encode("utf-8")


def _derive_key(passphrase: str, salt: bytes, kdf: dict[str, Any]) -> bytes:
    if (
        kdf.get("name") != "scrypt"
        or kdf.get("n") != KDF_N
        or kdf.get("r") != KDF_R
        or kdf.get("p") != KDF_P
        or kdf.get("length") != KDF_LENGTH
    ):
        raise CredentialError("The vault uses unsupported key-derivation settings.")
    try:
        return hashlib.scrypt(
            _validate_passphrase(passphrase),
            salt=salt,
            n=KDF_N,
            r=KDF_R,
            p=KDF_P,
            dklen=KDF_LENGTH,
            maxmem=KDF_MAX_MEMORY,
        )
    except (ValueError, MemoryError) as exc:
        raise CredentialError("The vault key could not be derived on this device.") from exc


def _acquire_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        _acquire_lock(handle)
        try:
            yield
        finally:
            _release_lock(handle)


class PortableVault:
    """An authenticated encrypted JSON vault stored in one portable file."""

    def __init__(self, path: Path | str | None = None):
        configured = path or os.getenv("PORTABLE_VAULT_PATH")
        self.path = Path(configured) if configured else default_vault_path()
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @staticmethod
    def empty_payload() -> dict[str, Any]:
        return {"schema_version": 1, "entries": {}}

    def initialize(self, passphrase: str) -> None:
        with _file_lock(self.lock_path):
            if self.path.exists():
                raise CredentialError(f"Vault already exists: {self.path}")
            self._write_unlocked(self.empty_payload(), passphrase, creating=True)

    def load(self, passphrase: str) -> dict[str, Any]:
        with _file_lock(self.lock_path):
            return self._load_unlocked(passphrase)

    def save(self, payload: dict[str, Any], passphrase: str) -> None:
        with _file_lock(self.lock_path):
            if not self.path.exists():
                raise CredentialError("The credential vault has not been initialised.")
            self._write_unlocked(payload, passphrase)

    def change_passphrase(self, old_passphrase: str, new_passphrase: str) -> None:
        with _file_lock(self.lock_path):
            payload = self._load_unlocked(old_passphrase)
            self._write_unlocked(payload, new_passphrase, creating=True)

    def get(self, entry: str, field: str, passphrase: str) -> Any:
        return self.get_fields(entry, [field], passphrase)[field]

    def get_fields(
        self,
        entry: str,
        fields: list[str],
        passphrase: str,
    ) -> dict[str, Any]:
        entry = _validate_name(entry, "Entry name")
        validated_fields = [_validate_name(field, "Field name") for field in fields]
        payload = self.load(passphrase)
        values: dict[str, Any] = {}
        for field in validated_fields:
            try:
                record = payload["entries"][entry]["fields"][field]
                kind = record["kind"]
                value = record["value"]
            except (KeyError, TypeError) as exc:
                raise CredentialError(f"Credential field does not exist: {entry}#{field}") from exc
            if kind not in {"text", "json"}:
                raise CredentialError(f"Credential field has an unsupported type: {entry}#{field}")
            values[field] = value
        return values

    def set(self, entry: str, field: str, value: Any, kind: str, passphrase: str) -> None:
        self.set_fields(entry, {field: (value, kind)}, passphrase)

    def set_fields(
        self,
        entry: str,
        values: dict[str, tuple[Any, str]],
        passphrase: str,
    ) -> None:
        entry = _validate_name(entry, "Entry name")
        if not values:
            raise CredentialError("At least one credential field is required.")
        validated: dict[str, tuple[Any, str]] = {}
        for raw_field, (value, kind) in values.items():
            field = _validate_name(raw_field, "Field name")
            if field in validated:
                raise CredentialError(f"Credential field was provided more than once: {field}")
            if kind not in {"text", "json"}:
                raise CredentialError("Credential values must be text or JSON.")
            if kind == "text" and (not isinstance(value, str) or not value):
                raise CredentialError("Text credential values must be non-empty strings.")
            if kind == "json" and not isinstance(value, dict):
                raise CredentialError("JSON credential values must be objects.")
            validated[field] = (value, kind)
        with _file_lock(self.lock_path):
            payload = self._load_unlocked(passphrase)
            entries = payload.setdefault("entries", {})
            fields = entries.setdefault(entry, {}).setdefault("fields", {})
            for field, (value, kind) in validated.items():
                fields[field] = {"kind": kind, "value": value}
            self._write_unlocked(payload, passphrase)

    def delete_entry(self, entry: str, passphrase: str) -> None:
        entry = _validate_name(entry, "Entry name")
        with _file_lock(self.lock_path):
            payload = self._load_unlocked(passphrase)
            entries = payload.get("entries")
            if not isinstance(entries, dict) or entry not in entries:
                raise CredentialError(f"Credential entry does not exist: {entry}")
            del entries[entry]
            self._write_unlocked(payload, passphrase)

    def _load_unlocked(self, passphrase: str) -> dict[str, Any]:
        if not self.path.exists():
            raise CredentialError(f"Credential vault does not exist: {self.path}")
        try:
            size = self.path.stat().st_size
        except OSError as exc:
            raise CredentialError("The credential vault cannot be read or is malformed.") from exc
        if size > MAXIMUM_VAULT_BYTES:
            raise CredentialError("The credential vault exceeds the maximum allowed size.")
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise CredentialError("The credential vault cannot be read or is malformed.") from exc
        if not isinstance(envelope, dict):
            raise CredentialError("The credential vault header is malformed.")
        kdf = envelope.get("kdf")
        cipher = envelope.get("cipher")
        if not isinstance(kdf, dict) or not isinstance(cipher, dict):
            raise CredentialError("The credential vault header is malformed.")
        try:
            header = {
                "format": envelope["format"],
                "version": envelope["version"],
                "kdf": kdf,
                "cipher": cipher,
            }
        except (KeyError, TypeError) as exc:
            raise CredentialError("The credential vault header is malformed.") from exc
        if envelope.get("format") != VAULT_FORMAT or envelope.get("version") != VAULT_VERSION:
            raise CredentialError("The credential vault format or version is unsupported.")
        if cipher.get("name") != "AES-256-GCM":
            raise CredentialError("The credential vault cipher is unsupported.")
        try:
            salt = _decode(kdf.get("salt"), "salt")
            nonce = _decode(cipher.get("nonce"), "nonce")
            ciphertext = _decode(envelope.get("ciphertext"), "ciphertext")
        except (CredentialError, AttributeError, TypeError, OverflowError) as exc:
            raise CredentialError("The credential vault cryptographic parameters are malformed.") from exc
        if len(salt) != 16 or len(nonce) != 12:
            raise CredentialError("The credential vault cryptographic parameters are malformed.")
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            key = _derive_key(passphrase, salt, kdf)
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise CredentialError(
                "The passphrase is incorrect or the credential vault was altered."
            ) from exc
        except (CredentialError, AttributeError, TypeError, OverflowError, ValueError) as exc:
            if isinstance(exc, CredentialError):
                raise
            raise CredentialError("The credential vault cryptographic parameters are malformed.") from exc
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialError("The decrypted credential vault is malformed.") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("entries"), dict)
        ):
            raise CredentialError("The decrypted credential vault schema is unsupported.")
        return payload

    def _write_unlocked(
        self,
        payload: dict[str, Any],
        passphrase: str,
        *,
        creating: bool = False,
    ) -> None:
        passphrase_bytes = _validate_passphrase(passphrase, creating=creating)
        salt = os.urandom(16)
        nonce = os.urandom(12)
        kdf = {
            "name": "scrypt",
            "n": KDF_N,
            "r": KDF_R,
            "p": KDF_P,
            "length": KDF_LENGTH,
            "salt": _encode(salt),
        }
        cipher = {"name": "AES-256-GCM", "nonce": _encode(nonce)}
        header = {
            "format": VAULT_FORMAT,
            "version": VAULT_VERSION,
            "kdf": kdf,
            "cipher": cipher,
        }
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = hashlib.scrypt(
            passphrase_bytes,
            salt=salt,
            n=KDF_N,
            r=KDF_R,
            p=KDF_P,
            dklen=KDF_LENGTH,
            maxmem=KDF_MAX_MEMORY,
        )
        plaintext = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        envelope = {**header, "ciphertext": _encode(AESGCM(key).encrypt(nonce, plaintext, aad))}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(envelope, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            _apply_windows_user_acl(self.path)
            _apply_windows_user_acl(self.path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _apply_windows_user_acl(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        from vault_agent_runtime import restrict_to_current_user

        restrict_to_current_user(path)
    except Exception:
        pass


class BrokerOAuthStore:
    """OAuth JSON field access through the unlocked Vault Agent (no passphrase in-process)."""

    def __init__(
        self,
        entry: str,
        field: str = "oauth_token_json",
        *,
        path: Path | str | None = None,
    ):
        from vault_broker_client import broker_request, broker_unlocked

        self.entry = _validate_name(entry, "Entry name")
        self.field = _validate_name(field, "Field name")
        self.vault = PortableVault(path)
        if not broker_unlocked():
            raise CredentialError(
                "Vault Agent is locked or unavailable. "
                "Start the Portable Vault tray app and unlock it from the tray menu."
            )
        broker_request("ping")
        self.path = f"broker://{self.vault.path.resolve()}#{self.entry}/{self.field}"
        digest = hashlib.sha256(
            f"{self.vault.path.resolve()}\0{self.entry}\0{self.field}".encode("utf-8")
        ).hexdigest()
        self.rotation_lock_path = (
            Path(tempfile.gettempdir())
            / "portable-ai-brain-credential-locks"
            / f"{digest}.lock"
        )
        self._broker_request = broker_request

    def load(self) -> dict[str, Any]:
        value = self._broker_request("get_json", entry=self.entry, field=self.field)
        if not isinstance(value, dict):
            raise CredentialError(
                f"Vault field must contain a JSON object: {self.entry}#{self.field}"
            )
        return value

    def save(self, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise CredentialError("JSON credential values must be objects.")
        self._broker_request(
            "set_json",
            entry=self.entry,
            field=self.field,
            value=value,
        )

    def clear(self) -> None:
        self.save({})

    @contextmanager
    def rotation_lock(self) -> Iterator[None]:
        with _file_lock(self.rotation_lock_path):
            yield


class PortableVaultJsonStore:
    """Dictionary storage in one portable-vault field.

    Prefers the Vault Agent broker. Direct passphrase access is emergency-only when
    PORTABLE_VAULT_PASSPHRASE is already present in this process.
    """

    def __init__(
        self,
        entry: str,
        field: str = "oauth_token_json",
        *,
        path: Path | str | None = None,
        passphrase: str | None = None,
    ):
        self.entry = _validate_name(entry, "Entry name")
        self.field = _validate_name(field, "Field name")
        self.vault = PortableVault(path)
        self._broker: BrokerOAuthStore | None = None
        self.passphrase = passphrase or os.getenv("PORTABLE_VAULT_PASSPHRASE", "")
        try:
            self._broker = BrokerOAuthStore(self.entry, self.field, path=path)
            self.path = self._broker.path
            self.rotation_lock_path = self._broker.rotation_lock_path
            return
        except CredentialError:
            self._broker = None
        if not self.passphrase:
            raise CredentialError(
                "Vault Agent is locked/unavailable and no in-process unlock is present. "
                "Start the Portable Vault tray app and unlock it from the tray menu."
            )
        self.path = f"vault://{self.vault.path.resolve()}#{self.entry}/{self.field}"
        digest = hashlib.sha256(
            f"{self.vault.path.resolve()}\0{self.entry}\0{self.field}".encode("utf-8")
        ).hexdigest()
        self.rotation_lock_path = (
            Path(tempfile.gettempdir())
            / "portable-ai-brain-credential-locks"
            / f"{digest}.lock"
        )

    def load(self) -> dict[str, Any]:
        if self._broker is not None:
            return self._broker.load()
        value = self.vault.get(self.entry, self.field, self.passphrase)
        if not isinstance(value, dict):
            raise CredentialError(
                f"Vault field must contain a JSON object: {self.entry}#{self.field}"
            )
        return value

    def save(self, value: dict[str, Any]) -> None:
        if self._broker is not None:
            self._broker.save(value)
            return
        self.vault.set(self.entry, self.field, value, "json", self.passphrase)

    def clear(self) -> None:
        self.save({})

    @contextmanager
    def rotation_lock(self) -> Iterator[None]:
        with _file_lock(self.rotation_lock_path):
            yield
