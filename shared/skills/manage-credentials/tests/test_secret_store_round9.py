"""Round-9 plan, rows M2, M3, M4, M5, M8 and M10: while the secrets store is on the old vault is
closed. The agent and the tray are built by one function; a vault-backed agent refuses with the
restart message once the store is on; the passphrase open refuses unless the migration path asks;
an unverified sign-in leaves no store copy; the agent's scrub, restore and marker operations need
the migration lock; the skeleton ignores the migration files; every command line refuses. Every
token is fictional; every agent is in-process; nothing touches the live vault or the network."""
import contextlib
import fnmatch
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import migrate_to_store  # noqa: E402
import migration_lock  # noqa: E402
import portable_vault  # noqa: E402
import vault_agent  # noqa: E402
import vault_credentials  # noqa: E402
import vaultctl  # noqa: E402
from portable_vault import STALE_AGENT_MESSAGE, STORE_ON_MESSAGE, CredentialError, PortableVault  # noqa: E402
from secret_store import broker_backend  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402
from test_secret_store_broker import FIELD, KEY, PASS, RT1, SECRET, StoreFixture, agent_request  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402

RESTART = "restart it"
LOCK_REFUSED = "migration lock"
SKELETON = Path(__file__).resolve().parents[3] / "templates" / "memory-skeleton" / ".gitignore"


class Patched(unittest.TestCase):
    def use(self, *patchers):
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def store_on(self, on=True):
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=on))


class VaultCase(Patched):
    """A temporary vault with one sign-in and one static secret, and a vault-backed agent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.vault = PortableVault(self.root / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: ({"refresh_token": RT1, "tenant_id": "t-1"}, "json"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set("plain", "api_key", KEY, "text", PASS)
        self.agent = VaultAgent(self.vault.path)
        self.agent.unlock(PASS)
        self.request = agent_request(self.agent)

    def bytes(self):
        return self.vault.path.read_bytes()


class OneBuilder(Patched):
    """M2: vault_agent.py serve and the tray build their agent through build_agent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(Path(self._tmp.name) / "credentials.vault")
        self.store = mock.Mock()
        self.store.status.return_value = {"backend": "store"}

    def test_store_on_builds_a_store_backed_agent(self):
        self.use(mock.patch.object(broker_backend, "backend_if_enabled", return_value=self.store))
        agent = vault_agent.build_agent(self.path)
        self.assertIs(agent._store, self.store)
        self.assertEqual(agent.status()["backend"], "store")

    def test_store_off_builds_the_vault_agent(self):
        self.use(mock.patch.object(broker_backend, "backend_if_enabled", return_value=None))
        self.assertIsNone(vault_agent.build_agent(self.path)._store)

    def test_a_malformed_configuration_stops_serve(self):
        self.use(mock.patch.object(broker_backend, "backend_if_enabled", side_effect=SecretStoreError("bad")),
                 mock.patch.object(VaultAgent, "serve_forever", side_effect=AssertionError("served")),
                 mock.patch.object(sys, "argv", ["vault_agent.py", "--vault", self.path, "serve"]))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(vault_agent.main(), 2)
        self.assertIn("not usable", err.getvalue())

    def tray(self):
        import vault_tray

        self.use(mock.patch.object(vault_tray, "_require_tray_deps",
                                   return_value=(mock.MagicMock(), mock.MagicMock(), mock.MagicMock())),
                 mock.patch.object(vault_tray, "log_tray"), mock.patch.object(vault_tray, "prepare_runtime_dir"))
        return vault_tray

    def test_a_malformed_configuration_stops_the_tray(self):
        vault_tray = self.tray()
        shown = mock.Mock()
        self.use(mock.patch.object(broker_backend, "backend_if_enabled", side_effect=SecretStoreError("bad")),
                 mock.patch.object(vault_tray, "_show_error", shown),
                 mock.patch.object(VaultAgent, "serve_forever", side_effect=AssertionError("served")),
                 mock.patch.object(sys, "argv", ["vault_tray.py", "--vault", self.path]))
        self.assertEqual(vault_tray.main(), 2)
        self.assertIn("not usable", shown.call_args[0][0])

    def test_the_tray_serves_the_store_and_asks_for_no_unlock(self):
        vault_tray = self.tray()
        ask = mock.Mock(side_effect=AssertionError("unlock window shown"))
        self.use(mock.patch.object(broker_backend, "backend_if_enabled", return_value=self.store),
                 mock.patch.object(vault_tray, "_ask_unlock_now", ask),
                 mock.patch.object(vault_tray, "_prompt_passphrase", ask))
        app = vault_tray.VaultTrayApp(self.path)
        self.assertIs(app.agent._store, self.store)
        with mock.patch.object(app, "_start_broker"):
            self.assertEqual(app.run(prompt_on_start=True), 0)
        app._do_unlock()  # the menu's unlock in store mode: no window either
        ask.assert_not_called()


class VaultAgentWithTheStoreOn(VaultCase):
    """M2: a vault-backed agent refuses every credential request once the store is switched on."""

    def test_every_credential_request_gets_the_restart_message(self):
        self.store_on()
        calls = [("get_fields", {"entry": "plain", "fields": ["api_key"]}),
                 ("get_json", {"entry": "xero-demo", "field": FIELD}),
                 ("get_access_token", {"entry": "xero-demo", "field": FIELD}),
                 ("set_text", {"entry": "plain", "field": "api_key", "value": "fictional-new"}),
                 ("set_json", {"entry": "xero-demo", "field": FIELD, "value": {"refresh_token": "x"}}),
                 ("unlock", {"passphrase": PASS}), ("vault_list_entries", {}),
                 ("vault_get_fields", {"entry": "plain", "fields": ["api_key"]})]
        before = self.bytes()
        for op, payload in calls:
            with self.assertRaisesRegex(CredentialError, RESTART, msg=op):
                self.request(op, **payload)
        self.assertEqual(self.bytes(), before)
        self.assertEqual(self.request("status")["running"], True)

    def test_the_same_agent_serves_again_when_the_store_is_off(self):
        self.store_on(False)
        self.assertEqual(self.request("get_fields", entry="plain", fields=["api_key"]), {"api_key": KEY})


class PassphraseOpenClosed(VaultCase):
    """M3: the one passphrase open refuses while the store is on, unless the migration path asks."""

    def test_every_vault_operation_is_refused(self):
        self.store_on()
        before = self.bytes()
        for name, call in (("load", lambda v: v.load(PASS)), ("entry_names", lambda v: v.entry_names(PASS)),
                           ("get", lambda v: v.get("plain", "api_key", PASS)),
                           ("get_fields", lambda v: v.get_fields("plain", ["api_key"], PASS)),
                           ("set", lambda v: v.set("plain", "api_key", "x", "text", PASS)),
                           ("set_fields", lambda v: v.set_fields("plain", {"k": ("x", "text")}, PASS)),
                           ("delete_entry", lambda v: v.delete_entry("plain", PASS)),
                           ("delete_field", lambda v: v.delete_field("plain", "api_key", PASS)),
                           ("change_passphrase", lambda v: v.change_passphrase(PASS, PASS + "-new"))):
            with self.assertRaisesRegex(CredentialError, STORE_ON_MESSAGE, msg=name):
                call(PortableVault(self.vault.path))
        self.assertEqual(self.bytes(), before)

    def test_the_migration_path_opens_it(self):
        self.store_on()
        self.assertEqual(PortableVault(self.vault.path, migration=True).get("plain", "api_key", PASS), KEY)

    def test_store_off_is_unchanged(self):
        self.store_on(False)
        self.assertEqual(PortableVault(self.vault.path).get("plain", "api_key", PASS), KEY)


class TheMigrationLock(VaultCase):
    """M5: scrub, both static restores and the marker operation run only under a live migration lock."""
    GUARDED = (("vault_scrub_signin", {"entry": "xero-demo", "field": FIELD}),
               ("vault_restore_static", {"entry": "plain", "values": {"api_key": {"value": "x", "kind": "text"}}}),
               ("vault_restore_marked_static", {"entry": "xero-demo",
                                                "values": {FIELD: {"value": {"note": "x"}, "kind": "json"}}}),
               ("vault_clear_migration_marker", {}))

    def assert_refused(self):
        before = self.bytes()
        for op, payload in self.GUARDED:
            with self.assertRaisesRegex(CredentialError, LOCK_REFUSED, msg=op):
                self.request(op, **payload)
        self.assertEqual(self.bytes(), before)
        self.assertFalse(portable_vault.migration_marker_path(self.vault.path).exists())

    def test_absent_lock_refuses(self):
        self.assert_refused()

    def test_a_lock_of_a_dead_process_refuses(self):
        with migration_lock.MigrationLock(self.vault.path, "migrate"), \
                mock.patch.object(migration_lock, "_pid_is_running", return_value=False):
            self.assert_refused()

    def test_an_old_lock_refuses(self):
        with migration_lock.MigrationLock(self.vault.path, "migrate"), \
                mock.patch.object(migration_lock.time, "time", return_value=time.time() + 7 * 3600):
            self.assert_refused()

    def test_a_malformed_lock_refuses(self):
        migration_lock.lock_path(self.vault.path).write_text("not json", "utf-8")
        self.assert_refused()

    def test_a_live_lock_lets_them_run(self):
        with migration_lock.MigrationLock(self.vault.path, "migrate"):
            self.assertEqual(self.request(*self.GUARDED[0][:1], **self.GUARDED[0][1]), {"scrubbed": True})
        self.assertNotIn("refresh_token", self.vault.get("xero-demo", FIELD, PASS))

    def test_the_lock_is_exclusive_names_its_process_and_is_removed(self):
        path = migration_lock.lock_path(self.vault.path)
        with migration_lock.MigrationLock(self.vault.path, "rollback"):
            held = json.loads(path.read_text("utf-8"))
            self.assertEqual((held["pid"], held["command"]), (os.getpid(), "rollback"))
            self.assertLessEqual(held["started"], time.time())
            with self.assertRaisesRegex(CredentialError, "already running"):
                with migration_lock.MigrationLock(self.vault.path, "migrate"):
                    pass
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())
        with self.assertRaises(RuntimeError), migration_lock.MigrationLock(self.vault.path, "migrate"):
            raise RuntimeError("stop")
        self.assertFalse(path.exists())

    def test_a_stale_lock_is_replaced(self):
        path = migration_lock.lock_path(self.vault.path)
        path.write_text(json.dumps({"pid": 1, "started": time.time() - 8 * 3600, "command": "migrate"}), "utf-8")
        with migration_lock.MigrationLock(self.vault.path, "migrate"):
            self.assertEqual(json.loads(path.read_text("utf-8"))["pid"], os.getpid())
        self.assertFalse(path.exists())


class MigrationUnderTheLock(StoreFixture):
    """M4 and M5 through migrate_to_store with an in-process agent and store."""

    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: ({"refresh_token": RT1, "tenant_id": "t-1"}, "json"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set("plain", "api_key", KEY, "text", PASS)
        self.agent = VaultAgent(self.vault.path)
        self.agent.unlock(PASS)
        self.lock = migration_lock.lock_path(self.vault.path)
        self.seen = []
        inner = agent_request(self.agent)

        def request(op, **payload):
            self.seen.append((op, self.lock.exists()))
            return inner(op, **payload)
        self.request = request

    def migrate(self, **options):
        lines = []
        code = migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append, **options)
        return code, "\n".join(lines)

    def test_the_migration_holds_the_lock_while_it_runs(self):
        self.assertEqual(self.migrate()[0], 0)
        self.assertIn(("vault_scrub_signin", True), self.seen)
        self.assertFalse(self.lock.exists())

    def test_an_unverified_sign_in_leaves_no_store_copy_and_no_marker(self):
        with mock.patch.object(migrate_to_store, "_verified", return_value=False):
            code, text = self.migrate()
        self.assertEqual(code, 4)
        self.assertIn("xero-demo#" + FIELD, text)
        self.assertIn("removed", text)
        names = set(self.a.list_entries())
        self.assertFalse({n for n in names if n.startswith("xero-demo#")}, names)
        self.assertIn("plain", names)
        self.assertEqual(self.vault.get("xero-demo", FIELD, PASS)["refresh_token"], RT1)
        self.assertFalse(portable_vault.migration_marker_path(self.vault.path).exists())
        self.assertNotIn("vault_scrub_signin", [op for op, _held in self.seen])
        self.assertFalse(self.lock.exists())

    def test_a_store_copy_that_cannot_be_removed_is_reported(self):
        with mock.patch.object(migrate_to_store, "_verified", return_value=False), \
                mock.patch.object(self.a, "delete_entry", side_effect=SecretStoreError("push refused")):
            code, text = self.migrate()
        self.assertEqual(code, 4)
        self.assertIn("could not be removed", text)
        self.assertFalse(portable_vault.migration_marker_path(self.vault.path).exists())

    def test_rollback_with_the_store_on_reads_the_vault_under_the_lock_only(self):
        self.assertEqual(self.migrate()[0], 0)
        agent = VaultAgent(self.vault.path, store=self.ba)
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=True):
            agent.unlock(PASS)
            request = agent_request(agent)
            with self.assertRaisesRegex(CredentialError, STORE_ON_MESSAGE):
                request("vault_list_entries")
            lines = []
            code = migrate_to_store.rollback(request, lambda: self.a, out=lines.append)
        self.assertEqual(code, 0, lines)
        self.assertFalse(portable_vault.migration_marker_path(self.vault.path).exists())
        self.assertFalse(self.lock.exists())


class StoreModeUnlockAndStatus(StoreFixture):
    """M10 (row 22) unlock and lock in store mode; M8 the migration backup's age in the status."""

    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.a.put_entry("plain", {"api_key": KEY})
        self.agent = VaultAgent(self.vault.path, store=self.ba)
        self.request = agent_request(self.agent)
        self.use = lambda p: (p.start(), self.addCleanup(p.stop))
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=True))

    def test_unlock_and_lock_in_store_mode(self):
        self.assertEqual(self.request("unlock", passphrase=PASS), {"unlocked": True})
        status = self.request("status")
        self.assertEqual((status["unlocked"], status["vault_unlocked"]), (True, True))
        self.assertEqual(self.request("get_fields", entry="plain", fields=["api_key"]), {"api_key": KEY})
        with self.assertRaisesRegex(CredentialError, STORE_ON_MESSAGE):
            self.request("vault_get_fields", entry="plain", fields=["api_key"])
        self.assertEqual(self.request("lock"), {"unlocked": False})
        status = self.request("status")
        self.assertEqual((status["unlocked"], status["vault_unlocked"]), (True, False))
        with self.assertRaises(CredentialError):
            self.request("unlock", passphrase="wrong passphrase for the test")

    def test_status_shows_the_migration_backup_age(self):
        self.assertNotIn("migration_backup_age", self.request("status"))
        folder = self.vault.path.parent / "migration-backups"
        folder.mkdir()
        backup = folder / "credentials-20261119-101010.vault"
        backup.write_bytes(self.vault.path.read_bytes())
        two_days = time.time() - 2 * 86400
        os.utime(backup, (two_days, two_days))
        self.assertEqual(self.request("status")["migration_backup_age"], "2.0 days")


class SkeletonIgnoresTheMigrationFiles(unittest.TestCase):
    def test_marker_record_and_lock_are_ignored(self):
        patterns = [line.strip() for line in SKELETON.read_text("utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
        for name in ("credentials.vault.migrated.json", "credentials-20261121-101010.migration.json",
                     "credentials.vault.migration.lock"):
            self.assertTrue(any(fnmatch.fnmatch(name, p) for p in patterns), name)


class CommandLineRefusals(VaultCase):
    """M10 (rows 20 and 22): every command line refuses with the store on; nothing is written."""

    def run_main(self, module, argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", [module.__name__ + ".py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main()
        return code, out.getvalue(), err.getvalue()

    def test_each_vault_credentials_command_is_refused(self):
        self.store_on()
        import vault_broker_client

        self.use(mock.patch.dict(os.environ, {"PORTABLE_VAULT_PASSPHRASE": PASS}),
                 mock.patch.object(vault_broker_client, "broker_unlocked", return_value=False),
                 mock.patch.object(vault_credentials, "_new_passphrase", return_value=PASS + "-new"),
                 mock.patch.object(vault_credentials, "_secret_value", return_value="fictional-value"),
                 mock.patch("builtins.input", side_effect=lambda prompt: prompt.split()[1]))
        vault, child = ["--vault", str(self.vault.path)], ["--", sys.executable, "-c", "pass"]
        commands = {"check": [], "list": [], "change-passphrase": [], "delete-entry": ["--entry", "plain"],
                    "delete-field": ["--entry", "plain", "--field", "api_key"],
                    "put": ["--entry", "plain", "--field", "api_key"],
                    "put-entry": ["--entry", "new", "--secret", "api_key"],
                    "init-json": ["--entry", "plain", "--field", "j"],
                    "run": ["--entry", "plain", "--map", "K=api_key", *child],
                    "session": ["--entry", "plain", "--map", "K=api_key", *child]}
        before = self.bytes()
        for command, extra in commands.items():
            code, out, err = self.run_main(vault_credentials, [*vault, command, *extra])
            self.assertNotEqual(code, 0, command)
            self.assertIn(STORE_ON_MESSAGE, err, command)
            self.assertNotIn(KEY, out + err, command)
        self.assertEqual(self.bytes(), before)

    def test_each_vaultctl_command_is_refused_by_a_vault_only_agent(self):
        self.store_on()
        forbidden = mock.Mock(side_effect=AssertionError("a vault-only agent was asked"))
        self.use(mock.patch.object(vaultctl, "broker_status", return_value={"backend": "vault", "unlocked": True}),
                 mock.patch.object(vaultctl, "broker_request", forbidden),
                 mock.patch.object(vaultctl, "broker_unlocked", return_value=True),
                 mock.patch.object(vaultctl, "_hidden_passphrase", return_value="fictional-value"))
        for argv in (["status"], ["access-token", "--entry", "xero-demo"],
                     ["secret-put", "--entry", "plain", "--field", "api_key"],
                     ["run", "--entry", "plain", "--map", "K=api_key", "--", sys.executable, "-c", "pass"]):
            code, _out, err = self.run_main(vaultctl, argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(STALE_AGENT_MESSAGE, err, argv)

    def test_vaultctl_unlock_and_lock_reach_a_store_agent(self):
        self.store_on()
        sent = []
        self.use(mock.patch.object(vaultctl, "broker_unlocked", return_value=False),
                 mock.patch.object(vaultctl, "broker_request", side_effect=lambda op, **p: sent.append(op) or {}),
                 mock.patch.object(vaultctl, "_hidden_passphrase", return_value=PASS))
        self.assertEqual(self.run_main(vaultctl, ["unlock"])[0], 0)
        self.assertEqual(self.run_main(vaultctl, ["lock"])[0], 0)
        self.assertEqual(sent, ["unlock", "lock"])


if __name__ == "__main__":
    unittest.main()
