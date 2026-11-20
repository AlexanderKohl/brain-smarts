"""Policy, commit acceptance and checkpoint of the synced secrets store (design sections 6 to 9).
Every key is generated for the test and every token is fictional; nothing touches a keychain, Git
or the network."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from secret_store import SecretStoreError, canonical, checkpoint, envelope, keys, policy, signing  # noqa: E402
from secret_store import accept_rules  # noqa: E402
from secret_store.accept import accept_commit  # noqa: E402

NAMES = ("alice-pc", "bob-pc", "carol-pc", "dave-pc", "recovery")
TOK_A = {"access_token": "fictional-a", "expires_at": 100, "token_type": "Bearer", "scope": "s", "tenant": "t1"}


def commit(*objs, pol=None, **records):
    files = {f"objects/{o['id']}.json": o for o in objs}
    if pol is not None:
        files["policy.json"] = pol
    files.update({f"releases/{name}.json": r for name, r in records.items()})
    return files


class World:
    """Alice administers; group ops is bob and carol, fin is dave; bob-pc refreshes sign-in o1/g1."""

    def __init__(self):
        self.k = {n: keys.generate_key_pairs() for n in NAMES}
        people = {p: {"computers": {"pc": self.entry(p + "-pc")}, "disabled_refresher": []}
                  for p in ("alice", "bob", "carol", "dave")}
        root = policy.create_trust_root(people, self.entry("recovery"), {"ops": ["bob", "carol"], "fin": ["dave"]},
                                        ["alice"], self.k["alice-pc"][1], repository="repo1")
        self.policy = policy.load_trust_root(root, policy.fingerprint(root))
        self.cp = checkpoint.initial(self.policy)

    def entry(self, n):
        return policy.public_entry(self.k[n][0].public_key(), self.k[n][1].public_key())

    def sign_id(self, n):
        return keys.key_id(self.k[n][1].public_key())

    def enc_id(self, n):
        return keys.key_id(self.k[n][0].public_key())

    def next_policy(self, change, signer="alice-pc"):
        doc = copy.deepcopy(self.policy.doc)
        doc.update(epoch=self.policy.epoch + 1, previous=self.policy.hash, cites=[])
        change(doc)
        return policy.sign_policy(doc, self.k[signer][1])

    def index(self, pol, group):
        return {"entries": {f"name-{i}": i for i in pol.assigned_ids(group)}}

    def obj(self, oid, payload, writer, pol=None, readers=None, **header):
        pol = pol or self.policy
        entry = self.cp.objects.get(oid)
        known = oid in pol.doc["assignments"] or oid.startswith("index-")
        group, kind = pol.assignment(oid) if known else ("ops", "static")
        h = {"repository": pol.repository, "group": group, "id": oid, "kind": kind,
             "revision": entry["revision"] + 1 if entry else 1, "previous": entry["hash"] if entry else None,
             "policy_epoch": pol.epoch, "operation": None, "writer": self.sign_id(writer)}
        h.update(header)
        public = {self.enc_id(n): self.k[n][0].public_key() for n in NAMES}
        sealed = envelope.seal(payload, [(i, public[i]) for i in (readers or pol.readers_for(oid))], h)
        return signing.sign(sealed, self.k[writer][1])

    def accept(self, files, me="bob-pc", latest=None):
        return accept_commit(self.policy, self.cp, files, {self.enc_id(me): self.k[me][0]}, latest)

    def apply(self, files, me="bob-pc", latest=None):
        result = self.accept(files, me, latest)
        self.policy, self.cp = result.policy, result.checkpoint
        return result


class Base(unittest.TestCase):
    def setUp(self):
        w = self.w = World()

        def assign(d):
            d["assignments"] = {"s1": {"group": "ops", "kind": "static"}, "o1": {"group": "ops", "kind": "oauth", "provider": "xero"},
                                "g1": {"group": "ops", "kind": "grant", "provider": "xero"}, "f1": {"group": "fin", "kind": "static"}}
            d["refreshers"] = {"g1": {"person": "bob", "computer": "pc", "oauth": "o1"}}
        doc = w.next_policy(assign)
        p = policy.Policy(doc)
        objs = [w.obj("s1", {"password": "x"}, "carol-pc", p), w.obj("o1", dict(TOK_A), "bob-pc", p),
                w.obj("g1", {"refresh_token": "r"}, "bob-pc", p), w.obj("f1", {"k": "v"}, "dave-pc", p),
                w.obj("index-ops", w.index(p, "ops"), "bob-pc", p), w.obj("index-fin", w.index(p, "fin"), "dave-pc", p)]
        self.setup_result = w.apply(commit(*objs, pol=doc))

    def refused(self, files, me="bob-pc", latest=None, text=None):
        with self.assertRaises(SecretStoreError) as ctx:
            self.w.accept(files, me, latest)
        if text:
            self.assertIn(text, str(ctx.exception))


class TrustRootTest(unittest.TestCase):
    def test_fingerprint_pins_the_root(self):
        w = World()
        doc = w.policy.doc
        fp = policy.fingerprint(doc)
        self.assertEqual(len(fp.split()), 16)
        self.assertEqual(policy.load_trust_root(doc, fp.upper()).hash, w.policy.hash)
        with self.assertRaises(SecretStoreError):
            policy.load_trust_root(doc, "0" * 64)
        forged = policy.sign_policy(doc, w.k["bob-pc"][1])  # bob is not an administrator
        with self.assertRaises(SecretStoreError):
            policy.load_trust_root(forged, policy.fingerprint(forged))


class PolicyTest(Base):
    def test_readers_for(self):
        w, e = self.w, self.w.enc_id
        self.assertEqual(w.policy.readers_for("s1"), sorted([e("alice-pc"), e("bob-pc"), e("carol-pc"), e("recovery")]))
        self.assertEqual(w.policy.readers_for("g1"), sorted([e("bob-pc"), e("recovery")]))
        self.assertEqual(w.policy.readers_for("index-fin"), sorted([e("alice-pc"), e("dave-pc"), e("recovery")]))
        with self.assertRaises(SecretStoreError):
            w.policy.readers_for("unknown")

    def test_transition_rules(self):
        w = self.w

        def same(_d):
            return None
        policy.validate_transition(w.policy, w.next_policy(same))
        policy.validate_transition(w.policy, w.next_policy(same, "recovery"))  # recovery key is an administrator
        bad = ((same, "bob-pc"), (lambda d: d.update(epoch=d["epoch"] + 1), "alice-pc"),
               (lambda d: d.update(previous="0" * 64), "alice-pc"), (lambda d: d["assignments"].pop("f1"), "alice-pc"),
               (lambda d: d.update(repository="other"), "alice-pc"))
        for number, (change, signer) in enumerate(bad):
            with self.subTest(number=number), self.assertRaises(SecretStoreError):
                policy.validate_transition(w.policy, w.next_policy(change, signer))
        self.refused(commit(pol=w.next_policy(same, "bob-pc")), text="administrator")


class AcceptTest(Base):
    def test_setup_flags_unreadable_objects_opaque(self):
        objs = self.setup_result.objects
        self.assertTrue(objs["s1"].usable)
        self.assertEqual(objs["s1"].payload, {"password": "x"})
        self.assertFalse(objs["f1"].usable)
        self.assertIsNone(objs["f1"].payload)

    def test_member_write_then_replay_refused(self):
        w = self.w
        revision = w.obj("s1", {"password": "y"}, "carol-pc")
        w.apply(commit(revision))
        self.assertEqual(w.cp.objects["s1"]["revision"], 2)
        self.refused(commit(revision), text="revision")

    def test_fork_and_lower_revision_refused(self):
        w = self.w
        a, b = w.obj("s1", {"password": "a"}, "carol-pc"), w.obj("s1", {"password": "b"}, "alice-pc")
        w.apply(commit(a))
        self.refused(commit(b), text="revision")
        self.refused(commit(w.obj("s1", {}, "carol-pc", revision=1, previous=None)), text="revision")
        self.refused(commit(w.obj("s1", {}, "carol-pc", previous="0" * 64)), text="previous")

    def test_wrong_group_kind_readers_and_old_epoch(self):
        w, e = self.w, self.w.enc_id
        self.refused(commit(w.obj("s1", {}, "carol-pc", group="fin")), text="group")
        self.refused(commit(w.obj("s1", {}, "carol-pc", kind="oauth")), text="kind")
        self.refused(commit(w.obj("s1", {}, "carol-pc", readers=w.policy.readers_for("f1"))), text="readers")
        self.refused(commit(w.obj("s1", {}, "carol-pc", readers=[e("carol-pc"), e("recovery")])), text="readers")
        self.refused(commit(w.obj("s1", {}, "carol-pc", policy_epoch=w.policy.epoch - 1)), text="epoch")
        w.apply(commit(w.obj("s1", {}, "carol-pc")))

    def test_writer_authority(self):
        w = self.w
        self.refused(commit(w.obj("s1", {}, "dave-pc")), text="authority")
        self.refused(commit(w.obj("g1", {"refresh_token": "z"}, "carol-pc")), text="authority")  # member, grant
        self.refused(commit(w.obj("g1", {"refresh_token": "z"}, "alice-pc")), text="authority")  # admin, grant
        w.apply(commit(w.obj("s1", {"password": "z"}, "alice-pc")))  # administrators are in every group
        w.apply(commit(w.obj("g1", {"refresh_token": "z"}, "bob-pc", operation="op-1")))
        self.refused(commit(w.obj("s1", {}, "carol-pc", operation="op-2")), text="operation")
        forged = w.obj("s1", {}, "carol-pc")
        forged["writer"] = w.sign_id("bob-pc")
        self.refused(commit(forged), text="signature")
        self.refused({"notes.txt": {}}, text="unexpected path")
        self.refused({"objects/s9.json": w.obj("s1", {}, "carol-pc")}, text="path")

    def test_token_fields_need_the_refresher_operation(self):
        w, latest = self.w, {"o1": dict(TOK_A)}
        changed = dict(TOK_A, access_token="fictional-b")
        self.refused(commit(w.obj("o1", changed, "carol-pc")), latest=latest, text="access-token")
        self.refused(commit(w.obj("o1", changed, "bob-pc")), latest=latest, text="access-token")
        good = w.accept(commit(w.obj("o1", changed, "bob-pc", operation="op-1")), latest=latest)
        self.assertTrue(good.objects["o1"].usable)
        opaque = w.accept(commit(w.obj("o1", changed, "carol-pc")), me="dave-pc", latest=latest)
        self.assertFalse(opaque.objects["o1"].usable)  # dave cannot read: structural only, never used

    def test_stale_token_save_refused(self):
        w = self.w
        tok_b = dict(TOK_A, access_token="fictional-b", expires_at=200)
        w.apply(commit(w.obj("o1", tok_b, "bob-pc", operation="op-1")), latest={"o1": dict(TOK_A)})
        self.refused(commit(w.obj("o1", dict(TOK_A, tenant="t2"), "carol-pc")), latest={"o1": tok_b},
                     text="access-token")
        good = w.accept(commit(w.obj("o1", dict(tok_b, tenant="t2"), "carol-pc")), latest={"o1": tok_b})
        self.assertTrue(good.objects["o1"].usable)
        # No verified baseline here: a member's revision is refused, not merely flagged (S3, A3).
        self.refused(commit(w.obj("o1", dict(tok_b, tenant="t2"), "carol-pc")), text="no verified baseline")

    def retire(self, oid, writer="alice-pc"):
        w = self.w
        prior = w.policy
        tomb = w.obj(oid, {}, writer, kind="tombstone", policy_epoch=prior.epoch + 1)

        def change(d):
            d["assignments"].pop(oid)
            d["retired"][oid] = policy.object_hash(tomb)
        doc = w.next_policy(change)
        p, group = policy.Policy(doc), prior.assignment(oid)[0]
        return commit(tomb, w.obj("index-" + group, w.index(p, group), "alice-pc", p), pol=doc)

    def test_deletion_and_retired_ids(self):
        w = self.w
        self.refused(self.retire("s1", writer="carol-pc"), text="administrator")
        result = w.apply(self.retire("s1"))
        self.assertEqual(result.objects["s1"].payload, {})
        self.assertIn("s1", w.policy.doc["retired"])
        self.refused(commit(w.obj("s1", {"password": "again"}, "carol-pc", readers=w.policy.readers_for("o1"))),
                     text="retired")
        again = w.next_policy(lambda d: d["assignments"].update(s1={"group": "ops", "kind": "static"}))
        with self.assertRaises(SecretStoreError):
            policy.validate_transition(w.policy, again)
        doc = w.next_policy(lambda d: (d["assignments"].pop("f1"), d["retired"].update(f1="0" * 64)))
        p = policy.Policy(doc)
        self.refused(commit(w.obj("index-fin", w.index(p, "fin"), "alice-pc", p), pol=doc), text="tombstone")

    def handover(self, bind=True, cite=True):
        w = self.w

        def change(d):
            d["refreshers"]["g1"]["person"] = "carol"
        resulting = policy.Policy(w.next_policy(change))
        grant = w.obj("g1", {"refresh_token": "r2"}, "bob-pc", resulting)
        release = signing.sign({
            "schema": 1, "type": "release", "repository": w.policy.repository, "grant": "g1",
            "source_epoch": w.policy.epoch, "new_refresher": w.sign_id("carol-pc"),
            "revision_hash": policy.object_hash(grant) if bind else "0" * 64, "writer": w.sign_id("bob-pc")},
            w.k["bob-pc"][1])
        doc = w.next_policy(lambda d: (change(d), d.update(cites=[policy.object_hash(release)] if cite else [])))
        return commit(grant, pol=doc, rel1=release)

    def test_cooperative_release(self):
        w = self.w
        self.refused(self.handover(bind=False), text="release")
        self.refused(self.handover(cite=False), text="cite")
        result = w.apply(self.handover(), me="carol-pc")
        self.assertEqual(w.policy.refresher("g1"), ("carol", "pc"))
        self.assertEqual(result.objects["g1"].payload, {"refresh_token": "r2"})

    def supersede(self, signer="alice-pc", confirmation="revoked at the provider", grant=False):
        w = self.w

        def change(d):
            d["refreshers"]["g1"]["person"] = "carol"
            d["people"]["bob"]["disabled_refresher"] = ["pc"]
        doc = w.next_policy(change)
        record = signing.sign({"schema": 1, "type": "supersession", "repository": w.policy.repository,
                               "grant": "g1", "provider": "xero", "person": "bob", "computer": "pc",
                               "confirmation": confirmation, "writer": w.sign_id(signer)}, w.k[signer][1])
        objs = [w.obj("g1", {"refresh_token": "n"}, "carol-pc", policy.Policy(doc))] if grant else []
        return commit(*objs, pol=doc, sup=record)

    def test_supersession_refused_without_a_verified_profile(self):
        self.refused(self.supersede(), me="carol-pc", text="no verified provider profile")

    def test_supersession(self):
        w = self.w
        doc = self.supersede()["policy.json"]
        self.refused(commit(pol=doc), text="exactly one release or supersession")
        with mock.patch.object(accept_rules.provider_profiles, "recovery_refusal", return_value=None):
            self.refused(self.supersede(signer="bob-pc"), text="administrator")
            self.refused(self.supersede(confirmation=" "), text="confirmation")
            w.apply(self.supersede(), me="carol-pc")
        self.assertEqual(w.policy.refresher("o1"), ("carol", "pc"))
        # The new refresher's first grant revision is accepted although the old one was never readable.
        first = w.apply(commit(w.obj("g1", {"refresh_token": "fresh"}, "carol-pc")), me="carol-pc")
        self.assertEqual(first.objects["g1"].payload, {"refresh_token": "fresh"})

    def test_recovery_key_cannot_move_a_refresher_without_a_record(self):
        w = self.w
        doc = w.next_policy(lambda d: d["refreshers"]["g1"].update(person="carol"))
        grant = w.obj("g1", {"refresh_token": "r2"}, "recovery", policy.Policy(doc))
        self.refused(commit(grant, pol=doc), me="carol-pc", text="exactly one release or supersession")

    def test_provider_token_fields_are_protected(self):
        w = self.w
        tok = {"provider": "gohighlevel", "accessToken": "fictional-a", "expiresAt": 1, "id_token": "i", "tenant": "t1"}
        w.apply(commit(w.obj("o1", tok, "bob-pc", operation="op-1")), latest={"o1": dict(TOK_A)})
        for name, value in (("accessToken", "fictional-b"), ("expiresAt", 2), ("id_token", "j"), ("provider", "x")):
            self.refused(commit(w.obj("o1", dict(tok, **{name: value}), "carol-pc")), latest={"o1": tok},
                         text="access-token")
        w.accept(commit(w.obj("o1", dict(tok, tenant="t2"), "carol-pc")), latest={"o1": tok})

    def test_reader_change_needs_an_administrator(self):
        w = self.w
        doc = w.next_policy(lambda d: d["groups"]["ops"].append("dave"))
        p = policy.Policy(doc)
        objs = [w.obj("s1", {"password": "x"}, "carol-pc", p), w.obj("o1", dict(TOK_A), "alice-pc", p),
                w.obj("index-ops", w.index(p, "ops"), "alice-pc", p)]
        self.refused(commit(*objs, pol=doc), me="dave-pc", text="administrator")

    def test_assignments_keep_group_and_kind(self):
        w = self.w
        for change in ({"group": "fin", "kind": "static"}, {"group": "ops", "kind": "oauth"}):
            doc = w.next_policy(lambda d: d["assignments"].update(s1=dict(change)))
            with self.assertRaises(SecretStoreError) as ctx:
                policy.validate_transition(w.policy, doc)
            self.assertIn("group, kind or provider", str(ctx.exception))

    def test_new_assignment_needs_its_object(self):
        w = self.w
        doc = w.next_policy(lambda d: d["assignments"].update(s2={"group": "ops", "kind": "static"}))
        p = policy.Policy(doc)
        self.refused(commit(w.obj("index-ops", w.index(p, "ops"), "carol-pc", p), pol=doc), text="new assignment")

    def test_index_must_equal_assignments(self):
        w = self.w
        doc = w.next_policy(lambda d: d["assignments"].update(s2={"group": "ops", "kind": "static"}))
        p = policy.Policy(doc)
        s2 = w.obj("s2", {"password": "n"}, "carol-pc", p)
        self.refused(commit(s2, pol=doc), text="index")
        self.refused(commit(s2, w.obj("index-ops", w.index(w.policy, "ops"), "carol-pc", p), pol=doc), text="index")
        w.apply(commit(s2, w.obj("index-ops", w.index(p, "ops"), "carol-pc", p), pol=doc))

    def test_membership_change_reissues_changed_readers(self):
        w = self.w
        doc = w.next_policy(lambda d: d["groups"]["ops"].append("dave"))
        p = policy.Policy(doc)
        self.refused(commit(pol=doc), text="readers change")
        objs = [w.obj("s1", {"password": "x"}, "alice-pc", p), w.obj("o1", dict(TOK_A), "alice-pc", p),
                w.obj("index-ops", w.index(p, "ops"), "alice-pc", p)]
        result = w.apply(commit(*objs, pol=doc), me="dave-pc")
        self.assertTrue(result.objects["o1"].usable)  # an administrator's re-key is a new reader's baseline

    def test_partly_valid_commit_refused_whole(self):
        w = self.w
        good, bad = w.obj("s1", {"password": "ok"}, "carol-pc"), w.obj("f1", {}, "carol-pc")
        self.refused(commit(good, bad), text="authority")
        self.assertEqual(w.cp.objects["s1"]["revision"], 1)
        w.apply(commit(good))


class CheckpointTest(Base):
    def test_signed_and_forward_only(self):
        w, key = self.w, self.w.k["bob-pc"][1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            checkpoint.save(path, w.cp, key)
            self.assertEqual(checkpoint.load(path, key.public_key()), w.cp)
            with self.assertRaises(SecretStoreError):
                checkpoint.load(path, w.k["carol-pc"][1].public_key())
            older = checkpoint.Checkpoint(w.cp.repository, w.cp.policy_epoch - 1, w.cp.policy_hash, {})
            with self.assertRaises(SecretStoreError):
                checkpoint.save(path, older, key)
            w.apply(commit(w.obj("s1", {"password": "y"}, "carol-pc")))
            checkpoint.save(path, w.cp, key)
            self.assertEqual(checkpoint.load(path, key.public_key()).objects["s1"]["revision"], 2)
            data = canonical.loads(path.read_bytes())
            data["policy_epoch"] += 5
            path.write_bytes(canonical.dumps(data))
            with self.assertRaises(SecretStoreError) as ctx:
                checkpoint.load(path, key.public_key())
            self.assertIn("signature", str(ctx.exception))
            with self.assertRaises(SecretStoreError):
                checkpoint.save(Path(tmp) / "clone" / "cp.json", w.cp, key, clone_root=Path(tmp) / "clone")


if __name__ == "__main__":
    unittest.main()
