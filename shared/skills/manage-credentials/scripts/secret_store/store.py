"""The personal secrets store (design synced-secrets-repository.md, sections 5 to 9): one person's
private repository, read and written through verified commits only. Messages name entries and
fields, never values, keys or recovery words."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from . import canonical, checkpoint, keys, provider_profiles, recovery, recovery_package, signing, static_fields
from .accept import accept_commit
from .accept_rules import RuleRefusal, coded
from .delete_ops import build_delete
from .errors import IntegrityError, SecretStoreError
from .policy import (INDEX_PREFIX, Policy, check_endorsement, create_trust_root, fingerprint, load_trust_root,
                     object_hash, public_entry)
from .repo import Conflict, MovedHead, RefusedCommit, SecretRepo
from .store_ops import (EMPTY_JSON, GROUP, INDEX_ID, build_put, checkpoint_commit, load_config,
                        not_enrolled_message,
                        marker_current, store_status, write_marker)

RETRIES = 3
PACKAGE_MAX_AGE = 7 * 24 * 3600
PACKAGE_CHECK_SECONDS = 24 * 3600


def _in_transaction() -> bool:
    """True while this thread holds a repository lock: the package is never built inside one."""
    from .repo import _HELD
    return any(n and k[1] == threading.get_ident() for k, n in _HELD.items())
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
    _head: str | None = None  # the clone commit the held policy and checkpoint describe
    _pinned: str | None = None  # the trust-root pin this instance verified at open
    _syncing = False  # a pull is saving checkpoints ahead of the held one: nothing to follow
    not_created = False  # the last open found the repository with no commit and no checkpoint here

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
        self._head, self._pinned = self.repo.head(), pinned
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
    def _tree_object(self, oid: str, cp: checkpoint.Checkpoint, at: str | None = None,
                     follow: bool = True) -> dict:
        """The clone's file for oid (or its version at commit at), refused unless its hash is the
        checkpoint's. A mismatch against the held checkpoint first follows a newer checkpoint that
        another process on this computer wrote meanwhile, or settles an unfinished write it left
        in the clone (_follow), then checks once again."""
        path = f"objects/{oid}.json"
        obj = self.repo.read(path) if at is None else self.repo.read_at(at, path)
        if oid in cp.objects and obj is not None and object_hash(obj) == cp.objects[oid]["hash"]:
            return obj
        if follow and at is None and cp is self.checkpoint and not self._syncing:
            self._follow(clone=True)
            return self._tree_object(oid, self.checkpoint, follow=False)
        raise IntegrityError(f"object {oid} in the local copy does not match the checkpoint")

    def _follow(self, clone: bool = False) -> None:
        """Plan section G: another process on this computer (brain_secrets.py beside the Vault
        Agent) may have written through the same clone and checkpoint folder. Under the
        repository lock, a checkpoint on disk that is not the held one is verified as at open
        (signature, pin) and taken only when it follows from the held one; the commits between
        the held state and the clone are verified one by one (accept_commit, the policy chain)
        and the local copy is checked against the result. A refusal writes nothing and leaves the
        held state as it was. With clone, a clone moved past the held commit is looked at while the
        checkpoint on disk is still the held one; that git call is made only there, not on every read.

        Plan section J: a writer saves its checkpoint only after its push, so commits up to the
        checkpoint on disk are confirmed. A commit past it is followed only when the fetched remote
        branch holds it (the writer pushed and stopped before its checkpoint). Any other commit past
        it is an unfinished write (a crash before the push: under the lock no writer is mid-write)
        and is settled by the store's own path for a failed write, settle_failed_write, which drops
        it from the clone, offline too. It is never followed or checkpointed; a refresh answer it
        held stays in the journal as answered, and the next write publishes it.

        Every failure raised here of its own (a checkpoint on disk older, forked, another
        repository's or not verifying; the pin changed or not verifying; the checkpoint ahead of the
        local copy; the local copy not matching; an unfinished write not settled) is an
        IntegrityError with its message; RefusedCommit and MovedHead stay what they are."""
        if self.policy is None or self.checkpoint is None or self.repo is None or self._syncing:
            return
        with self.repo.lock():
            try:
                self._follow_locked(clone)
            except (IntegrityError, RefusedCommit, MovedHead):
                raise
            except SecretStoreError as error:
                raise IntegrityError(str(error)) from None

    def _follow_locked(self, clone: bool) -> None:
        disk = self._load_checkpoint() if self.checkpoint_path.exists() else None
        if disk is None or disk == self.checkpoint:
            if not clone or self.repo.head() == self._head:
                return
            disk = self.checkpoint
        checkpoint.advance(self.checkpoint, disk)  # older, forked or another repository: refused
        if self._load_pin() != self._pinned:
            raise SecretStoreError("this computer's trust-root pin changed while the store was open; open it again")
        policy, cp, previous, accepted_all = self.policy, self.checkpoint, self._head, []
        confirmed = False  # the commits past the checkpoint on disk are on the remote
        for commit in self.repo.local_commits(self._head):
            if cp == disk and not confirmed:
                if not self._settle_unfinished(previous):
                    break  # dropped back to previous: nothing past the checkpoint is followed
                confirmed = True
            try:
                files = self.repo._changed_files(commit)
                accepted = accept_commit(policy, cp, files, self._identity().my_keys(),
                                         self._baseline(cp, files, at=previous))
            except Exception as error:  # noqa: BLE001 - plan section L: a fixed code, never the text
                raise RefusedCommit(commit, getattr(error, "code", None),
                                    self._safe_oid(error, policy, cp)) from None
            policy, cp, previous = accepted.policy, accepted.checkpoint, commit
            accepted_all.append(accepted)
        try:
            checkpoint.advance(disk, cp)
        except SecretStoreError:
            raise SecretStoreError("this computer's checkpoint is ahead of its local copy; "
                                   "refusing to use the copy") from None
        if object_hash(self.repo.read("policy.json")) != cp.policy_hash:
            raise SecretStoreError("the local copy does not match this computer's checkpoint")
        for oid in cp.objects:
            self._tree_object(oid, cp)  # the tamper check, against the reloaded checkpoint
        if cp != disk:  # the other process stopped between its push and its checkpoint
            self._save_checkpoint(cp)
        self.policy, self.checkpoint, self._head = policy, cp, previous
        for accepted in accepted_all:
            self._note_usable(accepted)

    def _settle_unfinished(self, confirmed: str) -> bool:
        """The clone has commits past confirmed (the commit of the checkpoint on disk). True when
        the fetched remote branch holds the clone's HEAD; else settle_failed_write has dropped
        them back to confirmed and the caller follows nothing past it. Called under the lock."""
        try:
            return self.repo.settle_failed_write(confirmed) is not None
        except SecretStoreError:
            raise SecretStoreError("an unfinished write is in this computer's local copy and could not be "
                                   "settled; nothing was followed from it, try again") from None

    @staticmethod
    def _safe_oid(error: BaseException, policy: Policy | None, cp: checkpoint.Checkpoint | None) -> str | None:
        """The object id of a refusal, only when the store already holds it (an id in the verified
        checkpoint or policy); an id a commit made up is never shown."""
        oid = getattr(error, "oid", None)
        known = set(cp.objects) if cp is not None else set()
        if policy is not None:
            known |= set(policy.doc.get("assignments", {})) | set(policy.doc.get("retired", {}))
        return oid if isinstance(oid, str) and oid in known else None

    def _baseline(self, cp: checkpoint.Checkpoint, files: dict, at: str | None = None) -> dict:
        """Latest verified payloads of oauth objects a commit changes (the field-rule baseline)."""
        out = {}
        for path, value in files.items():
            oid = path[len("objects/"):-len(".json")] if path.startswith("objects/") else None
            if (oid and isinstance(value, dict) and value.get("kind") == "oauth" and oid in cp.objects
                    and oid not in self.unusable):
                previous = self._tree_object(oid, cp, at)
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
        accepted commit once it has caught up with the saved one. Refusal stops the store. One
        repository lock covers following another process's checkpoint and the pull."""
        with self.repo.lock():
            self._follow(clone=True)
            self._sync_locked(pinned, saved)
            from .typed_write import replay
            replay(self)  # pending-write records left by a process that died (plan sections L2, L4)

    def _sync_locked(self, pinned: Any, saved: checkpoint.Checkpoint | None) -> None:
        if self.policy is None and saved is None and pinned is None and self.repo._fetch() is not None:
            # Plan section I: a computer never enrolled here meets a trust root it cannot pin. Said
            # plainly before any commit is judged, and nothing is marked refused in the clone.
            raise SecretStoreError(not_enrolled_message(self))
        state = {"policy": self.policy, "cp": self.checkpoint, "caught": saved is None or self.checkpoint is not None}

        def verify(_commit: str, files: dict) -> bool:
            try:
                return check(files)
            except SecretStoreError as error:  # plan section L: an object id only when it is the store's own
                error.safe_oid = self._safe_oid(error, state["policy"], state["cp"])
                raise

        def check(files: dict) -> bool:
            if state["policy"] is None:
                if set(files) != {"policy.json"} or pinned is None:
                    raise RuleRefusal("the first commit is not a trust root this computer can pin", "trust-root")
                doc = files["policy.json"]
                with coded("trust-root"):
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

        self._syncing = True
        try:
            self.repo.pull(verify, advanced)
        finally:
            self.policy, self.checkpoint = state["policy"], state["cp"]
            self._head, self._syncing = self.repo.head(), False
        if self.policy is None:  # the remote has no commit; with no checkpoint here it was never set up
            self.not_created = saved is None
            raise SecretStoreError("the team repository is empty; run team-init first" if self.team
                                   else "the personal repository is empty; run init first")
        self.not_created = False
        if not state["caught"]:
            raise SecretStoreError("the repository is older than this computer's checkpoint; refusing to use it")

    def open(self, fingerprint_to_pin: str | None = None) -> "SecretStore":
        """Pull and verify; a first open here needs the trust root fingerprint."""
        self._require_enabled()
        self.not_created = False
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
            self._head, self._pinned = self.repo.head(), pinned
            self._sync(pinned, saved)
        if not self.pin_path.exists() and pinned:
            self._save_pin(pinned)
        self._refresh_stale_package()  # after the transaction, never inside it
        return self

    def _refresh_stale_package(self) -> None:
        """A package on this computer that is missing or older than seven days is rebuilt when the
        store opens, and on the first use after each day the store stays open (a Vault Agent
        running for weeks); a failure (an offline cloud drive) never stops the operation and shows
        in status."""
        self._package_checked = time.time()
        if self.policy is None:
            return
        self._package_policy = self.policy.hash
        if self.package_fresh():
            self.package_error = None
            return
        self._package_upkeep()

    def package_fresh(self) -> bool:
        """Under seven days old and its signed marker names the current policy and the package."""
        path = self._package_path()
        marker = path.with_name(path.name + ".policy")
        return (self.policy is not None and path.exists() and time.time() - path.stat().st_mtime < PACKAGE_MAX_AGE
                and marker_current(marker, path, self.policy.hash, self._identity().ed25519.public_key()))

    def _package_upkeep(self) -> None:
        """refresh_recovery_package after a saved change or on schedule; a failure is kept as a
        warning (package_error, shown by status and the command line), never raised."""
        self._package_checked = time.time()
        self._package_busy = True
        try:
            self.refresh_recovery_package()
            self.package_error = None
        except (OSError, SecretStoreError) as error:
            self.package_error = (f"the recovery package could not be written ({type(error).__name__}); "
                                  "the change itself was saved")
        finally:
            self._package_busy = False
            self.record_upkeep()

    def record_upkeep(self, pull_error: str | None = None) -> None:
        """Keep the last upkeep failure (or clear it) where the daily due check reads it."""
        from .store_ops import write_upkeep_error

        problems = [self.package_error] if getattr(self, "package_error", None) else []
        if pull_error:
            problems.append(f"the last pull failed: {pull_error}")
        write_upkeep_error(self.config, self._package_path(), "; ".join(problems) or None)

    @classmethod
    def restore_from_package(cls, words: str, package_path: Any, folder: Any,
                             fingerprint_to_pin: str | None = None) -> "SecretStore":
        """Recover into an empty folder from the words and a package; every commit is verified again."""
        rx, re_ = recovery.derive_recovery_keys(words)
        folder = Path(folder)
        history = folder / "restored-history"
        package_cp = recovery_package.restore(package_path, rx, history, re_.public_key())
        if cls.team:  # the team target: team clone, team checkpoint and pin, never the personal paths
            paths = {"team_clone": folder / "brain-team-secrets", "team_repo_url": str(history),
                     "personal_clone": folder / "unused-personal"}
        else:
            paths = {"personal_clone": folder / "brain-secrets", "personal_repo_url": str(history),
                     "team_clone": folder / "unused-team"}
        store = cls(use_config_file=False, enabled=True, person="recovery", computer="recovery",
                    checkpoint_dir=folder / "checkpoint", recovery_package_dir=folder / "recovery-packages", **paths)
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
        self._follow()  # another process on this computer may have written since (plan section G)
        checked = getattr(self, "_package_checked", None)
        if checked is None or _in_transaction() or getattr(self, "_package_busy", False):
            return
        # A failed write is retried at the next use, a changed policy (a pull) is checked at once,
        # and the age check runs daily while the store stays open.
        if (getattr(self, "package_error", None) or getattr(self, "_package_policy", None) != self.policy.hash
                or time.time() - checked >= PACKAGE_CHECK_SECONDS):
            self._refresh_stale_package()

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

    def _payload(self, entry_name: str, group: str | None = None) -> tuple[dict, bool]:
        oid = self._index(group).get(entry_name)
        if oid is None:
            raise SecretStoreError(f"there is no entry {entry_name}")
        obj = self._tree_object(oid, self.checkpoint)
        if oid in self.unusable or sorted(r["key"] for r in obj["readers"]) != self.policy.readers_for(oid):
            raise SecretStoreError(f"entry {entry_name} is not usable yet: it waits for a verified new revision")
        return self._open_object(obj), self.policy.assignment(oid)[1] == "static"

    def get_record(self, entry_name: str, group: str | None = None) -> dict[str, str]:
        payload, static = self._payload(entry_name, group)
        return static_fields.split(payload)[0] if static else payload

    def get_typed(self, entry_name: str, group: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
        """(values, kinds) of a static entry (plan N2); kinds lacks fields written before kinds were kept."""
        payload, static = self._payload(entry_name, group)
        if not static:
            raise SecretStoreError(f"entry {entry_name} is not a plain entry")
        return static_fields.split(payload)

    def static_payload(self, entry_name: str, group: str | None = None) -> dict | None:
        """The raw payload of a static entry for a partial update, or None when there is none."""
        if entry_name not in self._index(group):
            return None
        payload, static = self._payload(entry_name, group)
        if not static:
            raise SecretStoreError(f"entry {entry_name} is not a plain entry")
        return payload

    def get_fields(self, entry_name: str, fields: list[str], group: str | None = None) -> dict[str, str]:
        record = self.get_record(entry_name, group)
        missing = [f for f in fields if f not in record]
        if missing:
            raise SecretStoreError(f"entry {entry_name} has no field " + ", ".join(missing))
        return {f: record[f] for f in fields}

    # -- writing ------------------------------------------------------------------------------
    def _write(self, build: Callable[[], tuple[dict, str]], typed: Any = None) -> None:
        """One change through sync, build, verify, commit, push and checkpoint, under one repository
        lock. A typed write (typed_write.write_typed) hands its Attempt down as typed: it is checked
        after the sync, its record written after the verification and before repo.write touches the
        clone, and told whether a local commit was made (plan section L4)."""
        def phase(name: str) -> None:
            if typed is not None:
                typed.phase = name
        self._ready()
        with self.repo.lock():
            for _attempt in range(1 + RETRIES):
                phase("sync")
                self._sync(None, self.checkpoint)
                phase("check")
                if typed is not None:
                    typed.check(self)
                phase("build")
                files, message = build()
                phase("verify")
                baseline, before = self._baseline(self.checkpoint, files), self.repo.head()
                accepted = accept_commit(self.policy, self.checkpoint, files, self._identity().my_keys(), baseline)
                phase("record")
                if typed is not None:
                    typed.before_commit(self, files)
                phase("commit")
                try:
                    written = self.repo.write(files, message, expected_parent=before)
                    if typed is not None and self.repo.last_commit:
                        typed.committed = True
                except SecretStoreError as error:
                    if typed is not None and self.repo.last_commit:
                        typed.committed = True
                    if isinstance(error, MovedHead):  # else a lost acknowledgement: settle it with the remote
                        raise
                    written = self.repo.settle_failed_write(before)
                    if written is None:
                        raise
                    accepted = accept_commit(self.policy, self.checkpoint, self.repo._changed_files(written),
                                             self._identity().my_keys(), baseline)
                if isinstance(written, Conflict):
                    continue
                phase("checkpoint")  # a failure here is the store's: never isolated (plan L4, correction 4)
                self._save_checkpoint(accepted.checkpoint)
                self.policy, self.checkpoint, self._head = accepted.policy, accepted.checkpoint, written
                self._note_usable(accepted)
                if "policy.json" in files:  # the change is saved: package upkeep only ever warns
                    self._package_upkeep()
                return
        raise SecretStoreError("the personal repository kept changing; the change was not saved, try again")

    def put_entry(self, entry_name: str, fields: dict[str, str], kind: str = "static",
                  group: str | None = None, field_kinds: dict[str, str] | None = None, typed: Any = None) -> None:
        """Store fields in entry_name: a new entry, or the next revision with these fields changed.
        A static entry records each written field's kind (plan N2): field_kinds, else text."""
        if not isinstance(entry_name, str) or not entry_name.strip():
            raise SecretStoreError("an entry needs a name")
        if not fields or not all(isinstance(k, str) and k and isinstance(v, str) for k, v in fields.items()):
            raise SecretStoreError("fields must be named text values")
        exposed = sorted(set(fields) & provider_profiles.grant_fields()) if kind == "static" else []
        if exposed:  # every group reader could decrypt a static object: grant fields go to the grant
            raise SecretStoreError(f"{', '.join(exposed)} is a grant field and never goes in a plain entry; "
                                   "store it as the sign-in's grant field instead")

        kinds = (field_kinds if field_kinds is not None else {f: "text" for f in fields}) if kind == "static" else None

        def build() -> tuple[dict, str]:
            index = self._index(group)
            if kinds is not None:
                payload = static_fields.merged(self.static_payload(entry_name, group), fields, kinds)
            else:
                payload = self.get_record(entry_name, group) if entry_name in index else {}
                payload.update(fields)
            return build_put(self.policy, self.checkpoint.objects, index, entry_name, payload, kind,
                             self._identity().ed25519, self._group(group))
        self._write(build, typed=typed)

    def delete_entry(self, entry_name: str, group: str | None = None, field: str | None = None) -> None:
        """The whole entry (its static object and every sign-in under it), or with field exactly the
        sign-in of entry_name under field, by an administrator (replace_ops.delete_signin, plan R11)."""
        if field is not None:
            from .replace_ops import delete_signin
            delete_signin(self, entry_name, field, group)
            return
        self._write(lambda: build_delete(self.policy, self.checkpoint.objects, self._index(group), entry_name,
                                         self._identity().ed25519))

    def static_grant_exposures(self) -> list[str]:
        """'group/entry: field, ...' for every static object this computer can read that holds a
        grant-field spelling (made before put_entry refused them). Names only, never values; each
        credential listed was readable by the whole group and must be changed at the provider."""
        self._ready()
        grant_keys, found = provider_profiles.grant_fields(), []
        for group in sorted(self.policy.doc["groups"]):
            try:
                index = self._index(group)
            except SecretStoreError:
                continue  # an index this computer cannot read
            for name, oid in sorted(index.items()):
                if self.policy.assignment(oid)[1] != "static":
                    continue
                try:
                    record = static_fields.split(self._open_object(self._tree_object(oid, self.checkpoint)))[0]
                except SecretStoreError:
                    continue
                held = sorted(set(record) & grant_keys)
                if held:
                    found.append(f"{group}/{name}: " + ", ".join(held))
        return found

    # -- recovery package and status ----------------------------------------------------------
    def _package_path(self) -> Path:
        return self.config["recovery_package_dir"] / f"brain-secrets-{self.config['person']}.package"

    def refresh_recovery_package(self, force: bool = False) -> Path:
        """Write the package when it is older than seven days or the policy changed since."""
        self._ready()
        path = self._package_path()
        marker = path.with_name(path.name + ".policy")
        if self.package_fresh() and not force:
            return path
        recovery_public = self.policy.enc_keys[self.policy.recovery[0]]
        recovery_package.build(self.repo, self.checkpoint_path.read_bytes(), recovery_public, path)
        write_marker(marker, path, self.policy.hash, self._identity().ed25519)
        return path

    def status(self) -> str:
        return store_status(self)

__all__ = ["SecretStore", "Identity", "EMPTY_JSON"]
