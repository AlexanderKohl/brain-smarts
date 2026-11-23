"""Token relay: the scenarios of the third review's findings 1, 2, 3 and 5 on the relayed store
(test_review3_finding_N_...). Finding 2 through the vault and seed --replace is in
test_token_relay_vault.py; finding 4 is in the Xero client's tests.

A second store instance stands for a second short-lived process on the same computer. Every test
runs on the in-memory backend: no network, no gh call, no Vault Agent and no real vault. Every
name, token and key is invented.
"""

from __future__ import annotations

import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import token_relay_backend as trb  # noqa: E402
import token_relay_store  # noqa: E402
from test_token_relay import (  # noqa: E402
    ENTRY,
    KEY,
    LEASE_B,
    NAME,
    START,
    Clock,
    LocalStore,
    at,
    relay,
    remote,
    seed,
    token,
)


class ConflictingSaves(trb.MemoryBackend):
    """Refuses the next few "save" writes as if another brain had just written."""

    def __init__(self) -> None:
        super().__init__()
        self.conflicts = 0

    def put(self, name, content, expected_tag, message):
        if self.conflicts and f"{ENTRY} save " in message:
            self.conflicts -= 1
            raise trb.Conflict("The relay file changed since it was read.")
        return super().put(name, content, expected_tag, message)


class ThirdReviewTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.backend = trb.MemoryBackend()
        self.stderr = io.StringIO()
        seed(self.backend, token(1, START + 30))
        self.local = at(1, token(1, START + 30))

    # -- finding 1: the holder is the computer -------------------------------------------------

    def test_review3_finding_1_holder_name_is_stable_per_computer(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        vault = folder / "credentials.vault"
        first = token_relay_store.holder_name(vault)
        self.assertEqual(token_relay_store.holder_name(vault), first)
        kept = (folder / token_relay_store.HOLDER_ID_NAME).read_text(encoding="ascii").strip()
        self.assertRegex(kept, r"\A[0-9a-f]{8}\Z")
        self.assertTrue(first.endswith(f"-{kept}"))
        other = folder / "elsewhere"
        self.assertNotEqual(token_relay_store.holder_name(other / "credentials.vault"), first)

    def test_review3_finding_1_a_later_process_recovers_over_this_computers_own_lease(self):
        store = relay(self.backend, self.local, self.clock, holder="brain-a-7f3c9e01", stderr=self.stderr)
        with store.rotation_lock():
            self.backend.unreachable = True
            store.save(token(2, START + 1800))
        self.backend.unreachable = False
        record = remote(self.backend)[0]
        self.assertEqual(record["lease"]["holder"], "brain-a-7f3c9e01")
        self.assertEqual(self.local.value["_relay_lease_id"], record["lease"]["id"])
        later = relay(self.backend, self.local, self.clock, holder="brain-a-7f3c9e01", stderr=self.stderr)
        self.assertEqual(later.load(), token(2, START + 1800))
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value), (2, None, token(2, START + 1800)))
        self.assertNotIn("_relay_lease_id", self.local.value)

    def test_review3_finding_1_the_kept_lease_id_marks_the_lease_as_own_under_another_holder(self):
        store = relay(self.backend, self.local, self.clock, holder="brain-a-101", stderr=self.stderr)
        with store.rotation_lock():
            self.backend.unreachable = True
            store.save(token(2, START + 1800))
        self.backend.unreachable = False
        later = relay(self.backend, self.local, self.clock, holder="brain-a-102", stderr=self.stderr)
        with later.rotation_lock():
            pass
        record, value = remote(self.backend)
        self.assertEqual((record["version"], value), (2, token(2, START + 1800)))
        self.assertEqual(self.clock.now, START)  # no wait for its own lease

    def test_review3_finding_1_a_foreign_lease_countdown_continues_across_processes(self):
        brain_b = relay(self.backend, at(1, token(1, START + 30)), self.clock, holder="brain-b-202")
        b_lock = ExitStack()
        store = relay(self.backend, self.local, self.clock, stderr=self.stderr)
        with store.rotation_lock(refresh=True):
            self.clock.advance(200)
            b_lock.enter_context(brain_b.rotation_lock(refresh=True))
            store.save(token(2, START + 1800))  # the lease was taken over: R2 stays local
        self.assertEqual(self.local.value["_relay_unpushed"], "token")
        lease_id = remote(self.backend)[0]["lease"]["id"]
        first_sight = self.clock.now
        for step in (0, 100):  # later processes on this computer, each a new store instance
            self.clock.advance(step)
            relay(self.backend, self.local, self.clock, stderr=self.stderr).load()
            self.assertEqual(remote(self.backend)[0]["version"], 1)
            self.assertEqual(self.local.value["_relay_seen"], [lease_id, first_sight])
        self.clock.advance(21)  # 121 seconds after the first sight on this computer's clock
        relay(self.backend, self.local, self.clock, stderr=self.stderr).load()
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"], value), (2, None, token(2, START + 1800)))
        self.assertNotIn("_relay_seen", self.local.value)
        b_lock.close()

    # -- finding 2: a new authorisation gets past a record it cannot read ---------------------

    def test_review3_finding_2_a_new_authorisation_gets_past_an_unusable_record(self):
        cases = {
            "wrong key": lambda backend: backend.put(NAME, trb.dump_record(trb.build_record(
                bytes(32), ENTRY, 3, token(1, START), lease=None, holder="h-1", updated_at="t")), None, "old key"),
            "damaged": lambda backend: backend.put(NAME, b"not a relay record", None, "damaged"),
            "rollback": lambda backend: seed(backend, token(1, START + 30), version=2),
        }
        for label, make in cases.items():
            with self.subTest(label):
                backend = trb.MemoryBackend()
                make(backend)
                before = dict(backend.files)
                local = at(5, token(4, START + 30))
                with self.assertRaises(trb.RelayIntegrityError):
                    with relay(backend, local, self.clock).rotation_lock(refresh=True):
                        self.fail("not a new authorisation: refused")
                stderr = io.StringIO()
                store = relay(backend, local, self.clock, stderr=stderr)
                with store.rotation_lock(refresh=True, new_authorisation=True):
                    store.save(token(9, START + 1800))
                self.assertEqual(local.value, {**token(9, START + 1800), "_relay_version": 5})
                self.assertEqual(backend.files, before)
                self.assertIn("cannot use", stderr.getvalue())
                self.assertIn(f"seed --entry {ENTRY} --replace next", stderr.getvalue())
                with self.assertRaises(trb.RelayIntegrityError):
                    store.save({**token(9, START + 1800), "selected_tenant_id": "tenant-example"})

    def test_review3_finding_2_an_unseeded_entry_with_a_refresh_token_here_goes_ahead(self):
        backend = trb.MemoryBackend()
        local = at(1, token(1, START + 30))
        store = relay(backend, local, self.clock, stderr=self.stderr)
        with store.rotation_lock(refresh=True, new_authorisation=True):
            store.save(token(2, START + 1800))
        self.assertEqual((backend.files, local.value["refresh_token"]), ({}, "example-refresh-2"))
        self.assertIn("no shared record yet", self.stderr.getvalue())

    # -- finding 3: recovery replaces token keys only for a token ------------------------------

    def test_review3_finding_3_a_cleared_computer_saving_outside_a_lock_keeps_the_shared_token(self):
        store = relay(self.backend, self.local, self.clock, stderr=self.stderr)
        store.clear()
        store.save({"selected_tenant_id": "tenant-example"})
        record, value = remote(self.backend)
        self.assertEqual(record["version"], 2)
        self.assertEqual(value, {**token(1, START + 30), "selected_tenant_id": "tenant-example"})
        self.assertEqual(self.local.value, {**value, "_relay_version": 2})

    def test_review3_finding_3_a_data_only_change_never_pushes_this_computers_chain(self):
        self.local.value = {
            **token(7, START + 1800), "selected_tenant_id": "tenant-example", "_relay_version": 1,
            "_relay_unpushed": True, "_relay_base_version": 1, "_relay_changed": ["selected_tenant_id"],
        }
        relay(self.backend, self.local, self.clock, stderr=self.stderr).sync()
        _, value = remote(self.backend)
        self.assertEqual(value, {**token(1, START + 30), "selected_tenant_id": "tenant-example"})

    # -- finding 5: expired foreign leases and pending changes ---------------------------------

    def test_review3_finding_5_an_expired_foreign_lease_no_longer_blocks_a_data_save(self):
        seed(self.backend, token(1, START + 1800), version=2, lease=LEASE_B)
        local = at(2, token(1, START + 1800))
        relay(self.backend, local, self.clock).save({**token(1, START + 1800), "selected_tenant_id": "tenant-1"})
        self.assertEqual(remote(self.backend)[0]["version"], 2)
        self.assertEqual(local.value["_relay_seen"], [LEASE_B["id"], START])
        self.clock.advance(121)
        later = relay(self.backend, local, self.clock)  # a later process continues the countdown
        later.save({**token(1, START + 1800), "selected_tenant_id": "tenant-1", "location_note": "example"})
        record, value = remote(self.backend)
        self.assertEqual((record["version"], record["lease"]), (3, None))
        self.assertEqual((value["selected_tenant_id"], value["location_note"]), ("tenant-1", "example"))
        self.assertNotIn("_relay_seen", local.value)

    def test_review3_finding_5_a_leased_save_folds_pending_data_changes(self):
        backend = ConflictingSaves()
        seed(backend, token(1, START + 30))
        backend.conflicts = 3  # the pending change cannot be pushed before the lease is taken
        local = LocalStore({
            **token(1, START + 30), "selected_tenant_id": "tenant-example", "_relay_version": 1,
            "_relay_unpushed": True, "_relay_base_version": 1, "_relay_changed": ["selected_tenant_id"],
        })
        store = relay(backend, local, self.clock, stderr=self.stderr)
        with store.rotation_lock():
            self.assertEqual(backend.conflicts, 0)
            store.save(token(2, START + 1800))  # a token answer that leaves the pending key out
        record, value = remote(backend)
        self.assertEqual((record["version"], record["lease"]), (2, None))
        self.assertEqual(value, {**token(2, START + 1800), "selected_tenant_id": "tenant-example"})
        self.assertEqual(local.value, {**value, "_relay_version": 2})


if __name__ == "__main__":
    unittest.main()
