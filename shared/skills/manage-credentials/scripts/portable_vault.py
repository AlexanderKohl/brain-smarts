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


class StaleAgentError(CredentialError):
    """The secrets store is on but the running Vault Agent serves only the old vault."""


def __getattr__(name: str) -> Any:
    """ProviderNotCalled: the secrets-store journal's class, re-exported so a connector can raise
    it for a failure before any provider request (the begun refresh is then removed, not held as
    uncertain). Imported on first use, so this module stays light."""
    if name == "ProviderNotCalled":
        from secret_store.journal import ProviderNotCalled

        return ProviderNotCalled
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def find_brain_root(start: Path | None = None) -> Path:
    """Walk upwards from this script (or ``start``) to the folder holding CONTRACT.md."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    # Fallback for a copy of the skill outside a brain: the historical fixed depth.
    return Path(__file__).resolve().parents[4]


SECRET_STORE_CONFIG = Path("memory") / "skills" / "manage-credentials" / "config" / "secret-store.json"
STORE_ON_MESSAGE = "the secrets store is on; start the Vault Agent"
STALE_AGENT_MESSAGE = "the Vault Agent was started before the secrets store was switched on; restart it"


def secret_store_enabled(brain_root: Path | None = None) -> bool:
    """Whether secret-store.json turns the secrets store on (as store_ops.load_config reads it: a
    file without "enabled" is on). An unreadable file counts as on, so nothing falls back."""
    path = Path(brain_root or find_brain_root()) / SECRET_STORE_CONFIG
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return True
    return not isinstance(data, dict) or bool(data.get("enabled", True))


def refuse_when_store_on() -> None:
    """Fail closed (round-6 review): with the store on, the passphrase vault and
    PORTABLE_VAULT_PASSPHRASE are never a fallback for an unavailable Vault Agent."""
    if secret_store_enabled():
        raise CredentialError(STORE_ON_MESSAGE)


def require_store_agent(status: Any) -> bool:
    """Fail closed (round-7 review): with the store on, the running agent's status must report
    backend "store"; a vault-only agent started earlier is refused, never read. Returns whether
    the agent serves the store."""
    serves = isinstance(status, dict) and status.get("backend") == "store"
    if not serves and secret_store_enabled():
        raise StaleAgentError(STALE_AGENT_MESSAGE)
    return serves


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


LOCK_TIMEOUT_SECONDS = 300.0  # the longest wait for a vault or rotation lock, the relay's lease


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    from secret_store import fileio

    def busy() -> CredentialError:
        return CredentialError(f"Another process on this computer holds the lock {path.name} and did not release "
                               f"it within {LOCK_TIMEOUT_SECONDS:.0f} seconds. Try again shortly.")
    with fileio.locked(path, LOCK_TIMEOUT_SECONDS, busy):
        yield


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

    def entry_names(self, passphrase: str) -> list[str]:
        """The names of the entries held, without any field name or value."""
        return list(self.load(passphrase)["entries"])

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

    def delete_field(self, entry: str, field: str, passphrase: str) -> None:
        """Remove one field and leave the rest of the entry as it was. The last field of an entry
        is refused: an entry with nothing in it is deleted as an entry, a separate decision."""
        entry = _validate_name(entry, "Entry name")
        field = _validate_name(field, "Field name")
        with _file_lock(self.lock_path):
            payload = self._load_unlocked(passphrase)
            try:
                fields = payload["entries"][entry]["fields"]
                if field not in fields:
                    raise KeyError(field)
            except (KeyError, TypeError) as exc:
                raise CredentialError(f"Credential field does not exist: {entry}#{field}") from exc
            if len(fields) == 1:
                raise CredentialError(
                    f"{field} is the only field of {entry}; delete the entry itself with delete-entry."
                )
            del fields[field]
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
        self._operation: str | None = None  # an open store refresh (vault_broker_client.store_refresh)
        self._saved = False
        self._store_mode: bool | None = None
        if secret_store_enabled():
            self._store_mode = require_store_agent(broker_request("status"))

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
        extra = {"operation": self._operation} if self._operation else {}
        self._broker_request("set_json", entry=self.entry, field=self.field, value=value, **extra)
        # Saved only once the broker confirms: a failed save leaves the refresh to be released with
        # its record kept (uncertain), never removed.
        self._saved = self._saved or bool(extra)

    def clear(self) -> None:
        if self.store_mode():
            self._broker_request("clear_signin", entry=self.entry, field=self.field)
            return
        self.save({})

    def sync_store(self) -> None:
        """Pull the secrets store now (PortableVaultJsonStore.sync)."""
        if self.store_mode():
            self._broker_request("sync_store")

    @contextmanager
    def rotation_lock(self) -> Iterator[None]:
        with _file_lock(self.rotation_lock_path):
            yield

    def store_mode(self) -> bool:
        """Whether the Vault Agent serves the secrets store (asked once)."""
        if self._store_mode is None:
            status = self._broker_request("status")
            self._store_mode = isinstance(status, dict) and status.get("backend") == "store"
        return self._store_mode

    def refresh_lock(self, local_lock: Any, **options: Any) -> Any:
        from vault_broker_client import store_refresh

        return store_refresh(self, local_lock, **options)


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
        except StaleAgentError:
            raise
        except CredentialError:
            self._broker = None
        if self._broker is None:
            refuse_when_store_on()
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
        # Token relay hook: a relayed store for an entry listed in token-relay.json beside the
        # vault, else None and the behaviour below is unchanged. The logic lives in token_relay.py.
        # With the secrets store on no relay is built, whatever token-relay.json lists.
        from token_relay import relay_for

        self._relay = relay_for(self)

    def _local_load(self) -> dict[str, Any]:
        if self._broker is not None:
            return self._broker.load()
        value = self.vault.get(self.entry, self.field, self.passphrase)
        if not isinstance(value, dict):
            raise CredentialError(
                f"Vault field must contain a JSON object: {self.entry}#{self.field}"
            )
        return value

    def _local_save(self, value: dict[str, Any]) -> None:
        if self._broker is not None:
            self._broker.save(value)
            return
        self.vault.set(self.entry, self.field, value, "json", self.passphrase)

    @contextmanager
    def _local_rotation_lock(self) -> Iterator[None]:
        with _file_lock(self.rotation_lock_path):
            yield

    def load(self) -> dict[str, Any]:
        if self._relay is not None:
            return self._relay.load()
        return self._local_load()

    def save(self, value: dict[str, Any]) -> None:
        if self._relay is not None:
            self._relay.save(value)
            return
        self._local_save(value)

    def clear(self) -> None:
        if self._relay is not None:
            self._relay.clear()
            return
        if self._broker is not None:
            self._broker.clear()
            return
        self.save({})

    def rotation_lock(
        self,
        *,
        refresh: bool = False,
        leeway_seconds: float | None = None,
        new_authorisation: bool = False,
    ) -> Any:
        """The rotation lock. A relayed store takes its lease when refresh=True (forced) or when the
        token expires within leeway_seconds; new_authorisation=True marks a code exchange, which
        may go ahead locally when the entry has no shared record yet and this computer holds no
        refresh token. Without the relay the arguments change nothing, except that a token carrying a
        relay version with no relay config found is refused (token_relay.refuse_unrelayed_refresh)."""
        if self._relay is not None:
            return self._relay.rotation_lock(
                refresh=refresh, leeway_seconds=leeway_seconds, new_authorisation=new_authorisation
            )
        # Fail closed: a relay-marked token with no relay config found is refused a refresh. With the
        # store on the relay is ignored and the store's journal decides instead.
        from token_relay import refuse_unrelayed_refresh

        if not getattr(self, "relay_ignored", False):
            refuse_unrelayed_refresh(
                self, refresh=refresh, leeway_seconds=leeway_seconds, new_authorisation=new_authorisation
            )
        # Secrets store: every lock on a sign-in, a plain one too, goes through the agent's journal on
        # the refresher; elsewhere a refresh waits for the refresher.
        if self._broker is not None and self._broker.store_mode():
            return self._broker.refresh_lock(self._local_rotation_lock, refresh=refresh,
                                             leeway_seconds=leeway_seconds, new_authorisation=new_authorisation)
        return self._local_rotation_lock()

    def sync(self) -> None:
        """Adopt the shared record: the relay's without a lease, or a pull of the secrets store."""
        if self._relay is not None:
            self._relay.sync()
        elif self._broker is not None:
            self._broker.sync_store()

    def set_chain_keys(self, keys: Any) -> None:
        """The keys a provider's token answer sets; the relay lets only a lease holder change them."""
        if self._relay is not None:
            self._relay.set_chain_keys(keys)
