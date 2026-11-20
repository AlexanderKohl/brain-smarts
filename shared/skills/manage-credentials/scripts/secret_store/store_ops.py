"""Building blocks of the personal secrets store (design synced-secrets-repository.md, sections 6
to 9): configuration and paths, and the pure builders of objects, indexes and policy changes.
No Git and no keychain here; store.py runs them."""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import socket
import sys
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import envelope, signing
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
    config["recovery_package_dir"] = Path(data.get("recovery_package_dir") or app_data_dir() / "recovery-packages")
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


def build_delete(policy: Policy, entries: dict, index: dict[str, str], name: str,
                 signer: Ed25519PrivateKey) -> tuple[dict, str]:
    """The tombstone transaction (section 7): the empty final revision signed by an administrator,
    the policy change retiring its id with that revision's hash, and the index without the name."""
    oid = index.get(name)
    if oid is None:
        raise SecretStoreError(f"there is no entry {name}")
    index_id = INDEX_PREFIX + policy.assignment(oid)[0]
    tombstone = seal_object(policy, oid, "tombstone", {}, signer, entries.get(oid),
                            epoch=policy.epoch + 1, readers=policy.readers_for(oid))
    final = object_hash(tombstone)

    def retire(doc: dict) -> None:
        del doc["assignments"][oid]
        doc["retired"][oid] = final

    new_doc = next_policy(policy, signer, retire)
    result = Policy(new_doc)
    names = {k: v for k, v in index.items() if k != name}
    return {"policy.json": new_doc, _path(oid): tombstone,
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
