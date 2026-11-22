"""Follow-up plan R11, rule 5 as amended twice (Sol round 11, second medium): the rollback never
clears the migration marker for a late restore and never scrubs. A static field under a migrated
sign-in's name (a late field) comes back through the agent's vault_restore_marked_static, which
restores only fields the marker names and leaves the marker as it is; the marker is cleared last,
only when every restore of both kinds succeeded. The operation validates its whole request before
its first write. Temporary folders, bare local repositories, an in-process agent, the fake keyring
and fictional values only."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate_to_store  # noqa: E402
import migration_lock  # noqa: E402
import portable_vault  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store import oauth_ops  # noqa: E402
from test_secret_store_broker import (FIELD, KEY, PASS, SECRET, StoreFixture, agent_request,  # noqa: E402,F401
                                      setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

LATE_SECRET = "fictional-late-client-secret"
FIRST = {"client_secret": LATE_SECRET, "region": "au"}  # a JSON static field, nothing that looks like a sign-in
SECOND = {"note": "fictional second settings"}
RESTORES = ("vault_restore_static", "vault_restore_marked_static")


class LateFields(StoreFixture):
    """Two migrated sign-ins whose names the store later holds as static JSON fields (late fields),
    and one ordinary static entry."""

    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: (self.token(), "json"), "client_secret": (SECRET, "text")}, PASS)
        self.vault.set_fields("xero-other", {FIELD: (self.token(), "json")}, PASS)
        self.vault.set_fields("plain", {"api_key": (KEY, "text")}, PASS)
        self.agent = VaultAgent(self.vault.path)
        self.agent.unlock(PASS)
        self.request = agent_request(self.agent)
        self.marker = portable_vault.migration_marker_path(self.vault.path)
        lines = []
        self.assertEqual(migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append), 0, lines)
        self.assertEqual(portable_vault.migrated_signins(self.vault.path), {"xero-demo": [FIELD], "xero-other": [FIELD]})
        for entry, value in (("xero-demo", FIRST), ("xero-other", SECOND)):
            self.a.delete_entry(oauth_ops.signin_names(entry, FIELD)[0])
            self.ba.set_json(entry, FIELD, value)
        self.ba.set_text("plain", "api_key", "fictional-api-key-later")
        self.ops = []

    def spy(self, fault=None):
        """The agent's request, recording each operation; fault(operation, request) may raise."""
        def request(operation, **payload):
            self.ops.append(operation)
            if fault:
                fault(operation, payload)
            return self.request(operation, **payload)
        return request

    def run_it(self, request):
        lines = []
        code = migrate_to_store.rollback(request, lambda: self.a, out=lines.append)
        text = "\n".join(lines)
        for value in (LATE_SECRET, SECRET, KEY):
            self.assertNotIn(value, text)
        return code, text

    def store_value(self, entry):
        return json.loads(self.a.get_typed(entry)[0][FIELD])

    def assert_fenced(self):
        for entry in ("xero-demo", "xero-other"):
            with self.assertRaisesRegex(CredentialError, "moved to the secrets store"):
                self.request("get_json", entry=entry, field=FIELD)


class ALateRestoreThatFails(LateFields):
    def test_the_marker_stays_byte_for_byte_and_no_restored_value_is_touched(self):
        before = self.marker.read_bytes()

        def second_fails(operation, request):
            if operation in RESTORES and request.get("entry") == "xero-other":
                raise CredentialError("fictional refusal")
        code, text = self.run_it(self.spy(second_fails))
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS), self.store_value("xero-demo"))
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS)["client_secret"], LATE_SECRET)
        self.assertEqual(self.marker.read_bytes(), before)
        self.assert_fenced()
        self.assertEqual(code, 5, text)
        self.assertIn(f"xero-other ({FIELD})", text.split("could not be restored", 1)[1])
        self.assertNotIn("vault_scrub_signin", self.ops)
        self.assertNotIn("vault_clear_migration_marker", self.ops)

        self.ops.clear()  # run again with the fault gone: it completes and only then clears the marker
        code, text = self.run_it(self.spy())
        self.assertEqual(code, 0, text)
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS), FIRST)
        self.assertEqual(self.vault.get("xero-other", FIELD, PASS), SECOND)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.ops.count("vault_clear_migration_marker"), 1)
        self.assertEqual(self.ops[-1], "vault_clear_migration_marker")
        self.assertNotIn("vault_scrub_signin", self.ops)

    def test_a_process_stopped_after_the_first_late_restore_leaves_the_marker_unchanged(self):
        before = self.marker.read_bytes()

        def stopped(operation, request):
            if operation in RESTORES and request.get("entry") == "xero-other":
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_it(self.spy(stopped))
        self.assertEqual(self.marker.read_bytes(), before)
        self.assert_fenced()

    def test_the_order_is_ordinary_fields_then_late_fields_then_the_clear(self):
        code, text = self.run_it(self.spy())
        self.assertEqual(code, 0, text)
        steps = [op for op in self.ops if op in RESTORES + ("vault_clear_migration_marker",)]
        self.assertEqual(steps, ["vault_restore_static", "vault_restore_marked_static", "vault_restore_marked_static",
                                 "vault_clear_migration_marker"])
        self.assertEqual(self.vault.get("plain", "api_key", PASS), "fictional-api-key-later")
        self.assertFalse(self.marker.exists())

    def test_a_failed_ordinary_restore_keeps_the_marker_and_still_restores_the_late_fields(self):
        before = self.marker.read_bytes()

        def plain_fails(operation, request):
            if operation == "vault_restore_static" and request.get("entry") == "plain":
                raise CredentialError("fictional refusal")
        code, text = self.run_it(self.spy(plain_fails))
        self.assertEqual(code, 5, text)
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(self.vault.get("xero-other", FIELD, PASS), SECOND)
        self.assertNotIn("vault_clear_migration_marker", self.ops)
        self.assert_fenced()


class TheMarkedRestoreOperation(LateFields):
    def marked_restore(self, entry, values):
        with migration_lock.MigrationLock(self.vault.path, "rollback"):
            return self.request("vault_restore_marked_static", entry=entry, values=values)

    def assert_refused(self, entry, values, operation="vault_restore_marked_static"):
        vault, marker = self.vault.path.read_bytes(), self.marker.read_bytes()
        with self.assertRaisesRegex(CredentialError, "nothing was restored"), \
                migration_lock.MigrationLock(self.vault.path, "rollback"):
            self.request(operation, entry=entry, values=values)
        self.assertEqual(self.vault.path.read_bytes(), vault)
        self.assertEqual(self.marker.read_bytes(), marker)

    def test_a_marked_field_is_restored_and_the_marker_is_left_as_it_is(self):
        marker = self.marker.read_bytes()
        self.assertEqual(self.marked_restore("xero-demo", {FIELD: {"value": FIRST, "kind": "json"}}),
                         {"restored": [FIELD]})
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS), FIRST)
        self.assertEqual(self.marker.read_bytes(), marker)
        self.assert_fenced()

    def test_a_field_the_marker_does_not_name_is_refused(self):
        self.assert_refused("xero-demo", {"note": {"value": "fictional", "kind": "text"}})
        self.assert_refused("plain", {"api_key": {"value": "fictional", "kind": "text"}})

    def test_a_json_value_that_looks_like_a_signin_is_refused(self):
        self.assert_refused("xero-demo", {FIELD: {"value": {"refresh_token": "fictional-refresh"}, "kind": "json"}})
        self.assert_refused("xero-demo", {FIELD: {"value": {"access_token": "fictional-access"}, "kind": "text"}})

    def test_a_malformed_request_is_refused(self):
        for values in (None, [], {}, "text", {FIELD: "bare value"}, {FIELD: None}, {FIELD: {"value": FIRST}},
                       {FIELD: {"value": FIRST, "kind": "yaml"}}, {FIELD: {"value": 7, "kind": "text"}},
                       {FIELD: {"value": "", "kind": "text"}}, {FIELD: {"value": "not an object", "kind": "json"}}):
            with self.subTest(values=values):
                self.assert_refused("xero-demo", values)

    def test_one_valid_and_one_invalid_field_write_nothing(self):
        self.assert_refused("xero-demo", {FIELD: {"value": FIRST, "kind": "json"},
                                          "note": {"value": "fictional", "kind": "text"}})
        self.assertNotIn("client_secret", self.vault.get("xero-demo", FIELD, PASS))

    def test_the_ordinary_restore_still_refuses_a_marked_name(self):
        self.assert_refused("xero-demo", {FIELD: {"value": FIRST, "kind": "json"}}, "vault_restore_static")

    def test_it_runs_only_under_the_migration_lock(self):
        vault = self.vault.path.read_bytes()
        with self.assertRaisesRegex(CredentialError, "migration lock"):
            self.request("vault_restore_marked_static", entry="xero-demo", values={FIELD: {"value": FIRST,
                                                                                          "kind": "json"}})
        self.assertEqual(self.vault.path.read_bytes(), vault)


if __name__ == "__main__":
    unittest.main()
