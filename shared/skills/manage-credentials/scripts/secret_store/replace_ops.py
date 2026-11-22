"""Replacing a sign-in (design synced-secrets-repository.md, section 9, Handing over item 4, with the
deletion of section 7). An uncertain sign-in whose provider has no profile is ended by one
administrator commit that retires the ids of its oauth and grant objects (tombstones, refresher
mapping and index names removed); the refresher discards the journal record of the retired grant.

Before that commit the shared settings of the oauth object (every field that is not a token or
grant field) are kept in a local hand-over file beside the journal, encrypted to this computer's
X25519 key only, like the journal. The first authorisation under the same entry name and field
(oauth_ops.put_signin) applies them beneath the new record's own fields, and the file is removed
once the new sign-in is published. A failed commit or push leaves the old sign-in as it was and
the hand-over file in place; status reports a hand-over file whose sign-in was never completed.
Nothing is ever retried with the old refresh token. Messages name entries and fields only.

A team sign-in whose refresher is not an administrator (follow-up plan M2) is ended by the design's
own deletion: the refresher's command changes nothing and names the step (AdministratorStep), its
calling journal record keeping the sign-in blocked there (it refuses every refresh and survives
restarts); an administrator deletes exactly that sign-in with delete --entry E --field F
(delete_signin, plan R11 rule 3: the same one commit retiring both ids that replace makes, built by
_delete for both), signs in again and hands the new sign-in back with the existing handover; the
old refresher's next operation discards its journal record of the exact retired grant
(discard_retired). The entry's static object and its other sign-ins are never in that commit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import canonical, envelope, fileio, provider_profiles
from .delete_ops import build_signin_delete
from .errors import SecretStoreError
from .journal import KEY_SEPARATOR, Journal
from .keys import key_id
from .oauth_ops import PROVIDER_KEY, SignIn, find, read_shared, signin_fields
from .store_ops import GROUP

SUFFIX = ".handover"


def handover_key(repository: str, group: str, entry: str, field: str) -> str:
    """The sign-in's name and place, never its object ids: the new pair has new ids."""
    return f"{entry}#{field}{KEY_SEPARATOR}{repository}/{group}"


def _journal(store: Any) -> Journal:
    return Journal(store.config["checkpoint_dir"], store._identity().x25519)


def _path(journal: Journal, key: str) -> Path:
    return journal.folder / f"{journal._name(key)}{SUFFIX}"


def _header(journal: Journal, key: str) -> dict:
    return {"repository": "local-journal", "group": "local", "id": "handover-" + journal._name(key),
            "kind": "static", "revision": 1}


def _write(journal: Journal, key: str, record: dict) -> None:
    obj = envelope.seal(record, [(journal._key_id, journal._key.public_key())], _header(journal, key))
    fileio.write_durable(_path(journal, key), json.dumps(obj).encode("utf-8"))


def _open(journal: Journal, path: Path) -> dict:
    try:
        record = envelope.open_(json.loads(path.read_text("utf-8")), journal._key_id, journal._key)
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict) or not isinstance(record.get("settings"), dict):
        raise SecretStoreError(f"the hand-over file {path.name} cannot be read; remove it to sign in again "
                               "without the kept settings")
    return record


def kept_settings(store: Any, entry: str, field: str, group: str) -> dict:
    """The settings a replaced sign-in left for its first new authorisation, else {}."""
    journal = _journal(store)
    path = _path(journal, handover_key(store.policy.repository, group, entry, field))
    if not path.exists():
        return {}
    record = _open(journal, path)
    if (record.get("entry"), record.get("field"), record.get("repository"), record.get("group")) != (
            entry, field, store.policy.repository, group):
        raise SecretStoreError(f"the hand-over file {path.name} names another sign-in; nothing was saved")
    return dict(record["settings"])


def finish(store: Any, entry: str, field: str, group: str) -> None:
    """Remove the hand-over file once the new sign-in holding its settings is published."""
    journal = _journal(store)
    fileio.remove_durable(_path(journal, handover_key(store.policy.repository, group, entry, field)))


def pending(store: Any) -> list[str]:
    """'entry field' of every hand-over file of this store's repository whose sign-in was never
    completed (status). Files of another repository, or unreadable here, are left out."""
    checkpoint_dir = store.config.get("checkpoint_dir")
    if not checkpoint_dir or not (Path(checkpoint_dir) / "journal").is_dir():
        return []
    folder = Path(checkpoint_dir) / "journal"
    try:
        journal = _journal(store)
        policy = getattr(store, "policy", None)
        repository = policy.repository if policy is not None else canonical.loads(
            (Path(store.clone) / "policy.json").read_bytes()).get("repository")
    except (OSError, ValueError, AttributeError, SecretStoreError):
        return []
    found = []
    for path in sorted(folder.glob("*" + SUFFIX)):
        try:
            record = _open(journal, path)
        except SecretStoreError:
            continue
        if record.get("repository") == repository:
            found.append(f"{record.get('entry')} {record.get('field')}")
    return found


def _choose(store: Any, entry: str, field: str | None, group: str | None) -> SignIn:
    fields = signin_fields(store, entry, group)
    if field is None:
        if not fields:
            raise SecretStoreError(f"there is no sign-in {entry}")
        if len(fields) > 1:
            raise SecretStoreError(f"{entry} has several sign-ins ({', '.join(fields)}); name one with --field")
        field = fields[0]
    signin = find(store, entry, field, group)
    if signin is None:
        raise SecretStoreError(f"there is no sign-in {entry} {field}")
    return signin


class AdministratorStep(SecretStoreError):
    """The refresher is not an administrator (follow-up plan K.1): nothing was changed, and the
    message names the administrator's step. brain_secrets.py exits 3 on it, not 1."""


def _is_admin(store: Any) -> bool:
    return store.policy.is_admin_key(key_id(store._identity().ed25519.public_key()))


def _require_admin(store: Any, verb: str = "replaced") -> None:
    if not _is_admin(store):
        if verb == "deleted":
            raise SecretStoreError("only an administrator of the repository may delete a sign-in; nothing was deleted")
        raise SecretStoreError("only an administrator of the repository may replace a sign-in; nothing was changed")


def _settings(store: Any, signin: SignIn) -> dict | None:
    """The oauth object's shared settings, or None when this computer cannot read it."""
    dropped = (provider_profiles.token_fields(signin.provider) | provider_profiles.grant_fields(signin.provider)
               | {PROVIDER_KEY})
    try:
        shared = read_shared(store, signin)
    except SecretStoreError:
        return None
    return {k: v for k, v in shared.items() if k not in dropped}


def _keep(store: Any, journal: Journal, signin: SignIn, settings: dict) -> None:
    _write(journal, handover_key(store.policy.repository, signin.group, signin.entry, signin.field),
           {"entry": signin.entry, "field": signin.field, "repository": store.policy.repository,
            "group": signin.group, "settings": settings})


def _delete(store: Any, signin: SignIn, group: str | None, verb: str = "replaced") -> None:
    """The one administrator commit of section 7 retiring the two ids of this sign-in, for replace
    and for delete_signin alike. Inside the write, after its sync, the store's lookup must still
    return the same pair (else refused: the sign-in changed meanwhile), and the commit is built from
    those two ids alone, never from a scan of names."""

    def build() -> tuple[dict, str]:
        _require_admin(store, verb)
        current = find(store, signin.entry, signin.field, group)
        if current is None or (current.oauth_id, current.grant_id) != (signin.oauth_id, signin.grant_id):
            raise SecretStoreError(f"the sign-in {signin.entry} {signin.field} changed meanwhile; nothing was {verb}")
        return build_signin_delete(store.policy, store.checkpoint.objects, store._index(group), current.oauth_id,
                                   current.grant_id, store._identity().ed25519)
    store._write(build)


def delete_signin(store: Any, entry: str, field: str, group: str | None = None) -> SignIn:
    """delete --entry E --field F (plan R11, rule 3): an administrator deletes exactly the sign-in of
    entry E under field F, the pair the store's lookup returns, in the commit replace makes. Refused
    with nothing written when there is no such sign-in or this computer is not an administrator's."""
    if store.policy is None:
        store.open()
    signin = find(store, entry, field, group)
    if signin is None:
        raise SecretStoreError(f"{entry} has no sign-in {field}; nothing was deleted")
    _require_admin(store, "deleted")
    _delete(store, signin, group, "deleted")
    return signin


def delete_command(signin: SignIn) -> str:
    """The administrator's step: the deletion of exactly this sign-in (delete --field)."""
    group = f" --group {signin.group}" if signin.group != GROUP else ""
    return f'brain_secrets.py delete --entry "{signin.entry}" --field "{signin.field}"{group}'


def replace(store: Any, entry: str, field: str | None = None, group: str | None = None,
            even_if_working: bool = False, journal: Journal | None = None) -> SignIn:
    """Follow-up plan M2. On the refresher that is an administrator, as before: the journal record
    must be calling (uncertain) or even_if_working; the shared settings go into the hand-over file,
    one administrator commit deletes the sign-in, and the retired grant's journal record is
    discarded. On the refresher that is not an administrator: with an uncertain record
    AdministratorStep (nothing changed; the calling record keeps the sign-in blocked here), with
    even_if_working refused (a working sign-in moves by the cooperative handover). On any other
    computer refused: an administrator ends it with delete --field. Returns the replaced
    sign-in."""
    if store.policy is None:
        store.open()
    discard_retired(store)
    signin = _choose(store, entry, field, group)
    holder = f"{signin.refresher[0]}/{signin.refresher[1]}"
    admin = _is_admin(store)
    if not signin.mine:
        if admin:
            raise SecretStoreError(
                f"this sign-in refreshes on {holder}, not here, so nothing was changed: replace it there, or as an "
                f"administrator end it by deleting this sign-in: {delete_command(signin)}, then sign in again in the browser and "
                "hand the new "
                f"sign-in to {holder} with handover-release and handover-accept")
        raise SecretStoreError(f"this sign-in refreshes on {holder}; replace it there; nothing was changed")
    if even_if_working and not admin:
        group_flag = f" --group {signin.group}" if signin.group != GROUP else ""
        raise SecretStoreError(
            f"this computer is not an administrator's, so it does not replace a sign-in; nothing was changed. A "
            "working sign-in moves to an administrator by the cooperative handover: run handover-release "
            f'--entry "{entry}" --to PERSON/COMPUTER{group_flag} here, then an administrator runs handover-accept')
    journal = journal or _journal(store)
    key = signin.journal_key
    with journal.lock(key):  # no refresh of the old grant starts while it is replaced
        record = journal.read(key)
        if not even_if_working and (record is None or record["state"] != "calling"):
            raise SecretStoreError(f"the last refresh of {entry} {signin.field} is not uncertain, so the sign-in "
                                   "is working; nothing was changed. Pass --even-if-working to replace it anyway")
        if not admin:
            raise AdministratorStep(
                f"The last refresh of {entry} {signin.field} is uncertain and this computer is not an "
                "administrator's, so nothing was changed: the sign-in stays blocked on this computer and its old "
                "refresh token is never used again. Next step: an administrator ends it by deleting the sign-in "
                f"on their own computer with {delete_command(signin)}, signs in again in the browser there, and "
                "hands the new sign-in back to this computer with handover-release and handover-accept. This "
                "computer drops its record of the deleted sign-in at its next operation.")
        _keep(store, journal, signin, _settings(store, signin) or {})
        _delete(store, signin, group)
        fileio.remove_durable(journal.path(key))  # the retired grant's record: never used again
    return signin


def discard_retired(store: Any, journal: Journal | None = None) -> list[str]:
    """The old refresher after a replacement (follow-up plan K.1): every journal record of this
    store's repository whose grant id the policy has retired is removed, under its lock, so the entry
    is no longer held as uncertain and the old refresh token is never used. Returns the labels of the
    records removed. A record locked by a running refresh, or unreadable here, is left alone."""
    policy = getattr(store, "policy", None)
    checkpoint_dir = store.config.get("checkpoint_dir")
    if policy is None or not checkpoint_dir or not (Path(checkpoint_dir) / "journal").is_dir():
        return []
    retired = set(policy.doc.get("retired", {}))
    if not retired:
        return []
    journal = journal or _journal(store)
    removed = []
    for path in sorted(journal.folder.glob("*.journal")):
        try:
            key = envelope.open_(json.loads(path.read_text("utf-8")), journal._key_id, journal._key)["entry"]
        except (OSError, ValueError, KeyError, TypeError, SecretStoreError):
            continue
        repository, _sep, grant_id = str(key).rpartition(KEY_SEPARATOR)[2].rpartition("/")
        if repository != policy.repository or grant_id not in retired or journal.path(key) != path:
            continue
        try:
            with journal.lock(key):
                fileio.remove_durable(path)
        except SecretStoreError:
            continue
        removed.append(key.rpartition(KEY_SEPARATOR)[0])
    return removed


def next_step(signin: SignIn) -> str:
    return (f"The sign-in {signin.entry} {signin.field} is deleted and its old ids are retired; its shared "
            "settings are kept on this computer. Next step: disconnect the app at the provider where it offers "
            "that, then sign in again in the browser on this computer. The new sign-in gets the kept settings.")
