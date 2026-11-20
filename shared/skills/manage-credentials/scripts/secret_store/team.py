"""The team repository of the synced secrets store (design synced-secrets-repository.md, sections
5, 6 and 8): creation with the owner as first administrator and the team recovery key, groups,
admission after a team enrolment, group changes and removal. Every change is one administrator
commit judged by accept.py; messages name people, computers, groups and entries, never values."""

from __future__ import annotations

import subprocess
from typing import Any, Callable

from . import keys, recovery
from .errors import SecretStoreError
from .policy import INDEX_PREFIX, NAME, create_trust_root, public_entry
from .store import SecretStore, _default_words_window
from .store_ops import build_policy_change, safe_name

REPOSITORY_NAME = "brain-team-secrets"
_CHECKPOINT = "team-checkpoint.json"
_PIN = "team-trust-root.json"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True)


def create_team_repository(owner: str, gh: Callable[..., Any] | None = None) -> str:
    """gh repo create <org-or-login>/brain-team-secrets --private; returns the clone URL."""
    name = f"{safe_name(owner)}/{REPOSITORY_NAME}"
    if (gh or _gh)("repo", "create", name, "--private").returncode != 0:
        raise SecretStoreError(f"gh could not create the private repository {name}")
    return f"https://github.com/{name}.git"


class TeamStore(SecretStore):
    """The team repository: the same verified store, its own clone, pin and checkpoint, and a
    group named on every read and write."""
    team = True

    def __init__(self, use_config_file: bool = True, brain_root: Any = None, **overrides: Any) -> None:
        super().__init__(use_config_file, brain_root, **overrides)
        self.clone = self.config["team_clone"]
        self.checkpoint_path = self.config["checkpoint_dir"] / _CHECKPOINT
        self.pin_path = self.config["checkpoint_dir"] / _PIN
        self.group = None

    def _remote_url(self) -> str:
        url = self.config["team_repo_url"]
        if not url and (self.clone / ".git").is_dir():
            result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(self.clone), capture_output=True)
            url = result.stdout.decode().strip() if result.returncode == 0 else None
        if not url:
            raise SecretStoreError("no team repository is configured; run team-init or set team_repo_url")
        return url

    def _package_path(self):
        return self.config["recovery_package_dir"] / f"{REPOSITORY_NAME}-{self.config['person']}.package"

    def init_team(self, owner: str, remote_url: str | None = None,
                  words_callback: Callable[[list[str]], bool] | None = None,
                  gh: Callable[..., Any] | None = None) -> str:
        """Create the team repository: this computer's person is the first administrator; the
        team recovery words are shown once in the local window and endorse the trust root."""
        self._require_enabled()
        if self.checkpoint_path.exists() or (self.clone / ".git").exists():
            raise SecretStoreError("the team store is already set up on this computer")
        person, computer = self.config["person"], self.config["computer"]
        try:
            ident = self._identity()
        except SecretStoreError:
            x, e = keys.generate_key_pairs()
            keys.store_private_keys(person, computer, x, e)
            ident = self._identity()
        words = recovery.generate_mnemonic()
        if (words_callback or _default_words_window)(words.split()) is not True:
            raise SecretStoreError("the team recovery words were not confirmed as stored; nothing was set up")
        rx, re_ = recovery.derive_recovery_keys(words)
        del words
        remote_url = remote_url or self.config["team_repo_url"] or create_team_repository(owner, gh)
        people = {person: {"computers": {computer: public_entry(ident.x25519.public_key(), ident.ed25519.public_key())},
                           "disabled_refresher": []}}
        root = create_trust_root(people, public_entry(rx.public_key(), re_.public_key()), {}, [person],
                                 ident.ed25519, recovery_signer=re_)
        del rx, re_
        return self._publish(root, remote_url, "team_repo_url")


# -- administrator transactions -------------------------------------------------------------------
def _ready(store: SecretStore) -> SecretStore:
    if store.policy is None:
        store.open()
    return store


def _require_admin(store: SecretStore) -> None:
    if not store.policy.is_admin_key(keys.key_id(store._identity().ed25519.public_key())):
        raise SecretStoreError("only an administrator may change the policy")


def _transact(store: SecretStore, change: Callable[[dict], None]) -> None:
    """One commit: the policy change and a new revision of every object whose readers change."""
    _ready(store)

    def build() -> tuple[dict, str]:
        _require_admin(store)
        files = build_policy_change(store.policy, store.checkpoint.objects, change, store._identity().ed25519,
                                    lambda oid: store._open_object(store._tree_object(oid, store.checkpoint)))
        return files, "policy"
    store._write(build)


def _check_groups(doc: dict, groups: list[str]) -> None:
    unknown = [g for g in groups if g not in doc["groups"]]
    if unknown:
        raise SecretStoreError("no such group: " + ", ".join(unknown))


def create_groups(store: SecretStore, names: list[str]) -> None:
    def change(doc: dict) -> None:
        for name in names:
            if not isinstance(name, str) or not NAME.fullmatch(name) or name in doc["groups"]:
                raise SecretStoreError(f"group {name} is malformed or exists already")
            doc["groups"][name] = []
    _transact(store, change)


def set_groups(store: SecretStore, login: str, groups: list[str]) -> None:
    """Make login a member of exactly these groups; objects whose readers change are re-keyed."""
    def change(doc: dict) -> None:
        if login not in doc["people"]:
            raise SecretStoreError(f"{login} is not enrolled; enrol a computer of theirs first")
        _check_groups(doc, groups)
        for name, members in doc["groups"].items():
            if name in groups and login not in members:
                members.append(login)
            elif name not in groups and login in members:
                members.remove(login)
    _transact(store, change)


def admit(store: SecretStore, login: str, groups: list[str]) -> None:
    """Admit a person after their team enrolment: their first groups, in one commit."""
    doc = _ready(store).policy.doc
    if login not in doc["people"]:
        raise SecretStoreError(f"{login} has no enrolled computer; run the team enrolment first")
    if any(login in members for members in doc["groups"].values()):
        raise SecretStoreError(f"{login} is admitted already; change their groups instead")
    set_groups(store, login, groups)


def entry_names(store: SecretStore) -> dict[str, str]:
    """Object id -> entry name, from every index this computer can read."""
    names: dict[str, str] = {}
    for oid in store.checkpoint.objects:
        if oid.startswith(INDEX_PREFIX) and oid not in store.policy.doc["retired"]:
            try:
                index = store._open_object(store._tree_object(oid, store.checkpoint))
            except SecretStoreError:
                continue
            names.update({v: k for k, v in index["entries"].items()})
    return names


def remove(store: SecretStore, login: str, computer: str | None = None) -> list[str]:
    """Remove a person (computer None) or one computer: one commit re-keying everything they could
    read. Returns the entry names whose provider secrets must be changed."""
    policy = _ready(store).policy
    _require_admin(store)
    gone = {enc for (person, comp), (enc, _s) in policy.computers.items()
            if person == login and (computer is None or comp == computer)}
    if not gone:
        raise SecretStoreError(f"{login}{'/' + computer if computer else ''} is not in the policy")
    names = entry_names(store)
    exposed = sorted({names[oid] for oid in store.checkpoint.objects
                      if oid in names and gone & set(policy.readers_for(oid))})

    def change(doc: dict) -> None:
        for grant, r in doc["refreshers"].items():
            if r["person"] == login and (computer is None or r["computer"] == computer):
                raise SecretStoreError(f"{login} refreshes grant {grant}; move its refresher first")
        if computer is None:
            del doc["people"][login]
            for members in doc["groups"].values():
                if login in members:
                    members.remove(login)
            if login in doc["administrators"]:
                doc["administrators"].remove(login)
            if not doc["administrators"]:
                raise SecretStoreError("removing the last administrator is refused")
        else:
            record = doc["people"][login]
            del record["computers"][computer]
            if computer in record["disabled_refresher"]:
                record["disabled_refresher"].remove(computer)
    _transact(store, change)
    return exposed
