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
Nothing is ever retried with the old refresh token. Messages name entries and fields only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import canonical, envelope, fileio, provider_profiles
from .delete_ops import build_delete
from .errors import SecretStoreError
from .journal import KEY_SEPARATOR, Journal
from .keys import key_id
from .oauth_ops import PROVIDER_KEY, SignIn, find, read_shared, signin_fields, signin_names

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


def _require_admin(store: Any) -> None:
    if not store.policy.is_admin_key(key_id(store._identity().ed25519.public_key())):
        raise SecretStoreError("only an administrator of the repository may replace a sign-in; nothing was changed")


def replace(store: Any, entry: str, field: str | None = None, group: str | None = None,
            even_if_working: bool = False, journal: Journal | None = None) -> SignIn:
    """Refused unless this computer is the sign-in's refresher and an administrator, and the
    journal record is calling (uncertain) or even_if_working. Keeps the shared settings in the
    hand-over file, then deletes the sign-in in one administrator commit and discards the journal
    record of the retired grant. Returns the replaced sign-in."""
    if store.policy is None:
        store.open()
    signin = _choose(store, entry, field, group)
    if not signin.mine:
        raise SecretStoreError(f"this sign-in refreshes on {signin.refresher[0]}/{signin.refresher[1]}; "
                               "replace it there; nothing was changed")
    _require_admin(store)
    journal = journal or _journal(store)
    key = signin.journal_key
    with journal.lock(key):  # no refresh of the old grant starts while it is replaced
        record = journal.read(key)
        if not even_if_working and (record is None or record["state"] != "calling"):
            raise SecretStoreError(f"the last refresh of {entry} {signin.field} is not uncertain, so the sign-in "
                                   "is working; nothing was changed. Pass --even-if-working to replace it anyway")
        dropped = (provider_profiles.token_fields(signin.provider) | provider_profiles.grant_fields(signin.provider)
                   | {PROVIDER_KEY})
        settings = {k: v for k, v in read_shared(store, signin).items() if k not in dropped}
        _write(journal, handover_key(store.policy.repository, signin.group, entry, signin.field),
               {"entry": entry, "field": signin.field, "repository": store.policy.repository,
                "group": signin.group, "settings": settings})
        oauth_name = signin_names(entry, signin.field)[0]

        def build() -> tuple[dict, str]:
            _require_admin(store)
            current = find(store, entry, signin.field, group)
            if current is None or (current.oauth_id, current.grant_id) != (signin.oauth_id, signin.grant_id):
                raise SecretStoreError(f"the sign-in {entry} {signin.field} changed meanwhile; nothing was replaced")
            return build_delete(store.policy, store.checkpoint.objects, store._index(group), oauth_name,
                                store._identity().ed25519)
        store._write(build)
        fileio.remove_durable(journal.path(key))  # the retired grant's record: never used again
    return signin


def next_step(signin: SignIn) -> str:
    return (f"The sign-in {signin.entry} {signin.field} is deleted and its old ids are retired; its shared "
            "settings are kept on this computer. Next step: disconnect the app at the provider where it offers "
            "that, then sign in again in the browser on this computer. The new sign-in gets the kept settings.")
