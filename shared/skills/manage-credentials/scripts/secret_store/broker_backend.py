"""The Vault Agent's secrets-store backend (design synced-secrets-repository.md, section 9,
Consumers). With /memory/skills/manage-credentials/config/secret-store.json enabled, the agent
serves get_fields, get_json, set_json, set_text and get_access_token from the store, with the
computer keys from the keychain and no passphrase. Per sign-in: the refresher reads the merged
record and publishes refreshed tokens through the refresh journal; any other computer reads the
access token and shared settings and may change shared settings only. Also the vault-only
operations the migration uses. Messages never carry values."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from . import oauth_ops, provider_profiles
from .errors import SecretStoreError
from .journal import Journal
from .store import SecretStore
from .store_ops import load_config

SYNC_SECONDS = 30.0
REFRESH_TIMEOUT = 600.0  # a begun refresh without its save by then stays uncertain
VAULT_OPS = frozenset({"vault_list_entries", "vault_verify_copy", "vault_get_fields", "vault_get_json"})
STORE_OPS = frozenset({"begin_refresh", "abort_refresh", "poll_refresh"})
AGENT_OPS = VAULT_OPS | STORE_OPS


def store_enabled(brain_root: Any = None) -> bool:
    """True when the store configuration is present, enabled and names a person. An unreadable
    configuration leaves the agent on the vault, as today."""
    try:
        config = load_config(True, brain_root)
    except SecretStoreError:
        return False
    return bool(config["enabled"] and config["person"])


def backend_if_enabled(brain_root: Any = None) -> "StoreBackend | None":
    return StoreBackend() if store_enabled(brain_root) else None


class StoreBackend:
    def __init__(self, store: Any = None, sync_seconds: float = SYNC_SECONDS) -> None:
        self.store = store if store is not None else SecretStore()
        self.sync_seconds = sync_seconds
        self._synced: float | None = None
        self._journal: Journal | None = None
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}  # journal key -> the begun refresh holding its lock
        self.refresh_timeout = REFRESH_TIMEOUT

    # -- plumbing ---------------------------------------------------------------------------
    def _ready(self) -> Any:
        st = self.store
        if st.policy is None:
            st.open()
            self._synced = time.monotonic()
        elif self._synced is None or time.monotonic() - self._synced >= self.sync_seconds:
            st._sync(None, st.checkpoint)
            self._synced = time.monotonic()
        if self._journal is None:
            self._journal = Journal(st.config["checkpoint_dir"], st._identity().x25519)
        return st

    def status(self) -> dict[str, Any]:
        try:
            text = self.store.status()
        except SecretStoreError as error:
            text = str(error)
        return {"backend": "store", "store": text}

    def _policy_disabled(self, st: Any) -> bool:
        person, computer = st.config["person"], st.config["computer"]
        return computer in st.policy.doc["people"].get(person, {}).get("disabled_refresher", [])

    def _hooks(self, signin: oauth_ops.SignIn) -> tuple:
        st = self.store
        return (lambda op, answer: oauth_ops.publish(st, signin, answer, op),
                lambda op, answer: oauth_ops.is_published(st, signin, op, answer))

    def _signin(self, st: Any, entry: str, field: str) -> oauth_ops.SignIn | None:
        signin = oauth_ops.find(st, entry, field)
        if signin is not None and signin.mine and signin.journal_key not in self._pending:
            self._journal.reconcile(signin.journal_key, *self._hooks(signin))
        return signin

    @staticmethod
    def _static(st: Any, entry: str) -> dict:
        return st.get_record(entry) if entry in st._index() else {}

    # -- the broker operations --------------------------------------------------------------
    def get_fields(self, entry: str, fields: list[str]) -> dict[str, Any]:
        with self._lock:
            st = self._ready()
            static, out = self._static(st, entry), {}
            for field in fields:
                if field in static:
                    out[field] = static[field]
                    continue
                signin = self._signin(st, entry, field)
                out[field] = oauth_ops.read(st, signin) if signin else self._grant_field(st, entry, field)
            return out

    def _grant_field(self, st: Any, entry: str, field: str) -> str:
        for name in oauth_ops.signin_fields(st, entry):
            signin = oauth_ops.find(st, entry, name)
            if not signin.mine:
                if field in provider_profiles.grant_fields(signin.provider):
                    oauth_ops.refuse_other(signin)
                continue
            found = oauth_ops.read_grant(st, signin).get("fields", {})
            if field in found:
                return found[field]
        raise SecretStoreError(f"Credential field does not exist: {entry}#{field}")

    def get_json(self, entry: str, field: str) -> dict[str, Any]:
        with self._lock:
            st = self._ready()
            signin = self._signin(st, entry, field)
            if signin is not None:
                return oauth_ops.read(st, signin)
            text = self._static(st, entry).get(field)
            if text is None:
                raise SecretStoreError(f"Credential field does not exist: {entry}#{field}")
            try:
                value = json.loads(text)
            except ValueError:
                value = None
            if not isinstance(value, dict):
                raise SecretStoreError(f"Vault field must contain a JSON object: {entry}#{field}")
            return value

    def set_json(self, entry: str, field: str, value: dict[str, Any], operation: str | None = None) -> None:
        with self._lock:
            st = self._ready()
            value = oauth_ops.plain_numbers(value)
            if operation is not None:
                self._complete_refresh(entry, field, value, operation)
                return
            if f"{entry}#{field}" in self._pending:
                raise SecretStoreError(f"a refresh of {entry} is under way; only its own save may change the token")
            signin = self._signin(st, entry, field)
            if signin is None:
                if field not in self._static(st, entry) and oauth_ops.looks_like_signin(value):
                    oauth_ops.put_signin(st, entry, field, value)
                else:
                    st.put_entry(entry, {field: json.dumps(value, sort_keys=True)})
                return
            if not signin.mine:
                oauth_ops.save_settings(st, signin, value)
                return
            current = oauth_ops.read(st, signin)
            watched = provider_profiles.token_fields(signin.provider) | provider_profiles.grant_fields(signin.provider)
            if any(k in value and value[k] != current.get(k) for k in watched):
                revision = st.checkpoint.objects[signin.oauth_id]["revision"]
                self._journal.publish_answer(signin.journal_key, revision, value, *self._hooks(signin),
                                             provider=signin.provider, policy_disabled=self._policy_disabled(st))
            else:
                oauth_ops.save_settings(st, signin, value)

    def set_text(self, entry: str, field: str, value: str) -> None:
        with self._lock:
            st = self._ready()
            if field not in self._static(st, entry):
                for name in oauth_ops.signin_fields(st, entry):
                    signin = oauth_ops.find(st, entry, name)
                    if field in provider_profiles.grant_fields(signin.provider):
                        oauth_ops.set_grant_fields(st, signin, {field: value})
                        return
            st.put_entry(entry, {field: value})


    # -- the refresh through the agent (section 9, refresh steps 1 to 7) --------------------
    def _pull(self, st: Any) -> None:
        st._sync(None, st.checkpoint)
        self._synced = time.monotonic()

    def begin_refresh(self, entry: str, field: str) -> dict[str, Any]:
        """On the refresher: take the per-entry lock, refuse a disabled or unresolved entry, write
        and flush the calling record; return its operation id and the full record. Elsewhere: the
        refresher's name and the latest published record, after a pull."""
        with self._lock:
            st = self._ready()
            signin = self._signin(st, entry, field)
            if signin is None:
                return {"signin": False}
            if not signin.mine:
                self._pull(st)
                return {"signin": True, "refresher": False, "computer": signin.refresher[1],
                        "record": oauth_ops.read(st, signin)}
            key = signin.journal_key
            if key in self._pending:
                raise SecretStoreError(f"a refresh of {entry} is already under way on this computer; try again shortly")
            revision = st.checkpoint.objects[signin.oauth_id]["revision"]
            stack, record = self._journal.begin(key, revision, signin.provider, self._policy_disabled(st))
            timer = threading.Timer(self.refresh_timeout, self._expire, (key, record["operation"]))
            timer.daemon = True
            self._pending[key] = {"stack": stack, "record": record, "timer": timer, "signin": signin}
            timer.start()
            return {"signin": True, "refresher": True, "operation": record["operation"],
                    "record": oauth_ops.read(st, signin)}

    def _expire(self, key: str, operation: str) -> None:
        """The time limit: release the lock and leave the record in calling (uncertain)."""
        with self._lock:
            held = self._pending.get(key)
            if held is not None and held["record"]["operation"] == operation:
                del self._pending[key]
                held["stack"].close()

    def _take(self, key: str, operation: str) -> dict | None:
        held = self._pending.get(key)
        if held is None or held["record"]["operation"] != operation:
            return None
        del self._pending[key]
        held["timer"].cancel()
        return held

    def _complete_refresh(self, entry: str, field: str, value: dict, operation: str) -> None:
        held = self._take(f"{entry}#{field}", operation)
        if held is None:
            raise SecretStoreError(f"the refresh of {entry} was not begun here or ran past its time limit; "
                                   "nothing was saved")
        try:
            self._journal.complete(held["signin"].journal_key, held["record"], value, self._hooks(held["signin"])[0])
        finally:
            held["stack"].close()

    def abort_refresh(self, entry: str, field: str, operation: str) -> dict[str, bool]:
        """The connector failed before any provider call: remove the calling record, release."""
        with self._lock:
            held = self._take(f"{entry}#{field}", operation)
            if held is None:
                return {"aborted": False}
            try:
                return {"aborted": self._journal.abandon(held["signin"].journal_key, held["record"])}
            finally:
                held["stack"].close()

    def poll_refresh(self, entry: str, field: str) -> dict[str, Any]:
        """The latest published record after a pull (another computer waiting for the refresher)."""
        with self._lock:
            st = self._ready()
            self._pull(st)
            signin = self._signin(st, entry, field)
            if signin is None:
                raise SecretStoreError(f"there is no sign-in {entry}#{field}")
            return oauth_ops.read(st, signin)


def agent_operation(agent: Any, operation: str, request: dict) -> Any:
    """The Vault Agent operations answered here: vault-only ones and the store's refresh ones."""
    if operation in VAULT_OPS:
        return vault_request(agent.vault, agent._require_passphrase(), operation, request)
    if agent._store is None:
        raise SecretStoreError("the secrets store is off on this computer")
    entry, field = str(request.get("entry") or ""), str(request.get("field") or "oauth_token_json")
    if operation == "begin_refresh":
        return agent._store.begin_refresh(entry, field)
    if operation == "abort_refresh":
        return agent._store.abort_refresh(entry, field, str(request.get("operation") or ""))
    return agent._store.poll_refresh(entry, field)


def vault_request(vault: Any, passphrase: str, operation: str, request: dict) -> Any:
    """Vault-only operations for the migration, answered from the unlocked portable vault."""
    entry = str(request.get("entry") or "")
    if operation == "vault_list_entries":
        entries = vault.load(passphrase).get("entries") or {}
        return {name: {f: r.get("kind") for f, r in (rec.get("fields") or {}).items()}
                for name, rec in entries.items()}
    if operation == "vault_verify_copy":
        path = Path(str(request.get("path") or "")).resolve()
        if Path(vault.path).resolve().parent not in path.parents:
            raise SecretStoreError("a vault copy to check must be inside the vault's folder")
        return sorted(type(vault)(path).load(passphrase).get("entries") or {})
    if operation == "vault_get_fields":
        fields = request.get("fields")
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise SecretStoreError("fields must be a list of strings")
        return vault.get_fields(entry, fields, passphrase)
    if operation == "vault_get_json":
        value = vault.get(entry, str(request.get("field") or ""), passphrase)
        if not isinstance(value, dict):
            raise SecretStoreError(f"Vault field must contain a JSON object: {entry}")
        return value
    raise SecretStoreError(f"unsupported vault operation {operation}")
