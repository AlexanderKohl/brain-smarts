"""Token relay: the record, the GitHub backend and the relayed store's rules (lease, saves with and
without the lease, recovery, fail-closed). One test per scenario of review findings 1 to 6 is named
after its finding (test_finding_N_...), and one per scenario of the second review's findings 1 to 5
(test_review2_finding_N_...); the third review's are in test_token_relay_review3.py. The
vault-backed store and the command line are in test_token_relay_vault.py.

Every test runs on the in-memory backend or a fake gh runner: no network, no gh call, no Vault
Agent and no real vault. Every name, token and key is invented.
"""

from __future__ import annotations

import base64
import copy
import io
import json
import sys
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import token_relay  # noqa: E402
import token_relay_backend as trb  # noqa: E402
import token_relay_store  # noqa: E402
from portable_vault import CredentialError  # noqa: E402

KEY = bytes(range(32))
ENTRY = "example-oauth"
NAME = "example-oauth.json"
START = 1_900_000_000.0
LEASE_B = {"holder": "brain-b-202", "id": "lease-b-1", "seconds": 120}


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class LocalStore:
    """Stands in for the local vault field."""

    def __init__(self, value: dict | None = None) -> None:
        self.value = copy.deepcopy(value or {})

    def load(self) -> dict:
        return copy.deepcopy(self.value)

    def save(self, value: dict) -> None:
        self.value = copy.deepcopy(value)

    @contextmanager
    def rotation_lock(self):
        yield


def token(number: int, expires_at: float, obtained_at: float | None = None) -> dict:
    return {
        "access_token": f"example-access-{number}",
        "refresh_token": f"example-refresh-{number}",
        "expires_at": expires_at,
        "obtained_at": START + number if obtained_at is None else obtained_at,
    }


def seed(backend, value: dict, version: int = 1, lease=None) -> None:
    record = trb.build_record(
        KEY, ENTRY, version, value, lease=lease, holder="seed-host-1", updated_at="2030-03-17T00:00:00+00:00"
    )
    current = backend.files.get(NAME)
    backend.put(NAME, trb.dump_record(record), current[1] if current else None, "seed")


def remote(backend) -> tuple[dict, dict]:
    record = trb.parse_record(backend.files[NAME][0], ENTRY)
    return record, trb.decrypt_token(KEY, ENTRY, record)


def relay(backend, local, clock, holder="brain-a-101", sleep=None, stderr=None, key_provider=None):
    token_relay_store._LAST_RECOVERY.clear()  # each test's clock starts again at START
    return token_relay.RelayedStore(
        local,
        ENTRY,
        backend=backend,
        key_provider=key_provider or (lambda: KEY),
        lease_seconds=120,
        holder=holder,
        clock=clock,
        wall_clock=clock,
        sleep=sleep or clock.advance,
        stderr=stderr if stderr is not None else io.StringIO(),
    )


def at(version: int, value: dict) -> LocalStore:
    return LocalStore({**value, "_relay_version": version})


class CryptoTests(unittest.TestCase):
    def test_round_trip_and_fresh_nonce(self):
        value = {**token(1, START + 1800), "_relay_version": 4, "_relay_unpushed": True}
        first = trb.build_record(KEY, ENTRY, 4, value, lease=None, holder="h-1", updated_at="t")
        second = trb.build_record(KEY, ENTRY, 4, value, lease=None, holder="h-1", updated_at="t")
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assertEqual(trb.decrypt_token(KEY, ENTRY, first), token(1, START + 1800))

    def test_tampered_record_or_wrong_associated_data_fails(self):
        record = trb.build_record(KEY, ENTRY, 2, token(1, START), lease=None, holder="h-1", updated_at="t")
        raw = bytearray(base64.b64decode(record["ciphertext"]))
        raw[0] ^= 1
        tampered = {**record, "ciphertext": base64.b64encode(bytes(raw)).decode()}
        cases = [
            (KEY, ENTRY, tampered),
            (KEY, ENTRY, {**record, "version": 3}),
            (KEY, ENTRY, {**record, "lease": LEASE_B}),
            (KEY, "other-oauth", record),
            (bytes(32), ENTRY, record),
        ]
        for key, entry, candidate in cases:
            with self.assertRaises(trb.RelayIntegrityError):
                trb.decrypt_token(key, entry, candidate)

    def test_key_must_be_32_bytes(self):
        self.assertEqual(len(trb.decode_key(trb.new_key_text())), 32)
        with self.assertRaises(CredentialError):
            trb.decode_key(base64.b64encode(b"short").decode())

    def test_names_are_anchored_and_a_repository_starts_with_a_letter_or_digit(self):
        for entry in ("example-oauth\n", ".hidden", "a/b"):
            with self.assertRaises(CredentialError):
                trb.validate_entry(entry)
        for repository in ("example-owner/..", "example-owner/.git", "example-owner/relay\n", "-x/relay"):
            with self.assertRaises(CredentialError):
                trb.GitHubBackend(repository, runner=FakeRunner([]))
        trb.GitHubBackend("example-owner/example-relay.data", runner=FakeRunner([]))


class FakeRunner:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs.get("input", b"")))
        code, stdout, stderr = self.answers.pop(0)
        return mock.Mock(returncode=code, stdout=stdout, stderr=stderr)


NOT_FOUND = (1, b'{"message":"Not Found"}', b"gh: Not Found (HTTP 404)")


class GitHubBackendTests(unittest.TestCase):
    def test_get_put_conflict_and_no_secret_in_arguments(self):
        content = trb.dump_record(
            trb.build_record(KEY, ENTRY, 1, token(7, START), lease=None, holder="h-1", updated_at="t")
        )
        answer = json.dumps({"content": base64.b64encode(content).decode(), "sha": "abc"}).encode()
        runner = FakeRunner(
            [
                NOT_FOUND,
                (0, b'{"full_name":"example-owner/example-relay"}', b""),
                (0, answer, b""),
                (0, json.dumps({"content": {"sha": "def"}}).encode(), b""),
                (1, b"{}", b"gh: is at x but expected y (HTTP 409)"),
                (1, b"{}", b"gh: Server Error (HTTP 502)"),
            ]
        )
        backend = trb.GitHubBackend("example-owner/example-relay", runner=runner)
        self.assertEqual(backend.get(NAME), (None, None))
        self.assertEqual(runner.calls[1][0][-1], "repos/example-owner/example-relay")
        self.assertEqual(backend.get(NAME), (content, "abc"))
        self.assertEqual(backend.put(NAME, content, "abc", "token-relay: example"), "def")
        with self.assertRaises(trb.Conflict):
            backend.put(NAME, content, "abc", "m")
        with self.assertRaises(trb.RelayUnavailable):
            backend.put(NAME, content, "abc", "m")
        for command, body in runner.calls:
            self.assertEqual(command[:2], ["gh", "api"])
            joined = " ".join(command)
            for secret in ("example-refresh-7", "example-access-7", "ciphertext"):
                self.assertNotIn(secret, joined)
            self.assertNotIn(b"example-refresh-7", body)
        put_command, put_body = runner.calls[3]
        self.assertIn("--input", put_command)
        self.assertEqual(json.loads(put_body)["sha"], "abc")

    def test_finding_1_a_404_for_an_unreadable_repository_is_unreachable(self):
        runner = FakeRunner([NOT_FOUND, NOT_FOUND])
        backend = trb.GitHubBackend("example-owner/example-relay", runner=runner)
        with self.assertRaises(trb.RelayUnavailable):
            backend.get(NAME)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        self.old = token(1, START + 30)
        self.local = at(1, self.old)

    def test_waits_out_a_lease_on_its_own_clock_then_takes_it_over(self):
        seed(self.backend, self.old, lease=LEASE_B)
        store = relay(self.backend, self.local, self.clock)
        with store.rotation_lock():
            record, _ = remote(self.backend)
            self.assertEqual(record["lease"]["holder"], "brain-a-101")
        self.assertGreaterEqual(self.clock.now, START + 120)

    def test_wait_ends_when_the_holder_pushes_a_fresh_token(self):
        seed(self.backend, self.old, lease=LEASE_B)
        fresh = token(2, START + 1800)

        def other_brain_finishes(seconds):
            self.clock.advance(seconds)
            if remote(self.backend)[0]["version"] == 1:
                seed(self.backend, fresh, version=2)

        store = relay(self.backend, self.local, self.clock, sleep=other_brain_finishes)
        with store.rotation_lock():
            self.assertEqual(store.load(), fresh)
        self.assertIsNone(remote(self.backend)[0]["lease"])
        self.assertEqual(self.local.value["_relay_version"], 2)

    def test_new_leases_past_the_window_refuse(self):
        seed(self.backend, self.old, lease=LEASE_B)
        count = iter(range(2, 1000))

        def another_lease_each_time(seconds):
            self.clock.advance(seconds)
            seed(self.backend, self.old, lease={**LEASE_B, "id": f"lease-b-{next(count)}"})

        store = relay(self.backend, self.local, self.clock, sleep=another_lease_each_time)
        with self.assertRaisesRegex(CredentialError, "still holds the relay lease"):
            with store.rotation_lock():
                pass
        self.assertLessEqual(self.clock.now, START + 120 + 10 + 2)

    def test_lease_released_when_leaving_without_a_save_and_authenticated(self):
        seed(self.backend, self.old)
        before = remote(self.backend)[0]["nonce"]
        store = relay(self.backend, self.local, self.clock)
        with store.rotation_lock():
            record, value = remote(self.backend)
            self.assertEqual((record["lease"]["holder"], value), ("brain-a-101", self.old))
            self.assertNotEqual(record["nonce"], before)
        self.assertIsNone(remote(self.backend)[0]["lease"])
        self.assertTrue(any("release" in message for message in self.backend.messages))

    def test_no_lease_while_the_token_is_valid(self):
        seed(self.backend, token(1, START + 1800))
        self.local.value = {**token(1, START + 1800), "_relay_version": 1}
        with relay(self.backend, self.local, self.clock).rotation_lock():
            self.assertIsNone(remote(self.backend)[0]["lease"])

    def test_forced_refresh_takes_the_lease_even_when_valid(self):
        seed(self.backend, token(1, START + 1800))
        with relay(self.backend, self.local, self.clock).rotation_lock(refresh=True):
            self.assertEqual(remote(self.backend)[0]["lease"]["holder"], "brain-a-101")

    def test_finding_6_the_callers_leeway_decides_the_lease(self):
        value = token(1, START + 200)
        for leeway, expected in ((300, "brain-a-101"), (90, None)):
            backend = trb.MemoryBackend()
            seed(backend, value)
            with relay(backend, at(1, value), self.clock).rotation_lock(leeway_seconds=leeway):
                lease = remote(backend)[0]["lease"]
                self.assertEqual(lease["holder"] if lease else None, expected)
        backend = trb.MemoryBackend()
        backend.unreachable = True
        with self.assertRaisesRegex(CredentialError, "cannot be reached"):
            with relay(backend, at(1, value), self.clock).rotation_lock(leeway_seconds=300):
                pass


class FailClosedTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()

    def test_finding_1_an_unseeded_listed_entry_refuses_and_takes_no_lease(self):
        for forced in (False, True):
            store = relay(self.backend, at(1, token(1, START + 30)), self.clock)
            with self.assertRaisesRegex(trb.RelayIntegrityError, "no shared record"):
                with store.rotation_lock(refresh=forced):
                    self.fail("the refresh must not run")
        with self.assertRaises(trb.RelayIntegrityError):
            relay(self.backend, at(1, token(1, START + 1800)), self.clock).save({"selected_tenant_id": "t"})
        self.assertEqual(self.backend.files, {})

    def test_finding_2_a_rolled_back_record_is_refused_in_lock_and_save(self):
        seed(self.backend, token(2, START + 1800), version=2)
        local = at(5, {**token(5, START + 1800), "selected_tenant_id": "tenant-example"})
        store = relay(self.backend, local, self.clock)
        with self.assertRaisesRegex(trb.RelayIntegrityError, "rollback"):
            with store.rotation_lock():
                pass
        with self.assertRaisesRegex(trb.RelayIntegrityError, "rollback"):
            store.save({**token(5, START + 1800), "selected_tenant_id": "tenant-other"})
        self.assertEqual(remote(self.backend)[1]["refresh_token"], "example-refresh-2")
        self.assertEqual(local.value["_relay_version"], 5)

    def test_finding_5_a_lease_set_or_cleared_without_the_key_is_refused(self):
        for authentic, forged in ((None, LEASE_B), (LEASE_B, None)):
            backend = trb.MemoryBackend()
            seed(backend, token(1, START + 30), lease=authentic)
            content, tag = backend.files[NAME]
            backend.files[NAME] = (trb.dump_record({**json.loads(content), "lease": forged}), tag)
            with self.assertRaises(trb.RelayIntegrityError):
                with relay(backend, at(1, token(1, START + 30)), self.clock).rotation_lock():
                    self.fail("the refresh must not run")

    def test_finding_5_a_missing_key_refuses_before_the_lease_at_equal_versions(self):
        seed(self.backend, token(1, START + 30))
        before = self.backend.files[NAME]

        def no_key():
            raise CredentialError("The relay key is missing or malformed.")

        store = relay(self.backend, at(1, token(1, START + 30)), self.clock, key_provider=no_key)
        with self.assertRaisesRegex(CredentialError, "relay key"):
            with store.rotation_lock(refresh=True):
                self.fail("the refresh must not run")
        self.assertEqual(self.backend.files[NAME], before)

    def test_finding_5_an_integrity_error_in_a_save_is_raised_not_swallowed(self):
        seed(self.backend, token(1, START + 1800))
        store = relay(self.backend, at(1, token(1, START + 1800)), self.clock)
        with store.rotation_lock():
            content, tag = self.backend.files[NAME]
            record = json.loads(content)
            record["ciphertext"] = base64.b64encode(b"x" * 40).decode()
            self.backend.files[NAME] = (trb.dump_record(record), tag)
            with self.assertRaises(trb.RelayIntegrityError):
                store.save({**token(1, START + 1800), "selected_tenant_id": "tenant-example"})


class SaveAndRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        seed(self.backend, token(1, START + 30))
        self.local = at(1, token(1, START + 30))

    def test_save_in_the_lease_pushes_a_new_version_and_clears_the_lease(self):
        store = relay(self.backend, self.local, self.clock)
        with store.rotation_lock():
            store.save(token(2, START + 1800))
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value), (2, None, token(2, START + 1800)))
        self.assertEqual(self.local.value, {**token(2, START + 1800), "_relay_version": 2})

    def test_crash_before_push_is_recovered_at_the_next_lock(self):
        stderr = io.StringIO()
        store = relay(self.backend, self.local, self.clock, stderr=stderr)
        with store.rotation_lock():
            self.backend.unreachable = True
            store.save(token(2, START + 1800))
        self.assertEqual(
            (self.local.value["_relay_unpushed"], self.local.value["_relay_version"],
             self.local.value["_relay_base_version"]), ("token", 1, 1)
        )
        self.assertIn("kept on this computer", stderr.getvalue())
        self.backend.unreachable = False
        # Third review, finding 1: a second store instance (a later process) recovers over the
        # lease the failed save left, here even under another holder name, by the kept lease id.
        with relay(self.backend, self.local, self.clock, holder="brain-a-102").rotation_lock():
            pass
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value), (2, token(2, START + 1800)))
        self.assertNotIn("_relay_unpushed", self.local.value)
        for secret in ("example-refresh-2", "example-access-2", base64.b64encode(KEY).decode()):
            self.assertNotIn(secret, stderr.getvalue())
            self.assertFalse(any(secret in message for message in self.backend.messages))

    def test_unpushed_token_is_recovered_at_the_next_save_outside_a_lock(self):
        store = relay(self.backend, self.local, self.clock)
        with store.rotation_lock():
            self.backend.unreachable = True
            store.save(token(2, START + 1800))
        self.backend.unreachable = False
        store.save({**token(2, START + 1800), "selected_tenant_id": "tenant-example"})
        record, value = remote(self.backend)
        self.assertEqual(record["version"], 2)  # the token and the new data in one version
        self.assertEqual(value, {**token(2, START + 1800), "selected_tenant_id": "tenant-example"})

    def test_metadata_save_keeps_the_shared_chain_and_waits_for_a_foreign_lease(self):
        store = relay(self.backend, at(1, token(1, START + 1800)), self.clock)
        with store.rotation_lock():
            current = store.load()
            seed(self.backend, token(5, START + 1800), version=2, lease=LEASE_B)
            store.save({**current, "selected_tenant_id": "tenant-example"})
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (2, "example-refresh-5"))
        self.assertNotIn("selected_tenant_id", value)
        self.assertEqual(store.load()["refresh_token"], "example-refresh-5")
        self.assertEqual(store.local.value["_relay_changed"], ["selected_tenant_id"])
        seed(self.backend, token(6, START + 1800), version=3)
        with store.rotation_lock():
            pass
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (4, "example-refresh-6"))
        self.assertEqual(value["selected_tenant_id"], "tenant-example")

    def test_bookkeeping_keys_never_reach_the_caller_or_the_record(self):
        store = relay(self.backend, self.local, self.clock)
        self.assertEqual(store.load(), token(1, START + 30))
        with store.rotation_lock():
            store.save({**token(2, START + 1800), "_relay_version": 99, "_relay_unpushed": True})
        self.assertEqual(remote(self.backend)[1], token(2, START + 1800))

    def test_sync_adopts_the_record_on_an_empty_computer(self):
        local = LocalStore({})
        relay(self.backend, local, self.clock).sync()
        self.assertEqual(local.value, {**token(1, START + 30), "_relay_version": 1})


class FindingThreeAndFourTests(unittest.TestCase):
    """Unpushed saves, stale loads and slow refreshes never restore a spent refresh token."""

    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        self.stderr = io.StringIO()
        seed(self.backend, token(1, START + 1800))
        self.local = at(1, token(1, START + 1800))
        self.store = relay(self.backend, self.local, self.clock, stderr=self.stderr)

    def test_finding_3_1_an_unpushed_save_never_raises_the_local_version(self):
        self.backend.unreachable = True
        self.store.save({**token(1, START + 1800), "selected_tenant_id": "tenant-example"})
        self.assertEqual(self.local.value["_relay_version"], 1)
        self.backend.unreachable = False
        seed(self.backend, token(2, START + 1800), version=2)
        self.store.save({**self.store.load(), "location_note": "example"})
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (4, "example-refresh-2"))
        self.assertEqual((value["selected_tenant_id"], value["location_note"]), ("tenant-example", "example"))
        self.assertEqual(self.local.value, {**value, "_relay_version": 4})

    def test_finding_3_2_recovery_after_two_unpushed_saves_keeps_the_newer_remote(self):
        self.backend.unreachable = True
        with self.store.rotation_lock():
            self.store.save({**self.store.load(), "selected_tenant_id": "tenant-example"})
            self.store.save({**self.store.load(), "location_note": "example"})
        self.assertEqual(self.local.value["_relay_version"], 1)
        self.backend.unreachable = False
        seed(self.backend, token(2, START + 1800), version=2)
        with self.store.rotation_lock():
            pass
        _, value = remote(self.backend)
        self.assertEqual(value["refresh_token"], "example-refresh-2")
        self.assertEqual((value["selected_tenant_id"], value["location_note"]), ("tenant-example", "example"))

    def test_finding_3_3_recovery_compares_versions_not_clocks(self):
        seed(self.backend, token(2, START + 30, obtained_at=START + 9_000), version=2)
        self.local.value = at(2, token(2, START + 30, obtained_at=START + 9_000)).value
        brain_b = relay(self.backend, at(2, token(2, START + 30, obtained_at=START + 9_000)), self.clock,
                        holder="brain-b-202")
        with self.store.rotation_lock():
            self.backend.unreachable = True
            self.store.save(token(3, START + 1800, obtained_at=START + 5))
            self.backend.unreachable = False
            brain_b.save({**brain_b.load(), "selected_tenant_id": "tenant-example"})
        self.assertEqual(remote(self.backend)[0]["version"], 2)
        with self.store.rotation_lock():
            pass
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (3, "example-refresh-3"))
        self.assertIs(brain_b.local.value["_relay_unpushed"], True)
        with brain_b.rotation_lock():
            pass
        self.assertNotIn("dropped", brain_b._stderr.getvalue())
        self.assertEqual(remote(self.backend)[1]["selected_tenant_id"], "tenant-example")
        self.assertEqual(brain_b.load()["refresh_token"], "example-refresh-3")

    def test_finding_4_1_a_load_before_the_lock_cannot_restore_a_spent_token(self):
        stale = self.store.load()
        seed(self.backend, token(2, START + 1800), version=2)
        with self.store.rotation_lock():
            self.store.save({**stale, "selected_tenant_id": "tenant-example"})
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (3, "example-refresh-2"))
        self.assertEqual(value["selected_tenant_id"], "tenant-example")
        self.assertEqual(self.store.load()["refresh_token"], "example-refresh-2")
        seed(self.backend, token(3, START + 1800), version=4)
        with self.store.rotation_lock():
            self.store.save(stale)
        self.assertEqual(remote(self.backend)[1]["refresh_token"], "example-refresh-3")

    def test_finding_4_2_a_slow_refresh_after_a_lease_takeover_is_dropped_not_pushed(self):
        brain_b = relay(self.backend, at(1, token(1, START + 1800)), self.clock, holder="brain-b-202")
        with self.store.rotation_lock(refresh=True):
            self.clock.advance(200)
            with brain_b.rotation_lock(refresh=True):
                brain_b.save(token(3, START + 1800))
            self.store.save(token(2, START + 1800))
        self.assertIn("lease was taken over", self.stderr.getvalue())
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (2, "example-refresh-3"))
        self.assertEqual(self.local.value["_relay_unpushed"], "token")
        with self.store.rotation_lock():
            pass
        self.assertIn("was dropped", self.stderr.getvalue())
        self.assertEqual(self.store.load(), token(3, START + 1800))
        self.assertEqual(remote(self.backend)[0]["version"], 2)


class SecondReviewTests(unittest.TestCase):
    """The scenarios of the second review's findings 1 to 5, on the relayed store."""

    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        self.stderr = io.StringIO()
        seed(self.backend, token(1, START + 1800))
        self.local = at(1, token(1, START + 1800))
        self.store = relay(self.backend, self.local, self.clock, stderr=self.stderr)

    def take_over_after_a_slow_refresh(self):
        """Brain A's slow refresh is overtaken by brain B's lease; A keeps R2 as unpushed."""
        brain_b = relay(self.backend, at(1, token(1, START + 1800)), self.clock, holder="brain-b-202")
        b_lock = ExitStack()
        with self.store.rotation_lock(refresh=True):
            self.clock.advance(200)
            b_lock.enter_context(brain_b.rotation_lock(refresh=True))
            self.store.save(token(2, START + 1800))
        self.assertEqual(self.local.value["_relay_unpushed"], "token")
        self.assertEqual(remote(self.backend)[0]["lease"]["holder"], "brain-b-202")
        return brain_b, b_lock

    def test_review2_finding_1_recovery_leaves_a_live_foreign_lease_alone(self):
        brain_b, b_lock = self.take_over_after_a_slow_refresh()
        before = self.backend.files[NAME]
        with self.store.rotation_lock():
            pass
        self.store.save({**self.store.load(), "selected_tenant_id": "tenant-example"})
        self.assertEqual(self.backend.files[NAME], before)
        self.assertEqual(self.store.load()["refresh_token"], "example-refresh-2")
        self.assertEqual(self.local.value["_relay_unpushed"], "token")
        brain_b.save(token(3, START + 1800))
        b_lock.close()
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value["refresh_token"]), (2, None, "example-refresh-3"))
        with self.store.rotation_lock():
            pass
        self.assertIn("was dropped", self.stderr.getvalue())
        self.assertEqual(self.store.load()["refresh_token"], "example-refresh-3")
        self.assertNotIn("_relay_unpushed", self.local.value)
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value["refresh_token"]), (3, "example-refresh-3"))
        self.assertEqual(value["selected_tenant_id"], "tenant-example")

    def test_review2_finding_1_recovery_pushes_once_the_lease_runs_out_on_this_clock(self):
        brain_b, b_lock = self.take_over_after_a_slow_refresh()
        with self.store.rotation_lock():
            pass
        self.assertEqual(remote(self.backend)[0]["version"], 1)
        self.clock.advance(121)
        with self.store.rotation_lock():
            pass
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value), (2, None, token(2, START + 1800)))
        self.assertNotIn("_relay_unpushed", self.local.value)
        b_lock.close()

    def test_review2_finding_1_a_dropped_token_loses_its_token_marker(self):
        brain_b, b_lock = self.take_over_after_a_slow_refresh()
        brain_b.save(token(3, START + 1800))
        b_lock.close()
        seed(self.backend, token(3, START + 1800), version=2, lease={**LEASE_B, "holder": "brain-c-303"})
        self.store.save({**token(2, START + 1800), "selected_tenant_id": "tenant-example"})
        self.assertIn("was dropped", self.stderr.getvalue())
        self.assertIs(self.local.value["_relay_unpushed"], True)
        self.assertEqual(self.store.load()["refresh_token"], "example-refresh-3")

    def test_review2_finding_2_a_cleared_computer_adopts_the_same_version_again(self):
        self.store.clear()
        self.assertEqual(self.local.value, {"_relay_version": 1})
        self.store.sync()
        self.assertEqual(self.store.load(), token(1, START + 1800))
        self.assertEqual(self.local.value["_relay_version"], 1)

    def test_review2_finding_3b_a_first_sign_in_with_no_record_goes_ahead_locally(self):
        backend = trb.MemoryBackend()
        local = LocalStore({})
        store = relay(backend, local, self.clock, stderr=self.stderr)
        with store.rotation_lock(refresh=True, new_authorisation=True):
            store.save(token(2, START + 1800))
        self.assertEqual(local.value, token(2, START + 1800))
        self.assertEqual(backend.files, {})
        self.assertIn(f"seed --entry {ENTRY} --replace next", self.stderr.getvalue())
        refused = (
            (LocalStore({}), {"refresh": True}),
            (LocalStore({}), {"new_authorisation": True}),
        )  # third review, finding 2: a refresh token here no longer refuses a new authorisation
        for candidate, options in refused:
            with self.assertRaisesRegex(trb.RelayIntegrityError, "no shared record"):
                with relay(backend, candidate, self.clock).rotation_lock(**options):
                    self.fail("a missing record must refuse here")
        with self.assertRaisesRegex(trb.RelayIntegrityError, "no shared record"):
            relay(backend, local, self.clock).save({**token(2, START + 1800), "selected_tenant_id": "t"})
        self.assertEqual((backend.files, local.value), ({}, token(2, START + 1800)))

    def test_review2_finding_4_a_load_offers_an_unpushed_token_at_most_every_30_seconds(self):
        with self.store.rotation_lock(refresh=True):
            self.backend.unreachable = True
            self.store.save(token(2, START + 1800))
        self.assertEqual(self.local.value["_relay_unpushed"], "token")
        self.assertEqual(self.store.load(), token(2, START + 1800))
        self.backend.unreachable = False
        self.clock.advance(29)
        self.assertEqual(self.store.load(), token(2, START + 1800))
        self.assertEqual(remote(self.backend)[0]["version"], 1)
        self.clock.advance(1)
        # Third review, finding 1: the next process on this computer (a second store instance,
        # the same computer holder) recovers over its own lease at once.
        later = relay(self.backend, self.local, self.clock, stderr=self.stderr)
        self.assertEqual(later.load(), token(2, START + 1800))
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value), (2, None, token(2, START + 1800)))
        self.assertNotIn("_relay_unpushed", self.local.value)

    def test_review2_finding_5_one_save_after_an_offline_one_makes_one_version(self):
        self.backend.unreachable = True
        self.store.save({**token(1, START + 1800), "selected_tenant_id": "tenant-1"})
        self.backend.unreachable = False
        pushed = len(self.backend.messages)
        self.store.save({**token(1, START + 1800), "selected_tenant_id": "tenant-0", "location_note": "x"})
        self.assertEqual(len(self.backend.messages), pushed + 1)
        record, value = remote(self.backend)
        self.assertEqual(record["version"], 2)
        self.assertEqual((value["selected_tenant_id"], value["location_note"]), ("tenant-0", "x"))
        self.assertEqual(self.local.value, {**value, "_relay_version": 2})


class UnreachableTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        self.backend.unreachable = True
        self.stderr = io.StringIO()

    def test_carries_on_when_the_local_token_is_valid(self):
        with relay(self.backend, at(1, token(1, START + 1800)), self.clock, stderr=self.stderr).rotation_lock():
            pass
        self.assertIn("unreachable", self.stderr.getvalue())

    def test_fails_closed_when_expiring_or_forced(self):
        for value, forced in ((token(1, START + 60), False), (token(1, START + 1800), True)):
            with self.assertRaisesRegex(CredentialError, "refresh or new authorisation is refused"):
                with relay(self.backend, at(1, value), self.clock).rotation_lock(refresh=forced):
                    pass


class FakeProvider:
    """Issues a new refresh token per refresh and refuses one spent twice."""

    def __init__(self, clock):
        self.clock = clock
        self.issued = 1
        self.spent: list[str] = []

    def refresh(self, refresh_token: str) -> dict:
        if refresh_token in self.spent:
            raise AssertionError(f"refresh token spent twice: {refresh_token}")
        self.spent.append(refresh_token)
        self.issued += 1
        return token(self.issued, self.clock() + 1800, obtained_at=self.clock())


def client_refresh(store, provider, clock, force=False) -> dict:
    """The library clients' refresh(), reduced to the relay-relevant steps."""
    with store.rotation_lock(refresh=force):
        current = store.load()
        if not force and current.get("access_token") and current["expires_at"] > clock() + 90:
            return current
        updated = provider.refresh(current["refresh_token"])
        store.save(updated)
        return updated


class TwoBrainTests(unittest.TestCase):
    def test_brains_refreshing_in_turn_never_spend_the_same_refresh_token(self):
        clock = Clock()
        backend = trb.MemoryBackend()
        provider = FakeProvider(clock)
        seed(backend, token(1, START + 30))
        brain_a = relay(backend, at(1, token(1, START + 30)), clock, "brain-a-101")
        brain_b = relay(backend, LocalStore({}), clock, "brain-b-202")
        for turn in range(6):
            first, second = (brain_a, brain_b) if turn % 2 == 0 else (brain_b, brain_a)
            client_refresh(first, provider, clock)
            client_refresh(second, provider, clock)
            self.assertEqual(first.load(), second.load())
            clock.advance(1800)
        self.assertEqual(len(provider.spent), 6)
        self.assertEqual(len(set(provider.spent)), 6)

    def test_a_brain_waiting_on_a_lease_picks_up_the_holders_token(self):
        clock = Clock()
        backend = trb.MemoryBackend()
        provider = FakeProvider(clock)
        seed(backend, token(1, START + 30))
        brain_a = relay(backend, at(1, token(1, START + 30)), clock, "brain-a-101")
        stack = ExitStack()
        stack.enter_context(brain_a.rotation_lock())
        self.assertEqual(remote(backend)[0]["lease"]["holder"], "brain-a-101")

        def brain_a_finishes(seconds):
            clock.advance(seconds)
            if stack._exit_callbacks:
                brain_a.save(provider.refresh(brain_a.load()["refresh_token"]))
                stack.close()

        brain_b = relay(backend, at(1, token(1, START + 30)), clock, "brain-b-202", sleep=brain_a_finishes)
        result = client_refresh(brain_b, provider, clock)
        self.assertEqual(provider.spent, ["example-refresh-1"])
        self.assertEqual(result["refresh_token"], "example-refresh-2")
        self.assertIsNone(remote(backend)[0]["lease"])


if __name__ == "__main__":
    unittest.main()
