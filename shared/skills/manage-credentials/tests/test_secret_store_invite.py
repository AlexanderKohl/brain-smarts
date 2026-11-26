"""Both ends of a waited-for team enrolment (secret_store/invite.py): the administrator's invite_member
and the new member's join_team, run against each other through a bare local team repository, both
loops at once in two threads; then each loop alone with the other side's steps played in its sleep:
another login's request left alone, a mismatch then a match, an expired request replaced by a new
one, a second computer that keeps its groups, and the checks made before anyone waits. A fake keyring
and fake word windows stand in for the keychain and the windows. Every name and value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import threading
import time
import unittest

from test_secret_store_store import VALUE, setUpModule, tearDownModule  # noqa: F401
from test_secret_store_team import TeamCase, match

from secret_store import SecretStoreError, enrol, invite  # noqa: E402


class Clock:
    """A clock the test moves on; sleep moves it by the poll and then runs the other side's step."""

    def __init__(self, other=None):
        self.now, self.other, self.ticks = time.time(), other, 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.ticks += 1
        if self.ticks > 50:
            raise AssertionError("the loop did not finish")
        if self.other:
            self.other(self)


class InviteCase(TeamCase):
    def setUp(self):
        super().setUp()
        self.admin, self.pinned = self.team_setup()
        self.said = []


class BothEndsTest(InviteCase):
    def test_invite_and_join_meet_through_the_repository(self):
        member = self.member("bob-pc", "bob", "desk")
        shown, result, failure = {}, {}, []

        def show(side):
            return lambda _title, words: shown.setdefault(side, list(words)) is not None

        def administrator():
            try:
                result["computer"] = invite.invite_member(self.admin, "bob", ["ops"], show("admin"), say=self.said.append,
                                                          poll=0.05, wait=120)
            except Exception as error:  # noqa: BLE001 - reported by the main thread
                failure.append(error)

        thread = threading.Thread(target=administrator)
        thread.start()
        groups = invite.join_team(member, self.pinned, show("member"), say=self.said.append, poll=0.05, wait=120)
        thread.join(120)
        self.assertFalse(failure, failure)
        self.assertEqual(result["computer"], "desk")
        self.assertEqual(groups, ["ops"])
        self.assertEqual(len(shown["member"]), 6)
        self.assertEqual(shown["member"], shown["admin"])
        reader = self.member("bob-pc", "bob", "desk").open()
        self.assertEqual(reader.get_fields("Ops API", ["api_key"], group="ops"), {"api_key": VALUE})
        with self.assertRaises(SecretStoreError):
            reader.get_fields("Finance API", ["api_key"], group="finance")
        requests = reader.clone / "requests"
        self.assertEqual(list(requests.glob("*")) if requests.exists() else [], [])
        for words in shown.values():
            self.assertFalse(any(" ".join(words) in line for line in self.said))


class AdministratorTest(InviteCase):
    def test_another_logins_request_is_left_alone(self):
        stranger, member, rids = self.member("eve-pc", "eve", "box"), self.member("bob-pc", "bob", "desk"), {}

        def play(clock):
            if clock.ticks == 1:
                rids["eve"] = enrol.request(stranger, self.pinned, clock.now)
                rids["bob"] = enrol.request(member, self.pinned, clock.now)
            elif clock.ticks == 2:
                enrol.prove(member, rids["bob"], display=match, now=clock.now)

        clock = Clock(play)
        computer = invite.invite_member(self.admin, "bob", ["ops"], match, say=self.said.append,
                                        clock=clock, sleep=clock.sleep)
        self.assertEqual(computer, "desk")
        policy = self.admin.open().policy
        self.assertNotIn(("eve", "box"), policy.computers)
        self.assertFalse((self.admin.clone / "requests" / f"{rids['eve']}.answer.json").exists())

    def test_a_mismatch_is_asked_again_then_a_match_enrols(self):
        member, rid, answers = self.member("bob-pc", "bob", "desk"), {}, iter([False, True])

        def play(clock):
            if clock.ticks == 1:
                rid["id"] = enrol.request(member, self.pinned, clock.now)
            elif clock.ticks == 2:
                enrol.prove(member, rid["id"], display=match, now=clock.now)

        clock = Clock(play)
        invite.invite_member(self.admin, "bob", ["ops"], lambda _t, _w: next(answers), say=self.said.append,
                             clock=clock, sleep=clock.sleep)
        self.assertTrue(any("did not match" in line for line in self.said))
        self.assertIn(("bob", "desk"), self.admin.open().policy.computers)

    def test_an_expired_request_is_let_go_and_the_next_taken_up(self):
        member, rid = self.member("bob-pc", "bob", "desk"), {}

        def play(clock):
            if clock.ticks == 1:
                rid["old"] = enrol.request(member, self.pinned, clock.now)
            elif clock.ticks == 2:
                clock.now += enrol.LIFETIME + 1  # nobody answered in time
            elif clock.ticks == 4:
                rid["new"] = enrol.request(member, self.pinned, clock.now)
            elif clock.ticks == 5:
                enrol.prove(member, rid["new"], display=match, now=clock.now)

        clock = Clock(play)
        invite.invite_member(self.admin, "bob", ["ops"], match, say=self.said.append, clock=clock, sleep=clock.sleep)
        self.assertTrue(any("expired" in line for line in self.said))
        self.assertIn(("bob", "desk"), self.admin.open().policy.computers)

    def test_a_second_computer_keeps_its_groups(self):
        self.enrol_member(self.admin, self.pinned, "bob-pc", "bob", "desk")
        from secret_store import team as team_ops
        team_ops.admit(self.admin.open(), "bob", ["finance"])
        laptop, rid = self.member("bob-lap", "bob", "lap"), {}

        def play(clock):
            if clock.ticks == 1:
                rid["id"] = enrol.request(laptop, self.pinned, clock.now)
            elif clock.ticks == 2:
                enrol.prove(laptop, rid["id"], display=match, now=clock.now)

        clock = Clock(play)
        invite.invite_member(self.admin, "bob", ["ops"], match, say=self.said.append, clock=clock, sleep=clock.sleep)
        self.assertEqual(invite.groups_of(self.admin.open(), "bob"), ["finance"])
        self.assertTrue(any("already in finance" in line for line in self.said))

    def test_checks_before_anyone_waits(self):
        with self.assertRaisesRegex(SecretStoreError, "no such group"):
            invite.invite_member(self.admin, "bob", ["sales"], match, sleep=self.fail)
        member = self.enrol_member(self.admin, self.pinned, "bob-pc", "bob", "desk")
        from secret_store import team as team_ops
        team_ops.admit(self.admin.open(), "bob", ["ops"])
        with self.assertRaisesRegex(SecretStoreError, "administrator"):
            invite.invite_member(member, "carol", ["ops"], match, sleep=self.fail)

    def test_gives_up_after_the_wait(self):
        clock = Clock()
        with self.assertRaisesRegex(SecretStoreError, "within 1 minutes"):
            invite.invite_member(self.admin, "bob", ["ops"], match, wait=60, clock=clock, sleep=clock.sleep)


class ReviewTest(InviteCase):
    """The cases of the build's review: a swapped request, a stop between enrolment and admission, words
    compared past the expiry, and a person's second computer."""

    def test_a_request_swapped_while_it_is_answered_is_let_go(self):
        from unittest import mock
        from secret_store import signing
        carol = self.enrol_member(self.admin, self.pinned, "carol-pc", "carol", "box")
        from secret_store import team as team_ops
        team_ops.admit(self.admin.open(), "carol", ["finance"])
        bob, made = self.member("bob-pc", "bob", "desk"), {}
        real_answer = enrol.answer

        def swap_then_answer(store, rid, now=None):
            # Bob, who can write to the repository, swaps his chosen request for one naming Carol, signed
            # with his own keys, just before the administrator's answer pulls again.
            request = invite._read(store, rid)
            body = {k: v for k, v in request.items() if k != "signature"}
            forged = signing.sign({**body, "login": "carol", "computer": "box2"}, bob._identity().ed25519)
            bob._write(lambda: ({f"requests/{rid}.json": forged}, "update"))
            return real_answer(store, rid, now)

        def play(clock):
            if clock.ticks == 1:
                made["rid"] = enrol.request(bob, self.pinned, clock.now)

        clock = Clock(play)
        with mock.patch.object(enrol, "answer", swap_then_answer):
            with self.assertRaisesRegex(SecretStoreError, "within 1 minutes"):
                invite.invite_member(self.admin, "bob", ["ops"], match, say=self.said.append, wait=60,
                                     clock=clock, sleep=clock.sleep)
        self.assertTrue(any("changed while it was being answered" in line for line in self.said))
        policy = self.admin.open().policy
        self.assertEqual(sorted(c for p, c in policy.computers if p == "carol"), ["box"])
        self.assertIsNone(enrol._load_pending(self.admin, made["rid"]))
        self.assertIsNotNone(carol)

    def test_a_stop_between_enrolment_and_admission_is_finished_by_the_next_invite(self):
        self.enrol_member(self.admin, self.pinned, "bob-pc", "bob", "desk")  # enrolled, never admitted
        computer = invite.invite_member(self.admin, "bob", ["ops"], match, say=self.said.append, sleep=self.fail)
        self.assertEqual(computer, "desk")
        self.assertEqual(invite.groups_of(self.admin.open(), "bob"), ["ops"])

    def test_words_compared_past_the_expiry_enrol_nothing(self):
        from unittest import mock
        member = self.member("bob-pc", "bob", "desk")
        rid = enrol.request(member, self.pinned)
        enrol.answer(self.admin, rid)
        enrol.prove(member, rid, display=match)
        now = [time.time()]

        def slow(_title, _words):
            now[0] += enrol.LIFETIME + 5  # the person looked away from the window
            return True
        with mock.patch.object(enrol.time, "time", lambda: now[0]):
            with self.assertRaisesRegex(SecretStoreError, "expired while the words were compared"):
                enrol.approve(self.admin, rid, slow)
        self.assertNotIn(("bob", "desk"), self.admin.open().policy.computers)

    def test_a_persons_second_computer_joins_their_personal_store(self):
        from secret_store.store_ops import GROUP
        first, pinned = self.init()
        first.open().put_entry("Example API", {"api_key": VALUE})
        second, rid = self.personal("b", "desktop"), {}

        def play(clock):
            if clock.ticks == 1:
                rid["id"] = enrol.request(second, pinned, clock.now)
            elif clock.ticks == 2:
                enrol.prove(second, rid["id"], display=match, now=clock.now)

        clock = Clock(play)
        self.assertEqual(invite.invite_member(first, "tester", [GROUP], match, say=self.said.append,
                                              clock=clock, sleep=clock.sleep), "desktop")
        self.assertEqual(self.personal("b", "desktop").open().get_fields("Example API", ["api_key"]),
                         {"api_key": VALUE})


class MemberTest(InviteCase):
    def administrator(self, display=match):
        rid = {}

        def play(clock):
            self.admin.open()
            if "id" not in rid:
                found = invite.open_request(self.admin, "bob", clock.now)
                if found:
                    rid["id"] = found
                    enrol.answer(self.admin, found, clock.now)
            elif (self.admin.clone / "requests" / f"{rid['id']}.proof.json").exists():
                enrol.approve(self.admin, rid["id"], display, clock.now)
                invite._admit(self.admin, "bob", ["ops"], self.said.append)
                rid["done"] = True
        return play, rid

    def test_join_requests_shows_the_words_and_waits_for_admission(self):
        play, rid = self.administrator()
        clock, shown = Clock(play), []
        member = self.member("bob-pc", "bob", "desk")
        groups = invite.join_team(member, self.pinned, lambda _t, words: shown.append(words) or True,
                                  say=self.said.append, clock=clock, sleep=clock.sleep)
        self.assertEqual(groups, ["ops"])
        self.assertEqual(len(shown), 1)
        self.assertTrue(rid.get("done"))

    def test_an_expired_request_is_replaced_by_a_new_one(self):
        member, made = self.member("bob-pc", "bob", "desk"), []
        play, rid = self.administrator()

        def late(clock):
            if clock.ticks == 1:
                made.append(sorted(p.name for p in (member.clone / "requests").glob("*.json")))
                clock.now += enrol.LIFETIME + 1  # the administrator was not there in time
                return
            play(clock)

        clock = Clock(late)
        invite.join_team(member, self.pinned, match, say=self.said.append, clock=clock, sleep=clock.sleep)
        self.assertTrue(any("making a new one" in line for line in self.said))
        self.assertIn(("bob", "desk"), self.admin.open().policy.computers)

    def test_an_enrolled_computer_only_waits_for_admission(self):
        member = self.enrol_member(self.admin, self.pinned, "bob-pc", "bob", "desk")

        def admit(clock):
            invite._admit(self.admin.open(), "bob", ["finance"], self.said.append)

        clock = Clock(admit)
        self.assertEqual(invite.join_team(member, None, self.fail, say=self.said.append, clock=clock,
                                          sleep=clock.sleep), ["finance"])


if __name__ == "__main__":
    unittest.main()
