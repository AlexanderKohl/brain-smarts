"""The personal secrets store (design synced-secrets-repository.md, sections 5 to 9): one person's
private repository, read and written through verified commits only. Messages name entries and
fields, never values, keys or recovery words."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from . import canonical, checkpoint, keys, recovery, recovery_package, signing
from .accept import accept_commit
from .errors import SecretStoreError
from .policy import (INDEX_PREFIX, Policy, check_endorsement, create_trust_root, fingerprint, load_trust_root,
                     object_hash, public_entry)
from .repo import Conflict, MovedHead, SecretRepo
from .store_ops import (EMPTY_JSON, GROUP, INDEX_ID, build_delete, build_put, checkpoint_commit, load_config,
                        marker_current, store_status, write_marker)

RETRIES = 3
PACKAGE_MAX_AGE = 7 * 24 * 3600
_CHECKPOINT = "personal-checkpoint.json"
_PIN = "personal-trust-root.json"


@dataclass
class Identity:
    person: str | None
    computer: str
    x25519: X25519PrivateKey
    ed25519: Ed25519PrivateKey

    def my_keys(self) -> dict[str, X25519PrivateKey]:
        return {keys.key_id(self.x25519.public_key()): self.x25519}


def _default_words_window(words: list[str]) -> bool:
    from secret_window import show_recovery_words  # the scripts folder is on sys.path for the CLI
    return show_recovery_words(words)


class SecretStore:
    team = False

    def __init__(self, use_config_file: bool = True, brain_root: Any = None, **overrides: Any) -> None:
        self.config = load_config(use_config_file, brain_root, **overrides)
        self.clone = self.config["personal_clone"]
        self.checkpoint_path = self.config["checkpoint_dir"] / _CHECKPOINT
        self.pin_path = self.config["checkpoint_dir"] / _PIN
        self.identity: Identity | None = None
        self.policy: Policy | None = None
        self.checkpoint: checkpoint.Checkpoint | None = None
        self.repo: SecretRepo | None = None
        self.group: str | None = GROUP
        self.unusable: set[str] = set()  # accepted but not usable here: never served, never a baseline

    # -- setup --------------------------------------------------------------------------------
    def _require_enabled(self) -> None:
        if not self.config["enabled"] or not self.config["person"]:
            raise SecretStoreError("the secrets store is off on this computer (no configuration with a person)")

    def _remote_url(self) -> str:
        url = self.config["personal_repo_url"]
        if not url and (self.clone / ".git").is_dir():
            result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(self.clone), capture_output=True)
            url = result.stdout.decode().strip() if result.returncode == 0 else None
        if not url:
            raise SecretStoreError("no personal repository is configured; run init first")
        return url

    def _identity(self) -> Identity:
        if self.identity is None:
            x, e = keys.load_private_keys(self.config["person"], self.config["computer"])
            self.identity = Identity(self.config["person"], self.config["computer"], x, e)
        return self.identity

    @staticmethod
    def _github_repository() -> str:
        """Create <login>/brain-secrets as a private repository, or reuse it when it is empty."""
        def gh(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["gh", *args], capture_output=True)
        login = gh("api", "user", "--jq", ".login")
        if login.returncode != 0 or not login.stdout.strip():
            raise SecretStoreError("GitHub sign-in through gh is needed first (gh auth login)")
        name = login.stdout.decode().strip() + "/brain-secrets"
        view = gh("repo", "view", name, "--json", "isEmpty", "--jq", ".isEmpty")
        if view.returncode == 0:
            if view.stdout.decode().strip() != "true":
                raise SecretStoreError(f"{name} already exists and is not empty; refusing to set it up again")
        elif gh("repo", "create", name, "--private").returncode != 0:
            raise SecretStoreError(f"gh could not create the private repository {name}")
        return f"https://github.com/{name}.git"

    def init_personal(self, remote_url: str | None = None,
                      words_callback: Callable[[list[str]], bool] | None = None) -> str:
        """First computer: keys, words, trust root, first commit, checkpoint, package; returns the fingerprint."""
        self._require_enabled()
        if self.checkpoint_path.exists() or (self.clone / ".git").exists():
            raise SecretStoreError("the secrets store is already set up on this computer")
        person, computer = self.config["person"], self.config["computer"]
        x, e = keys.generate_key_pairs()
        words = recovery.generate_mnemonic()
        if (words_callback or _default_words_window)(words.split()) is not True:
            raise SecretStoreError("the recovery words were not confirmed as stored; nothing was set up")
        rx, re_ = recovery.derive_recovery_keys(words)
        del words
        remote_url = remote_url or self.config["personal_repo_url"] or self._github_repository()
        keys.store_private_keys(person, computer, x, e)
        self.identity = Identity(person, computer, x, e)
        people = {person: {"computers": {computer: public_entry(x.public_key(), e.public_key())},
                           "disabled_refresher": []}}
        root = create_trust_root(people, public_entry(rx.public_key(), re_.public_key()),
                                 {GROUP: [person]}, [person], e, recovery_signer=re_)
        return self._publish(root, remote_url, "personal_repo_url")

    def _publish(self, root: dict, remote_url: str, url_key: str) -> str:
        """First commit of a new repository: the trust root; then pin, checkpoint and package."""
        self.config[url_key] = remote_url
        self.repo = SecretRepo(self.clone, remote_url).clone_or_open()
        if self.repo.head() is not None:
            raise SecretStoreError("the repository is not empty; refusing to set it up again")
        if isinstance(self.repo.write({"policy.json": root}, "policy"), Conflict):
            raise SecretStoreError("the repository changed during setup; nothing was set up")
        pinned = fingerprint(root)
        self.policy = load_trust_root(root, pinned)
        self._save_pin(pinned)
        self.checkpoint = checkpoint.initial(self.policy)
        self._save_checkpoint(self.checkpoint)
        self.refresh_recovery_package(force=True)
        return pinned

    # -- pins and checkpoints -----------------------------------------------------------------
    def _save_pin(self, pinned: str) -> None:
        signer = self._identity().ed25519
        doc = signing.sign({"type": "pin", "fingerprint": pinned, "writer": keys.key_id(signer.public_key())}, signer)
        self.pin_path.parent.mkdir(parents=True, exist_ok=True)
        self.pin_path.write_bytes(canonical.dumps(doc))

    def _load_pin(self) -> str | None:
        if not self.pin_path.exists():
            return None
        doc = canonical.loads(self.pin_path.read_bytes())
        signing.verify(doc, self._identity().ed25519.public_key())
        return doc["fingerprint"]

    def _save_checkpoint(self, cp: checkpoint.Checkpoint) -> None:
        checkpoint.save(self.checkpoint_path, cp, self._identity().ed25519, clone_root=self.clone)

    def _load_checkpoint(self) -> checkpoint.Checkpoint | None:
        if not self.checkpoint_path.exists():
            return None
        return checkpoint.load(self.checkpoint_path, self._identity().ed25519.public_key())

    # -- verified sync ------------------------------------------------------------------------
    def _tree_object(self, oid: str, cp: checkpoint.Checkpoint) -> dict:
        """The clone's file for oid, refused unless its hash is the checkpoint's."""
        obj = self.repo.read(f"objects/{oid}.json")
        if oid not in cp.objects or object_hash(obj) != cp.objects[oid]["hash"]:
            raise SecretStoreError(f"object {oid} in the local copy does not match the checkpoint")
        return obj

    def _baseline(self, cp: checkpoint.Checkpoint, files: dict) -> dict:
        """Latest verified payloads of oauth objects a commit changes (the field-rule baseline)."""
        out = {}
        for path, value in files.items():
            oid = path[len("objects/"):-len(".json")] if path.startswith("objects/") else None
            if (oid and isinstance(value, dict) and value.get("kind") == "oauth" and oid in cp.objects
                    and oid not in self.unusable):
                previous = self._tree_object(oid, cp)
                if any(r["key"] in self._identity().my_keys() for r in previous["readers"]):
                    out[oid] = self._open_object(previous)  # else opaque: structural checks only
        return out

    def _from_tree(self, saved: checkpoint.Checkpoint | None, retry: bool = True) -> Policy:
        if saved is None:
            raise SecretStoreError("this computer has a local copy but no checkpoint; move the copy aside and open again")
        try:
            doc = self.repo.read("policy.json")
            if object_hash(doc) != saved.policy_hash:
                raise SecretStoreError("the local copy does not match this computer's checkpoint")
            for oid in saved.objects:
                self._tree_object(oid, saved)
            return Policy(doc)
        except (SecretStoreError, OSError, ValueError):
            if retry is False:
                raise
        commit = checkpoint_commit(self.repo, saved)  # after a crash; pull re-verifies later commits
        if commit is None:  # the checkpoint is ahead of the clone
            raise SecretStoreError("this computer's checkpoint is ahead of its local copy; refusing to use the copy")
        self.repo.reset_to(commit)
        return self._from_tree(saved, retry=False)

    def _sync(self, pinned: Any, saved: checkpoint.Checkpoint | None) -> None:
        """Pull, verifying every new commit with accept_commit; save the checkpoint after each
        accepted commit once it has caught up with the saved one. Refusal stops the store."""
        state = {"policy": self.policy, "cp": self.checkpoint, "caught": saved is None or self.checkpoint is not None}

        def verify(_commit: str, files: dict) -> bool:
            if state["policy"] is None:
                if set(files) != {"policy.json"} or pinned is None:
                    raise SecretStoreError("the first commit is not a trust root this computer can pin")
                doc = files["policy.json"]
                root = load_trust_root(doc, pinned(doc) if callable(pinned) else pinned)
                state["policy"], state["cp"] = root, checkpoint.initial(root)
            else:
                accepted = accept_commit(state["policy"], state["cp"], files, self._identity().my_keys(),
                                         self._baseline(state["cp"], files))
                state["policy"], state["cp"] = accepted.policy, accepted.checkpoint
                self._note_usable(accepted)
            return True

        def advanced(_commit: str) -> None:  # after the clone moved, so the checkpoint never leads it
            if not state["caught"]:
                try:
                    checkpoint.advance(saved, state["cp"])
                    state["caught"] = True
                except SecretStoreError:
                    return
            self._save_checkpoint(state["cp"])

        try:
            self.repo.pull(verify, advanced)
        finally:
            self.policy, self.checkpoint = state["policy"], state["cp"]
        if self.policy is None:
            raise SecretStoreError("the personal repository is empty; run init first")
        if not state["caught"]:
            raise SecretStoreError("the repository is older than this computer's checkpoint; refusing to use it")

    def open(self, fingerprint_to_pin: str | None = None) -> "SecretStore":
        """Pull and verify; a first open here needs the trust root fingerprint."""
        self._require_enabled()
        self._identity()
        self.repo = SecretRepo(self.clone, self._remote_url()).clone_or_open()
        saved = self._load_checkpoint()
        pinned = self._load_pin()
        if pinned is None and fingerprint_to_pin:
            pinned = "".join(fingerprint_to_pin.split()).lower()
        self.policy, self.checkpoint = None, None
        with self.repo.lock():
            if self.repo.head() is not None:
                self.policy, self.checkpoint = self._from_tree(saved), saved
            self._sync(pinned, saved)
        if not self.pin_path.exists() and pinned:
            self._save_pin(pinned)
        return self

    @classmethod
    def restore_from_package(cls, words: str, package_path: Any, folder: Any,
                             fingerprint_to_pin: str | None = None) -> "SecretStore":
        """Recover into an empty folder from the words and a package; every commit is verified again."""
        rx, re_ = recovery.derive_recovery_keys(words)
        folder = Path(folder)
        history = folder / "restored-history"
        package_cp = recovery_package.restore(package_path, rx, history, re_.public_key())
        store = cls(use_config_file=False, enabled=True, person="recovery", computer="recovery",
                    personal_clone=folder / "brain-secrets", checkpoint_dir=folder / "checkpoint",
                    recovery_package_dir=folder / "recovery-packages", personal_repo_url=str(history))
        store.identity = Identity(None, "recovery", rx, re_)
        mine = public_entry(rx.public_key(), re_.public_key())

        def pin(doc: dict) -> str:
            check_endorsement(doc, re_.public_key())  # a trust root the recovery key never endorsed is refused
            if fingerprint_to_pin:
                return fingerprint_to_pin
            if doc.get("recovery") != mine:
                raise SecretStoreError("the trust root does not name this recovery key")
            return fingerprint(doc)

        doc = canonical.loads(package_cp)
        saved = checkpoint.Checkpoint.from_doc({k: v for k, v in doc.items() if k not in ("writer", "signature")})
        store.repo = SecretRepo(store.clone, str(history)).clone_or_open()
        store._sync(pin, saved)
        store.policy.verify(doc, doc.get("writer"))  # the package checkpoint was signed by a listed key
        return store

    # -- reading ------------------------------------------------------------------------------
    def _ready(self) -> None:
        if self.policy is None or self.checkpoint is None:
            raise SecretStoreError("the secrets store is not open")

    def _open_object(self, obj: dict) -> dict:
        from . import envelope
        mine = [r["key"] for r in obj["readers"] if r["key"] in self._identity().my_keys()]
        if not mine:
            raise SecretStoreError(f"this computer is not a reader of object {obj.get('id')}")
        return envelope.open_(obj, mine[0], self._identity().my_keys()[mine[0]])

    def _note_usable(self, accepted: Any) -> None:  # e.g. a superseded grant waits for its new revision
        self.unusable = (self.unusable | {o for o, i in accepted.objects.items() if i.payload is not None and not i.usable}
                         ) - {o for o, i in accepted.objects.items() if i.payload is None or i.usable}

    def _group(self, group: str | None) -> str:
        if not (group or self.group):
            raise SecretStoreError("name a group")
        return group or self.group

    def _index(self, group: str | None = None) -> dict[str, str]:
        self._ready()
        index_id = INDEX_PREFIX + self._group(group)
        if index_id not in self.checkpoint.objects:
            return {}
        return dict(self._open_object(self._tree_object(index_id, self.checkpoint))["entries"])

    def list_entries(self, group: str | None = None) -> list[str]:
        return sorted(self._index(group))

    def get_record(self, entry_name: str, group: str | None = None) -> dict[str, str]:
        oid = self._index(group).get(entry_name)
        if oid is None:
            raise SecretStoreError(f"there is no entry {entry_name}")
        obj = self._tree_object(oid, self.checkpoint)
        if oid in self.unusable or sorted(r["key"] for r in obj["readers"]) != self.policy.readers_for(oid):
            raise SecretStoreError(f"entry {entry_name} is not usable yet: it waits for a verified new revision")
        return self._open_object(obj)

    def get_fields(self, entry_name: str, fields: list[str], group: str | None = None) -> dict[str, str]:
        record = self.get_record(entry_name, group)
        missing = [f for f in fields if f not in record]
        if missing:
            raise SecretStoreError(f"entry {entry_name} has no field " + ", ".join(missing))
        return {f: record[f] for f in fields}

    # -- writing ------------------------------------------------------------------------------
    def _write(self, build: Callable[[], tuple[dict, str]]) -> None:
        self._ready()  # one repository lock spans sync, build, verify, commit, push and checkpoint
        with self.repo.lock():
            for _attempt in range(1 + RETRIES):
                self._sync(None, self.checkpoint)
                files, message = build()
                baseline, before = self._baseline(self.checkpoint, files), self.repo.head()
                accepted = accept_commit(self.policy, self.checkpoint, files, self._identity().my_keys(), baseline)
                try:
                    written = self.repo.write(files, message, expected_parent=before)
                except SecretStoreError as error:
                    if isinstance(error, MovedHead):  # else a lost acknowledgement: settle it with the remote
                        raise
                    written = self.repo.settle_failed_write(before)
                    if written is None:
                        raise
                    accepted = accept_commit(self.policy, self.checkpoint, self.repo._changed_files(written),
                                             self._identity().my_keys(), baseline)
                if isinstance(written, Conflict):
                    continue
                self._save_checkpoint(accepted.checkpoint)
                self.policy, self.checkpoint = accepted.policy, accepted.checkpoint
                self._note_usable(accepted)
                if "policy.json" in files:
                    self.refresh_recovery_package()
                return
        raise SecretStoreError("the personal repository kept changing; the change was not saved, try again")

    def put_entry(self, entry_name: str, fields: dict[str, str], kind: str = "static",
                  group: str | None = None) -> None:
        """Store fields in entry_name: a new entry, or the next revision with these fields changed."""
        if not isinstance(entry_name, str) or not entry_name.strip():
            raise SecretStoreError("an entry needs a name")
        if not fields or not all(isinstance(k, str) and k and isinstance(v, str) for k, v in fields.items()):
            raise SecretStoreError("fields must be named text values")

        def build() -> tuple[dict, str]:
            index = self._index(group)
            payload = self.get_record(entry_name, group) if entry_name in index else {}
            payload.update(fields)
            return build_put(self.policy, self.checkpoint.objects, index, entry_name, payload, kind,
                             self._identity().ed25519, self._group(group))
        self._write(build)

    def delete_entry(self, entry_name: str, group: str | None = None) -> None:
        self._write(lambda: build_delete(self.policy, self.checkpoint.objects, self._index(group), entry_name,
                                         self._identity().ed25519))

    # -- recovery package and status ----------------------------------------------------------
    def _package_path(self) -> Path:
        return self.config["recovery_package_dir"] / f"brain-secrets-{self.config['person']}.package"

    def refresh_recovery_package(self, force: bool = False) -> Path:
        """Write the package when it is older than seven days or the policy changed since."""
        self._ready()
        path = self._package_path()
        marker = path.with_name(path.name + ".policy")
        current = (path.exists() and time.time() - path.stat().st_mtime < PACKAGE_MAX_AGE
                   and marker_current(marker, path, self.policy.hash, self._identity().ed25519.public_key()))
        if current and not force:
            return path
        recovery_public = self.policy.enc_keys[self.policy.recovery[0]]
        recovery_package.build(self.repo, self.checkpoint_path.read_bytes(), recovery_public, path)
        write_marker(marker, path, self.policy.hash, self._identity().ed25519)
        return path

    def status(self) -> str:
        return store_status(self)

__all__ = ["SecretStore", "Identity", "EMPTY_JSON"]
