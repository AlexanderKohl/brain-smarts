"""Accepting one commit of the synced secrets store (design sections 6, 7 and 9). Every file of
the commit is checked together; the whole commit is refused if any file fails. Pure logic: no Git."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import envelope
from .accept_rules import (check_chain, check_index_payload, check_oauth_payload, check_object_shape,
                           check_readers, check_release, check_supersession, split_files)
from .checkpoint import Checkpoint, advance
from .errors import SecretStoreError
from .policy import INDEX_PREFIX, Policy, object_hash, validate_transition


@dataclass
class AcceptedObject:
    obj: dict
    payload: dict | None  # None when this computer cannot read the object
    usable: bool


@dataclass
class Accepted:
    policy: Policy
    checkpoint: Checkpoint
    objects: dict  # object id -> AcceptedObject


def accept_commit(current: Policy, checkpoint: Checkpoint, files: dict[str, Any], my_keys: dict,
                  latest_payloads: dict[str, dict] | None = None) -> Accepted:
    """files: repository path -> parsed JSON of every file the commit changes. my_keys: reader key
    id -> this computer's X25519 private key. latest_payloads: object id -> latest verified payload
    this computer holds (the oauth field-rule baseline). Raises SecretStoreError on any failure."""
    latest_payloads = latest_payloads or {}
    if (current.hash, current.epoch, current.repository) != (
            checkpoint.policy_hash, checkpoint.policy_epoch, checkpoint.repository):
        raise SecretStoreError("the trusted policy does not match the checkpoint")
    policy_doc, objects, records = split_files(files)
    # A policy change is validated first; objects are then judged against the resulting policy.
    result = validate_transition(current, policy_doc) if policy_doc is not None else current
    if records and policy_doc is None:
        raise SecretStoreError("release and supersession records need a policy change in the same commit")
    releases: dict[str, dict] = {}
    superseded: set[str] = set()
    for record in records.values():
        if record.get("type") == "release":
            grant = check_release(record, current, result, objects)
            if grant in releases:
                raise SecretStoreError("two releases for one grant in one commit")
            releases[grant] = record
        else:
            superseded.add(check_supersession(record, current, result))
    moved = {g for g in result.doc["refreshers"]
             if g in current.doc["refreshers"] and current.refresher(g) != result.refresher(g)}
    if set(releases) & superseded or set(releases) | superseded != moved:
        raise SecretStoreError("every grant whose refresher moves needs exactly one release or supersession")
    for oid, obj in objects.items():
        _structural(obj, oid, current, result, checkpoint, moved, releases, superseded)
    _completeness(current, result, checkpoint, objects, superseded)
    accepted = {oid: _content(obj, oid, result, my_keys, latest_payloads) for oid, obj in objects.items()}
    entries = dict(checkpoint.objects)
    for oid, obj in objects.items():
        entries[oid] = {"revision": obj["revision"], "hash": object_hash(obj)}
    new_checkpoint = advance(checkpoint, Checkpoint(result.repository, result.epoch, result.hash, entries))
    return Accepted(result, new_checkpoint, accepted)


def _structural(obj: dict, oid: str, prior: Policy, result: Policy, checkpoint: Checkpoint,
                moved: set[str], releases: dict[str, dict], superseded: set[str]) -> None:
    check_object_shape(obj, oid)
    if obj["repository"] != result.repository:
        raise SecretStoreError(f"object {oid}: belongs to another repository")
    if obj["policy_epoch"] != result.epoch:
        raise SecretStoreError(f"object {oid}: policy_epoch is not the current epoch")
    check_chain(obj, oid, checkpoint.objects.get(oid))
    if oid in prior.doc["retired"]:
        raise SecretStoreError(f"object {oid}: reuses a retired id")
    writer = obj["writer"]
    if obj["kind"] == "tombstone":
        # Authorised against the assignment of the policy before the change (section 7).
        group, _kind = prior.assignment(oid)
        if oid in result.doc["assignments"] or result.doc["retired"].get(oid) != object_hash(obj):
            raise SecretStoreError(f"object {oid}: tombstone does not match the policy's retired ids")
        if obj["group"] != group:
            raise SecretStoreError(f"object {oid}: group does not match the policy")
        check_readers(obj, oid, prior.readers_for(oid))
        if not prior.is_admin_key(writer):
            raise SecretStoreError(f"object {oid}: only an administrator may delete an object")
        prior.verify(obj, writer)
        if obj["operation"] is not None:
            raise SecretStoreError(f"object {oid}: a tombstone carries no operation id")
        return
    if oid in result.doc["retired"]:
        raise SecretStoreError(f"object {oid}: reuses a retired id")
    group, kind = result.assignment(oid)
    if obj["group"] != group:
        raise SecretStoreError(f"object {oid}: group does not match the policy")
    if obj["kind"] != kind:
        raise SecretStoreError(f"object {oid}: kind does not match the policy")
    check_readers(obj, oid, result.readers_for(oid))
    if kind != "grant" and oid in checkpoint.objects and not result.is_admin_key(writer):
        try:
            before = prior.readers_for(oid)
        except SecretStoreError:
            before = None
        if before != result.readers_for(oid):
            raise SecretStoreError(f"object {oid}: a revision that changes its readers must be an administrator's")
    refresher = result.refresher_sign_id(oid)
    if kind == "grant" and oid in moved:
        old = prior.refresher_sign_id(oid)
        if writer == old:
            # Cooperative release: signed by the source policy's refresher, bound by the release.
            if oid not in releases or releases[oid]["revision_hash"] != object_hash(obj):
                raise SecretStoreError(f"object {oid}: grant revision is not bound by a release")
            prior.verify(obj, writer)
        elif writer == result.recovery[1] or (writer == refresher and oid in superseded):
            result.verify(obj, writer)
        else:
            raise SecretStoreError(f"object {oid}: writer has no authority for this object")
        refresher_writer = writer in (old, refresher)
    else:
        if not result.may_write(writer, oid):
            raise SecretStoreError(f"object {oid}: writer has no authority for this object")
        result.verify(obj, writer)
        refresher_writer = refresher is not None and writer == refresher
    if obj["operation"] is not None and not refresher_writer:
        raise SecretStoreError(f"object {oid}: only the refresher may carry an operation id")


def _completeness(prior: Policy, result: Policy, checkpoint: Checkpoint, objects: dict, superseded: set) -> None:
    """Files a policy change obliges the same commit to carry."""
    for oid in set(result.doc["retired"]) - set(prior.doc["retired"]):
        if objects.get(oid, {}).get("kind") != "tombstone":
            raise SecretStoreError(f"retiring {oid} needs its tombstone in the same commit")
    for oid in set(result.doc["assignments"]) - set(prior.doc["assignments"]):
        if oid not in objects:
            raise SecretStoreError(f"new assignment {oid} needs its object in the same commit")
    for group in result.doc["groups"]:
        before = prior.assigned_ids(group) if group in prior.doc["groups"] else []
        if before != result.assigned_ids(group) and INDEX_PREFIX + group not in objects:
            raise SecretStoreError(f"group {group} changes its assignments, so its index must be in the same commit")
    for oid in checkpoint.objects:
        if oid in objects or oid in result.doc["retired"] or oid in superseded:
            continue
        try:
            before, after = prior.readers_for(oid), result.readers_for(oid)
        except SecretStoreError:
            continue  # no longer assigned (a removed group's index): nothing to re-key
        if before != after:
            raise SecretStoreError(f"object {oid}: its readers change, so it needs a new revision in this commit")


def _content(obj: dict, oid: str, result: Policy, my_keys: dict, latest: dict) -> AcceptedObject:
    """Content checks, only where this computer is a reader; otherwise opaque and unusable."""
    mine = [r["key"] for r in obj["readers"] if r["key"] in my_keys]
    if not mine:
        return AcceptedObject(obj, None, False)
    try:
        payload = envelope.open_(obj, mine[0], my_keys[mine[0]])
    except SecretStoreError as error:
        raise SecretStoreError(f"object {oid}: {error}") from None
    kind, usable = obj["kind"], True
    if kind == "tombstone" and payload != {}:
        raise SecretStoreError(f"object {oid}: a tombstone must be empty")
    if kind == "index":
        check_index_payload(payload, oid, result)
    if kind == "oauth":
        token_writer = obj["writer"] == result.refresher_sign_id(oid) and obj["operation"] is not None
        usable = check_oauth_payload(payload, latest.get(oid), obj, token_writer, result.is_admin_key(obj["writer"]),
                                     result.provider(oid))
    return AcceptedObject(obj, payload, usable)
