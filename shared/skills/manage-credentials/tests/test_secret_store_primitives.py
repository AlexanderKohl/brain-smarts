"""Secrets-store primitives: RFC 9180 HPKE vector, canonical JSON, signatures, keychain allowlist,
BIP-39 recovery and the object envelope. Every key here is fictional and made for the test; the
keychain is an in-memory fake patched in per test, never the real one."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import keyring  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402

from secret_store import SecretStoreError, canonical, envelope, hpke, keys, recovery, signing  # noqa: E402

# RFC 9180 Appendix A.1.1: DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, AES-128-GCM, base mode.
# Source: https://www.rfc-editor.org/rfc/rfc9180.txt, retrieved 2026-11-20T18:09+10:00.
A11_INFO = "4f6465206f6e2061204772656369616e2055726e"
A11_IKM_E = "7268600d403fce431561aef583ee1613527cff655c1343f29812e66706df3234"
A11_IKM_R = "6db9df30aa07dd42ee5e8181afdb977e538f5e1fec8a06223f33f7013e525037"
A11_PK_EM = "37fda3567bdbd628e88668c3c8d7e97d1d1253b6d4ea6d44c150f741f1bf4431"
A11_PK_RM = "3948cfe0ad1ddb695d780e59077195da6c56506b027329794ab02bca80815c4d"
A11_ENC = "37fda3567bdbd628e88668c3c8d7e97d1d1253b6d4ea6d44c150f741f1bf4431"
A11_SHARED_SECRET = "fe0e18c9f024ce43799ae393c7e8fe8fce9d218875e8227b0187c04e7d2ea1fc"
A11_KEY = "4531685d41d65f03dc48f6b8302c05b0"
A11_BASE_NONCE = "56d890e5accaaf011cff4b7d"
A11_PT = "4265617574792069732074727574682c20747275746820626561757479"
A11_AAD = "436f756e742d30"
A11_NONCE = "56d890e5accaaf011cff4b7d"
A11_CT = ("f938558b5d72f1a23810b4be2ab4f84331acc02fc97babc53a52ae8218a355a9"
          "6d8770ac83d07bea87e13c512a")
H = bytes.fromhex


class HpkeTest(unittest.TestCase):
    def test_rfc9180_a11_vector(self):
        sk_e, sk_r = hpke.derive_key_pair(H(A11_IKM_E)), hpke.derive_key_pair(H(A11_IKM_R))
        self.assertEqual(hpke.public_bytes(sk_e.public_key()).hex(), A11_PK_EM)
        self.assertEqual(hpke.public_bytes(sk_r.public_key()).hex(), A11_PK_RM)
        shared, enc = hpke.encap(sk_r.public_key(), sk_e)
        self.assertEqual(enc.hex(), A11_ENC)
        self.assertEqual(shared.hex(), A11_SHARED_SECRET)
        self.assertEqual(hpke.decap(enc, sk_r).hex(), A11_SHARED_SECRET)
        key, base_nonce = hpke.key_schedule(shared, H(A11_INFO), hpke.AES_128_GCM)
        self.assertEqual(key.hex(), A11_KEY)
        self.assertEqual(base_nonce.hex(), A11_BASE_NONCE)
        self.assertEqual(base_nonce.hex(), A11_NONCE)  # sequence number 0
        enc2, ct = hpke.seal(sk_r.public_key(), H(A11_INFO), H(A11_AAD), H(A11_PT), hpke.AES_128_GCM, _sk_e=sk_e)
        self.assertEqual((enc2.hex(), ct.hex()), (A11_ENC, A11_CT))
        self.assertEqual(hpke.open_(H(A11_ENC), sk_r, H(A11_INFO), H(A11_AAD), H(A11_CT), hpke.AES_128_GCM),
                         H(A11_PT))

    def test_round_trip_aes256_and_refusals(self):
        sk = X25519PrivateKey.generate()
        enc, ct = hpke.seal(sk.public_key(), b"info", b"aad", b"fictional")
        self.assertEqual(hpke.open_(enc, sk, b"info", b"aad", ct), b"fictional")
        for args in ((enc, sk, b"other", b"aad", ct), (enc, sk, b"info", b"other", ct),
                     (enc, X25519PrivateKey.generate(), b"info", b"aad", ct)):
            with self.assertRaises(SecretStoreError):
                hpke.open_(*args)

    def test_low_order_and_malformed_public_keys_refused(self):
        low_order = [bytes(32), (1).to_bytes(32, "little"),
                     H("e0eb7a7c3b41b8ae1656e3faf19fc46ada098deb9c32b1fd866205165f49b800")]
        for raw in low_order:
            with self.assertRaises(SecretStoreError):
                hpke.load_public_key(raw)
            with self.assertRaises(SecretStoreError):
                hpke.decap(raw, X25519PrivateKey.generate())
        with self.assertRaises(SecretStoreError):
            hpke.load_public_key(b"short")


class CanonicalTest(unittest.TestCase):
    def test_ordering_and_escaping(self):
        # UTF-16 code-unit order (RFC 8785 3.2.3): U+20AC < U+1F600 (D83D DE00) < U+FB33,
        # although by code point U+FB33 < U+1F600.
        value = {"b": [1, True, None], "a": "x\n\"\u0001é", "\ufb33": 3, "\U0001F600": 2, "\u20ac": 1, "A": False}
        self.assertEqual(canonical.dumps(value),
                         '{"A":false,"a":"x\\n\\"\\u0001é","b":[1,true,null],"\u20ac":1,"\U0001F600":2,"\ufb33":3}'
                         .encode("utf-8"))
        self.assertEqual(canonical.loads(canonical.dumps(value)), value)

    def test_refusals(self):
        for bad in (1.5, {1: "x"}, 2**53, -(2**53), {"a": float("nan")}, b"bytes", "\ud800"):
            with self.assertRaises(SecretStoreError):
                canonical.dumps(bad)
        for text in ('{"a":1,"a":2}', '{"a":1.0}', '{"a":1e3}', '{"a":NaN}', '{"a":9007199254740992}', "{"):
            with self.assertRaises(SecretStoreError):
                canonical.loads(text)
        self.assertEqual(canonical.loads('{"a":9007199254740991}'), {"a": 2**53 - 1})


class SigningTest(unittest.TestCase):
    def test_sign_verify_and_tamper(self):
        _, ed = keys.generate_key_pairs()
        signed = signing.sign({"b": 1, "a": "fictional"}, ed)
        signing.verify(signed, ed.public_key())
        for change in ({"a": "changed"}, {"c": 1}, {"signature": signed["signature"][:-4] + "AAAA"}):
            with self.assertRaises(SecretStoreError):
                signing.verify({**signed, **change}, ed.public_key())
        with self.assertRaises(SecretStoreError):
            signing.verify(signed, keys.generate_key_pairs()[1].public_key())
        with self.assertRaises(SecretStoreError):
            signing.verify({"a": 1}, ed.public_key())


class FakeKeyring:
    """In-memory stand-in, patched in as keyring.get_keyring() for one test only."""

    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, value):
        self.items[(service, user)] = value


class BrokenKeyring(FakeKeyring):
    def get_password(self, service, user):
        raise keyring.errors.KeyringLocked("locked")


def _name(cls):
    return f"{cls.__module__}.{cls.__qualname__}"


class KeysTest(unittest.TestCase):
    def test_key_id(self):
        x, ed = keys.generate_key_pairs()
        self.assertEqual(keys.key_id(x.public_key()),
                         hashlib.sha256(keys.raw_public(x.public_key())).hexdigest()[:32])
        self.assertEqual(len(keys.key_id(ed.public_key())), 32)

    def test_store_and_load_with_allowed_fake(self):
        fake = FakeKeyring()
        allowed = keys.ALLOWED_BACKENDS | {_name(FakeKeyring)}
        with mock.patch.object(keyring, "get_keyring", return_value=fake), \
                mock.patch.object(keys, "ALLOWED_BACKENDS", allowed):
            x, ed = keys.generate_key_pairs()
            keys.store_private_keys("Fictional Person", "fictional-pc", x, ed)
            self.assertEqual(list(fake.items), [("brain-secrets", "Fictional Person@fictional-pc")])
            x2, ed2 = keys.load_private_keys("Fictional Person", "fictional-pc")
            self.assertEqual(keys.raw_private(x2), keys.raw_private(x))
            self.assertEqual(keys.raw_private(ed2), keys.raw_private(ed))
            with self.assertRaises(SecretStoreError):
                keys.store_private_keys("Fictional Person", "fictional-pc", x, ed)
            with self.assertRaises(SecretStoreError):
                keys.load_private_keys("Other", "fictional-pc")

    def test_backend_not_on_allowlist_refused(self):
        x, ed = keys.generate_key_pairs()
        with mock.patch.object(keyring, "get_keyring", return_value=FakeKeyring()):
            with self.assertRaises(SecretStoreError) as caught:
                keys.store_private_keys("p", "c", x, ed)
            self.assertIn("allowlist", str(caught.exception))
            with self.assertRaises(SecretStoreError):
                keys.load_private_keys("p", "c")

    def test_keyring_error_fails_closed_without_key_material(self):
        x, ed = keys.generate_key_pairs()
        allowed = keys.ALLOWED_BACKENDS | {_name(BrokenKeyring)}
        with mock.patch.object(keyring, "get_keyring", return_value=BrokenKeyring()), \
                mock.patch.object(keys, "ALLOWED_BACKENDS", allowed):
            with self.assertRaises(SecretStoreError) as caught:
                keys.store_private_keys("p", "c", x, ed)
            self.assertNotIn(keys.raw_private(x).hex(), str(caught.exception))


class RecoveryTest(unittest.TestCase):
    def test_wordlist_hash_and_known_vectors(self):
        data = recovery.WORDLIST_PATH.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(data).hexdigest(), recovery.WORDLIST_SHA256)
        self.assertEqual(recovery.entropy_to_mnemonic(bytes(32)), " ".join(["abandon"] * 23 + ["art"]))
        self.assertEqual(recovery.entropy_to_mnemonic(b"\xff" * 32), " ".join(["zoo"] * 23 + ["vote"]))

    def test_a_word_list_checked_out_with_windows_line_endings_still_verifies(self):
        # Git on Windows may write the file with CRLF line endings; the words are the same.
        lf = recovery.WORDLIST_PATH.read_bytes().replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "bip39_english.txt"
            copied.write_bytes(lf.replace(b"\n", b"\r\n"))
            with mock.patch.object(recovery, "WORDLIST_PATH", copied):
                recovery.wordlist.cache_clear()
                try:
                    self.assertEqual(len(recovery.wordlist()), 2048)
                    copied.write_bytes(lf.replace(b"abandon", b"abandom", 1).replace(b"\n", b"\r\n"))
                    recovery.wordlist.cache_clear()
                    with self.assertRaises(SecretStoreError):
                        recovery.wordlist()
                finally:
                    recovery.wordlist.cache_clear()

    def test_round_trip_and_determinism(self):
        phrase = recovery.generate_mnemonic()
        self.assertEqual(len(phrase.split()), 24)
        entropy = recovery.mnemonic_to_entropy(phrase)
        self.assertEqual(recovery.entropy_to_mnemonic(entropy), phrase)
        (x1, e1), (x2, e2) = recovery.derive_recovery_keys(phrase), recovery.derive_recovery_keys(phrase.upper())
        self.assertEqual(keys.raw_private(x1), keys.raw_private(x2))
        self.assertEqual(keys.raw_private(e1), keys.raw_private(e2))
        self.assertNotEqual(keys.raw_private(x1), keys.raw_private(e1))
        other = recovery.derive_recovery_keys(recovery.generate_mnemonic())
        self.assertNotEqual(keys.raw_private(other[0]), keys.raw_private(x1))

    def test_checksum_and_shape_failures(self):
        words = " ".join(["abandon"] * 24).split()
        with self.assertRaises(SecretStoreError):
            recovery.mnemonic_to_entropy(" ".join(words))  # checksum wrong
        good = recovery.generate_mnemonic().split()
        # One altered word keeps a valid 8-bit checksum about once in 256 tries, so a single
        # alteration cannot be asserted to fail. Alter the last word 64 ways: nearly all must fail.
        candidates = [w for w in recovery.wordlist() if w != good[-1]][:64]
        refused = 0
        for word in candidates:
            try:
                recovery.mnemonic_to_entropy(" ".join(good[:-1] + [word]))
            except SecretStoreError:
                refused += 1
        self.assertGreaterEqual(refused, len(candidates) - 8)
        for bad in (" ".join(good[:23]), " ".join(good[:23] + ["notaword"]), ""):
            with self.assertRaises(SecretStoreError) as caught:
                recovery.mnemonic_to_entropy(bad)
            # A leak shows as the words in sequence; a single word may also be ordinary English in
            # the fixed message (for example "list"), so check every consecutive pair instead.
            for first, second in zip(good, good[1:]):
                self.assertNotIn(f" {first} {second} ", f" {caught.exception} ")


HEADER = {"repository": "fictional-repo", "group": "fictional-group", "id": "obj-1", "kind": "static",
          "revision": 3, "operation": None, "policy_epoch": 2, "previous": "fictional-hash", "writer": "w"}


class EnvelopeTest(unittest.TestCase):
    def setUp(self):
        self.me = X25519PrivateKey.generate()
        self.other = X25519PrivateKey.generate()
        self.my_id = keys.key_id(self.me.public_key())
        readers = [(self.my_id, self.me.public_key()), (keys.key_id(self.other.public_key()), self.other.public_key())]
        self.payload = {"api_key": "fictional-value"}
        self.obj = envelope.seal(self.payload, readers, HEADER)

    def test_round_trip_both_readers(self):
        self.assertEqual(envelope.open_(self.obj, self.my_id, self.me), self.payload)
        self.assertEqual(envelope.open_(self.obj, keys.key_id(self.other.public_key()), self.other), self.payload)
        self.assertEqual(self.obj["suite"], envelope.SUITE)
        self.assertNotIn("fictional-value", canonical.dumps(self.obj).decode())

    def _refused(self, obj, key_id=None):
        with self.assertRaises(SecretStoreError) as caught:
            envelope.open_(obj, key_id or self.my_id, self.me)
        self.assertNotIn("fictional-value", str(caught.exception))

    def _flip(self, b64):
        raw = bytearray(envelope._unb64(b64, "x"))
        raw[0] ^= 1
        return envelope._b64(bytes(raw))

    def test_every_tampered_field_refused(self):
        for field in ("ciphertext", "nonce"):
            obj = copy.deepcopy(self.obj)
            obj[field] = self._flip(obj[field])
            self._refused(obj)
        changes = {"schema": 2, "suite": "other", "repository": "r2", "group": "g2", "id": "obj-2",
                   "kind": "oauth", "revision": 4, "operation": "op-1"}
        for field, value in changes.items():
            obj = copy.deepcopy(self.obj)
            obj[field] = value
            self._refused(obj)
        for field in ("wrapped", "enc"):
            obj = copy.deepcopy(self.obj)
            obj["readers"][0][field] = self._flip(obj["readers"][0][field])
            self._refused(obj)
        obj = copy.deepcopy(self.obj)
        obj["readers"][0]["key"] = "0" * 32
        self._refused(obj)
        obj = copy.deepcopy(self.obj)  # swap reader ids: my wrap now bound to the other reader's id
        obj["readers"][0]["key"], obj["readers"][1]["key"] = obj["readers"][1]["key"], obj["readers"][0]["key"]
        self._refused(obj)
        obj = copy.deepcopy(self.obj)
        obj["readers"].append(dict(obj["readers"][0]))
        self._refused(obj)

    def test_seal_refusals(self):
        pk = self.me.public_key()
        with self.assertRaises(SecretStoreError):
            envelope.seal(self.payload, [("0" * 32, pk)], HEADER)
        with self.assertRaises(SecretStoreError):
            envelope.seal(self.payload, [], HEADER)
        with self.assertRaises(SecretStoreError):
            envelope.seal(self.payload, [(self.my_id, pk), (self.my_id, pk)], HEADER)
        with self.assertRaises(SecretStoreError):
            envelope.seal(self.payload, [(self.my_id, pk)], {**HEADER, "kind": "unknown"})
        with self.assertRaises(SecretStoreError):
            envelope.seal(self.payload, [(self.my_id, pk)], {**HEADER, "extra": 1})
        with self.assertRaises(SecretStoreError):
            envelope.open_(self.obj, self.my_id, self.other)


if __name__ == "__main__":
    unittest.main()
