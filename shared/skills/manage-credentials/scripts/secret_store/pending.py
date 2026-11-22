"""Pending-write records (plan section L2): typed static fields survive a crash between a local
commit and its push. Before the first change to the store a record is written atomically and
flushed beside the refresh journal, encrypted to this computer's X25519 key only, the way a journal
record is: a write id, the repository, the group, the entry, the fields and their values, the time
and the revision of the entry's object the write was built on (None: the entry did not exist).
The repository and group are also in the envelope's authenticated header. A record is removed only
when its write is confirmed, when the entry already holds exactly those values, or when the
command failed before any local commit. A damaged record is never applied and stays until
discarded. Messages name the write id, entry and time, never a value."""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from . import envelope, fileio
from .errors import SecretStoreError
from .keys import key_id

WRITE_ID = re.compile(r"[0-9a-f]{16}")
_SUFFIX = ".pending"


class PendingWrites:
    def __init__(self, checkpoint_dir: Any, x25519_private: Any) -> None:
        self.folder = Path(checkpoint_dir) / "pending"
        self._key = x25519_private
        self._key_id = key_id(x25519_private.public_key())

    def path(self, write_id: str) -> Path:
        if not WRITE_ID.fullmatch(write_id or ""):
            raise SecretStoreError("a pending write id is 16 hexadecimal characters")
        return self.folder / f"{write_id}{_SUFFIX}"

    def save(self, repository: str, group: str, entry: str, fields: dict[str, str], base: int | None,
             write_id: str | None = None) -> str:
        """Write (or rewrite, with write_id) one record durably; returns its write id."""
        write_id = write_id or secrets.token_hex(8)
        record = {"id": write_id, "repository": repository, "group": group, "entry": entry,
                  "fields": dict(fields), "base": base, "time": int(time.time())}
        header = {"repository": repository, "group": group, "id": write_id, "kind": "static", "revision": 1}
        obj = envelope.seal(record, [(self._key_id, self._key.public_key())], header)
        fileio.write_durable(self.path(write_id), json.dumps(obj).encode("utf-8"))
        return write_id

    def remove(self, write_id: str) -> None:
        fileio.remove_durable(self.path(write_id))

    def read(self, write_id: str) -> dict | None:
        """The record, or None when it is damaged (unreadable, not authentic or malformed)."""
        try:
            obj = json.loads(self.path(write_id).read_text("utf-8"))
            record = envelope.open_(obj, self._key_id, self._key)
        except (OSError, ValueError, TypeError, AttributeError, SecretStoreError):
            return None
        ok = (record.get("id") == write_id == obj.get("id")
              and isinstance(record.get("repository"), str) and record["repository"] == obj.get("repository")
              and isinstance(record.get("group"), str) and record["group"] == obj.get("group")
              and isinstance(record.get("entry"), str) and record["entry"]
              and isinstance(record.get("fields"), dict) and record["fields"]
              and all(isinstance(k, str) and isinstance(v, str) for k, v in record["fields"].items())
              and (record.get("base") is None or (isinstance(record["base"], int)
                                                  and not isinstance(record["base"], bool)))
              and isinstance(record.get("time"), int))
        return record if ok else None

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


def describe(write_id: str, record: dict | None, held: bool | None = None) -> str:
    """One line for status and the unfinished command: the write id, entry and time, never a value."""
    if record is None:
        return (f"Pending write {write_id} on this computer is damaged or unreadable: it is never applied; "
                f"remove it with brain_secrets.py unfinished --discard {write_id}.")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(record["time"]))
    name = record["entry"] + ("" if record["group"] == "personal" else f" (group {record['group']})")
    if held:
        return (f"Pending write {write_id} of {name} made {when} is kept on this computer: the entry changed "
                f"since, so it is not applied by itself; run brain_secrets.py unfinished --apply {write_id} to "
                f"write the kept values over the present ones, or --discard {write_id}.")
    return (f"Pending write {write_id} of {name} made {when} is kept on this computer and is saved at the "
            "next operation of the store.")
