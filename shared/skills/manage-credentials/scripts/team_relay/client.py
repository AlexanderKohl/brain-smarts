"""The relay transport (design 7.1 and 10.5): one signed HTTPS request per call. It holds no secret
of any provider: only this computer's relay key, which signs, and for an administrator the store key,
which signs administrator requests. A connector's relay mode passes the method, the full URL, its
headers and body and a token selector, and gets back the provider's status, headers and body.

When the relay cannot be reached every call fails at once, naming the relay's address; nothing
falls back to a local copy, because there is none."""

from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from secret_store import canonical
from secret_store.errors import SecretStoreError

TIMEOUT = 100  # above the relay's 90-second provider time-out, so the relay's answer arrives first


class RelayRefused(SecretStoreError):
    """The relay refused a request with one of its fixed codes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"the team credential relay refused the call ({code}): {message}")
        self.code = code


class RelayUnreachable(SecretStoreError):
    """No answer from the relay."""


@dataclass
class Answer:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body or b"null")


Opener = Callable[[urllib.request.Request, float], tuple[int, bytes]]


def _open(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https only, checked
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class RelayClient:
    def __init__(self, url: str, person: str, computer: str, relay_key: Ed25519PrivateKey | None = None,
                 store_key: Ed25519PrivateKey | None = None, opener: Opener = _open) -> None:
        if not url.startswith("https://"):
            raise SecretStoreError("the relay's address must be https")
        self.url, self.person, self.computer = url.rstrip("/"), person, computer
        self.relay_key, self.store_key, self.opener = relay_key, store_key, opener

    def _post(self, path: str, doc: dict, key: Ed25519PrivateKey) -> tuple[int, dict]:
        raw = canonical.dumps(doc)
        request = urllib.request.Request(self.url + path, data=raw, method="POST", headers={
            "Content-Type": "application/json",
            "Relay-Signature": base64.b64encode(key.sign(raw)).decode("ascii")})
        try:
            status, body = self.opener(request, TIMEOUT)
        except (urllib.error.URLError, OSError, TimeoutError):
            raise RelayUnreachable(f"the team credential relay cannot be reached at {self.url}") from None
        try:
            answer = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise RelayUnreachable(f"the team credential relay at {self.url} gave an answer that is not JSON "
                                   f"(HTTP {status})") from None
        if not isinstance(answer, dict):
            raise RelayUnreachable(f"the team credential relay at {self.url} gave a malformed answer")
        if "refused" in answer:
            raise RelayRefused(str(answer.get("refused")), str(answer.get("message", "")))
        return status, answer

    def _stamp(self) -> dict:
        return {"computer": f"{self.person}/{self.computer}", "time": int(time.time()), "nonce": secrets.token_hex(16)}

    def call(self, credential: str, method: str, url: str, headers: dict[str, str] | None = None,
             body: bytes | None = None, token: str = "default") -> Answer:
        if self.relay_key is None:
            raise SecretStoreError("this computer has no relay key; run brain_secrets.py relay-enrol")
        doc = {"credential": credential, "token": token, "method": method.upper(), "url": url,
               "headers": dict(headers or {}),
               "body": base64.b64encode(body).decode("ascii") if body is not None else None, **self._stamp()}
        _status, answer = self._post("/v1/call", doc, self.relay_key)
        try:
            return Answer(int(answer["status"]), [(str(n), str(v)) for n, v in answer["headers"]],
                          base64.b64decode(answer["body"], validate=True))
        except (KeyError, TypeError, ValueError):
            raise RelayUnreachable(f"the team credential relay at {self.url} gave a malformed answer") from None

    def admin(self, action: str, args: dict | None = None) -> dict:
        if self.store_key is None:
            raise SecretStoreError("administrator requests are signed with this computer's store key")
        _status, answer = self._post("/v1/admin", {"action": action, "args": args or {}, **self._stamp()},
                                     self.store_key)
        return answer


def for_this_computer(admin: bool = False) -> tuple[RelayClient, Any]:
    """The client of this computer's person and computer, at the address the relay document names,
    checked against the team policy; with admin=True it also signs with the store key. Returns the
    client and the verified relay document."""
    from secret_store.team import TeamStore

    from . import document, keys
    store = TeamStore().open()
    identity = store._identity()
    clone = document.clone_path()
    try:
        document.pull(clone)
    except SecretStoreError:
        pass  # the local copy is still checked against the policy below
    view = document.verify(document.read(clone), store.policy)
    relay_key = keys.load(identity.person, identity.computer) if not admin else None
    client = RelayClient(view.url, identity.person, identity.computer, relay_key=relay_key,
                         store_key=identity.ed25519 if admin else None)
    return client, (store, view, clone)
