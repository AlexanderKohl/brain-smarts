"""Token relay, part one: the encrypted remote record and the backends that hold it.

The record is one JSON file per vault entry. It carries a version, an optional lease and the
token dictionary encrypted with AES-256-GCM under the relay key, which only the brains hold. The
associated data binds the schema, the entry, the version and the lease in a canonical form, so a
lease can be neither set nor cleared without the key. A lease is {"holder", "id", "seconds"}: no
time of day, so no brain compares its clock with another's. A backend offers two calls:
get(name) and put(name, content, expected_tag, message), the second a compare-and-swap that
raises Conflict when the tag has moved.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import urllib.parse
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from portable_vault import CredentialError


SCHEMA = 1
KEY_BYTES = 32
NONCE_BYTES = 12
BOOKKEEPING_KEYS = (
    "_relay_version",
    "_relay_unpushed",
    "_relay_base_version",
    "_relay_changed",
    "_relay_lease_id",  # this computer's lease left on the record by a leased save that failed
    "_relay_seen",  # [another brain's lease id, this computer's clock when first seen]
)
MIN_LEASE_SECONDS = 120
MAX_LEASE_SECONDS = 900
_ENTRY_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_REPOSITORY_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_HTTP_STATUS = re.compile(r"HTTP (\d{3})")


class RelayError(CredentialError):
    """A relay operation could not complete."""


class RelayUnavailable(RelayError):
    """The relay backend could not be reached or answered with an unexpected error."""


class Conflict(RelayError):
    """The remote file changed since it was read (compare-and-swap failed)."""


class RelayIntegrityError(RelayError):
    """A remote record is malformed or failed authentication."""


def strip_bookkeeping(token: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in token.items() if key not in BOOKKEEPING_KEYS}


def validate_entry(entry: str) -> str:
    if not isinstance(entry, str) or not _ENTRY_PATTERN.match(entry):
        raise CredentialError(
            "A relayed entry name may hold letters, digits, dots, underscores and hyphens only."
        )
    return entry


def remote_name(entry: str) -> str:
    return f"{validate_entry(entry)}.json"


def new_key_text() -> str:
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def decode_key(text: Any) -> bytes:
    if not isinstance(text, str):
        raise CredentialError("The relay key is missing or malformed.")
    try:
        key = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CredentialError("The relay key is missing or malformed.") from exc
    if len(key) != KEY_BYTES:
        raise CredentialError("The relay key must be 32 bytes, base64 encoded.")
    return key


def associated_data(entry: str, version: int, lease: dict[str, Any] | None) -> bytes:
    """Schema, entry, version and lease in one canonical form."""
    return json.dumps(
        {"entry": entry, "lease": lease, "schema": SCHEMA, "version": version},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def encrypt_token(
    key: bytes, entry: str, version: int, token: dict[str, Any], lease: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Encrypt the token dictionary (without bookkeeping keys) with a fresh nonce."""
    nonce = os.urandom(NONCE_BYTES)
    plaintext = json.dumps(
        strip_bookkeeping(token), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data(entry, version, lease))
    return (
        base64.b64encode(nonce).decode("ascii"),
        base64.b64encode(ciphertext).decode("ascii"),
    )


def decrypt_token(key: bytes, entry: str, record: dict[str, Any]) -> dict[str, Any]:
    try:
        nonce = base64.b64decode(record["nonce"], validate=True)
        ciphertext = base64.b64decode(record["ciphertext"], validate=True)
        plaintext = AESGCM(key).decrypt(
            nonce,
            ciphertext,
            associated_data(entry, int(record["version"]), record.get("lease")),
        )
        token = json.loads(plaintext.decode("utf-8"))
    except InvalidTag as exc:
        raise RelayIntegrityError(
            f"The relay record for {entry} failed authentication: wrong key or altered record."
        ) from exc
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise RelayIntegrityError(f"The relay record for {entry} is malformed.") from exc
    if not isinstance(token, dict):
        raise RelayIntegrityError(f"The relay record for {entry} is malformed.")
    return token


def build_record(
    key: bytes,
    entry: str,
    version: int,
    token: dict[str, Any],
    *,
    lease: dict[str, Any] | None,
    holder: str,
    updated_at: str,
) -> dict[str, Any]:
    nonce, ciphertext = encrypt_token(key, entry, version, token, lease)
    return {
        "schema": SCHEMA,
        "version": version,
        "lease": lease,
        "nonce": nonce,
        "ciphertext": ciphertext,
        "updated_by": holder,
        "updated_at": updated_at,
    }


def parse_record(content: bytes, entry: str) -> dict[str, Any]:
    try:
        record = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayIntegrityError(f"The relay record for {entry} is malformed.") from exc
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise RelayIntegrityError(f"The relay record for {entry} has an unsupported schema.")
    version = record.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise RelayIntegrityError(f"The relay record for {entry} has an invalid version.")
    lease = record.get("lease")
    if lease is not None and (
        not isinstance(lease, dict)
        or set(lease) != {"holder", "id", "seconds"}
        or not isinstance(lease["holder"], str)
        or not isinstance(lease["id"], str)
        or not isinstance(lease["seconds"], int)
        or isinstance(lease["seconds"], bool)
        or not MIN_LEASE_SECONDS <= lease["seconds"] <= MAX_LEASE_SECONDS
    ):
        raise RelayIntegrityError(f"The relay record for {entry} has a malformed lease.")
    if not isinstance(record.get("nonce"), str) or not isinstance(record.get("ciphertext"), str):
        raise RelayIntegrityError(f"The relay record for {entry} is malformed.")
    return record


def dump_record(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")


class MemoryBackend:
    """In-memory compare-and-swap store, used by every test."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.messages: list[str] = []
        self.unreachable = False
        self.fail_puts = 0
        self._counter = 0

    def get(self, name: str) -> tuple[bytes | None, str | None]:
        if self.unreachable:
            raise RelayUnavailable("The relay backend cannot be reached.")
        content, tag = self.files.get(name, (None, None))
        return content, tag

    def put(self, name: str, content: bytes, expected_tag: str | None, message: str) -> str:
        if self.unreachable:
            raise RelayUnavailable("The relay backend cannot be reached.")
        if self.fail_puts > 0:
            self.fail_puts -= 1
            raise RelayUnavailable("The relay backend cannot be reached.")
        current = self.files.get(name)
        current_tag = current[1] if current else None
        if current_tag != expected_tag:
            raise Conflict(f"The relay file {name} changed since it was read.")
        self._counter += 1
        tag = f"tag-{self._counter}"
        self.files[name] = (bytes(content), tag)
        self.messages.append(message)
        return tag


Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


class GitHubBackend:
    """A private GitHub repository through the Contents API, called with the gh command line.

    The gh command line holds its own sign-in; this class never reads or handles a GitHub token.
    Request bodies travel on standard input, never in arguments. The file's sha is the tag.
    """

    def __init__(self, repository: str, *, runner: Runner | None = None, gh: str = "gh") -> None:
        if not isinstance(repository, str) or not _REPOSITORY_PATTERN.match(repository):
            raise CredentialError("The relay repository must be written as owner/name.")
        self.repository = repository
        self._runner = runner or subprocess.run
        self._gh = gh

    def _path(self, name: str) -> str:
        return f"repos/{self.repository}/contents/{urllib.parse.quote(name)}"

    def _call(self, arguments: list[str], body: bytes | None = None) -> tuple[int, bytes, str]:
        try:
            completed = self._runner(
                [self._gh, "api", *arguments],
                input=body if body is not None else b"",
                capture_output=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RelayUnavailable("The gh command line is not installed.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RelayUnavailable("The relay repository did not answer in time.") from exc
        except OSError as exc:
            raise RelayUnavailable("The gh command line could not be started.") from exc
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
        stdout = completed.stdout or b""
        return completed.returncode, stdout, stderr + stdout.decode("utf-8", errors="replace")

    @staticmethod
    def _status(text: str) -> int | None:
        match = _HTTP_STATUS.search(text)
        return int(match.group(1)) if match else None

    def get(self, name: str) -> tuple[bytes | None, str | None]:
        code, stdout, text = self._call(
            ["-H", "Accept: application/vnd.github+json", self._path(name)]
        )
        if code != 0:
            status = self._status(text)
            if status == 404 and self._repository_readable():
                return None, None
            raise RelayUnavailable(
                f"The relay repository could not be read (HTTP {status or 'unknown'})."
            )
        try:
            answer = json.loads(stdout.decode("utf-8"))
            content = base64.b64decode(str(answer["content"]).replace("\n", ""), validate=True)
            tag = str(answer["sha"])
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise RelayUnavailable("The relay repository answered in an unexpected shape.") from exc
        return content, tag

    def _repository_readable(self) -> bool:
        """A 404 for the file means "no record yet" only when the repository itself answers:
        GitHub also says 404 for a repository the signed-in account cannot see."""
        code, _, _ = self._call(
            ["-H", "Accept: application/vnd.github+json", f"repos/{self.repository}"]
        )
        return code == 0

    def put(self, name: str, content: bytes, expected_tag: str | None, message: str) -> str:
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
        }
        if expected_tag:
            body["sha"] = expected_tag
        code, stdout, text = self._call(
            [
                "-X",
                "PUT",
                "-H",
                "Accept: application/vnd.github+json",
                self._path(name),
                "--input",
                "-",
            ],
            json.dumps(body).encode("utf-8"),
        )
        if code != 0:
            status = self._status(text)
            if status == 409 or (status == 422 and not expected_tag):
                raise Conflict(f"The relay file {name} changed since it was read.")
            raise RelayUnavailable(
                f"The relay repository refused the write (HTTP {status or 'unknown'})."
            )
        try:
            return str(json.loads(stdout.decode("utf-8"))["content"]["sha"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RelayUnavailable("The relay repository answered in an unexpected shape.") from exc
