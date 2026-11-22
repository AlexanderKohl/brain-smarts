"""Pending-write records (plan sections L2 and L4 with their amendments): a value a person typed
survives a crash between a local commit and its push. One record per write, for its whole life:
written atomically and flushed beside the refresh journal after the change is built and verified
and before the local commit, encrypted to this computer's X25519 key only, the way a journal record
is, with the repository and group also in the envelope's authenticated header. It holds a write
id, the repository, the group, the entry, the plain fields with their kinds, the grant fields, the
base (each target the write was built on, by object id and checkpoint hash; an absent target by the
group's index object, or by "no index" and the policy hash), the projected identities (id and hash
of every object revision the commit writes, an index excepted), the time and the held mark. Each
further attempt rewrites only the projected identities, and marking a record held changes only
that mark. A damaged record, or one made by the first build (no kinds), is never applied. Only
typed_write.write_typed makes one, so a provider's token answer never enters a record. Messages name
the write id, entry and time, never a value."""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from . import envelope, fileio, static_fields
from .errors import SecretStoreError
from .keys import key_id

WRITE_ID = re.compile(r"[0-9a-f]{16}")
_SUFFIX = ".pending"
FIELDS = ("id", "repository", "group", "entry", "plain", "kinds", "grant", "base", "projected", "time", "held")


def _texts(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and k and isinstance(v, str) for k, v in value.items())


def _identity(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"id", "hash"} and _texts(value)


def _base_ok(base: Any) -> bool:
    if not isinstance(base, dict) or set(base) != {"targets", "index", "policy"}:
        return False
    targets = base["targets"]
    if not isinstance(targets, dict) or not targets or not all(
            isinstance(k, str) and (v is None or _identity(v)) for k, v in targets.items()):
        return False
    if None in targets.values():  # an absent target is bound to the index, or to no index and the policy
        return _identity(base["index"]) or (base["index"] is None and isinstance(base["policy"], str))
    return True


def valid(record: Any) -> bool:
    """The shape of a current record (kinds included)."""
    if not isinstance(record, dict) or set(record) != set(FIELDS):
        return False
    plain, kinds, grant = record["plain"], record["kinds"], record["grant"]
    if not (_texts(plain) and _texts(kinds) and _texts(grant) and set(kinds) == set(plain) and (plain or grant)):
        return False
    try:
        for field, kind in kinds.items():
            static_fields.check_kind(field, plain[field], kind)
    except SecretStoreError:
        return False
    return (WRITE_ID.fullmatch(record["id"] if isinstance(record["id"], str) else "") is not None
            and all(isinstance(record[k], str) and record[k] for k in ("repository", "group", "entry"))
            and _base_ok(record["base"]) and _texts(record["projected"])
            and isinstance(record["time"], int) and not isinstance(record["time"], bool)
            and isinstance(record["held"], bool))


class PendingWrites:
    def __init__(self, checkpoint_dir: Any, x25519_private: Any) -> None:
        self.folder = Path(checkpoint_dir) / "pending"
        self._key = x25519_private
        self._key_id = key_id(x25519_private.public_key())

    def path(self, write_id: str) -> Path:
        if not isinstance(write_id, str) or not WRITE_ID.fullmatch(write_id):
            raise SecretStoreError("a pending write id is 16 hexadecimal characters")
        return self.folder / f"{write_id}{_SUFFIX}"

    def new(self, repository: str, group: str, entry: str, plain: dict, kinds: dict, grant: dict,
            base: dict, projected: dict) -> dict:
        """The first write's record, built only: nothing touches the disk here. The caller binds it to
        its attempt and enters its id among the writes in flight, then writes it (plan R13, fix 1)."""
        record = {"id": secrets.token_hex(8), "repository": repository, "group": group, "entry": entry,
                  "plain": dict(plain), "kinds": dict(kinds), "grant": dict(grant), "base": base,
                  "projected": dict(projected), "time": int(time.time()), "held": False}
        if not valid(record):
            raise SecretStoreError("a pending-write record is malformed; nothing was written")
        return record

    def write(self, record: dict) -> None:
        """One atomic write (temporary file, flush, replace) of a whole record."""
        if not valid(record):
            raise SecretStoreError("a pending-write record is malformed; nothing was written")
        header = {"repository": record["repository"], "group": record["group"], "id": record["id"],
                  "kind": "static", "revision": 1}
        obj = envelope.seal(record, [(self._key_id, self._key.public_key())], header)
        fileio.write_durable(self.path(record["id"]), json.dumps(obj).encode("utf-8"))

    def remove(self, write_id: str) -> None:
        fileio.remove_durable(self.path(write_id))

    def read(self, write_id: str) -> dict | None:
        """The record; {"legacy": True, ...} for one made by the first build (no kinds); None when
        it is damaged (unreadable, not authentic or malformed)."""
        try:
            obj = json.loads(self.path(write_id).read_text("utf-8"))
            record = envelope.open_(obj, self._key_id, self._key)
        except (OSError, ValueError, TypeError, AttributeError, SecretStoreError):
            return None
        if record.get("id") != write_id or obj.get("id") != write_id or record.get("repository") != obj.get(
                "repository") or record.get("group") != obj.get("group"):
            return None
        if "plain" not in record and "fields" in record:  # the first build's shape: never applied
            ok = all(isinstance(record.get(k), str) for k in ("repository", "group", "entry")) \
                and isinstance(record.get("time"), int)
            return {"legacy": True, **{k: record.get(k) for k in ("id", "repository", "group", "entry", "time")}} \
                if ok else None
        return record if valid(record) else None

    def all(self) -> dict[str, dict | None]:
        """Every record on this computer by write id, oldest first; None marks a damaged one."""
        if not self.folder.is_dir():
            return {}
        found = []
        for path in self.folder.glob(f"*{_SUFFIX}"):
            write_id = path.name[:-len(_SUFFIX)]
            if WRITE_ID.fullmatch(write_id):
                found.append((path.stat().st_mtime, write_id))
        return {write_id: self.read(write_id) for _mtime, write_id in sorted(found)}


def describe(write_id: str, record: dict | None) -> str:
    """One line for status and the unfinished command: the write id, entry and time, never a value."""
    if record is None:
        return (f"Pending write {write_id} on this computer is damaged or unreadable: it is never applied; "
                f"remove it with brain_secrets.py unfinished --discard {write_id}.")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(record["time"]))
    name = record["entry"] + ("" if record["group"] == "personal" else f" (group {record['group']})")
    if record.get("legacy"):
        return (f"Pending write {write_id} of {name} made {when} was kept by an earlier version without field "
                "kinds and is never applied: store the entry again, then run brain_secrets.py unfinished "
                f"--discard {write_id}.")
    if record["held"]:
        return (f"Pending write {write_id} of {name} made {when} is held on this computer: the entry changed "
                f"since, or the store refused it, so it is not applied by itself; run brain_secrets.py "
                f"unfinished --apply {write_id} to write the kept values over the present ones, or --discard "
                f"{write_id}.")
    return (f"Pending write {write_id} of {name} made {when} is kept on this computer and is saved at the "
            "next operation of the store.")
