"""A second computer reads a team secret through a store-backed backend (plan section I). The
rehearsal's sequence: init on the first computer, team-init, a group with the person in it, the
second computer enrolled in the team store, a team secret put, a team recovery package, then the
second computer's agent answers get_fields for the team entry. Two key sets, two clones of each
repository, one bare repository per store, a fake keyring and fake word windows; every value is
fictional. Found: the second computer was never enrolled in the personal store its configuration
names, so its backend's first open of that store met the personal trust root with no pin and
refused the root commit with no reason. The product now says so plainly, a refused commit names
the rule, and the sequence that does both enrolments (design section 6) reads the team secret."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import unittest

from test_secret_store_store import VALUE, git, setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase, match

from secret_store import SecretStoreError, enrol  # noqa: E402
from secret_store import team as team_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.repo import RefusedCommit, SecretRepo  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402

GROUP, ENTRY = "rehearsal", "rehearsal-team"


class SecondComputerCase(TeamCase):
    def setUp(self):
        super().setUp()
        self.team_bare = self.root / "team.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(self.team_bare), cwd=self.root)

    def personal_of(self, name, person, computer, bare=None):
        return SecretStore(use_config_file=False, enabled=True, person=person, computer=computer,
                           personal_clone=self.root / name / "clone", checkpoint_dir=self.root / name / "state",
                           recovery_package_dir=self.root / name / "packages",
                           personal_repo_url=str(bare or self.bare))

    def enrol(self, approver, new, fingerprint):
        rid = enrol.request(new, fingerprint)
        self.assertEqual(enrol.approve_step(approver, rid), "answered")
        enrol.prove(new, rid, display=match)
        self.assertEqual(enrol.approve_step(approver, rid, display=match), "approved")

    def first_computer(self):
        """pc1: init, team-init, the group with the person in it (the rehearsal's step 6 team store)."""
        personal, pinned = self.init()
        team = self.member("a", "tester", "laptop")
        team_pin = team.init_team("example-org", words_callback=self._words,
                                  gh=lambda *args: self.fail("gh must not run when a URL is configured"))
        team_ops.create_groups(team, [GROUP])
        team_ops.set_groups(team, "tester", [GROUP])
        return personal, pinned, team, team_pin

    def put_and_package(self, team):
        team.put_entry(ENTRY, {"value": VALUE}, group=GROUP)
        team.refresh_recovery_package(force=True)

    def backend(self, name, person, computer, bare=None):
        return StoreBackend(self.personal_of(name, person, computer, bare), sync_seconds=3600,
                            team=self.member(name, person, computer))


class SecondComputer(SecondComputerCase):
    # -- the rehearsal's own sequence --------------------------------------------------------------
    def test_team_only_enrolment_is_named_plainly_not_a_refused_commit(self):
        _personal, _pinned, team, team_pin = self.first_computer()
        self.enrol(team, self.member("b", "tester", "desk"), team_pin)
        self.put_and_package(team)
        backend = self.backend("b", "tester", "desk")
        self.assertIn("enrol-request", backend.status()["store"])  # said at the agent's start, before a read
        with self.assertRaises(SecretStoreError) as caught:
            backend.get_fields(ENTRY, ["value"])
        self.assertNotIsInstance(caught.exception, RefusedCommit)
        self.assertIn("not enrolled in the personal store", str(caught.exception))
        self.assertIn("enrol-request", str(caught.exception))
        clone = self.root / "b" / "clone"
        self.assertIsNone(SecretRepo(clone, str(self.bare))._state().get("refused") if (clone / ".git").is_dir()
                          else None)  # nothing is marked refused, so the later enrolment works

    def test_both_enrolments_then_the_agent_reads_the_team_secret(self):
        personal, pinned, team, team_pin = self.first_computer()
        self.enrol(personal, self.personal_of("b", "tester", "desk"), pinned)  # personal: by the person
        self.enrol(team, self.member("b", "tester", "desk"), team_pin)  # team: by an administrator
        self.put_and_package(team)
        backend = self.backend("b", "tester", "desk")
        self.assertEqual(backend.get_fields(ENTRY, ["value"]), {"value": VALUE})
        self.assertNotIn("store_sync", backend.status())

    def test_team_enrolment_first_then_personal_then_the_agent_reads(self):
        personal, pinned, team, team_pin = self.first_computer()
        self.enrol(team, self.member("b", "tester", "desk"), team_pin)
        self.put_and_package(team)
        with self.assertRaisesRegex(SecretStoreError, "not enrolled in the personal store"):
            self.backend("b", "tester", "desk").get_fields(ENTRY, ["value"])
        self.enrol(personal, self.personal_of("b", "tester", "desk"), pinned)
        self.assertEqual(self.backend("b", "tester", "desk").get_fields(ENTRY, ["value"]), {"value": VALUE})

    def test_a_second_person_in_the_group_reads_through_their_own_backend(self):
        _personal, _pinned, team, team_pin = self.first_computer()
        bob_bare = self.root / "bob.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(bob_bare), cwd=self.root)
        self.personal_of("c", "bob", "desk", bob_bare).init_personal(words_callback=self._words)
        self.enrol(team, self.member("c", "bob", "desk"), team_pin)
        team_ops.set_groups(team, "bob", [GROUP])
        self.put_and_package(team)
        self.assertEqual(self.backend("c", "bob", "desk", bob_bare).get_fields(ENTRY, ["value"]), {"value": VALUE})

    def test_a_second_person_without_a_personal_store_is_named_plainly(self):
        _personal, _pinned, team, team_pin = self.first_computer()
        self.enrol(team, self.member("c", "bob", "desk"), team_pin)
        team_ops.set_groups(team, "bob", [GROUP])
        self.put_and_package(team)
        with self.assertRaisesRegex(SecretStoreError, "not enrolled in the personal store"):
            self.backend("c", "bob", "desk").get_fields(ENTRY, ["value"])


class RefusalNamesTheRule(SecondComputerCase):
    """Every refused commit's message names the rule that refused it, never a value (section I,
    last row); the refusal itself stays."""

    def test_a_trust_root_against_another_pin_names_the_pin_rule(self):
        from secret_store import keys
        _personal, _pinned, _team, team_pin = self.first_computer()
        keys.store_private_keys("tester", "desk", *keys.generate_key_pairs())
        with self.assertRaises(RefusedCommit) as caught:
            self.personal_of("b", "tester", "desk").open(team_pin)  # the team pin on the personal repository
        message = str(caught.exception)
        self.assertRegex(message, r"remote commit [0-9a-f]{40} was refused by verification: \S")
        self.assertNotIn("gave no reason", message)
        self.assertIn(caught.exception.reason, SecretRepo(self.root / "b" / "clone", str(self.bare)).status())

    def test_a_tampered_object_names_its_rule_and_no_value(self):
        import base64
        import json
        personal, pinned = self.init()
        personal.open().put_entry("Example API", {"api_key": VALUE})
        attacker = self.root / "attacker"
        git("clone", "--quiet", str(self.bare), str(attacker), cwd=self.root)
        target = next(p for p in (attacker / "objects").glob("*.json") if not p.name.startswith("index-"))
        obj = json.loads(target.read_text("utf-8"))
        obj["ciphertext"] = base64.b64encode(b"x" * 48).decode("ascii")
        target.write_text(json.dumps(obj), "utf-8")
        git("commit", "--quiet", "-am", "update", cwd=attacker)
        git("push", "--quiet", "origin", "main", cwd=attacker)
        with self.assertRaises(RefusedCommit) as caught:
            self.store("b").open(pinned)
        message = str(caught.exception)
        self.assertIn(f"object {target.stem}", message)
        self.assertNotIn(VALUE, message)
        self.assertNotIn(obj["ciphertext"], message)
        with self.assertRaises(SecretStoreError):
            personal.put_entry("Another", {"api_key": VALUE})  # the store still stops

    def test_a_commit_with_another_subject_names_the_shape_rule(self):
        _personal, pinned = self.init()
        side = self.root / "side"
        git("clone", "--quiet", str(self.bare), str(side), cwd=self.root)
        (side / "objects").mkdir(exist_ok=True)
        (side / "objects" / "extra.json").write_text("{}", "utf-8")
        git("add", "objects/extra.json", cwd=side)
        git("commit", "--quiet", "-m", "Example API rotated", cwd=side)
        git("push", "--quiet", "origin", "main", cwd=side)
        with self.assertRaisesRegex(RefusedCommit, "a subject outside the allowed set"):
            self.store("b").open(pinned)

    def test_an_empty_commit_names_its_rule(self):
        _personal, pinned = self.init()
        side = self.root / "side"
        git("clone", "--quiet", str(self.bare), str(side), cwd=self.root)
        git("commit", "--quiet", "--allow-empty", "-m", "update", cwd=side)
        git("push", "--quiet", "origin", "main", cwd=side)
        with self.assertRaisesRegex(RefusedCommit, "must change at least one file"):
            self.store("b").open(pinned)

    def test_a_hostile_pathname_appears_neither_in_the_message_nor_in_the_state_file(self):
        """Sol round 10, low: a fixed rule code and the commit id only, never text from the commit."""
        _personal, pinned = self.init()
        hostile = "fictional-token-abcdefghij"
        side = self.root / "side"
        git("clone", "--quiet", str(self.bare), str(side), cwd=self.root)
        (side / f"{hostile}.json").write_text("{}", "utf-8")
        git("add", f"{hostile}.json", cwd=side)
        git("commit", "--quiet", "-m", "update", cwd=side)
        git("push", "--quiet", "origin", "main", cwd=side)
        with self.assertRaises(RefusedCommit) as caught:
            self.store("b").open(pinned)
        self.assertEqual(caught.exception.code, "commit-path")
        self.assertIn("rule commit-path", str(caught.exception))
        self.assertNotIn(hostile, str(caught.exception))
        clone = self.root / "b" / "clone"
        self.assertNotIn(hostile, (clone / ".git" / "secret-store-state.json").read_text("utf-8"))
        status = SecretRepo(clone, str(self.bare)).status()
        self.assertIn("commit-path", status)
        self.assertNotIn(hostile, status)

if __name__ == "__main__":
    unittest.main()
