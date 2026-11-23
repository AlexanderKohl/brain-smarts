"""The migration and its rollback with the store switched on (found by the rehearsal, 2026-11-22):
a vault-backed Vault Agent, unlocked, serves migrate_to_store.py while it holds the migration
lock. Every step (lock, backup, verify the backup copy, copy, read-back, scrub, marker) runs
through the agent; the backup copy is opened with the same migration permission as the vault the
operation was given, so it is read under a live lock and refused without one. Every token is
fictional; every agent is in-process; nothing touches the live vault or the network."""
import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import migrate_to_store  # noqa: E402
import migration_lock  # noqa: E402
import portable_vault  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402
from test_secret_store_broker import FIELD, KEY, PASS, RT1, SECRET, StoreFixture, agent_request  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402


class MigrationWithTheStoreOn(StoreFixture):
    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: ({"refresh_token": RT1, "tenant_id": "t-1"}, "json"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set("plain", "api_key", KEY, "text", PASS)
        self.lock = migration_lock.lock_path(self.vault.path)
        patcher = mock.patch.object(portable_vault, "secret_store_enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # the agent serve builds with the store on: store-backed, and unlocked in store mode for the
        # vault operations (an agent without a store cannot be unlocked while the store is on)
        self.agent = VaultAgent(self.vault.path, store=self.ba)
        self.agent.unlock(PASS)
        self.request = agent_request(self.agent)

    def test_migrate_then_rollback_through_a_vault_backed_agent(self):
        lines = []
        code = migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append)
        self.assertEqual(code, 0, lines)
        self.assertEqual(portable_vault.migrated_signins(self.vault.path), {"xero-demo": [FIELD]})
        self.assertFalse(self.lock.exists())
        lines = []
        code = migrate_to_store.rollback(self.request, lambda: self.a, out=lines.append)
        self.assertEqual(code, 0, lines)
        self.assertFalse(portable_vault.migration_marker_path(self.vault.path).exists())
        self.assertFalse(self.lock.exists())

    def test_verify_copy_without_a_live_lock_is_refused(self):
        copy = self.vault.path.with_name("credentials.copy.vault")
        copy.write_bytes(self.vault.path.read_bytes())
        with self.assertRaises((CredentialError, SecretStoreError)):
            self.request("vault_verify_copy", path=str(copy))
        with migration_lock.MigrationLock(self.vault.path, "migrate"):
            self.assertIn("plain", self.request("vault_verify_copy", path=str(copy)))

    def test_the_migration_and_the_rollback_print_one_line_per_entry_with_names_only(self):
        """Plan R23, rule 4 and test (d): a start line, then one line per entry as it is done (its name
        and field names), on the same stream as the summary; no value of the test's secrets."""
        lines = []
        self.assertEqual(migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append), 0, lines)
        start = lines.index("Copying 2 entries; each is committed and pushed, which takes a few seconds an entry.")
        progress = [line for line in lines if line.startswith("  ")]
        self.assertEqual(progress, ["  1/2 plain: api_key", f"  2/2 xero-demo: client_secret, {FIELD}"])
        self.assertLess(start, lines.index(progress[0]))
        self.assertTrue(lines[-1].startswith("Copied 2 entries into the store."))
        back = []
        self.assertEqual(migrate_to_store.rollback(self.request, lambda: self.a, out=back.append), 0, back)
        self.assertIn("  restored plain: api_key", back)
        self.assertIn("Restoring", " ".join(back))
        for secret in (RT1, SECRET, KEY, PASS):
            self.assertNotIn(secret, " | ".join(lines + back))

    def test_the_default_output_is_flushed_at_once(self):
        for command in (migrate_to_store.migrate, migrate_to_store.rollback):
            self.assertIs(inspect.signature(command).parameters["out"].default, migrate_to_store._say)
        with mock.patch("builtins.print") as printed:
            migrate_to_store._say("a line")
        printed.assert_called_once_with("a line", flush=True)


if __name__ == "__main__":
    unittest.main()
