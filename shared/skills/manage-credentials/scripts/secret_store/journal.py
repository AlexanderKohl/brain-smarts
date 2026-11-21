"""The refresh journal and per-entry refresh lock (design synced-secrets-repository.md, section 9,
refresh steps 1 to 7). One exclusive file lock per entry is held from step 1 to step 6. Each state
(calling, answered, published, superseded) is flushed to disk before the next step, encrypted to
this computer's X25519 key only, under the checkpoint folder. A record left in calling is
uncertain: every further refresh of the entry is refused. Publication retries never call the
provider. A persisted local disabled flag per entry is honoured at every start. A published
record is retired (its file removed). A journal key names the entry and field for messages, then
the repository id and the grant object id after KEY_SEPARATOR, so same-named sign-ins in
different repositories or groups never share a lock, record or disabled flag."""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from . import envelope, fileio, provider_profiles
from .errors import SecretStoreError
from .keys import key_id
from .oauth_ops import DEFAULT_FIELD, plain_numbers

STATES = ("calling", "answered", "published", "superseded")
LOCK_SECONDS = 30.0  # how long a second process waits for the per-entry lock
KEY_SEPARATOR = " @ "


def label(key: str) -> str:
    """The entry and field of a journal key, for messages."""
    return key.split(KEY_SEPARATOR, 1)[0]


class ProviderNotCalled(Exception):
    """Raised by a provider call that certainly sent nothing (for example no network). Any other
    exception from the call leaves the record in calling: the call may have reached the provider."""


def uncertain_message(entry: str, provider: str | None) -> str:
    name, _sep, field = label(entry).rpartition("#")
    name = name or field
    command = f'brain_secrets.py replace-signin "{name}"' + (f" --field {field}" if _sep and field != DEFAULT_FIELD else "")
    procedure = ("" if provider_profiles.recovery_refusal(provider)
                 else "Run the uncertain-refresh procedure for this provider, or replace the sign-in. ")
    return (f"The last refresh of {label(entry)} is uncertain: the provider was called but its answer was never "
            "recorded, so the old refresh token must not be used again and the entry is not refreshed. "
            + procedure + "Next step: on the computer that refreshes it, an administrator runs "
            f"{command} (add --group G for a team sign-in), then disconnect the app at the provider where it "
            "offers that and sign in again in the browser on that computer.")


class Journal:
    lock_timeout = LOCK_SECONDS

    def __init__(self, checkpoint_dir: Any, x25519_private: Any) -> None:
        self.folder = Path(checkpoint_dir) / "journal"
        self._key = x25519_private
        self._key_id = key_id(x25519_private.public_key())

    def _name(self, entry: str) -> str:
        return hashlib.sha256(entry.encode("utf-8")).hexdigest()[:40]

    def path(self, entry: str) -> Path:
        return self.folder / f"{self._name(entry)}.journal"

    @contextmanager
    def lock(self, entry: str) -> Iterator[None]:
        """The per-entry refresh lock (exclusive, across processes), waited for up to lock_timeout."""
        def busy() -> SecretStoreError:
            return SecretStoreError(f"another refresh of {label(entry)} holds its lock on this computer; try again shortly")
        with fileio.locked(self.folder / f"{self._name(entry)}.lock", self.lock_timeout, busy):
            yield

    def read(self, entry: str) -> dict | None:
        path = self.path(entry)
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            raise SecretStoreError(f"the refresh journal of {label(entry)} cannot be read; the entry is held") from None
        record = envelope.open_(obj, self._key_id, self._key)
        if record.get("entry") != entry or record.get("state") not in STATES:
            raise SecretStoreError(f"the refresh journal of {label(entry)} is malformed; the entry is held")
        return record

    def write(self, entry: str, record: dict) -> None:
        if record.get("state") not in STATES:
            raise SecretStoreError("unknown journal state")
        header = {"repository": "local-journal", "group": "local", "id": self._name(entry), "kind": "static",
                  "revision": 1}
        obj = envelope.seal(record, [(self._key_id, self._key.public_key())], header)
        fileio.write_durable(self.path(entry), json.dumps(obj).encode("utf-8"))

    def disabled(self, entry: str) -> bool:
        return (self.folder / f"{self._name(entry)}.disabled").exists()

    def set_disabled(self, entry: str) -> None:
        """Persist this computer's local disabled flag for the entry (handover, section 9)."""
        fileio.write_durable(self.folder / f"{self._name(entry)}.disabled", b"disabled\n")

    def check(self, entry: str, provider: str | None = None, policy_disabled: bool = False) -> dict | None:
        """Steps 1 and 2: refuse a disabled refresher and an uncertain record; return a record whose
        publication is still pending (answered), else None."""
        if policy_disabled or self.disabled(entry):
            raise SecretStoreError(f"refreshing {label(entry)} is switched off on this computer; it is not refreshed here")
        record = self.read(entry)
        if record is not None and record["state"] == "calling":
            raise SecretStoreError(uncertain_message(entry, provider))
        return record if record is not None and record["state"] == "answered" else None

    def _finish(self, entry: str, record: dict, publish: Callable, is_published: Callable) -> dict:
        """Step 6: publish (or find the publication already there), then retire the record: its
        file is removed, so no answer stays on disk once the remote holds it."""
        if not is_published(record["operation"], record["answer"]):
            publish(record["operation"], record["answer"])
        fileio.remove_durable(self.path(entry))
        return record["answer"]

    def refresh(self, entry: str, revision: int, call: Callable[[], dict], publish: Callable,
                is_published: Callable, provider: str | None = None, policy_disabled: bool = False) -> dict:
        """Steps 1 to 6 around a provider call. A pending publication is finished first and its
        answer returned, without calling the provider."""
        with self.lock(entry):
            pending = self.check(entry, provider, policy_disabled)
            if pending is not None:
                return self._finish(entry, pending, publish, is_published)
            base = {"operation": secrets.token_hex(16), "entry": entry, "revision": revision}
            self.write(entry, {**base, "state": "calling"})
            try:
                answer = call()
            except ProviderNotCalled:
                self.path(entry).unlink(missing_ok=True)
                raise
            record = {**base, "state": "answered", "answer": plain_numbers(dict(answer))}
            self.write(entry, record)
            return self._finish(entry, record, publish, lambda *_: False)

    def begin(self, entry: str, revision: int, provider: str | None = None,
              policy_disabled: bool = False, write: bool = True) -> tuple[ExitStack, dict]:
        """Steps 1 to 3 for a provider call made in another process (the Vault Agent's
        begin_refresh). The per-entry lock stays held in the returned stack until the caller closes
        it after complete or abandon, or at its own time limit (the record then stays uncertain).
        With write=False (a code exchange, which never spends the stored grant) nothing is written
        until complete: a block that ends without a save leaves no record."""
        stack = ExitStack()
        stack.enter_context(self.lock(entry))
        try:
            if self.check(entry, provider, policy_disabled) is not None:
                raise SecretStoreError(f"a refreshed token of {label(entry)} is still waiting to be published; try again")
            record = {"operation": secrets.token_hex(16), "entry": entry, "revision": revision, "state": "calling"}
            if write:
                self.write(entry, record)
        except BaseException:
            stack.close()
            raise
        return stack, record

    def complete(self, entry: str, record: dict, answer: dict, publish: Callable) -> dict:
        """Steps 5 and 6 for a begun refresh; the caller holds the per-entry lock."""
        answered = {**record, "state": "answered", "answer": plain_numbers(dict(answer))}
        self.write(entry, answered)
        return self._finish(entry, answered, publish, lambda *_: False)

    def abandon(self, entry: str, record: dict) -> bool:
        """Remove a begun record still in calling: the connector failed before any provider call."""
        current = self.read(entry)
        if current is None or current["state"] != "calling" or current["operation"] != record["operation"]:
            return False
        self.path(entry).unlink(missing_ok=True)
        return True

    def reconcile(self, entry: str, publish: Callable, is_published: Callable, disabled: bool = False) -> None:
        """Finish a pending publication (never a provider call); an uncertain record stays as it is.
        A disabled refresher (the local flag, or disabled in the policy) publishes nothing. A failed
        publication (an unreachable remote) leaves the answer journalled for a later attempt, so
        reads go on from the local clone."""
        if disabled or self.disabled(entry):
            return
        with self.lock(entry):
            record = self.read(entry)
            if record is not None and record["state"] == "answered":
                try:
                    self._finish(entry, record, publish, is_published)
                except SecretStoreError:
                    return

    def resolve_uncertain(self, entry: str, provider: str | None) -> None:
        """Mark an uncertain record superseded: only for a provider with a verified profile, after
        the uncertain-refresh procedure has run. Refused everywhere for now."""
        refusal = provider_profiles.recovery_refusal(provider)
        if refusal:
            raise SecretStoreError(refusal)
        with self.lock(entry):
            record = self.read(entry)
            if record is None or record["state"] != "calling":
                raise SecretStoreError(f"{label(entry)} has no uncertain refresh to resolve")
            self.write(entry, {**record, "state": "superseded"})
