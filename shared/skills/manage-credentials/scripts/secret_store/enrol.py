"""Enrolment protocol of the synced secrets store (design synced-secrets-repository.md, section 8).

1. The new computer makes its keys and writes a signed request under requests/: both public keys,
   the login, the repository id, the protocol version, a random challenge and an expiry ten
   minutes ahead.
2. An approver answers with a challenge encrypted to the new X25519 key; the new computer decrypts
   it and signs it back, proving it holds both private keys. The challenge itself never enters
   the repository: the approver keeps it in its own state folder and checks the signature.
3. Both computers derive six words (66 bits, BIP-39 list) from the canonical transcript and show
   them in a local window. Three mismatches or the expiry end the attempt.
4. On a match the approver signs one commit: the policy change adding exactly that computer, a new
   revision of every object whose readers change (grants excepted) and the removal of the
   request files.

The files under requests/ hold public keys, hashes and an encrypted challenge only, never a secret.
Personal enrolment is approved by one of the person's computers or the recovery key; team
enrolment by an administrator."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable

from . import canonical, hpke, keys, recovery, signing
from .errors import SecretStoreError
from .policy import NAME, _keys as policy_keys, object_hash, public_entry
from .store_ops import build_policy_change

PROTOCOL = 1
LIFETIME = 600  # ten minutes
SKEW = 60  # allowed clock difference between the two computers
MAX_MISMATCHES = 3
WORD_COUNT = 6  # 66 bits
_INFO = b"brain-secrets enrolment challenge v1"
_ID = re.compile(r"[0-9a-f]{16}")
REQUEST_FIELDS = frozenset({"schema", "type", "protocol", "repository", "login", "computer", "keys",
                            "challenge", "expires", "writer", "signature"})
ANSWER_FIELDS = frozenset({"schema", "type", "request", "enc", "sealed", "writer", "signature"})
PROOF_FIELDS = frozenset({"schema", "type", "request", "answer", "writer", "signature"})


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: Any) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise SecretStoreError("enrolment file malformed") from None


def _paths(rid: str) -> tuple[str, str, str]:
    if not isinstance(rid, str) or not _ID.fullmatch(rid):
        raise SecretStoreError("an enrolment request id is 16 hexadecimal characters")
    return f"requests/{rid}.json", f"requests/{rid}.answer.json", f"requests/{rid}.proof.json"


def _read(store, path: str) -> dict | None:
    file = store.clone / path
    return canonical.loads(file.read_bytes()) if file.exists() else None


def _my_sign_id(store) -> str:
    return keys.key_id(store._identity().ed25519.public_key())


def _default_display(title: str, words: list[str]) -> bool:
    from secret_window import show_words  # the scripts folder is on sys.path for the CLI
    return show_words(title, words)


def transcript_words(req: dict, ans: dict, proof: dict) -> list[str]:
    """Six BIP-39 words: the first 66 bits of SHA-256 of the canonical transcript."""
    digest = hashlib.sha256(canonical.dumps({"request": req, "answer": ans, "proof": proof})).digest()
    bits = int.from_bytes(digest[:9], "big") >> (72 - 11 * WORD_COUNT)
    words = recovery.wordlist()
    return [words[(bits >> (11 * (WORD_COUNT - 1 - i))) & 0x7FF] for i in range(WORD_COUNT)]


def check_request(req: Any, repository: str, now: float) -> tuple[Any, Any]:
    """Shape, repository, protocol, expiry and self-signature of a request; its public keys."""
    if not isinstance(req, dict) or set(req) != REQUEST_FIELDS or req["schema"] != 1 or req["type"] != "enrol-request":
        raise SecretStoreError("enrolment request malformed")
    if req["protocol"] != PROTOCOL:
        raise SecretStoreError("enrolment request has an unknown protocol version")
    if req["repository"] != repository:
        raise SecretStoreError("enrolment request is for another repository")
    if not all(isinstance(req[k], str) and NAME.fullmatch(req[k]) for k in ("login", "computer")):
        raise SecretStoreError("enrolment request names a malformed login or computer")
    expires = req["expires"]
    if isinstance(expires, bool) or not isinstance(expires, int) or expires > now + LIFETIME + SKEW:
        raise SecretStoreError("enrolment request has a malformed expiry")
    if now > expires:
        raise SecretStoreError("the enrolment request has expired; start a new one")
    x_pub, e_pub = policy_keys(req["keys"], "enrolment request")
    if req["writer"] != keys.key_id(e_pub) or len(_unb64(req["challenge"])) != 32:
        raise SecretStoreError("enrolment request malformed")
    signing.verify(req, e_pub)
    return x_pub, e_pub


# -- state the approver keeps on its own computer ------------------------------------------------
def _pending_path(store, rid: str) -> Path:
    return store.config["checkpoint_dir"] / "enrolment" / f"{store.policy.repository}-{rid}.json"


def _load_pending(store, rid: str) -> dict | None:
    path = _pending_path(store, rid)
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _save_pending(store, rid: str, state: dict) -> None:
    path = _pending_path(store, rid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), "utf-8")


def _end(store, rid: str) -> None:
    _pending_path(store, rid).unlink(missing_ok=True)


# -- new computer -----------------------------------------------------------------------------------
def request(store, fingerprint: str | None = None, now: float | None = None) -> str:
    """New computer: make (or reuse) its keys, open the repository pinning the trust root, and
    commit a signed request. Returns the request id (not secret)."""
    now = time.time() if now is None else now
    store._require_enabled()
    person, computer = store.config["person"], store.config["computer"]
    try:
        store._identity()
    except SecretStoreError:
        x, e = keys.generate_key_pairs()
        keys.store_private_keys(person, computer, x, e)
    store.open(fingerprint)
    ident = store._identity()
    if (person, computer) in store.policy.computers:
        raise SecretStoreError("this computer is already enrolled")
    rid = secrets.token_hex(8)
    body = {"schema": 1, "type": "enrol-request", "protocol": PROTOCOL, "repository": store.policy.repository,
            "login": person, "computer": computer,
            "keys": public_entry(ident.x25519.public_key(), ident.ed25519.public_key()),
            "challenge": _b64(os.urandom(32)), "expires": int(now) + LIFETIME, "writer": _my_sign_id(store)}
    signed = signing.sign(body, ident.ed25519)
    store._write(lambda: ({_paths(rid)[0]: signed}, "update"))
    return rid


def prove(store, rid: str, display: Callable[[str, list[str]], bool] | None = None,
          now: float | None = None) -> None:
    """New computer: decrypt the approver's challenge, sign it back, and show the six words."""
    now = time.time() if now is None else now
    req_path, ans_path, proof_path = _paths(rid)
    store.open()
    req, ans = _read(store, req_path), _read(store, ans_path)
    if req is None or ans is None:
        raise SecretStoreError(f"enrolment {rid} has no request or no answer yet")
    check_request(req, store.policy.repository, now)
    if req["writer"] != _my_sign_id(store):
        raise SecretStoreError("this enrolment request was not made by this computer")
    if not isinstance(ans, dict) or set(ans) != ANSWER_FIELDS or ans["type"] != "enrol-answer" \
            or ans["request"] != object_hash(req):
        raise SecretStoreError("enrolment answer malformed")
    if not store.policy.is_admin_key(ans["writer"]):
        raise SecretStoreError("the enrolment answer is not signed by an approver of this repository")
    store.policy.verify(ans, ans["writer"])
    challenge = hpke.open_(_unb64(ans["enc"]), store._identity().x25519, _INFO, ans["request"].encode("ascii"),
                           _unb64(ans["sealed"]), hpke.AES_256_GCM)
    body = {"schema": 1, "type": "enrol-proof", "request": ans["request"], "answer": object_hash(ans),
            "writer": _my_sign_id(store)}
    signature = signing.sign({**body, "challenge": _b64(challenge)}, store._identity().ed25519)["signature"]
    proof = {**body, "signature": signature}
    store._write(lambda: ({proof_path: proof}, "update"))
    (display or _default_display)("Enrolment words", transcript_words(req, ans, proof))


# -- approver ---------------------------------------------------------------------------------------
def _check_approver(store, req: dict) -> None:
    if not store.policy.is_admin_key(_my_sign_id(store)):
        raise SecretStoreError("only an administrator may approve an enrolment (personal: one of the person's "
                               "computers or the recovery key)")
    if not store.team and req["login"] not in store.policy.doc["people"]:
        raise SecretStoreError("a personal repository enrols only its own person's computers")
    if (req["login"], req["computer"]) in store.policy.computers:
        raise SecretStoreError("that computer is already enrolled")


def answer(store, rid: str, now: float | None = None) -> None:
    """Approver: check the request and commit a challenge encrypted to the new X25519 key."""
    now = time.time() if now is None else now
    req_path, ans_path, _proof = _paths(rid)
    store.open()
    req = _read(store, req_path)
    if req is None:
        raise SecretStoreError(f"there is no enrolment request {rid}")
    x_pub, _e = check_request(req, store.policy.repository, now)
    _check_approver(store, req)
    if _read(store, ans_path) is not None:
        raise SecretStoreError(f"enrolment {rid} was already answered and has ended or is open elsewhere; "
                               "start a new request")
    challenge = os.urandom(32)
    request_hash = object_hash(req)
    enc, sealed = hpke.seal(x_pub, _INFO, request_hash.encode("ascii"), challenge, hpke.AES_256_GCM)
    body = {"schema": 1, "type": "enrol-answer", "request": request_hash, "enc": _b64(enc),
            "sealed": _b64(sealed), "writer": _my_sign_id(store)}
    signed = signing.sign(body, store._identity().ed25519)
    _save_pending(store, rid, {"request": request_hash, "challenge": _b64(challenge), "mismatches": 0})
    store._write(lambda: ({ans_path: signed}, "update"))


def approve(store, rid: str, display: Callable[[str, list[str]], bool] | None = None,
            now: float | None = None, clock: Callable[[], float] | None = None) -> None:
    """Approver: verify the proof, compare the six words, then one commit enrolling the computer. The
    expiry is checked again once the words window closes, so a comparison that ran past it enrols
    nothing."""
    clock = clock or (time.time if now is None else (lambda: now))
    now = clock()
    paths = _paths(rid)
    store.open()
    pending = _load_pending(store, rid)
    if pending is None:
        raise SecretStoreError(f"enrolment {rid} is not open on this computer")
    req, ans, proof = (_read(store, p) for p in paths)
    if req is None or ans is None or object_hash(req) != pending["request"]:
        _end(store, rid)
        raise SecretStoreError(f"enrolment {rid} changed in the repository; it has ended")
    try:
        _x, e_pub = check_request(req, store.policy.repository, now)
        _check_approver(store, req)
    except SecretStoreError:
        _end(store, rid)
        raise
    if proof is None:
        raise SecretStoreError("the new computer has not answered the challenge yet")
    if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS or proof["type"] != "enrol-proof" \
            or proof["request"] != pending["request"] or proof["answer"] != object_hash(ans) \
            or proof["writer"] != req["writer"]:
        raise SecretStoreError("enrolment proof malformed")
    signing.verify({**proof, "challenge": pending["challenge"]}, e_pub)  # proves both private keys
    if (display or _default_display)("Enrolment words", transcript_words(req, ans, proof)) is not True:
        pending["mismatches"] += 1
        if pending["mismatches"] >= MAX_MISMATCHES:
            _end(store, rid)
            raise SecretStoreError("three mismatches: the enrolment has ended; start a new request")
        _save_pending(store, rid, pending)
        raise SecretStoreError(f"the words did not match ({pending['mismatches']} of {MAX_MISMATCHES})")
    if clock() > req["expires"]:
        _end(store, rid)
        raise SecretStoreError("the enrolment request expired while the words were compared; start a new one")
    login, computer = req["login"], req["computer"]

    def change(doc: dict) -> None:
        record = doc["people"].setdefault(login, {"computers": {}, "disabled_refresher": []})
        if computer in record["computers"]:
            raise SecretStoreError("that computer is already enrolled")
        record["computers"][computer] = req["keys"]

    def build() -> tuple[dict, str]:
        files = build_policy_change(store.policy, store.checkpoint.objects, change, store._identity().ed25519,
                                    lambda oid: store._open_object(store._tree_object(oid, store.checkpoint)))
        files.update({path: None for path in paths})
        return files, "policy"

    store._write(build)
    _end(store, rid)


def approve_step(store, rid: str, display: Callable[[str, list[str]], bool] | None = None,
                 now: float | None = None) -> str:
    """One command for the approver: answer a new request, or compare words and approve an
    answered one. Returns "answered" or "approved"."""
    store.open()
    if _load_pending(store, rid) is None:
        answer(store, rid, now)
        return "answered"
    approve(store, rid, display, now)
    return "approved"
