"""Enrolment, the team repository and the recovery endorsement: a second personal computer, three
mismatches, an expired request, groups, removal, a non-administrator, and a forged recovery
package. Bare local repositories are the remotes; a fake keyring, fake recovery-word and
enrolment-word displays stand in for the keychain and the windows. Every key and value is fictional."""
import time
import unittest

from test_secret_store_store import (OTHER, VALUE, StoreCase, git, setUpModule,  # noqa: F401
                                     tearDownModule)

from secret_store import SecretStoreError, checkpoint, enrol, keys, recovery, recovery_package  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.policy import Policy, check_endorsement, create_trust_root, public_entry  # noqa: E402
from secret_store.repo import SecretRepo  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402


def match(_title, _words):
    return True


class TeamCase(StoreCase):
    def personal(self, name, computer):
        return SecretStore(use_config_file=False, enabled=True, person="tester", computer=computer,
                           personal_clone=self.root / name / "clone", checkpoint_dir=self.root / name / "state",
                           recovery_package_dir=self.root / name / "packages", personal_repo_url=str(self.bare))

    def member(self, name, person, computer):
        return team_ops.TeamStore(use_config_file=False, enabled=True, person=person, computer=computer,
                                  team_clone=self.root / name / "team", checkpoint_dir=self.root / name / "state",
                                  recovery_package_dir=self.root / name / "packages",
                                  team_repo_url=str(self.team_bare))

    def team_setup(self):
        self.team_bare = self.root / "team.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(self.team_bare), cwd=self.root)
        admin = self.member("ta", "alice", "laptop")
        pinned = admin.init_team("example-org", words_callback=self._words,
                                 gh=lambda *args: self.fail("gh must not run when a URL is configured"))
        team_ops.create_groups(admin, ["ops", "finance"])
        admin.put_entry("Ops API", {"api_key": VALUE}, group="ops")
        admin.put_entry("Finance API", {"api_key": OTHER}, group="finance")
        return admin, pinned

    def enrol_member(self, admin, pinned, name, person, computer):
        new = self.member(name, person, computer)
        rid = enrol.request(new, pinned)
        self.assertEqual(enrol.approve_step(admin, rid), "answered")
        enrol.prove(new, rid, display=match)
        self.assertEqual(enrol.approve_step(admin, rid, display=match), "approved")
        return new


class EnrolmentTests(TeamCase):
    def test_second_personal_computer_enrols_and_reads(self):
        first, pinned = self.init()
        first.open().put_entry("Example API", {"api_key": VALUE})
        new = self.personal("b", "desktop")
        rid = enrol.request(new, pinned)
        with self.assertRaises(SecretStoreError):
            new.get_record("Example API")  # not a reader yet
        self.assertEqual(enrol.approve_step(self.store("a"), rid), "answered")
        shown = {}
        enrol.prove(new, rid, display=lambda title, words: shown.setdefault("new", words) is not None)
        self.assertEqual(enrol.approve_step(self.store("a"), rid,
                                            display=lambda title, words: shown.setdefault("old", words) is not None),
                         "approved")
        self.assertEqual(len(shown["new"]), 6)
        self.assertEqual(shown["new"], shown["old"])
        reopened = self.personal("b", "desktop").open()
        self.assertEqual(reopened.get_fields("Example API", ["api_key"]), {"api_key": VALUE})
        self.assertEqual(list((reopened.clone / "requests").glob("*")) if (reopened.clone / "requests").exists()
                         else [], [])
        reopened.put_entry("From desktop", {"token": OTHER})
        self.assertEqual(self.store("a").open().get_fields("From desktop", ["token"]), {"token": OTHER})
        for words in shown.values():
            self.assertNotIn(" ".join(words), self.out.getvalue() + self.err.getvalue())

    def test_three_mismatches_end_the_enrolment(self):
        first, pinned = self.init()
        new = self.personal("b", "desktop")
        rid = enrol.request(new, pinned)
        enrol.approve_step(first, rid)
        enrol.prove(new, rid, display=match)
        for _ in range(2):
            with self.assertRaisesRegex(SecretStoreError, "did not match"):
                enrol.approve_step(first, rid, display=lambda title, words: False)
        with self.assertRaisesRegex(SecretStoreError, "three mismatches"):
            enrol.approve_step(first, rid, display=lambda title, words: False)
        with self.assertRaises(SecretStoreError):
            enrol.approve_step(first, rid, display=match)  # the attempt has ended
        self.assertNotIn(("tester", "desktop"), first.open().policy.computers)

    def test_expired_request_is_refused(self):
        first, pinned = self.init()
        new = self.personal("b", "desktop")
        rid = enrol.request(new, pinned, now=time.time() - enrol.LIFETIME - 1)
        with self.assertRaisesRegex(SecretStoreError, "expired"):
            enrol.approve_step(first, rid)

    def test_forged_recovery_package_is_refused(self):
        first, _pinned = self.init()
        words = " ".join(self.words)
        rx, re_ = recovery.derive_recovery_keys(words)
        check_endorsement(first.repo.read("policy.json"), re_.public_key())  # the real root is endorsed
        evil_x, evil_e = keys.generate_key_pairs()
        people = {"tester": {"computers": {"evil": public_entry(evil_x.public_key(), evil_e.public_key())},
                             "disabled_refresher": []}}
        forged = create_trust_root(people, public_entry(rx.public_key(), re_.public_key()),
                                   {"personal": ["tester"]}, ["tester"], evil_e)
        forged_bare = self.root / "forged.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(forged_bare), cwd=self.root)
        repo = SecretRepo(self.root / "forger", str(forged_bare)).clone_or_open()
        repo.write({"policy.json": forged}, "policy")
        cp_path = self.root / "forger-state" / "checkpoint.json"
        checkpoint.save(cp_path, checkpoint.initial(Policy(forged)), evil_e)
        package = recovery_package.build(repo, cp_path.read_bytes(), rx.public_key(), self.root / "forged.package")
        with self.assertRaisesRegex(SecretStoreError, "endorsement"):
            SecretStore.restore_from_package(words, package, self.root / "victim")
        restored = SecretStore.restore_from_package(words, first.refresh_recovery_package(), self.root / "real")
        self.assertEqual(restored.list_entries(), [])


class TeamTests(TeamCase):
    def test_member_reads_own_group_only(self):
        admin, pinned = self.team_setup()
        self.enrol_member(admin, pinned, "tb", "bob", "desk")
        bob = self.member("tb", "bob", "desk").open()
        with self.assertRaises(SecretStoreError):
            bob.get_record("Ops API", group="ops")  # enrolled, not yet admitted
        team_ops.admit(admin, "bob", ["ops"])
        bob = self.member("tb", "bob", "desk").open()
        self.assertEqual(bob.get_fields("Ops API", ["api_key"], group="ops"), {"api_key": VALUE})
        with self.assertRaises(SecretStoreError):
            bob.list_entries("finance")
        team_ops.set_groups(admin, "bob", ["ops", "finance"])
        self.assertEqual(self.member("tb", "bob", "desk").open().list_entries("finance"), ["Finance API"])

    def test_removal_rekeys_and_removed_computer_cannot_read(self):
        admin, pinned = self.team_setup()
        self.enrol_member(admin, pinned, "tb", "bob", "desk")
        team_ops.admit(admin, "bob", ["ops"])
        bob = self.member("tb", "bob", "desk").open()
        self.assertEqual(bob.get_fields("Ops API", ["api_key"], group="ops"), {"api_key": VALUE})
        bob_key = keys.key_id(bob._identity().x25519.public_key())
        self.assertEqual(team_ops.remove(admin, "bob"), ["Ops API"])
        oid = team_ops.entry_names(admin.open())
        ops_id = next(k for k, v in oid.items() if v == "Ops API")
        new_revision = admin.repo.read(f"objects/{ops_id}.json")
        self.assertNotIn(bob_key, [r["key"] for r in new_revision["readers"]])
        after = self.member("tb", "bob", "desk").open()  # the commit still verifies structurally
        with self.assertRaises(SecretStoreError):
            after.get_record("Ops API", group="ops")
        self.assertEqual(admin.get_fields("Ops API", ["api_key"], group="ops"), {"api_key": VALUE})

    def test_non_administrator_cannot_admit_or_change_groups(self):
        admin, pinned = self.team_setup()
        self.enrol_member(admin, pinned, "tb", "bob", "desk")
        self.enrol_member(admin, pinned, "tc", "carol", "tablet")
        team_ops.admit(admin, "bob", ["ops"])
        bob = self.member("tb", "bob", "desk").open()
        epoch = bob.policy.epoch
        with self.assertRaises(SecretStoreError):
            team_ops.admit(bob, "carol", ["ops"])
        with self.assertRaises(SecretStoreError):
            team_ops.set_groups(bob, "bob", ["ops", "finance"])
        with self.assertRaises(SecretStoreError):
            enrol.approve_step(bob, enrol.request(self.member("td", "dave", "phone"), pinned))
        self.assertEqual(self.member("tb", "bob", "desk").open().policy.epoch, epoch)

    def test_team_trust_root_is_endorsed_by_the_team_recovery_key(self):
        admin, _pinned = self.team_setup()
        _rx, team_re = recovery.derive_recovery_keys(" ".join(self.words))
        first = SecretRepo(self.root / "inspect", str(self.team_bare)).clone_or_open()
        first.pull(lambda commit, files: True)
        import subprocess
        root_commit = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=first.path,
                                     capture_output=True).stdout.decode().strip()
        from secret_store import canonical
        blob = subprocess.run(["git", "cat-file", "blob", f"{root_commit}:policy.json"], cwd=first.path,
                              capture_output=True).stdout
        check_endorsement(canonical.loads(blob), team_re.public_key())
        with self.assertRaises(SecretStoreError):
            check_endorsement(canonical.loads(blob), keys.generate_key_pairs()[1].public_key())



class RefresherGroupAndRecoveryTests(TeamCase):
    def signin_setup(self):
        from secret_store import oauth_ops
        admin, pinned = self.team_setup()
        bob = self.enrol_member(admin, pinned, "tb", "bob", "pc")
        team_ops.admit(admin, "bob", ["ops"])
        self.enrol_member(admin, pinned, "td", "dave", "pc")
        team_ops.admit(admin, "dave", ["finance"])
        token = {"access_token": "fictional-access", "refresh_token": "fictional-refresh", "token_type": "Bearer"}
        oauth_ops.put_signin(admin, "Ops sign-in", oauth_ops.DEFAULT_FIELD, token, group="ops")
        return admin, bob, oauth_ops.find(admin, "Ops sign-in", oauth_ops.DEFAULT_FIELD, "ops")

    def test_refresher_outside_the_group_is_refused(self):
        from secret_store import handover
        from secret_store.store_ops import next_policy
        admin, _bob, signin = self.signin_setup()
        with self.assertRaisesRegex(SecretStoreError, "not a member of group ops"):
            handover.release(admin, "Ops sign-in", "dave/pc", group="ops")

        def move(doc):
            doc["refreshers"][signin.grant_id].update(person="dave", computer="pc")
        with self.assertRaisesRegex(SecretStoreError, "not a member of the grant's group"):
            Policy(next_policy(admin.policy, admin._identity().ed25519, move))
        handover.release(admin, "Ops sign-in", "bob/pc", group="ops")
        handover.accept(admin, "Ops sign-in", group="ops")
        with self.assertRaisesRegex(SecretStoreError, "move its refresher first"):
            team_ops.set_groups(admin, "bob", ["finance"])
        self.assertIn("bob", admin.open().policy.doc["groups"]["ops"])

    def test_team_recovery_restores_into_the_team_target(self):
        from unittest import mock
        from secret_store import store_ops
        admin, _pinned = self.team_setup()
        words = " ".join(self.words)
        package = admin.refresh_recovery_package(force=True)
        target = self.root / "team-recovered"
        with mock.patch.object(store_ops, "project_repos_root", lambda _root: self.root / "defaults"):
            restored = team_ops.TeamStore.restore_from_package(words, package, target)
        self.assertEqual(restored.clone, target / "brain-team-secrets")
        self.assertTrue((target / "brain-team-secrets" / ".git").is_dir())
        self.assertFalse((self.root / "defaults").exists())
        self.assertEqual(restored.get_record("Ops API", group="ops"), {"api_key": VALUE})
        self.assertEqual(restored.get_record("Finance API", group="finance"), {"api_key": OTHER})


if __name__ == "__main__":
    unittest.main()
