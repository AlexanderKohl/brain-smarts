"""Building blocks of the personal secrets store (design synced-secrets-repository.md, sections 6
to 9): configuration and paths, and the pure builders of objects, indexes and policy changes.
No Git and no keychain here; store.py runs them."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import canonical, envelope, signing
from .errors import SecretStoreError
from .keys import key_id
from .policy import INDEX_PREFIX, Policy, object_hash, sign_policy

GROUP = "personal"
INDEX_ID = INDEX_PREFIX + GROUP
CONFIG_RELATIVE = Path("memory") / "skills" / "manage-credentials" / "config" / "secret-store.json"
CONFIG_KEYS = frozenset({"enabled", "person", "computer", "personal_repo_url", "personal_clone",
                         "checkpoint_dir", "recovery_package_dir", "team_repo_url", "team_clone"})
WRITABLE_KINDS = ("static", "oauth")
EMPTY_JSON = "{}"
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def find_brain_root(start: str | os.PathLike | None = None) -> Path | None:
    """Walk upwards to the folder holding CONTRACT.md, as portable_vault.find_brain_root does."""
    here = Path(start or __file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    return None


RECOVERY_FOLDER = "brain-secrets-recovery"


def recovery_package_place() -> tuple[Path, bool]:
    """The default recovery-package folder and whether it is in the person's own cloud drive:
    OneDrive (the OneDrive or OneDriveConsumer environment variable) on Windows, iCloud Drive on
    macOS, else the local application-data folder (status then warns)."""
    found: list = []
    if sys.platform == "win32":
        found = [os.environ.get("OneDrive"), os.environ.get("OneDriveConsumer")]
    elif sys.platform == "darwin":
        found = [Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"]
    for folder in found:
        if folder and Path(folder).is_dir():
            return Path(folder) / RECOVERY_FOLDER, True
    return app_data_dir() / "recovery-packages", False


def app_data_dir() -> Path:
    """The per-user application data folder that holds the checkpoint (outside every clone)."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "brain-secrets"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "brain-secrets"
    return Path.home() / ".local" / "share" / "brain-secrets"


def project_repos_root(brain_root: Path) -> Path:
    """project_repos_root from /memory/OWNER.md; the brain root's parent when it is not set."""
    try:
        text = (brain_root / "memory" / "OWNER.md").read_text("utf-8")
    except OSError:
        text = ""
    match = re.search(r"^project_repos_root:\s*(\S.*?)\s*$", text, re.M)
    return Path(match.group(1)) if match else brain_root.parent


def safe_name(value: str) -> str:
    cleaned = _UNSAFE.sub("-", str(value).strip())[:128]
    if not cleaned.strip("-"):
        raise SecretStoreError("a person or computer name needs letters or digits")
    return cleaned


def load_config(use_config_file: bool = True, brain_root: str | os.PathLike | None = None,
                **overrides: Any) -> dict[str, Any]:
    """The store configuration: the memory configuration file when present, then defaults; every
    key can be overridden (tests). Without a file and without overrides the store is off."""
    unknown = set(overrides) - CONFIG_KEYS
    if unknown:
        raise SecretStoreError("unknown configuration keys: " + ", ".join(sorted(unknown)))
    root = Path(brain_root) if brain_root else find_brain_root()
    data: dict[str, Any] = {}
    if use_config_file and root is not None and (root / CONFIG_RELATIVE).is_file():
        try:
            data = json.loads((root / CONFIG_RELATIVE).read_text("utf-8"))
        except (OSError, ValueError):
            raise SecretStoreError("the secrets-store configuration cannot be read") from None
        if not isinstance(data, dict) or set(data) - CONFIG_KEYS:
            raise SecretStoreError("the secrets-store configuration has unknown keys")
        data.setdefault("enabled", True)
    data.update({k: v for k, v in overrides.items() if v is not None})
    person = data.get("person")
    config: dict[str, Any] = {
        "enabled": bool(data.get("enabled", False)),
        "person": safe_name(person) if person else None,
        "computer": safe_name(data.get("computer") or socket.gethostname()),
        "personal_repo_url": data.get("personal_repo_url"),
        "team_repo_url": data.get("team_repo_url"),
    }
    repos = project_repos_root(root) if root is not None else Path.home()
    config["personal_clone"] = Path(data.get("personal_clone") or repos / "brain-secrets")
    config["team_clone"] = Path(data.get("team_clone") or repos / "brain-team-secrets")
    config["checkpoint_dir"] = Path(data.get("checkpoint_dir") or app_data_dir())
    if data.get("recovery_package_dir"):  # the person's own choice
        config["recovery_package_dir"], config["recovery_package_cloud"] = Path(data["recovery_package_dir"]), True
    else:
        config["recovery_package_dir"], config["recovery_package_cloud"] = recovery_package_place()
    for name in ("personal_clone", "team_clone"):
        clone, brain = config[name].resolve(), root.resolve() if root is not None else None
        if brain is not None and (clone == brain or brain in clone.parents):
            raise SecretStoreError("the secrets clone must not be inside the brain repository")
    return config


def new_object_id(policy: Policy) -> str:
    while True:
        oid = secrets.token_hex(16)
        if oid not in policy.doc["assignments"] and oid not in policy.doc["retired"]:
            return oid


def seal_object(policy: Policy, oid: str, kind: str, payload: dict, signer: Ed25519PrivateKey,
                entry: dict | None, epoch: int | None = None, readers: list[str] | None = None) -> dict:
    """The next signed revision of oid (revision 1 when entry, its checkpoint entry, is None)."""
    reader_ids = policy.readers_for(oid) if readers is None else readers
    header = {"repository": policy.repository, "group": policy.assignment(oid)[0], "id": oid, "kind": kind,
              "revision": 1 if entry is None else entry["revision"] + 1,
              "previous": None if entry is None else entry["hash"],
              "policy_epoch": policy.epoch if epoch is None else epoch,
              "writer": key_id(signer.public_key())}
    obj = envelope.seal(payload, [(rid, policy.enc_keys[rid]) for rid in reader_ids], header)
    return signing.sign(obj, signer)


def next_policy(current: Policy, signer: Ed25519PrivateKey, change: Callable[[dict], None]) -> dict:
    """The next policy document: epoch one higher, chained to the current hash, then signed."""
    doc = copy.deepcopy(current.doc)
    doc.pop("signature", None)
    doc.pop("endorsement", None)  # only a trust root carries the recovery endorsement
    doc["epoch"], doc["previous"], doc["cites"] = current.epoch + 1, current.hash, []
    change(doc)
    return sign_policy(doc, signer)


def _path(oid: str) -> str:
    return f"objects/{oid}.json"


def build_put(policy: Policy, entries: dict, index: dict[str, str], name: str, payload: dict,
              kind: str, signer: Ed25519PrivateKey, group: str = GROUP) -> tuple[dict, str]:
    """(files, message) of one commit storing payload as entry name in group. entries: checkpoint objects."""
    index_id = INDEX_PREFIX + group
    if kind not in WRITABLE_KINDS:
        raise SecretStoreError(f"entries of kind {kind} cannot be stored here")
    oid = index.get(name)
    if oid is not None:
        _group, current_kind = policy.assignment(oid)
        if current_kind != kind:
            raise SecretStoreError(f"entry {name} is a {current_kind} entry, not {kind}")
        return {_path(oid): seal_object(policy, oid, kind, payload, signer, entries.get(oid))}, "update"
    oid = new_object_id(policy)

    def assign(doc: dict) -> None:
        doc["assignments"][oid] = {"group": group, "kind": kind}

    new_doc = next_policy(policy, signer, assign)
    result = Policy(new_doc)
    names = dict(index)
    names[name] = oid
    return {"policy.json": new_doc,
            _path(oid): seal_object(result, oid, kind, payload, signer, None),
            _path(index_id): seal_object(result, index_id, "index", {"entries": names}, signer,
                                         entries.get(index_id))}, "policy"


def build_policy_change(policy: Policy, entries: dict, change: Callable[[dict], None], signer: Ed25519PrivateKey,
                        open_payload: Callable[[str], dict]) -> dict:
    """The files of one administrator commit (section 8): the next policy and a new revision of
    every object whose readers change, re-keyed with its payload unchanged. Grants are left as
    they are (section 6); a grant whose readers would change is refused."""
    new_doc = next_policy(policy, signer, change)
    result = Policy(new_doc)
    files: dict = {"policy.json": new_doc}
    for oid, entry in sorted(entries.items()):
        if oid in result.doc["retired"]:
            continue
        try:
            before, after = policy.readers_for(oid), result.readers_for(oid)
        except SecretStoreError:
            continue  # no longer assigned: nothing to re-key
        if before == after:
            continue
        kind = result.assignment(oid)[1]
        if kind == "grant":
            raise SecretStoreError(f"grant {oid} would change readers; its refresher or the recovery words must re-issue it")
        files[_path(oid)] = seal_object(result, oid, kind, open_payload(oid), signer, entry)
    return files


def checkpoint_commit(repo: Any, cp: Any) -> str | None:
    """The newest commit of the clone whose policy and objects are exactly the checkpoint's, or
    None (the checkpoint is ahead of, or apart from, the clone)."""
    for commit in repo.commits():
        doc = repo.read_at(commit, "policy.json")
        if doc is None or object_hash(doc) != cp.policy_hash:
            continue
        if all(object_hash(repo.read_at(commit, f"objects/{oid}.json")) == entry["hash"]
               for oid, entry in cp.objects.items()):
            return commit
    return None


def _marker_doc(package: Path, policy_hash: str) -> dict:
    return {"policy": policy_hash, "package": hashlib.sha256(package.read_bytes()).hexdigest()}


def marker_current(marker: Path, package: Path, policy_hash: str, public_key: Any) -> bool:
    """The recovery package's policy marker: signed by this computer's key and naming both the
    current policy and the package's own hash; anything stale, unsigned or tampered is not current."""
    try:
        doc = canonical.loads(marker.read_bytes())
        signing.verify(doc, public_key)
        return {k: v for k, v in doc.items() if k != "signature"} == _marker_doc(package, policy_hash)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, SecretStoreError):
        return False


def _upkeep_file(config: dict[str, Any], package: Path) -> Path:
    return Path(config["checkpoint_dir"]) / (Path(package).name + ".upkeep-error")


def write_upkeep_error(config: dict[str, Any], package: Path, text: str | None) -> None:
    """The last recovery-package upkeep failure, beside the checkpoint on this computer (never in the
    package folder, which may be the offline drive that failed); None clears it. Best effort."""
    path = _upkeep_file(config, package)
    try:
        if text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, "utf-8")
        elif path.exists():
            path.unlink()
    except OSError:
        pass


TEAM_PACKAGE_PREFIX = "brain-team-secrets"  # team.REPOSITORY_NAME (team imports this module)


def package_health(config: dict[str, Any]) -> str | None:
    """The daily due check's read-only look at every configured store's recovery package (round-8
    review: the personal one, and the team one when team_repo_url or a team clone is configured):
    None when the store is off or every package is fresh (under seven days old, its marker naming
    the clone's current policy and the package), else the plain problems. Files only: no Git,
    keychain or network, so the marker's signature is left to the store, which checks it at its
    next use."""
    if not config.get("enabled") or not config.get("person"):
        return None
    folder, person = Path(config["recovery_package_dir"]), config["person"]
    problems = [_one_package_health(config, Path(config["personal_clone"]), folder / f"brain-secrets-{person}.package")]
    team_clone = Path(config["team_clone"]) if config.get("team_clone") else None
    if config.get("team_repo_url") or (team_clone is not None and (team_clone / ".git").is_dir()):
        team = _one_package_health(config, team_clone, folder / f"{TEAM_PACKAGE_PREFIX}-{person}.package")
        problems.append(f"team store: {team}" if team else None)
    return "; ".join(p for p in problems if p) or None


def _one_package_health(config: dict[str, Any], clone: Any, path: Path) -> str | None:
    if clone is None or not (Path(clone) / ".git").is_dir():
        return "the secrets store is on but not set up on this computer, so there is no recovery package"
    try:
        failed = _upkeep_file(config, path).read_text("utf-8").strip()
    except OSError:
        failed = ""
    if failed:
        return f"the Vault Agent's recovery-package upkeep failed: {failed}; it retries, or run recovery-package"
    if not path.is_file():
        return f"no recovery package at {path}; run recovery-package"
    days = (time.time() - path.stat().st_mtime) / 86400
    if days >= 7:
        return f"the recovery package is {int(days)} day(s) old; run recovery-package"
    try:
        doc = canonical.loads(path.with_name(path.name + ".policy").read_bytes())
        current = object_hash(canonical.loads((clone / "policy.json").read_bytes()))
        fresh = {k: v for k, v in doc.items() if k != "signature"} == _marker_doc(path, current)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, SecretStoreError):
        fresh = False
    return None if fresh else "the recovery package does not match the current policy; run recovery-package"


def write_marker(marker: Path, package: Path, policy_hash: str, signer: Ed25519PrivateKey) -> None:
    marker.write_bytes(canonical.dumps(signing.sign(_marker_doc(package, policy_hash), signer)))


def not_enrolled_message(store: Any) -> str:
    """Plan section I: the store's repository has commits but this computer holds no pin and no
    checkpoint for it. Each store needs its own enrolment (design section 6): a team enrolment
    never covers the personal store, and the agent always serves the personal store."""
    if store.team:
        return ("this computer is not enrolled in the team store: its repository has commits but this "
                "computer holds no pin or checkpoint for it. Run enrol-request --team --fingerprint F here "
                "and enrol-approve --team on an administrator's computer; nothing was changed")
    return ("this computer is not enrolled in the personal store: its repository has commits but this "
            "computer holds no pin or checkpoint for it. Run enrol-request --fingerprint F here and "
            "enrol-approve on one of your computers already in it (a team enrolment does not cover the "
            "personal store; a new person runs init); nothing was changed")


def store_status(self: Any) -> str:
    """SecretStore.status: one line on the clone and one on the recovery package."""
    if not self.config["enabled"] or not self.config["person"]:
        return "The secrets store is off on this computer."
    held = [getattr(self, name, None) for name in ("checkpoint_path", "pin_path")]
    if all(path is not None and not path.exists() for path in held):
        enrol = "enrol-request --team" if self.team else "enrol-request"
        return (f"The {'team' if self.team else 'personal'} secrets store is on but not set up here: run "
                f"{'team-init' if self.team else 'init'} (first computer) or enrol this computer with {enrol} "
                "(a team enrolment does not set up the personal store).")
    if not (self.clone / ".git").is_dir():
        return "The secrets store is on but not set up here: run init (first computer) or open."
    from .repo import SecretRepo
    repo = self.repo or SecretRepo(self.clone, self._remote_url())
    lines = [repo.status()]
    path = self._package_path()
    if path.exists():
        days = int((time.time() - path.stat().st_mtime) // 86400)
        lines.append(f"Recovery package: made {days} day(s) ago at {path}.")
    else:
        lines.append("Recovery package: none yet; run recovery-package.")
    if getattr(self, "package_error", None):
        lines.append("Recovery package: the automatic weekly refresh failed; run recovery-package.")
    from .replace_ops import pending
    for signin in pending(self):
        lines.append(f"Replaced sign-in {signin} is not signed in again yet: its kept settings wait on this "
                     "computer; sign in again in the browser to complete it.")
    if not self.config.get("recovery_package_cloud", True):
        lines.append("Warning: no OneDrive or iCloud Drive folder was found, so the recovery package is only on "
                     "this computer; set recovery_package_dir to a folder that is backed up elsewhere.")
    return " ".join(lines)
