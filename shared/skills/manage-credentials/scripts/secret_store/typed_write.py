"""Typed values and their pending-write records (plan sections L2 and L4 with their amendments).

write_typed is the one function that makes a record and writes: brain_secrets.py put and the
agent's set_text and set_json of a static or grant field call it, always; the replay and
unfinished --apply call it under the record that exists. A typed value is recorded whatever its
field is called. The writers beneath it (put_entry, oauth_ops.put_fields, set_grant_fields,
put_signin, put_grant_fields) make no record: they take a keyword typed=None, passed to their one
_write, and only this module hands one down. A provider's token answer (a browser authorisation, a
migrated sign-in, a refresh) goes through put_signin with a token record or through publish, never
through here, so it never enters a record.

_write runs the Attempt it is handed at its phases: after the write's own sync (check: a replay is
replayed, saved or held, decided in the verified state the write is built on, under the repository
lock), after the change is built and verified (record: the first write's record is written, a later
attempt rewrites only the projected identities; before repo.write touches the clone), at the commit
(committed) and before the checkpoint is saved (a failure there is never isolated)."""

from __future__ import annotations

from typing import Any

from .errors import IntegrityError, SecretStoreError
from .pending import PendingWrites
from .policy import INDEX_PREFIX, object_hash


class Saved(SecretStoreError):
    """The verified checkpoint holds every projected identity: nothing is written."""


class Held(SecretStoreError):
    """A target changed since the record was built: nothing is written."""


def records(store: Any) -> PendingWrites:
    return PendingWrites(store.config["checkpoint_dir"], store._identity().x25519)


def _in_flight(store: Any) -> set:
    """Write ids this instance is writing now: never replayed as a dead process's record."""
    if "_typed_flight" not in store.__dict__:
        store._typed_flight = set()
    return store._typed_flight


def _target_names(store: Any, entry: str, group: str, grant: dict) -> list[str]:
    """The index names a write touches: the entry's static object, and with grant fields the grant
    of its first sign-in (the default sign-in's grant when there is none)."""
    if not grant:
        return [entry]
    from . import oauth_ops
    fields = oauth_ops.signin_fields(store, entry, group)
    return [entry, oauth_ops.signin_names(entry, fields[0] if fields else oauth_ops.DEFAULT_FIELD)[1]]


def base_of(store: Any, entry: str, group: str, grant: dict) -> dict:
    """Each target by object id and checkpoint hash; an absent one by the group's index object, or by
    no index and the policy hash (amendment b)."""
    index, objects = store._index(group), store.checkpoint.objects
    targets = {name: ({"id": index[name], "hash": objects[index[name]]["hash"]} if name in index else None)
               for name in _target_names(store, entry, group, grant)}
    index_id = INDEX_PREFIX + group
    anchor = {"id": index_id, "hash": objects[index_id]["hash"]} if index_id in objects else None
    absent = None in targets.values()
    return {"targets": targets, "index": anchor if absent else None,
            "policy": store.policy.hash if absent and anchor is None else None}


def base_holds(store: Any, record: dict) -> bool:
    base, group = record["base"], record["group"]
    index, objects = store._index(group), store.checkpoint.objects
    for name, target in base["targets"].items():
        if target is None:
            if name in index:
                return False
        elif index.get(name) != target["id"] or objects.get(target["id"], {}).get("hash") != target["hash"]:
            return False
    if None in base["targets"].values():
        index_id = INDEX_PREFIX + group
        if base["index"] is not None:
            return objects.get(index_id, {}).get("hash") == base["index"]["hash"]
        return index_id not in objects and store.policy.hash == base["policy"]
    return True


def projected_of(files: dict) -> dict:
    """Id and hash of every object revision the commit writes, an index excepted."""
    out = {}
    for path, obj in files.items():
        if path.startswith("objects/") and obj is not None:
            oid = path[len("objects/"):-len(".json")]
            if not oid.startswith(INDEX_PREFIX):
                out[oid] = object_hash(obj)
    return out


class Attempt:
    """One write of typed values. mode: "first", "replay" or "apply"."""

    def __init__(self, store: Any, entry: str, group: str, plain: dict, kinds: dict, grant: dict,
                 record: dict | None, mode: str) -> None:
        self.store, self.entry, self.group = store, entry, group
        self.plain, self.kinds, self.grant = dict(plain), dict(kinds), dict(grant)
        self.record, self.mode = record, mode
        # phases: sync, check, prepare, build, verify, record, commit, checkpoint
        self.phase, self.committed, self.recorded = "sync", False, False

    def check(self, store: Any) -> None:
        if self.mode != "replay":
            return
        if base_holds(store, self.record):
            return
        projected = self.record["projected"]
        if projected and all(store.checkpoint.objects.get(o, {}).get("hash") == h for o, h in projected.items()):
            raise Saved("the pending write is already in the store")
        raise Held("a target of the pending write changed since it was made")

    def before_commit(self, store: Any, files: dict) -> None:
        projected = projected_of(files)
        self.recorded = True
        if self.record is None:  # built, bound and in flight first; only then written (plan R13, fix 1)
            self.record = records(store).new(store.policy.repository, self.group, self.entry, self.plain,
                                             self.kinds, self.grant, base_of(store, self.entry, self.group,
                                                                             self.grant), projected)
            _in_flight(store).add(self.record["id"])
            records(store).write(self.record)
        else:  # each further attempt: the projected identities and nothing else
            self.record = {**self.record, "projected": projected}
            records(store).write(self.record)


def _writer(store: Any, entry: str, group: str, plain: dict, kinds: dict, grant: dict, typed: Attempt) -> None:
    from . import oauth_ops
    if plain and grant:
        oauth_ops.put_fields(store, entry, plain, grant, group, plain_kinds=kinds, typed=typed)
    elif plain:
        store.put_entry(entry, plain, group=group, field_kinds=kinds, typed=typed)
    else:
        from .broker_backend import put_grant_fields
        put_grant_fields(store, group, entry, grant, typed=typed)


def _run(attempt: Attempt) -> None:
    store = attempt.store
    if attempt.mode == "replay":  # decided before the writer looks at the store, after a sync of its own
        with store.repo.lock():
            store._sync(None, store.checkpoint)
            attempt.phase = "check"
            attempt.check(store)
    attempt.phase = "prepare"  # the writer's own reads before its _write (finding the sign-in)
    _writer(store, attempt.entry, attempt.group, attempt.plain, attempt.kinds, attempt.grant, attempt)
    if not attempt.recorded:  # the writer returned without the record phase: never a silent success
        raise SecretStoreError(f"the write of {attempt.entry} ended without its pending-write record; check the "
                               "entry and store it again")


def _commit_mark(attempt: Attempt) -> bool:
    """In the commit step, the repository's own mark (plan R11 rule 1), set once git commit's child
    was created or may have been (plan R15 fix 2): an interrupt can skip the finally of _write that
    copies it into the attempt."""
    return attempt.phase == "commit" and bool(attempt.store.repo.commit_started)


def _committed(attempt: Attempt) -> bool:
    """An attempt of this write started a commit: its record is kept (plan R11 rule 1)."""
    return attempt.committed or _commit_mark(attempt)


def write_typed(store: Any, entry: str, plain: dict | None = None, kinds: dict | None = None,
                grant: dict | None = None, group: str | None = None) -> None:
    """A first write of typed values: plain fields at their kinds and grant fields of one entry."""
    plain, grant = dict(plain or {}), dict(grant or {})
    kinds = dict(kinds) if kinds is not None else {f: "text" for f in plain}
    attempt = Attempt(store, entry, store._group(group), plain, kinds, grant, None, "first")
    try:
        _run(attempt)
    except BaseException as error:
        if attempt.record is not None and not _committed(attempt):  # no change to the store: nothing kept
            records(store).remove(attempt.record["id"])
        elif attempt.record is not None and isinstance(error, SecretStoreError):
            kept = attempt.record["id"]
            raise SecretStoreError(f"{error} The typed values of {entry} are kept on this computer (pending write "
                                   f"{kept}) and are saved at the next operation of the store.") from None
        raise
    finally:
        if attempt.record is not None:
            _in_flight(store).discard(attempt.record["id"])
    records(store).remove(attempt.record["id"])  # confirmed: pushed and checkpointed


def _again(store: Any, record: dict, mode: str) -> Attempt:
    return Attempt(store, record["entry"], record["group"], record["plain"], record["kinds"], record["grant"],
                   record, mode)


def _run_record(attempt: Attempt) -> None:
    flight = _in_flight(attempt.store)
    flight.add(attempt.record["id"])
    try:
        _run(attempt)
    finally:
        flight.discard(attempt.record["id"])


def replay(store: Any) -> None:
    """After a sync, under the repository lock: each record of this repository that is current, not
    held and not this instance's own write is replayed, saved or held. Only the record-local outcomes
    (a push that failed after the commit, a refusal by the store, an unexpected error building this
    record's change) are isolated; anything from the sync, a remote commit, the checkpoint or the pin
    stops the operation."""
    if store.policy is None or getattr(store, "_replaying", False):
        return
    store._replaying = True
    try:
        pending = records(store)
        for write_id, record in pending.all().items():
            if (record is None or record.get("legacy") or record["held"] or write_id in _in_flight(store)
                    or record["repository"] != store.policy.repository):
                continue
            attempt = _again(store, record, "replay")
            try:
                _run_record(attempt)
            except Saved:
                pending.remove(write_id)
                continue
            except Held:  # the mark only, on the record as this attempt last wrote it (correction 5)
                pending.write({**attempt.record, "held": True})
                continue
            except Exception as error:  # noqa: BLE001 - classified below; the rest is raised
                if not _isolated(attempt, error):
                    raise
                continue
            pending.remove(write_id)  # confirmed
    finally:
        store._replaying = False


def _isolated(attempt: Attempt, error: Exception) -> bool:
    """The three record-local rows of L4 rule 1; marks a refused record held. False: raise it."""
    from .repo import MovedHead, RefusedCommit
    if isinstance(error, (IntegrityError, RefusedCommit, MovedHead)):
        return False
    if attempt.phase in ("prepare", "build", "verify"):
        if isinstance(error, SecretStoreError):  # the store refuses the change: held for good
            records(attempt.store).write({**attempt.record, "held": True})
        return True  # an unexpected error building this record's change: untouched
    if attempt.phase == "record":
        return False  # a record that cannot be written stops the operation, whatever the error (R11 rule 2)
    return _commit_mark(attempt)  # the attempt started a commit and its push failed: record-local


def apply(store: Any, write_id: str) -> str:
    """unfinished --apply ID: the kept values over the present ones through the normal path, no
    precondition check, under the same record; removed once confirmed. Returns the entry name."""
    pending = records(store)
    record = pending.read(write_id) if pending.path(write_id).exists() else None
    if record is None or record.get("legacy"):
        raise SecretStoreError(f"pending write {write_id} is not on this computer, cannot be read or has no field "
                               "kinds; it is never applied")
    if record["repository"] != store.policy.repository:
        raise SecretStoreError(f"pending write {write_id} belongs to another store; run it with or without --team")
    _run_record(_again(store, record, "apply"))
    pending.remove(write_id)
    return record["entry"]
