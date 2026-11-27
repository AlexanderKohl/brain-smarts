"""A member shares one of their own logins with another member (design team-credential-relay.md,
8.6): sealed to the other member's computers in a share file of the team repository, accepted into
their personal store, the file removed; refused for an entry the relay holds, for oneself, for a
forged file, and for a name the other store already has. Bare local repositories are the remotes and
a fake keyring the keychain; every person and value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import json
import unittest

from test_secret_store_store import OTHER, VALUE, git, setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase

from secret_store import SecretStoreError, share, signing  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402


class ShareTests(TeamCase):
    def personal_of(self, name, person, computer):
        bare = self.root / f"{name}.git"
        if not bare.exists():
            git("init", "--quiet", "--bare", "--initial-branch=main", str(bare), cwd=self.root)
        return SecretStore(use_config_file=False, enabled=True, person=person, computer=computer,
                           personal_clone=self.root / name / "clone", checkpoint_dir=self.root / name / "pstate",
                           recovery_package_dir=self.root / name / "packages", personal_repo_url=str(bare))

    def setUp(self):
        super().setUp()
        alice_personal = self.personal_of("pa", "alice", "laptop")
        alice_personal.init_personal(remote_url=str(self.root / "pa.git"), words_callback=self._words)
        alice_personal.open().put_entry("Ads login", {"username": "alice@example.com", "password": VALUE})
        self.admin, pinned = self.team_setup()
        bob_personal = self.personal_of("pb", "bob", "desktop")
        bob_personal.init_personal(remote_url=str(self.root / "pb.git"), words_callback=lambda _w: True)
        self.bob = self.enrol_member(self.admin, pinned, "tb", "bob", "desktop")
        from secret_store import team as team_ops
        team_ops.admit(self.admin.open(), "bob", ["ops"])
        self.alice_personal = lambda: self.personal_of("pa", "alice", "laptop")
        self.bob_personal = lambda: self.personal_of("pb", "bob", "desktop")
        self.bob_team = lambda: self.member("tb", "bob", "desktop")

    def test_a_login_reaches_the_other_member_and_the_file_goes(self):
        path = share.share(self.member("ta", "alice", "laptop"), self.alice_personal(), "Ads login", "bob")
        found = share.incoming(self.bob_team())
        self.assertEqual([(p, d["entry"], d["from"]) for p, d in found], [(path, "Ads login", "alice")])
        self.assertEqual(share.incoming(self.member("ta", "alice", "laptop")), [])  # not addressed to Alice
        self.assertEqual(share.accept(self.bob_team(), self.bob_personal(), path), "Ads login")
        self.assertEqual(self.bob_personal().open().get_fields("Ads login", ["password"]), {"password": VALUE})
        self.assertEqual(share.incoming(self.bob_team()), [])
        self.assertFalse((self.member("ta", "alice", "laptop").open().clone / path).exists())

    def test_refusals(self):
        alice_team = self.member("ta", "alice", "laptop")
        with self.assertRaises(SecretStoreError):
            share.share(alice_team, self.alice_personal(), "Ads login", "bob", relayed={"Ads login": {}})
        with self.assertRaises(SecretStoreError):
            share.share(alice_team, self.alice_personal(), "Ads login", "alice")
        with self.assertRaises(SecretStoreError):
            share.share(alice_team, self.alice_personal(), "No such entry", "bob")
        with self.assertRaises(SecretStoreError):
            share.share(alice_team, self.alice_personal(), "Ads login", "carol")

    def test_a_name_already_held_is_refused_and_another_name_taken(self):
        self.bob_personal().open().put_entry("Ads login", {"password": OTHER})
        path = share.share(self.member("ta", "alice", "laptop"), self.alice_personal(), "Ads login", "bob")
        with self.assertRaises(SecretStoreError):
            share.accept(self.bob_team(), self.bob_personal(), path)
        self.assertEqual(share.accept(self.bob_team(), self.bob_personal(), path, "Ads login (Alice)"), "Ads login (Alice)")

    def test_a_forged_share_is_refused(self):
        path = share.share(self.member("ta", "alice", "laptop"), self.alice_personal(), "Ads login", "bob")
        bob = self.bob_team().open()
        file = bob.clone / path
        doc = json.loads(file.read_text("utf-8"))
        doc["from"] = "bob"
        doc["from_computer"] = "desktop"
        file.write_text(json.dumps(signing.sign({k: v for k, v in doc.items() if k != "signature"},
                                                bob._identity().ed25519)), "utf-8")
        with self.assertRaises(SecretStoreError):
            share.incoming(self.bob_team())  # Bob's key, but Bob's key in the policy is a different id


if __name__ == "__main__":
    unittest.main()
