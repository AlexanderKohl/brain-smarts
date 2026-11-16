"""Token relay, part two: the relayed store around one local JSON store.

The rules, in short:

- Chain keys are the keys a provider's token answer sets (access_token, refresh_token, expiry and
  so on); everything else in the dictionary is other data (a selected tenant, a catalogue).
- Only a lease holder changes chain keys in the shared record. Its save is a compare-and-swap
  against the tag its own lease write returned; a conflict means the lease was taken over, and
  the new token stays on this computer as unpushed.
- A save without the lease applies only this brain's other-data changes on top of the latest
  remote record, and adopts the remote chain keys locally. Its changes are first folded into
  any unpushed ones, so one save makes at most one version. It never pushes while another
  brain's lease is on the record (that would break the holder's compare-and-swap).
- The local _relay_version is always the last remote version this brain synced or pushed. An
  unpushed local change carries _relay_unpushed, _relay_base_version (the remote version it was
  made from) and _relay_changed (the other-data keys this brain changed).
- The holder is the computer, not the process: the hostname plus a random id kept in a
  non-secret file beside the vault (holder_name). A lease whose holder is this computer, or
  whose id a failed leased save kept locally (_relay_lease_id), is this computer's own in every
  process: recovery pushes over it and a new lease replaces it without waiting.
- Recovery: only an unpushed marker of "token" may change the shared chain keys. When the remote
  version still equals the base version the local token is pushed, unless another brain holds a
  lease that has not yet run out on this computer's own clock: then nothing is written and the
  unpushed token is kept as it is. When the remote has moved on, the remote wins for the chain
  keys (the unpushed token is dropped, and so is its "token" marker) and the other-data changes
  are re-applied. A data-only unpushed change never touches the chain keys.
- Another brain's lease is timed from when this computer first saw it. While a local change is
  unpushed, that first sight (lease id and this computer's clock reading) is kept as
  _relay_seen, so later short-lived processes continue the same countdown. A push of other data
  waits for such a lease only until it has run out, as recovery does. No clock is ever compared
  with another computer's.
- A leased save folds this computer's pending other-data changes into what it writes.
- A sync adopts the remote record when it is newer, or at the same version when this computer's
  copy holds neither an access nor a refresh token (a cleared computer).
- load() outside a lock offers an unpushed change again, at most once every 30 seconds per
  process, so a leased save whose write failed does not wait for the next refresh.
- Fail closed for a listed entry: no remote record, a remote version lower than the local one, a
  record that does not decrypt or a missing key always raise. Only an unreachable relay or a
  conflict is carried on from, and only where the rules say so. The one exception: a forced lock
  for a new authorisation (rotation_lock(refresh=True, new_authorisation=True)) that meets a
  missing record or one it cannot use (wrong key, damaged record, rollback) goes ahead locally,
  without a lease, and warns that token_relay.py seed --entry NAME --replace must be run next.
"""

from __future__ import annotations

import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TextIO

from portable_vault import CredentialError
from token_relay_backend import (
    MAX_LEASE_SECONDS,
    MIN_LEASE_SECONDS,
    Conflict,
    RelayIntegrityError,
    RelayUnavailable,
    build_record,
    decrypt_token,
    dump_record,
    parse_record,
    remote_name,
    strip_bookkeeping,
    validate_entry,
)


DEFAULT_LEASE_SECONDS = 300
LEASE_GRACE_SECONDS = 10
DEFAULT_LEEWAY_SECONDS = 90
POLL_SECONDS = 2.0
PUSH_ATTEMPTS = 3
RECOVERY_INTERVAL_SECONDS = 30
# When load() last offered an unpushed change again, per (entry, holder): once per process.
_LAST_RECOVERY: dict[tuple[str, str], float] = {}
# The keys a token answer sets in either client; each client passes its own exact set.
DEFAULT_CHAIN_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "expires_at",
        "expires_in",
        "obtained_at",
        "token_type",
        "scope",
        "id_token",
        "refresh_token_id",
    }
)


class RelayUnseeded(RelayIntegrityError):
    """A listed entry has no shared record."""


HOLDER_ID_NAME = "token-relay-computer-id"
_HOLDER_ID_PATTERN = re.compile(r"\A[0-9a-f]{8}\Z")


def holder_name(vault_path: Path | str | None = None) -> str:
    """This computer's name on the shared record: the hostname plus a random 8-hex-character id
    kept in a small non-secret file beside the vault file (made on first use, read afterwards).
    It is the same in every process of one computer; the local rotation lock keeps those apart."""
    import socket

    from portable_vault import PortableVault

    path = PortableVault(vault_path).path.parent / HOLDER_ID_NAME
    for _ in range(2):
        try:
            text = path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            text = ""
        except (OSError, UnicodeError) as exc:
            raise CredentialError(f"The token relay computer id cannot be read: {path}") from exc
        if _HOLDER_ID_PATTERN.match(text):
            return f"{socket.gethostname()}-{text}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if text:  # unreadable content: replace it
                path.write_text(os.urandom(4).hex() + "\n", encoding="ascii")
            else:  # exclusive create, so two first processes agree on one id
                with path.open("x", encoding="ascii") as handle:
                    handle.write(os.urandom(4).hex() + "\n")
        except FileExistsError:
            continue
        except OSError as exc:
            raise CredentialError(f"The token relay computer id cannot be written: {path}") from exc
    raise CredentialError(f"The token relay computer id cannot be read: {path}")


def _version(raw: dict[str, Any]) -> int:
    value = raw.get("_relay_version", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _base_version(raw: dict[str, Any]) -> int:
    value = raw.get("_relay_base_version")
    return value if isinstance(value, int) and not isinstance(value, bool) else _version(raw)


def _carried(raw: dict[str, Any]) -> dict[str, Any]:
    """The lease bookkeeping an unpushed change keeps while it is rewritten."""
    return {key: raw[key] for key in ("_relay_lease_id", "_relay_seen") if key in raw}


def _entry_of(token: dict[str, Any], key: str) -> tuple[bool, Any]:
    return (key in token, token.get(key))


def other_changes(base: dict[str, Any], mine: dict[str, Any], chain_keys: Iterable[str]) -> set[str]:
    """The other-data keys whose presence or value differs between base and mine."""
    keys = (set(base) | set(mine)) - set(chain_keys)
    return {key for key in keys if _entry_of(base, key) != _entry_of(mine, key)}


def apply_other(target: dict[str, Any], source: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """target with the given keys taken from source (a key missing from source is removed)."""
    result = dict(target)
    for key in keys:
        if key in source:
            result[key] = source[key]
        else:
            result.pop(key, None)
    return result


def _now_iso(clock: Callable[[], float]) -> str:
    import datetime as dt

    return dt.datetime.fromtimestamp(clock(), dt.timezone.utc).isoformat(timespec="seconds")


class RelayedStore:
    """The relayed behaviour around a local JSON store (load, save, clear, sync, rotation_lock)."""

    def __init__(
        self,
        local: Any,
        entry: str,
        *,
        backend: Any,
        key_provider: Callable[[], bytes],
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        holder: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        stderr: TextIO | None = None,
        chain_keys: Iterable[str] | None = None,
    ) -> None:
        if not MIN_LEASE_SECONDS <= lease_seconds <= MAX_LEASE_SECONDS:
            raise CredentialError(
                f"The relay lease must be {MIN_LEASE_SECONDS} to {MAX_LEASE_SECONDS} seconds."
            )
        self.local = local
        self.entry = validate_entry(entry)
        self.name = remote_name(entry)
        self.backend = backend
        self._key_provider = key_provider
        self._key: bytes | None = None
        self.lease_seconds = lease_seconds
        self.holder = holder or holder_name()
        self.clock = clock  # this computer's own clock, for timing another brain's lease
        self.wall_clock = wall_clock  # for the provider's expires_at, as before the relay
        self.sleep = sleep
        self._stderr = stderr
        self.chain_keys = frozenset(chain_keys or DEFAULT_CHAIN_KEYS)
        self._in_lock = False
        self._local_only = False  # a new authorisation with no shared record yet
        self._lease: dict[str, Any] | None = None
        self._base: dict[str, Any] = {}
        self._seen: tuple[str, float] | None = None  # another brain's lease id, first seen at
        self._deferred = False  # the last recovery waited for another brain's lease

    def set_chain_keys(self, keys: Iterable[str]) -> None:
        self.chain_keys = frozenset(keys)

    # -- helpers -----------------------------------------------------------------------------

    def _warn(self, message: str) -> None:
        print(f"token relay: {message}", file=self._stderr or sys.stderr, flush=True)

    def key(self) -> bytes:
        if self._key is None:
            self._key = self._key_provider()
        return self._key

    def _chain(self, token: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in token.items() if key in self.chain_keys}

    def _local_token(self) -> dict[str, Any]:
        """This computer's copy without bookkeeping, never offering anything again (load does)."""
        return strip_bookkeeping(self.local.load())

    def _own_lease(self, lease: dict[str, Any], raw: dict[str, Any] | None = None) -> bool:
        """A lease is this computer's own, in every process, when its holder is this computer or
        its id is the one a failed leased save kept locally (_relay_lease_id)."""
        if lease["holder"] == self.holder:
            return True
        raw = self.local.load() if raw is None else raw
        return raw.get("_relay_lease_id") == lease["id"]

    def _lease_ends(self, record: dict[str, Any]) -> float | None:
        """When another brain's lease on the record ends on this computer's clock, timed from
        when this computer first saw it; None when no other brain holds one. While a local change
        is unpushed, the first sight is kept in local bookkeeping (_relay_seen), so a later
        process on this computer continues the same countdown instead of restarting it. Only
        this computer's clock is compared with itself; a kept reading later than now (a restart
        of the clock) starts the countdown again."""
        lease = record.get("lease")
        if lease is None:
            return None
        raw = self.local.load()
        if self._own_lease(lease, raw):
            return None
        now = self.clock()
        if self._seen is not None and (self._seen[0] != lease["id"] or self._seen[1] > now):
            self._seen = None
        kept = raw.get("_relay_seen")
        if (
            self._seen is None
            and isinstance(kept, list)
            and len(kept) == 2
            and kept[0] == lease["id"]
            and isinstance(kept[1], (int, float))
            and not isinstance(kept[1], bool)
            and kept[1] <= now
        ):
            self._seen = (lease["id"], float(kept[1]))
        if self._seen is None:
            self._seen = (lease["id"], now)
        if raw.get("_relay_unpushed") and kept != [lease["id"], self._seen[1]]:
            self.local.save({**raw, "_relay_seen": [lease["id"], self._seen[1]]})
        return self._seen[1] + lease["seconds"]

    def _expiring(self, token: dict[str, Any], leeway_seconds: float) -> bool:
        """Expiry is the provider's own timestamp against this computer's clock, as before the
        relay existed; it never compares two computers' clocks."""
        if not token.get("access_token"):
            return True
        try:
            expires_at = float(token.get("expires_at", 0))
        except (TypeError, ValueError):
            return True
        return expires_at <= self.wall_clock() + leeway_seconds

    def _read(self) -> tuple[dict[str, Any] | None, str | None]:
        content, tag = self.backend.get(self.name)
        if content is None:
            return None, None
        return parse_record(content, self.entry), tag

    def _verified(self, record: dict[str, Any] | None) -> dict[str, Any]:
        """The remote token, after every fail-closed check (rule G)."""
        if record is None:
            raise RelayUnseeded(
                f"{self.entry} is listed for the relay but has no shared record; run "
                "token_relay.py seed on the computer that holds the sign-in."
            )
        local_version = _version(self.local.load())
        if record["version"] < local_version:
            raise RelayIntegrityError(
                f"The shared record for {self.entry} is at version {record['version']}, older "
                f"than this computer's {local_version}: refused as a possible rollback."
            )
        return decrypt_token(self.key(), self.entry, record)

    def _write(
        self, version: int, token: dict[str, Any], lease: Any, tag: str | None, action: str
    ) -> tuple[dict[str, Any], str]:
        record = build_record(
            self.key(), self.entry, version, token,
            lease=lease, holder=self.holder, updated_at=_now_iso(self.wall_clock),
        )
        message = f"token-relay: {self.entry} {action} version {version} by {self.holder}"
        return record, self.backend.put(self.name, dump_record(record), tag, message)

    def _lease_blocks(self, record: dict[str, Any]) -> bool:
        """Another brain's lease that has not yet run out on this computer's clock."""
        ends = self._lease_ends(record)
        return ends is not None and self.clock() < ends

    def _adopt(self, version: int, token: dict[str, Any]) -> None:
        self.local.save({**strip_bookkeeping(token), "_relay_version": version})

    def _pending(self, source: dict[str, Any], changed: set[str]) -> tuple[dict[str, Any], set[str]]:
        """Fold this computer's earlier unpushed other-data changes into a new set of changes."""
        raw = self.local.load()
        if not raw.get("_relay_unpushed"):
            return source, set(changed)
        earlier = raw.get("_relay_changed")
        earlier = {key for key in earlier if isinstance(key, str)} if isinstance(earlier, list) else set()
        return apply_other(strip_bookkeeping(raw), source, changed), earlier | set(changed)

    def _keep_unpushed(
        self,
        chain_token: dict[str, Any],
        base_version: int,
        source: dict[str, Any],
        changed: set[str],
        new_token: bool = False,
        lease_id: str | None = None,
    ) -> None:
        """_relay_unpushed is "token" when the chain keys are a new token (a lease-held save that
        could not be pushed), else true (other data only). An earlier "token" marker is carried
        over only while the base version is unchanged: once recovery has dropped the token for a
        newer remote one, the marker goes too. lease_id is this computer's lease that the failed
        save left on the record; it is kept as _relay_lease_id, so every later process treats a
        remote lease with that id as this computer's own."""
        raw = self.local.load()
        keep_token = raw.get("_relay_unpushed") == "token" and base_version == _base_version(raw)
        source, changed = self._pending(source, changed)
        token = apply_other(strip_bookkeeping(chain_token), source, changed)
        carried = _carried(raw)
        if lease_id is not None:
            carried["_relay_lease_id"] = lease_id
        self.local.save(
            {
                **token,
                **carried,
                "_relay_version": base_version,
                "_relay_unpushed": "token" if new_token or keep_token else True,
                "_relay_base_version": base_version,
                "_relay_changed": sorted(changed),
            }
        )

    def _fold_unpushed(self, mine: dict[str, Any], changed: set[str]) -> None:
        """Fold a save's other-data changes into this computer's unpushed changes before any
        recovery runs, so the earlier and the new changes are pushed as one version."""
        raw = self.local.load()
        source, changed = self._pending(mine, changed)
        self.local.save(
            {
                **apply_other(strip_bookkeeping(raw), source, changed),
                **_carried(raw),
                "_relay_version": _version(raw),
                "_relay_unpushed": raw.get("_relay_unpushed") or True,
                "_relay_base_version": _base_version(raw),
                "_relay_changed": sorted(changed),
            }
        )

    # -- sync, recovery and the lease --------------------------------------------------------

    def _sync_locked(self) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        """Read and verify the remote record, recover an unpushed local change, adopt a newer
        remote (or the same version on a cleared computer). Returns the record, its tag and its
        token as they stand afterwards."""
        self._deferred = False
        record, tag = self._read()
        remote = self._verified(record)
        raw = self.local.load()
        if raw.get("_relay_unpushed"):
            return self._recover(raw, record, tag, remote)
        local = strip_bookkeeping(raw)
        cleared = not local.get("access_token") and not local.get("refresh_token")
        if record["version"] > _version(raw) or cleared:
            self._adopt(record["version"], remote)
        return record, tag, remote

    def _recover(
        self, raw: dict[str, Any], record: dict[str, Any], tag: str | None, remote: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        """Rule F: push the unpushed token when the remote has not moved since its base; else the
        remote wins for the chain keys and this brain's other-data changes are re-applied. While
        another brain holds a lease that has not run out on this computer's clock, a remote at
        the base version is left alone and the unpushed token is kept as it is: that brain may
        be refreshing, and its compare-and-swap must not be broken. This computer's own lease
        (its holder, or the id a failed leased save kept) is pushed over at once. Only an
        unpushed marker of "token" may change the shared chain keys: a data-only change never
        does, whatever this computer's copy holds (a cleared computer, a stale load)."""
        mine = strip_bookkeeping(raw)
        base_version = _base_version(raw)
        changed = raw.get("_relay_changed")
        changed = {key for key in changed if isinstance(key, str)} if isinstance(changed, list) else set()
        for _ in range(PUSH_ATTEMPTS):
            if raw.get("_relay_unpushed") == "token" and self._chain(mine) != self._chain(remote):
                if record["version"] == base_version:
                    if self._lease_blocks(record):
                        self._deferred = True
                        return record, tag, remote
                    try:
                        record, tag = self._write(base_version + 1, mine, None, tag, "recover")
                    except Conflict:
                        record, tag = self._read()
                        remote = self._verified(record)
                        continue
                    self._adopt(record["version"], mine)
                    return record, tag, mine
                self._warn(
                    f"the {self.entry} token kept on this computer was dropped: another "
                    "brain shared a newer one first."
                )
            return self._push_changes(mine, changed, record, tag, remote)
        raise Conflict(f"The relay file for {self.entry} kept changing; three attempts failed.")

    def _push_changes(
        self,
        source: dict[str, Any],
        changed: set[str],
        record: dict[str, Any],
        tag: str | None,
        remote: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        """Rule C: this brain's other-data changes on top of the latest remote record; the
        remote chain keys are adopted locally. Another brain's lease blocks the push only until
        it has run out on this computer's clock, as in recovery."""
        source, changed = self._pending(source, changed)
        for _ in range(PUSH_ATTEMPTS):
            merged = apply_other(remote, source, changed)
            if merged == remote:
                self._adopt(record["version"], remote)
                return record, tag, remote
            if self._lease_blocks(record):
                break
            try:
                new_record, new_tag = self._write(record["version"] + 1, merged, None, tag, "save")
            except Conflict:
                record, tag = self._read()
                remote = self._verified(record)
                continue
            self._adopt(new_record["version"], merged)
            return new_record, new_tag, merged
        self._keep_unpushed(remote, record["version"], source, changed)
        self._warn(
            f"a change to {self.entry} is kept on this computer and will be shared at the next "
            "lock or save (another brain holds the lease or the record kept changing)."
        )
        return record, tag, remote

    def _take_lease(self, forced: bool, leeway_seconds: float) -> None:
        """Sync, then take the lease when forced or when the synced token expires within the
        leeway. Another brain's lease is timed on this computer's clock from when it was first
        seen; this brain waits until it ends plus the grace, then refuses. When the sync's
        recovery waited for that lease, the next sync offers the unpushed token again before any
        lease is taken."""
        deadline: float | None = None
        conflicts = 0
        while True:
            record, tag, remote = self._sync_locked()
            if not forced and not self._expiring(self._local_token(), leeway_seconds):
                return
            ends = self._lease_ends(record)
            now = self.clock()
            if ends is not None and (now < ends or self._deferred):
                if now < ends:
                    if deadline is None:
                        deadline = now + record["lease"]["seconds"] + LEASE_GRACE_SECONDS
                    if now >= deadline:
                        raise CredentialError(
                            f"Another brain still holds the relay lease for {self.entry}; "
                            "the refresh is refused."
                        )
                    self.sleep(max(0.1, min(POLL_SECONDS, ends - now, deadline - now)))
                continue
            taken = {"holder": self.holder, "id": os.urandom(8).hex(), "seconds": self.lease_seconds}
            try:
                _, lease_tag = self._write(record["version"], remote, taken, tag, "lease")
            except Conflict:
                conflicts += 1
                if conflicts >= 10:
                    raise
                continue
            self._lease = {
                "tag": lease_tag, "version": record["version"], "token": remote, "id": taken["id"]
            }
            return

    def _release_lease(self) -> None:
        lease, self._lease = self._lease, None
        try:
            self._write(lease["version"], lease["token"], None, lease["tag"], "release")
        except (RelayUnavailable, Conflict):
            self._warn(f"the lease on {self.entry} could not be released; it will run out.")

    # -- the store interface -----------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """This computer's copy. Outside a lock, an unpushed change is offered again first, at
        most once every RECOVERY_INTERVAL_SECONDS per process; only an unreachable relay or a
        conflict is swallowed."""
        raw = self.local.load()
        if raw.get("_relay_unpushed") and not self._in_lock:
            key = (self.entry, self.holder)
            now = self.clock()
            last = _LAST_RECOVERY.get(key)
            if last is None or now - last >= RECOVERY_INTERVAL_SECONDS:
                _LAST_RECOVERY[key] = now
                try:
                    with self.local.rotation_lock():
                        self._sync_locked()
                except (RelayUnavailable, Conflict):
                    pass
                raw = self.local.load()
        return strip_bookkeeping(raw)

    def sync(self) -> None:
        """Adopt the remote record without a lease (a computer whose local entry is empty)."""
        with self.local.rotation_lock():
            self._sync_locked()

    @contextmanager
    def rotation_lock(
        self,
        *,
        refresh: bool = False,
        leeway_seconds: float | None = None,
        new_authorisation: bool = False,
    ) -> Iterator[None]:
        """new_authorisation=True (with refresh=True) tells the store that the lock is for a code
        exchange: only then may a missing or unusable shared record be met with a local-only
        sign-in."""
        leeway = DEFAULT_LEEWAY_SECONDS if leeway_seconds is None else leeway_seconds
        with self.local.rotation_lock():
            self._enter(refresh, leeway, new_authorisation)
            try:
                yield
            finally:
                self._in_lock = False
                self._local_only = False
                if self._lease is not None:
                    self._release_lease()

    def _enter(self, forced: bool, leeway_seconds: float, new_authorisation: bool = False) -> None:
        self._lease = None
        self._local_only = False
        try:
            self._take_lease(forced, leeway_seconds)
        except RelayIntegrityError as exc:
            # A new authorisation gets past a record it cannot use: none yet, a wrong key, a
            # damaged record or a rollback. Anything else that is not a new authorisation stays
            # refused.
            if not (forced and new_authorisation):
                raise
            self._local_only = True
            problem = (
                "has no shared record yet" if isinstance(exc, RelayUnseeded)
                else "has a shared record this computer cannot use (wrong key, damaged record or rollback)"
            )
            self._warn(
                f"{self.entry} {problem}, so this new authorisation is kept on this computer only, "
                f"without a lease. Run token_relay.py seed --entry {self.entry} --replace next."
            )
        except RelayUnavailable as exc:
            if forced or self._expiring(self._local_token(), leeway_seconds):
                raise CredentialError(
                    f"The token relay cannot be reached, so the lease for {self.entry} cannot be "
                    "taken and the refresh or new authorisation is refused: another brain may "
                    "hold a newer token. Try again when the relay is reachable."
                ) from exc
            self._warn(f"unreachable; carrying on with the local {self.entry} token, which is still valid.")
        self._base = self._local_token()
        self._in_lock = True

    def save(self, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise CredentialError("JSON credential values must be objects.")
        mine = strip_bookkeeping(value)
        if self._in_lock:
            if self._local_only:
                version = _version(self.local.load())
                self.local.save({**mine, "_relay_version": version} if version else mine)
            elif self._lease is not None:
                self._save_leased(mine)
            else:
                self._save_unleased(mine)
            return
        with self.local.rotation_lock():
            self._base = self._local_token()
            self._save_unleased(mine)

    def _save_leased(self, mine: dict[str, Any]) -> None:
        """Rule B: compare-and-swap against the tag of this brain's own lease write. This
        computer's pending data-only changes are folded in first, so a save that leaves them out
        (a token answer with a few carried fields) does not drop them; only a value this save
        itself sets for such a key wins over the pending one."""
        lease, self._lease = self._lease, None
        version = lease["version"] + 1
        changed = other_changes(self._base, mine, self.chain_keys)
        raw = self.local.load()
        if raw.get("_relay_unpushed"):
            earlier = raw.get("_relay_changed")
            earlier = {key for key in earlier if isinstance(key, str)} if isinstance(earlier, list) else set()
            folded = {key for key in earlier if not (key in mine and key in changed)}
            mine = apply_other(mine, strip_bookkeeping(raw), folded)
            changed |= earlier
        try:
            self._write(version, mine, None, lease["tag"], "save")
        except (RelayUnavailable, Conflict) as exc:
            self._keep_unpushed(mine, lease["version"], mine, changed, new_token=True, lease_id=lease["id"])
            reason = "the lease was taken over" if isinstance(exc, Conflict) else "the relay is unreachable"
            self._warn(
                f"the new {self.entry} token is kept on this computer and offered again at the "
                f"next lock or save ({reason})."
            )
            self._base = mine
            return
        self._adopt(version, mine)
        self._base = mine

    def _save_unleased(self, mine: dict[str, Any]) -> None:
        """Rule C: never change the chain keys; push only this brain's other-data changes. The
        changes are folded into the unpushed ones first, and the sync's recovery pushes them all
        as one version. A refused sync (integrity, key) leaves this computer's copy as it was."""
        base = self._base
        changed = other_changes(base, mine, self.chain_keys)
        if self._chain(mine) != self._chain(base):
            self._warn(
                f"a save to {self.entry} without the lease cannot change the sign-in itself; "
                "only its other data is kept."
            )
        before = self.local.load()
        if changed:
            self._fold_unpushed(mine, changed)
        try:
            self._sync_locked()
        except (RelayUnavailable, Conflict):
            if changed:
                self._warn(f"a change to {self.entry} is kept on this computer; the relay is unreachable.")
        except Exception:
            self.local.save(before)
            raise
        self._base = self._local_token()

    def clear(self) -> None:
        """Clear this computer's copy only; the shared record is left for the other brains."""
        version = _version(self.local.load())
        self.local.save({"_relay_version": version} if version else {})
