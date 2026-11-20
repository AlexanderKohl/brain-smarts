"""Policy document of the synced secrets store (design synced-secrets-repository.md, section 6):
shape checks, readers and writer authority by object id, transition validation and the trust root."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import hmac
import re
import secrets
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

from . import canonical, hpke, signing
from .errors import SecretStoreError
from .keys import key_id, raw_public

SCHEMA = 1
ASSIGNABLE_KINDS = frozenset({"static", "oauth", "grant"})
INDEX_PREFIX = "index-"
NAME = re.compile(r"[A-Za-z0-9_-]{1,128}")
HASH = re.compile(r"[0-9a-f]{64}")
FIELDS = frozenset({"schema", "type", "repository", "epoch", "previous", "people", "recovery", "groups",
                    "assignments", "refreshers", "retired", "administrators", "cites", "writer", "signature"})
RECOVERY = ("", "recovery")  # signer identity of the recovery key; "" is never a valid login


def object_hash(obj: Any) -> str:
    """Hex SHA-256 of the canonical bytes of a whole signed document (signature included)."""
    return hashlib.sha256(canonical.dumps(obj)).hexdigest()


def fingerprint(doc: dict[str, Any]) -> str:
    """The trust root fingerprint people compare on two screens: its hash in groups of four."""
    digest = object_hash(doc)
    return " ".join(digest[i:i + 4] for i in range(0, len(digest), 4))


def public_entry(x25519_public: X25519PublicKey, ed25519_public: Ed25519PublicKey) -> dict[str, str]:
    return {"x25519": base64.b64encode(raw_public(x25519_public)).decode("ascii"),
            "ed25519": base64.b64encode(raw_public(ed25519_public)).decode("ascii")}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecretStoreError("policy refused: " + message)


def _name(value: Any) -> bool:
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def _hash(value: Any) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _keys(entry: Any, label: str) -> tuple[X25519PublicKey, Ed25519PublicKey]:
    _require(isinstance(entry, dict) and set(entry) == {"x25519", "ed25519"}, f"{label} needs x25519 and ed25519 keys")
    try:
        x_raw = base64.b64decode(entry["x25519"], validate=True)
        e_raw = base64.b64decode(entry["ed25519"], validate=True)
        hpke.load_public_key(x_raw)  # refuses low-order and malformed points
        return X25519PublicKey.from_public_bytes(x_raw), Ed25519PublicKey.from_public_bytes(e_raw)
    except (SecretStoreError, binascii.Error, ValueError, TypeError):
        raise SecretStoreError(f"policy refused: {label} has a malformed public key") from None


class Policy:
    """A shape-checked policy document. Its signature and transition are checked separately."""

    def __init__(self, doc: Any):
        _require(isinstance(doc, dict) and set(doc) == FIELDS, "unexpected or missing fields")
        _require(doc["schema"] == SCHEMA and doc["type"] == "policy", "unknown schema or type")
        _require(_name(doc["repository"]), "repository id malformed")
        epoch = doc["epoch"]
        _require(_int(epoch) and epoch >= 1, "epoch malformed")
        _require(doc["previous"] is None if epoch == 1 else _hash(doc["previous"]), "previous hash malformed")
        self.doc, self.epoch, self.repository, self.hash = doc, epoch, doc["repository"], object_hash(doc)
        self.enc_keys: dict[str, X25519PublicKey] = {}
        self.sign_keys: dict[str, Ed25519PublicKey] = {}
        self.signers: dict[str, tuple[str, str]] = {}
        self.computers: dict[tuple[str, str], tuple[str, str]] = {}  # (person, computer) -> (enc id, sign id)
        self._add(RECOVERY, doc["recovery"], "recovery key")
        people = doc["people"]
        _require(isinstance(people, dict), "people malformed")
        for person, record in people.items():
            _require(_name(person) and isinstance(record, dict)
                     and set(record) == {"computers", "disabled_refresher"}
                     and isinstance(record["computers"], dict), "person malformed")
            for computer, entry in record["computers"].items():
                _require(_name(computer), "computer name malformed")
                self._add((person, computer), entry, f"computer {person}/{computer}")
            disabled = record["disabled_refresher"]
            _require(isinstance(disabled, list) and all(_name(c) for c in disabled)
                     and len(set(disabled)) == len(disabled), "disabled_refresher malformed")
        admins = doc["administrators"]
        _require(isinstance(admins, list) and all(_name(a) and a in people for a in admins)
                 and len(set(admins)) == len(admins), "administrators malformed")
        groups = doc["groups"]
        _require(isinstance(groups, dict) and all(
            _name(g) and isinstance(m, list) and all(_name(p) and p in people for p in m) and len(set(m)) == len(m)
            for g, m in groups.items()), "groups malformed")
        retired = doc["retired"]
        _require(isinstance(retired, dict) and all(_name(i) and _hash(h) for i, h in retired.items()), "retired malformed")
        assignments = doc["assignments"]
        _require(isinstance(assignments, dict), "assignments malformed")
        for oid, a in assignments.items():
            _require(_name(oid) and not oid.startswith(INDEX_PREFIX), "assignment id malformed")
            _require(oid not in retired, f"assignment {oid} reuses a retired id")
            _require(isinstance(a, dict) and set(a) == {"group", "kind"} and isinstance(a["group"], str)
                     and a["group"] in groups and a["kind"] in ASSIGNABLE_KINDS, f"assignment {oid} malformed")
        refreshers = doc["refreshers"]
        _require(isinstance(refreshers, dict), "refreshers malformed")
        self.oauth_refresher: dict[str, str] = {}
        for grant, r in refreshers.items():
            _require(_name(grant) and assignments.get(grant, {}).get("kind") == "grant", "refresher named for a non-grant")
            _require(isinstance(r, dict) and set(r) == {"person", "computer", "oauth"} and _name(r["person"])
                     and _name(r["computer"]) and (r["person"], r["computer"]) in self.computers,
                     f"refresher of {grant} malformed or unknown")
            _require(r["computer"] not in people[r["person"]]["disabled_refresher"], f"refresher of {grant} is disabled")
            oauth = assignments.get(r["oauth"]) if _name(r["oauth"]) else None
            _require(oauth is not None and oauth["kind"] == "oauth" and oauth["group"] == assignments[grant]["group"]
                     and r["oauth"] not in self.oauth_refresher, f"refresher of {grant} names a bad oauth id")
            self.oauth_refresher[r["oauth"]] = grant
        _require(all(a["kind"] != "grant" or oid in refreshers for oid, a in assignments.items()), "a grant has no refresher")
        _require(isinstance(doc["cites"], list) and all(_hash(c) for c in doc["cites"]), "cites malformed")
        _require(isinstance(doc["writer"], str) and isinstance(doc["signature"], str), "writer or signature missing")

    def _add(self, who: tuple[str, str], entry: Any, label: str) -> None:
        x, e = _keys(entry, label)
        enc_id, sign_id = key_id(x), key_id(e)
        known = set(self.enc_keys) | set(self.sign_keys)
        _require(enc_id not in known and sign_id not in known and enc_id != sign_id, "a public key appears twice")
        self.enc_keys[enc_id], self.sign_keys[sign_id], self.signers[sign_id] = x, e, who
        self.computers[who] = (enc_id, sign_id)

    @property
    def recovery(self) -> tuple[str, str]:
        """(encryption key id, signing key id) of the recovery key."""
        return self.computers[RECOVERY]

    def is_admin_key(self, sign_id: Any) -> bool:
        who = self.signers.get(sign_id) if isinstance(sign_id, str) else None
        return who is not None and (who == RECOVERY or who[0] in self.doc["administrators"])

    def members(self, group: str) -> set[str]:
        """Group members; administrators are members of every group (section 6)."""
        return set(self.doc["groups"][group]) | set(self.doc["administrators"])

    def assignment(self, oid: str) -> tuple[str, str]:
        """(group, kind) the policy gives an id; an index's group comes from its id."""
        if isinstance(oid, str) and oid.startswith(INDEX_PREFIX):
            if oid[len(INDEX_PREFIX):] in self.doc["groups"]:
                return oid[len(INDEX_PREFIX):], "index"
        elif isinstance(oid, str) and oid in self.doc["assignments"]:
            a = self.doc["assignments"][oid]
            return a["group"], a["kind"]
        raise SecretStoreError(f"object {oid} is not assigned by the policy")

    def assigned_ids(self, group: str) -> list[str]:
        return sorted(o for o, a in self.doc["assignments"].items() if a["group"] == group)

    def refresher(self, oid: str) -> tuple[str, str] | None:
        """(person, computer) refreshing the sign-in a grant or oauth id belongs to, or None."""
        grant = oid if oid in self.doc["refreshers"] else self.oauth_refresher.get(oid)
        if grant is None:
            return None
        r = self.doc["refreshers"][grant]
        return r["person"], r["computer"]

    def refresher_sign_id(self, oid: str) -> str | None:
        who = self.refresher(oid)
        return None if who is None else self.computers[who][1]

    def readers_for(self, oid: str) -> list[str]:
        """Exact reader key ids: the group's computers and the recovery key; for a grant, its
        refresher computer and the recovery key only."""
        group, kind = self.assignment(oid)
        if kind == "grant":
            return sorted({self.computers[self.refresher(oid)][0], self.recovery[0]})
        members = self.members(group)
        return sorted({self.recovery[0]} | {enc for (person, _c), (enc, _s) in self.computers.items()
                                            if person in members})

    def may_write(self, sign_id: Any, oid: str) -> bool:
        """Writer authority for a revision of oid under this policy (tombstones and refresher
        handovers are judged by accept.py)."""
        who = self.signers.get(sign_id) if isinstance(sign_id, str) else None
        if who is None:
            return False
        group, kind = self.assignment(oid)
        if kind == "grant":
            return sign_id in (self.refresher_sign_id(oid), self.recovery[1])
        return who == RECOVERY or who[0] in self.members(group)

    def verify(self, obj: dict[str, Any], sign_id: Any) -> None:
        if not isinstance(sign_id, str) or sign_id not in self.sign_keys:
            raise SecretStoreError("writer key is not in the policy")
        signing.verify(obj, self.sign_keys[sign_id])


def sign_policy(doc: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    body = copy.deepcopy(doc)
    body["writer"] = key_id(private_key.public_key())
    return signing.sign(body, private_key)


def new_repository_id() -> str:
    return secrets.token_hex(16)


def create_trust_root(people: dict, recovery: dict, groups: dict, administrators: list,
                      signer: Ed25519PrivateKey, repository: str | None = None) -> dict[str, Any]:
    """The first policy (epoch 1), signed by an administrator key it names."""
    doc = {"schema": SCHEMA, "type": "policy", "repository": repository or new_repository_id(), "epoch": 1,
           "previous": None, "people": people, "recovery": recovery, "groups": groups, "assignments": {},
           "refreshers": {}, "retired": {}, "administrators": administrators, "cites": []}
    signed = sign_policy(doc, signer)
    load_trust_root(signed, fingerprint(signed))
    return signed


def load_trust_root(doc: Any, expected_fingerprint: str) -> Policy:
    """Pin a trust root after its fingerprint was compared on two screens."""
    root = Policy(doc)
    _require(root.epoch == 1, "a trust root has epoch 1 and no previous hash")
    _require(root.is_admin_key(doc["writer"]), "trust root is not signed by an administrator key it names")
    root.verify(doc, doc["writer"])
    given = "".join(str(expected_fingerprint).split()).lower()
    _require(hmac.compare_digest(given.encode("ascii", "replace"), root.hash.encode("ascii")),
             "trust root fingerprint does not match")
    return root


def validate_transition(current: Policy, proposed: Any) -> Policy:
    """Section 6: epoch one higher, previous hash of the trusted policy, signed by an
    administrator key (the recovery key included) of the current trusted policy."""
    nxt = Policy(proposed)
    _require(nxt.repository == current.repository, "repository id changed")
    _require(nxt.epoch == current.epoch + 1, "epoch is not one higher than the trusted policy")
    _require(proposed["previous"] == current.hash, "previous hash does not match the trusted policy")
    _require(current.is_admin_key(proposed["writer"]), "not signed by an administrator of the current policy")
    current.verify(proposed, proposed["writer"])
    for oid, final in current.doc["retired"].items():
        _require(nxt.doc["retired"].get(oid) == final, f"retired id {oid} was changed or dropped")
    for oid in current.doc["assignments"]:
        _require(oid in nxt.doc["assignments"] or oid in nxt.doc["retired"], f"assignment {oid} removed without retiring it")
    return nxt
