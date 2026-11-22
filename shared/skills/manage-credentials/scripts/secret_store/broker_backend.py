"""The Vault Agent's secrets-store backend (design synced-secrets-repository.md, section 9,
Consumers). With /memory/skills/manage-credentials/config/secret-store.json enabled, the agent
serves get_fields, get_json, set_json, set_text and get_access_token from the store, with the
computer keys from the keychain and no passphrase. Per sign-in: the refresher reads the merged
record and publishes refreshed tokens through the refresh journal; any other computer reads the
access token and shared settings and may change shared settings only. An entry is served from
the personal store or the team store by which index holds its name (personal first; a name held
twice is refused as ambiguous; a new name goes to the personal store). The team store is built
and opened when the configuration names one (team_repo_url, or a team_clone that holds a
clone); while its repository has no commit the personal store is served, status shows the team
store as not created yet, and the next operation after team-init opens it. Grant fields are never stored in or served from a static object. A token field of a
sign-in changes only inside a begun refresh (begin_refresh, then set_json with its operation
id); a first sign-in begins with new_authorisation. Also the vault-only operations the
migration uses. Messages never carry values."""

from __future__ import annotations

import json
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from . import oauth_ops, provider_profiles
from .errors import SecretStoreError
from .journal import Journal
from .store import SecretStore
from .store_ops import load_config

SYNC_SECONDS = 30.0
REFRESH_TIMEOUT = 600.0  # a begun refresh without its save by then stays uncertain
VAULT_OPS = frozenset({"vault_clear_migration_marker", "vault_get_fields", "vault_get_json", "vault_list_entries",
                       "vault_restore_static", "vault_scrub_signin", "vault_verify_copy"})
TOKEN_KEYS = frozenset({"access_token", "accessToken", "refresh_token", "refreshToken"})
STORE_OPS = frozenset({"abort_refresh", "begin_refresh", "clear_signin", "poll_refresh", "release_refresh",
                       "sync_store"})
AGENT_OPS = VAULT_OPS | STORE_OPS
# Run only while migrate_to_store.py holds the migration lock (round-9 plan, row M5).
LOCKED_VAULT_OPS = frozenset({"vault_clear_migration_marker", "vault_restore_static", "vault_scrub_signin"})


PACKAGE_TIMER_SECONDS = 6 * 3600.0  # the recovery-package timer runs at least this often
PACKAGE_TIMER_POLL = 60.0


def store_enabled(brain_root: Any = None) -> bool:
    """True when the store configuration is present, enabled and names a person. A configuration
    that cannot be read, has unknown keys, or is enabled without a person raises SecretStoreError
    (round-7 review): it is fatal, never the old vault in the store's place."""
    config = load_config(True, brain_root)
    if config["enabled"] and not config["person"]:
        raise SecretStoreError("the secrets-store configuration is enabled but names no person")
    return bool(config["enabled"])


def backend_if_enabled(brain_root: Any = None) -> "StoreBackend | None":
    return StoreBackend(brain_root=brain_root) if store_enabled(brain_root) else None


def team_configured(config: dict) -> bool:
    """The configuration names a team store: team_repo_url, or a team_clone holding a clone."""
    return bool(config.get("team_repo_url")) or (Path(config["team_clone"]) / ".git").is_dir()


def unbegun_message(entry: str, field: str) -> str:
    return (f"{entry}#{field}: a sign-in token is saved only inside a begun refresh (rotation_lock with "
            "refresh=True, leeway_seconds, or new_authorisation=True for a first sign-in); nothing was saved")


def put_grant_fields(st: Any, group: str, entry: str, fields: dict) -> None:
    """Grant fields (provider_profiles.grant_fields) go to the entry's grant, created with an
    empty sign-in when none exists yet; never to a static object."""
    names = oauth_ops.signin_fields(st, entry, group)
    if names:
        oauth_ops.set_grant_fields(st, oauth_ops.find(st, entry, names[0], group), fields)
    else:
        oauth_ops.put_signin(st, entry, oauth_ops.DEFAULT_FIELD, {}, fields, group=group)


class StoreBackend:
    def __init__(self, store: Any = None, sync_seconds: float = SYNC_SECONDS, team: Any = None,
                 brain_root: Any = None) -> None:
        if store is None:
            store = SecretStore(brain_root=brain_root)
            if team is None and team_configured(store.config):
                from .team import TeamStore
                team = TeamStore(brain_root=brain_root)
        self.store = store
        self.team = team  # a TeamStore, or None for the personal store alone
        self.sync_seconds = sync_seconds
        self._sync_errors: dict[int, str] = {}  # per store: the reason its last pull failed
        self._synced: float | None = None
        self._journal: Journal | None = None
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}  # journal key -> the begun refresh holding its lock
        self.refresh_timeout = REFRESH_TIMEOUT

    # -- plumbing ---------------------------------------------------------------------------
    def _stores(self) -> list:
        return [st for st in (self.store, self.team) if st is not None]

    @property
    def sync_error(self) -> str | None:
        return "; ".join(self._sync_errors[n] for n in sorted(self._sync_errors)) or None

    def _pull_all(self, tolerate: bool) -> None:
        """Open or pull every store. With tolerate, an unreachable or refused remote leaves reads
        on the last verified local state, and the reason is kept for status, per store: a later
        store's success never clears an earlier store's error."""
        for number, st in enumerate(self._stores()):
            if st.policy is None:
                try:
                    st.open()
                    self._sync_errors.pop(number, None)
                except SecretStoreError as error:  # a team store not reachable yet leaves the personal one
                    if st is self.store:
                        raise
                    if getattr(st, "not_created", False):  # retried at every operation until team-init ran
                        self._sync_errors.pop(number, None)
                        continue
                    if not tolerate:
                        raise
                    self._sync_errors[number] = str(error)
                continue
            try:
                st._sync(None, st.checkpoint)
                self._sync_errors.pop(number, None)
            except SecretStoreError as error:
                if not tolerate:
                    raise
                self._sync_errors[number] = str(error)
        self._synced = time.monotonic()

    def _ready(self) -> Any:
        if (any(st.policy is None for st in self._stores()) or self._synced is None
                or time.monotonic() - self._synced >= self.sync_seconds):
            self._pull_all(tolerate=True)
        if self._journal is None:
            self._journal = Journal(self.store.config["checkpoint_dir"], self.store._identity().x25519)
        self._discard_retired()
        return self.store

    def _discard_retired(self) -> None:
        """A deleted sign-in's old record is never held as uncertain (plan M2): the record of each
        exact retired grant is removed, at every operation and right after a pull."""
        from .replace_ops import discard_retired
        for st in self._stores():
            if st.policy is not None:
                discard_retired(st, self._journal)

    def status(self) -> dict[str, Any]:
        try:
            text = self.store.status()
        except SecretStoreError as error:
            text = str(error)
        out = {"backend": "store", "store": text}
        if getattr(self, "timer_error", None):
            out["package_timer"] = f"the last recovery-package check failed: {self.timer_error}"
        out["recovery_packages"] = {label: package_state(st) for label, st
                                    in (("personal", self.store), ("team", self.team)) if st is not None}
        if self.team is not None and self.team.policy is None and getattr(self.team, "not_created", False):
            out["team_store"] = ("not created yet: the team repository has no commit; after team-init this "
                                 "agent opens it at its next operation, without a restart")
        if self.sync_error:
            out["store_sync"] = f"the last pull failed, so reads use this computer's copy: {self.sync_error}"
        return out

    def package_tick(self) -> None:
        """The agent's timer (PackageTimer): pull every store, then rebuild a recovery package that is
        stale or does not match the current policy, with no credential request. A failure is kept on
        the store (status) and in its upkeep file (the daily due check) and retried at the next tick."""
        with self._lock:
            self._pull_all(tolerate=True)
            for number, st in enumerate(self._stores()):
                if st.policy is not None:
                    st._refresh_stale_package()
                    st.record_upkeep(self._sync_errors.get(number))

    def _groups(self, st: Any) -> list[str]:
        if st.group:
            return [st.group]
        person = st.config["person"]
        return sorted(g for g in st.policy.doc.get("groups", {}) if person in st.policy.members(g))

    def _route(self, entry: str) -> tuple[Any, str]:
        """(store, group) whose index holds entry, personal first."""
        found = []
        for st in (st for st in self._stores() if st.policy is not None):
            for group in self._groups(st):
                names = st._index(group)
                if entry in names or any(n.startswith(entry + "#") for n in names):
                    found.append((st, group))
        if len(found) > 1:
            raise SecretStoreError(f"{entry} is held in more than one store or group, so it is ambiguous; "
                                   "rename or remove one of them")
        return found[0] if found else (self.store, self.store._group(None))

    @staticmethod
    def _policy_disabled(st: Any) -> bool:
        person, computer = st.config["person"], st.config["computer"]
        return computer in st.policy.doc["people"].get(person, {}).get("disabled_refresher", [])

    @staticmethod
    def _hooks(st: Any, signin: oauth_ops.SignIn) -> tuple:
        return (lambda op, answer: oauth_ops.publish(st, signin, answer, op),
                lambda op, answer: oauth_ops.is_published(st, signin, op, answer))

    def _signin(self, st: Any, group: str, entry: str, field: str) -> oauth_ops.SignIn | None:
        signin = oauth_ops.find(st, entry, field, group)
        if signin is not None and signin.mine and f"{entry}#{field}" not in self._pending:
            self._journal.reconcile(signin.journal_key, *self._hooks(st, signin), disabled=self._policy_disabled(st))
        return signin

    @staticmethod
    def _static(st: Any, entry: str, group: str) -> dict:
        return st.get_record(entry, group) if entry in st._index(group) else {}

    # -- the broker operations --------------------------------------------------------------
    def get_fields(self, entry: str, fields: list[str]) -> dict[str, Any]:
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            static, out = self._static(st, entry, group), {}
            for field in fields:
                if field in provider_profiles.grant_fields():
                    out[field] = self._grant_field(st, group, entry, field, field in static)
                elif field in static:
                    out[field] = static[field]
                else:
                    signin = self._signin(st, group, entry, field)
                    out[field] = oauth_ops.read(st, signin) if signin else self._grant_field(st, group, entry, field)
            return out

    @staticmethod
    def _grant_field(st: Any, group: str, entry: str, field: str, in_static: bool = False) -> str:
        for name in oauth_ops.signin_fields(st, entry, group):
            signin = oauth_ops.find(st, entry, name, group)
            if not signin.mine:
                if field in provider_profiles.grant_fields():
                    oauth_ops.refuse_other(signin)
                continue
            found = oauth_ops.read_grant(st, signin).get("fields", {})
            if field in found:
                return found[field]
        if in_static:
            raise SecretStoreError(f"{entry}#{field} is a grant field kept in a plain entry, so it is not served; "
                                   "store it again with set_text on the computer that refreshes the sign-in")
        raise SecretStoreError(f"Credential field does not exist: {entry}#{field}")

    def get_json(self, entry: str, field: str) -> dict[str, Any]:
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            signin = self._signin(st, group, entry, field)
            if signin is not None:
                return oauth_ops.read(st, signin)
            text = self._static(st, entry, group).get(field)
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
            self._ready()
            value = oauth_ops.plain_numbers(value)
            if operation is not None:
                self._complete_refresh(entry, field, value, operation)
                return
            if f"{entry}#{field}" in self._pending:
                raise SecretStoreError(f"a refresh of {entry} is under way; only its own save may change the token")
            st, group = self._route(entry)
            signin = self._signin(st, group, entry, field)
            if signin is None:
                if oauth_ops.looks_like_signin(value):  # a first sign-in begins with new_authorisation
                    raise SecretStoreError(unbegun_message(entry, field))
                from .typed_write import write_typed  # a typed value: always its pending record (plan L4)
                write_typed(st, entry, {field: json.dumps(value, sort_keys=True)}, {field: "json"}, group=group)
                return
            if not signin.mine:
                oauth_ops.save_settings(st, signin, value)
                return
            current = oauth_ops.read(st, signin)
            watched = provider_profiles.token_fields(signin.provider) | provider_profiles.grant_fields(signin.provider)
            if any(k in value and value[k] != current.get(k) for k in watched):
                raise SecretStoreError(unbegun_message(entry, field))
            oauth_ops.save_settings(st, signin, value)

    def set_text(self, entry: str, field: str, value: str) -> None:
        """A text field; a grant field goes to the entry's grant, created when no sign-in exists yet."""
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            from .typed_write import write_typed  # a typed value: always its pending record (plan L4)
            if field not in provider_profiles.grant_fields():
                write_typed(st, entry, {field: value}, {field: "text"}, group=group)
                return
            write_typed(st, entry, grant={field: value}, group=group)

    def clear(self, entry: str, field: str) -> dict[str, bool]:
        """clear() on a stored sign-in: the refresher publishes a revision without the tokens;
        elsewhere it is refused. A plain JSON field is emptied as before."""
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            signin = self._signin(st, group, entry, field)
            if signin is None:
                self.set_json(entry, field, {})
                return {"cleared": True}
            if f"{entry}#{field}" in self._pending:
                raise SecretStoreError(f"a refresh of {entry} is under way; clear it once that ends")
            if not signin.mine:
                oauth_ops.clear_tokens(st, signin, "")
            with self._journal.lock(signin.journal_key):
                oauth_ops.clear_tokens(st, signin, oauth_ops.new_operation())
            return {"cleared": True}

    def sync(self) -> dict[str, bool]:
        """Pull every store now (PortableVaultJsonStore.sync); a failed pull is reported."""
        with self._lock:
            self._ready()
            self._pull_all(tolerate=False)
            self._discard_retired()
            return {"synced": True}

    # -- the refresh through the agent (section 9, refresh steps 1 to 7) --------------------
    def _pull(self, st: Any) -> None:
        st._sync(None, st.checkpoint)
        self._synced = time.monotonic()

    def begin_refresh(self, entry: str, field: str, new_authorisation: bool = False) -> dict[str, Any]:
        """Called only when a provider call is due. On the refresher: read the record, then take
        the per-entry lock, refuse a disabled or unresolved entry, write and flush the calling
        record; return its operation id and the full record. Elsewhere: the refresher's name and
        the latest published record, after a pull. No sign-in yet: with new_authorisation (a code
        exchange) an operation id for the first save, which creates the sign-in; else nothing.
        A sign-in whose record holds no token (grant text stored before the first browser sign-in,
        or cleared) counts as no sign-in yet unless this is a new authorisation, and a new
        authorisation writes no calling record: it never spends the stored grant, so a block that
        ends without a save leaves nothing uncertain."""
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            signin = self._signin(st, group, entry, field)
            key = f"{entry}#{field}"
            if signin is not None and not signin.mine:
                self._pull(st)
                return {"signin": True, "refresher": False, "computer": signin.refresher[1],
                        "record": oauth_ops.read(st, signin)}
            if signin is None and not new_authorisation:
                return {"signin": False}
            if key in self._pending:
                raise SecretStoreError(f"a refresh of {entry} is already under way on this computer; try again shortly")
            if signin is None:
                stack, begun, record = ExitStack(), {"operation": oauth_ops.new_operation()}, {}
            else:
                revision = st.checkpoint.objects[signin.oauth_id]["revision"]
                record = oauth_ops.read(st, signin)  # first: a failure to read never leaves a calling record
                if not new_authorisation and not oauth_ops.looks_like_signin(record):
                    return {"signin": False}  # no token yet: nothing to refresh, nothing journalled
                stack, begun = self._journal.begin(signin.journal_key, revision, signin.provider,
                                                   self._policy_disabled(st), write=not new_authorisation)
            timer = threading.Timer(self.refresh_timeout, self._expire, (key, begun["operation"]))
            timer.daemon = True
            self._pending[key] = {"stack": stack, "record": begun, "timer": timer, "signin": signin, "store": st,
                                  "group": group}
            timer.start()
            return {"signin": signin is not None, "refresher": True, "operation": begun["operation"],
                    "record": record}

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
            if held["signin"] is None:  # a first sign-in (new_authorisation): it is created now
                if oauth_ops.find(held["store"], entry, field, held["group"]) is not None:
                    raise SecretStoreError(f"{entry}#{field} was signed in elsewhere meanwhile; nothing was saved")
                oauth_ops.put_signin(held["store"], entry, field, value, group=held["group"])
                return
            publish = self._hooks(held["store"], held["signin"])[0]
            self._journal.complete(held["signin"].journal_key, held["record"], value, publish)
        finally:
            held["stack"].close()

    def abort_refresh(self, entry: str, field: str, operation: str) -> dict[str, bool]:
        """The provider was certainly not called (the token was already fresh, or the connector
        raised ProviderNotCalled, or ProviderRefused for a well-formed OAuth error answer): remove the
        calling record and release the lock."""
        with self._lock:
            held = self._take(f"{entry}#{field}", operation)
            if held is None:
                return {"aborted": False}
            try:
                if held["signin"] is None:
                    return {"aborted": True}
                return {"aborted": self._journal.abandon(held["signin"].journal_key, held["record"])}
            finally:
                held["stack"].close()

    def release_refresh(self, entry: str, field: str, operation: str) -> dict[str, bool]:
        """The connector's block raised after begin_refresh: the provider may have been called, so
        the record stays in calling (uncertain) and only the lock is released."""
        with self._lock:
            held = self._take(f"{entry}#{field}", operation)
            if held is not None:
                held["stack"].close()
            return {"released": held is not None}

    def poll_refresh(self, entry: str, field: str) -> dict[str, Any]:
        """The latest published record after a pull (another computer waiting for the refresher)."""
        with self._lock:
            self._ready()
            st, group = self._route(entry)
            self._pull(st)
            signin = self._signin(st, group, entry, field)
            if signin is None:
                raise SecretStoreError(f"there is no sign-in {entry}#{field}")
            return oauth_ops.read(st, signin)


class PackageTimer:
    """Runs StoreBackend.package_tick at least every PACKAGE_TIMER_SECONDS while the agent serves
    the store; the clock and the wait are injectable for tests."""

    def __init__(self, backend: Any, interval: float = PACKAGE_TIMER_SECONDS, clock: Any = time.monotonic) -> None:
        self.backend, self.interval, self.clock = backend, interval, clock
        self.last: float | None = None

    def tick(self) -> bool:
        """Run when due; an unexpected error is kept as the backend's timer_error, never raised."""
        if self.last is not None and self.clock() - self.last < self.interval:
            return False
        self.last = self.clock()
        try:
            self.backend.package_tick()
            self.backend.timer_error = None
        except Exception as error:  # noqa: BLE001 - the timer thread must survive to retry
            self.backend.timer_error = f"{type(error).__name__}: {error}"
        return True

    def run(self, stopped: Any, wait: Any = time.sleep, poll: float = PACKAGE_TIMER_POLL) -> None:
        while not stopped():
            self.tick()
            wait(min(poll, self.interval))


def package_state(st: Any) -> str:
    """One store's recovery package for status (round-8 review: every configured store)."""
    if getattr(st, "package_error", None):
        return f"failed: {st.package_error}; the timer retries, or run recovery-package"
    if st.policy is None:
        if getattr(st, "not_created", False):
            return "not created yet: no package until the store exists"
        return "not checked yet: the store is not open"
    try:
        fresh = st.package_fresh()
    except (OSError, SecretStoreError):
        fresh = False
    return "fresh" if fresh else "stale or missing; the timer rebuilds it"


def scrubbed(value: dict) -> dict:
    """A migrated sign-in without its tokens: access, refresh and every grant or token field."""
    drop = TOKEN_KEYS | provider_profiles.token_fields() | provider_profiles.grant_fields()
    return {k: v for k, v in value.items() if k not in drop}


def agent_operation(agent: Any, operation: str, request: dict) -> Any:
    """The Vault Agent operations answered here: vault-only ones and the store's refresh ones."""
    if operation in VAULT_OPS:
        import migration_lock  # round-9 plan, row M5

        locked = migration_lock.holder(agent.vault.path) is not None
        if operation in LOCKED_VAULT_OPS and not locked:
            migration_lock.require(agent.vault.path, operation)
        vault = type(agent.vault)(agent.vault.path, migration=True) if locked else agent.vault
        return vault_request(vault, agent._require_passphrase(), operation, request)
    if agent._store is None:
        raise SecretStoreError("the secrets store is off on this computer")
    if operation == "sync_store":
        return agent._store.sync()
    entry, field = str(request.get("entry") or ""), str(request.get("field") or oauth_ops.DEFAULT_FIELD)
    held = str(request.get("operation") or "")
    if operation == "begin_refresh":
        return agent._store.begin_refresh(entry, field, bool(request.get("new_authorisation")))
    if operation == "abort_refresh":
        return agent._store.abort_refresh(entry, field, held)
    if operation == "release_refresh":
        return agent._store.release_refresh(entry, field, held)
    if operation == "clear_signin":
        return agent._store.clear(entry, field)
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
        # the copy has the migration permission of the vault it was given: under a live lock only
        copy = type(vault)(path, migration=bool(getattr(vault, "_migration", False)))
        return sorted(copy.load(passphrase).get("entries") or {})
    if operation == "vault_get_fields":
        fields = request.get("fields")
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise SecretStoreError("fields must be a list of strings")
        return vault.get_fields(entry, fields, passphrase)
    if operation in ("vault_scrub_signin", "vault_restore_static", "vault_clear_migration_marker"):
        from portable_vault import migrated_signins, write_migration_marker
        marked = migrated_signins(vault.path)
        if operation == "vault_clear_migration_marker":  # the rollback, after its static secrets
            write_migration_marker(vault.path, {})
            return {"cleared": True}
        if operation == "vault_restore_static":  # never a sign-in: no token leaves the store
            values = request.get("values")
            if not isinstance(values, dict) or not values:
                raise SecretStoreError("values must be a non-empty object")
            fields = {}
            for field, item in values.items():
                value, kind = (item or {}).get("value"), (item or {}).get("kind")
                if (field in marked.get(entry, []) or kind not in ("text", "json")
                        or (kind == "json" and (not isinstance(value, dict) or oauth_ops.looks_like_signin(value)))
                        or (kind == "text" and not isinstance(value, str))):
                    raise SecretStoreError(f"{entry}#{field} is not a static secret; nothing was restored")
                fields[field] = (value, kind)
            vault.set_fields(entry, fields, passphrase)
            return {"restored": sorted(fields)}
        field = str(request.get("field") or "")  # the marker first: a stop before the scrub still refuses the copy
        write_migration_marker(vault.path, {**marked, entry: marked.get(entry, []) + [field]})
        value = vault.get(entry, field, passphrase)
        if isinstance(value, dict):
            vault.set(entry, field, scrubbed(value), "json", passphrase)
        return {"scrubbed": True}
    if operation == "vault_get_json":
        value = vault.get(entry, str(request.get("field") or ""), passphrase)
        if not isinstance(value, dict):
            raise SecretStoreError(f"Vault field must contain a JSON object: {entry}")
        return value
    raise SecretStoreError(f"unsupported vault operation {operation}")
