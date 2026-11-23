"""Follow-up plan K.2 (Sol round 9, medium) and N2 (Sol round 10, medium): the rollback walks every
static object of the store, so a static entry or field created after the migration is restored too,
and every entry it restored or could not restore is named; one that cannot be restored makes the
exit code non-zero and keeps the migration marker. A static field under the name of a migrated
sign-in is restored, not skipped. The recorded kinds themselves are tested in
test_secret_store_rollback_kinds.py. Temporary folders, an in-process agent and fictional values
only."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate_to_store  # noqa: E402
import portable_vault  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store import oauth_ops  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, KEY, PASS, RT1, SECRET, StoreFixture,  # noqa: E402,F401
                                      agent_request, setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

NEW_KEY, NEW_EXTRA = "fictional-new-key", "fictional-extra-value"
LOOKS_LIKE_JSON = '{"note": "kept as text"}'


class MigratedStore(StoreFixture):
    """A migrated old vault and later store writes; no tests of its own."""

    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: (self.token(), "json"), "client_id": ("fictional-id", "text"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set_fields("plain", {"api_key": (KEY, "text"), "shaped": (LOOKS_LIKE_JSON, "text"),
                                        "options": ({"mode": "old"}, "json")}, PASS)
        self.agent = VaultAgent(self.vault.path)
        self.agent.unlock(PASS)
        self.request = agent_request(self.agent)
        self.marker = portable_vault.migration_marker_path(self.vault.path)
        lines = []
        self.assertEqual(migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append), 0, lines)
        # created in the store after the migration: a new entry of each kind and new fields of each kind
        self.ba.set_text("new-text", "api_key", NEW_KEY)
        self.ba.set_json("new-json", "settings", {"region": "au", "count": 2})
        self.ba.set_text("plain", "extra", NEW_EXTRA)
        self.ba.set_json("plain", "config", {"flag": True})
        self.ba.set_json("plain", "options", {"mode": "new"})

    def run_it(self, request=None, **options):
        lines = []
        code = migrate_to_store.rollback(request or self.request, lambda: self.a, out=lines.append, **options)
        text = "\n".join(lines)
        for value in (SECRET, KEY, RT1, AT1, NEW_KEY, NEW_EXTRA, "fictional-id"):
            self.assertNotIn(value, text)
        return code, text

    def drop_the_signin(self):
        self.a.delete_entry(oauth_ops.signin_names("xero-demo", FIELD)[0])  # its grant goes with it
        self.assertNotIn(oauth_ops.signin_names("xero-demo", FIELD)[1], self.a.list_entries())


class RollbackWalksTheStore(MigratedStore):
    def test_entries_and_fields_created_after_the_migration_are_restored_with_their_kind(self):
        code, text = self.run_it()
        self.assertEqual(code, 0, text)
        self.assertEqual(self.vault.get("new-text", "api_key", PASS), NEW_KEY)
        self.assertEqual(self.vault.get("new-json", "settings", PASS), {"region": "au", "count": 2})
        self.assertEqual(self.vault.get("plain", "extra", PASS), NEW_EXTRA)
        self.assertEqual(self.vault.get("plain", "config", PASS), {"flag": True})
        self.assertEqual(self.vault.get("plain", "options", PASS), {"mode": "new"})
        self.assertEqual(self.vault.get("plain", "shaped", PASS), LOOKS_LIKE_JSON)
        self.assertEqual(self.vault.get("plain", "api_key", PASS), KEY)
        for name in ("new-text (api_key)", "new-json (settings)", "plain (api_key, config, extra, options, shaped)"):
            self.assertIn(name, text)
        self.assertNotIn("refresh_token", self.vault.get("xero-demo", FIELD, PASS))
        self.assertFalse(self.marker.exists())

    def test_the_dry_run_names_the_new_entries_and_changes_nothing(self):
        code, text = self.run_it(dry_run=True)
        self.assertEqual(code, 0, text)
        self.assertIn("new-text (api_key)", text)
        self.assertIn("new-json (settings)", text)
        self.assertNotIn("new-text", self.vault.load(PASS)["entries"])
        self.assertTrue(self.marker.exists())

    def test_an_entry_the_agent_refuses_is_named_and_the_exit_code_is_not_zero(self):
        def refusing(operation, **request):
            if operation == "vault_restore_static" and request.get("entry") == "new-json":
                raise CredentialError("fictional refusal")
            return self.request(operation, **request)
        code, text = self.run_it(refusing)
        self.assertNotEqual(code, 0, text)
        self.assertIn("could not be restored", text)
        self.assertIn("new-json", text.split("could not be restored", 1)[1])
        self.assertEqual(self.vault.get("new-text", "api_key", PASS), NEW_KEY)  # the others are restored
        self.assertNotIn("new-json", self.vault.load(PASS)["entries"])
        self.assertTrue(self.marker.exists())  # incomplete: the marker stays, run it again

    def test_a_static_value_holding_a_token_is_never_restored_and_is_named(self):
        self.a.put_entry("odd", {"held": json.dumps({"refresh_token": "fictional-odd-refresh"}, sort_keys=True)})
        code, text = self.run_it()
        self.assertNotEqual(code, 0, text)
        self.assertNotIn("fictional-odd-refresh", text)
        self.assertIn("odd (held)", text.split("could not be restored", 1)[1])
        self.assertNotIn("odd", self.vault.load(PASS)["entries"])
        self.assertEqual(self.vault.get("new-text", "api_key", PASS), NEW_KEY)

    def test_a_static_field_under_the_name_of_a_migrated_signin_is_restored(self):
        self.drop_the_signin()
        self.ba.set_json("xero-demo", FIELD, {"note": "plain settings"})
        code, text = self.run_it()
        self.assertEqual(code, 0, text)
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS), {"note": "plain settings"})
        self.assertIn(f"xero-demo ({FIELD})", text)
        self.assertFalse(self.marker.exists())

    def test_a_failed_restore_under_a_migrated_signin_name_keeps_the_marker(self):
        self.drop_the_signin()
        self.ba.set_json("xero-demo", FIELD, {"note": "plain settings"})
        before = portable_vault.migrated_signins(self.vault.path)

        def refusing(operation, **request):  # a late field comes back through vault_restore_marked_static
            if operation in ("vault_restore_static", "vault_restore_marked_static") \
                    and request.get("entry") == "xero-demo":
                raise CredentialError("fictional refusal")
            return self.request(operation, **request)
        code, text = self.run_it(refusing)
        self.assertEqual(code, 5, text)
        self.assertIn(f"xero-demo ({FIELD})", text.split("could not be restored", 1)[1])
        self.assertEqual(portable_vault.migrated_signins(self.vault.path), before)
        self.assertNotIn("refresh_token", self.vault.get("xero-demo", FIELD, PASS))
        self.assertEqual(self.vault.get("new-text", "api_key", PASS), NEW_KEY)

    def test_a_static_field_shadowed_by_a_signin_the_store_still_holds_is_named(self):
        self.a.put_entry("xero-demo", {FIELD: json.dumps({"note": "shadow"}, sort_keys=True)},
                         field_kinds={FIELD: "json"})
        code, text = self.run_it()
        self.assertEqual(code, 5, text)
        self.assertIn(f"xero-demo ({FIELD})", text.split("could not be restored", 1)[1])
        self.assertTrue(self.marker.exists())
        self.assertNotIn("note", self.vault.get("xero-demo", FIELD, PASS))


if __name__ == "__main__":
    unittest.main()
