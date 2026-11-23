"""Round-8 review fixes: with the store on the token relay command line is retired (status only);
migration scrubs the old vault's sign-in tokens once the store holds them, leaves a migration
marker every legacy OAuth path and the relay obey, and rolls back static secrets only, every
sign-in needing a browser sign-in; agent status and the daily check cover the team recovery package too. Every token
is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import json
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
import token_relay  # noqa: E402
from portable_vault import CredentialError, PortableVault, PortableVaultJsonStore  # noqa: E402
from secret_store import broker_backend, store_ops  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, KEY, PASS, RT1, SECRET, StoreFixture,  # noqa: E402,F401
                                      agent_request, setUpModule, tearDownModule)
from test_secret_store_team import TeamCase  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402

MOVED = "moved to the secrets store"
RT2, AT2 = "fictional-refresh-2", "fictional-access-2"


class Patched(unittest.TestCase):
    def use(self, *patchers):
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)


class RelayRetired(Patched):
    def setUp(self):
        forbidden = mock.Mock(side_effect=AssertionError("relay used in store mode"))
        self.use(*(mock.patch.object(token_relay, name, forbidden) for name in
                   ("_seed", "_store_key", "read_relay_key", "_check_vault", "_status", "_key_exists",
                    "_hidden_input", "make_backend")),
                 mock.patch.object(token_relay, "_agent_unlocked", return_value=False))

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = token_relay.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_every_key_and_seed_command_is_refused_in_store_mode(self):
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=True))
        for argv in (["seed", "--entry", "xero-demo"], ["seed", "--entry", "xero-demo", "--replace"],
                     ["key-new"], ["key-new", "--replace"], ["key-import"], ["key-import", "--replace"],
                     ["key-export"], ["--vault", "v.vault", "seed", "--entry", "xero-demo"]):
            code, out, err = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("retired while the secrets store is on", err, argv)
            self.assertEqual(out, "", argv)

    def test_status_reports_retired(self):
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=True))
        code, out, _err = self.run_main(["status"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["relay"], "retired")

    def test_store_off_unchanged(self):
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=False),
                 mock.patch.object(token_relay, "_seed", return_value=0))
        self.assertEqual(self.run_main(["seed", "--entry", "xero-demo"])[0], 0)
        token_relay._seed.assert_called_once()


class MigrationRetiresTheOldGrant(StoreFixture):
    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: (self.token(), "json"), "client_id": ("fictional-id", "text"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set("plain", "api_key", KEY, "text", PASS)
        self.agent = VaultAgent(self.vault.path)
        self.agent.unlock(PASS)
        self.request = agent_request(self.agent)
        self.marker = portable_vault.migration_marker_path(self.vault.path)

    def run_it(self, function, store=None, **options):
        lines = []
        code = function(self.request, lambda: store or self.a, out=lines.append, **options)
        text = "\n".join(lines)
        for value in (SECRET, KEY, RT1, AT1, RT2, AT2, "fictional-id"):
            self.assertNotIn(value, text)
        return code, text

    def held(self):
        return self.vault.get("xero-demo", FIELD, PASS)

    def test_migration_scrubs_tokens_and_writes_the_marker(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        held = self.held()
        self.assertFalse({"refresh_token", "access_token"} & set(held))
        self.assertEqual(held["tenant_id"], "tenant-1")
        self.assertEqual(json.loads(self.marker.read_text("utf-8"))["entries"], {"xero-demo": [FIELD]})
        self.assertEqual(self.vault.get("plain", "api_key", PASS), KEY)
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], RT1)

    def test_store_off_restart_with_the_marker_refuses_the_migrated_entry(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        restarted = VaultAgent(self.vault.path)
        restarted.unlock(PASS)
        request = agent_request(restarted)
        for op in ("get_json", "get_access_token"):
            with self.assertRaisesRegex(CredentialError, MOVED):
                request(op, entry="xero-demo", field=FIELD)
        with self.assertRaisesRegex(CredentialError, MOVED):
            request("set_json", entry="xero-demo", field=FIELD, value={"refresh_token": "fictional-x"})
        self.assertEqual(request("get_fields", entry="plain", fields=["api_key"]), {"api_key": KEY})
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=False), \
                mock.patch.object(portable_vault, "BrokerOAuthStore", side_effect=CredentialError("locked")):
            with self.assertRaisesRegex(CredentialError, MOVED):
                PortableVaultJsonStore("xero-demo", path=self.vault.path, passphrase=PASS)
        broker = mock.Mock(path="broker://x", rotation_lock_path=self.root / "l.lock")
        with mock.patch.object(portable_vault, "BrokerOAuthStore", return_value=broker), \
                mock.patch.object(token_relay, "relay_for", return_value=None):
            broker.store_mode.return_value = False
            with self.assertRaisesRegex(CredentialError, MOVED):
                PortableVaultJsonStore("xero-demo", path=self.vault.path)
            broker.store_mode.return_value = True
            self.assertIs(PortableVaultJsonStore("xero-demo", path=self.vault.path)._broker, broker)

    def test_a_second_migration_leaves_migrated_entries_alone(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        code, text = self.run_it(migrate_to_store.migrate, replace=True)
        self.assertEqual(code, 0)
        self.assertIn("Already migrated", text)
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], RT1)

    def test_rollback_restores_static_secrets_and_no_sign_in_token(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        begun = self.ba.begin_refresh("xero-demo", FIELD)  # the store rotates after migration
        self.ba.set_json("xero-demo", FIELD, self.token(refresh_token=RT2, access_token=AT2),
                         operation=begun["operation"])
        self.a.put_entry("plain", {"api_key": "fictional-api-key-2"})
        code, text = self.run_it(migrate_to_store.rollback, dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("Dry run", text)
        self.assertIn(f"xero-demo#{FIELD}: sign in again in the browser", text)
        self.assertEqual(self.vault.get("plain", "api_key", PASS), KEY)
        self.assertTrue(self.marker.exists())
        code, text = self.run_it(migrate_to_store.rollback)
        self.assertEqual(code, 0)
        self.assertIn(f"xero-demo#{FIELD}: sign in again in the browser", text)
        self.assertEqual(self.vault.get("plain", "api_key", PASS), "fictional-api-key-2")
        held = self.held()
        self.assertFalse({"refresh_token", "access_token"} & set(held))
        self.assertFalse({RT1, RT2, AT1, AT2} & set(map(str, held.values())))
        self.assertFalse(self.marker.exists())

    def test_the_agent_refuses_to_restore_a_sign_in(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        for values in ({FIELD: {"value": self.token(), "kind": "json"}},
                       {"other": {"value": {"refresh_token": RT2}, "kind": "json"}}):
            with self.assertRaisesRegex(CredentialError, "not a static secret"),                     migration_lock.MigrationLock(self.vault.path, "rollback"):  # round 9: only under the lock
                self.request("vault_restore_static", entry="xero-demo", values=values)
        self.assertNotIn("refresh_token", self.held())

    def test_the_relay_never_seeds_a_migrated_entry_store_on_or_off(self):
        self.assertEqual(self.run_it(migrate_to_store.migrate)[0], 0)
        forbidden = mock.Mock(side_effect=AssertionError("relay used for a migrated entry"))
        err = io.StringIO()
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=False), \
                mock.patch.object(token_relay, "_seed", forbidden), \
                mock.patch.object(token_relay, "_store_key", forbidden), \
                mock.patch.object(token_relay, "_check_vault", forbidden), contextlib.redirect_stderr(err):
            for argv in (["seed", "--entry", "xero-demo"], ["key-new"], ["key-import"], ["key-export"]):
                self.assertEqual(token_relay.main(["--vault", str(self.vault.path), *argv]), 2, argv)
        self.assertIn("migration marker names xero-demo", err.getvalue())

    def test_rollback_command_line_has_a_dry_run(self):
        with mock.patch.object(migrate_to_store, "rollback", return_value=0) as rollback, \
                mock.patch("vault_broker_client.broker_request"), mock.patch("secret_store.store.SecretStore"):
            self.assertEqual(migrate_to_store.main(["rollback", "--dry-run"]), 0)
        self.assertTrue(rollback.call_args.kwargs["dry_run"])


class TeamPackageHealth(TeamCase):
    def test_unwritable_team_package_folder_is_reported(self):
        admin, _pinned = self.team_setup()
        blocked = self.root / "blocked"
        blocked.write_text("not a folder", "utf-8")
        admin.config["recovery_package_dir"] = blocked
        admin.config["personal_clone"] = self.root / "no-personal-clone"
        admin._refresh_stale_package()
        self.assertTrue(admin.package_error)
        backend = broker_backend.StoreBackend(self.personal("pa", "laptop"), team=admin)
        packages = backend.status()["recovery_packages"]
        self.assertIn("failed", packages["team"])
        self.assertIn("personal", packages)
        health = store_ops.package_health(admin.config)
        self.assertIn("team store", health)
        self.assertIn("upkeep failed", health)


if __name__ == "__main__":
    unittest.main()
