"""Round-7 review fixes: with the store enabled every client path requires the running agent to
serve the store (a vault-only agent started earlier is refused with a restart message), malformed
enabled configuration is fatal, and no token relay is built or used; the Vault Agent keeps the
recovery package fresh on its own timer and keeps its failures for status and the due check.
Every token is fictional."""
import contextlib
import io
import os
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable_vault  # noqa: E402
import token_relay  # noqa: E402
import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
import vaultctl  # noqa: E402
from portable_vault import BrokerOAuthStore, CredentialError, PortableVaultJsonStore  # noqa: E402
from secret_store import broker_backend, enrol, store_ops  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402
from test_secret_store_broker import StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401
from vault_agent import VaultAgent  # noqa: E402

RESTART = "started before the secrets store was switched on; restart it"
VAULT_ONLY = {"running": True, "unlocked": True, "pid": 1, "vault_path": "v"}
STORE = dict(VAULT_ONLY, backend="store", store="ok")


def agent(status):
    def request(op, **_payload):
        return {"ping": "pong", "status": status, "get_fields": {"f": "fictional"}}.get(op)
    return [mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True),
            mock.patch.object(vault_broker_client, "broker_request", side_effect=request)]


class Patched(unittest.TestCase):
    def use(self, *patchers):
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def store_on(self, on=True):
        self.use(mock.patch.object(portable_vault, "secret_store_enabled", return_value=on))


class StaleVaultOnlyAgent(Patched):
    def setUp(self):
        self.vault = Path(tempfile.mkdtemp()) / "credentials.vault"

    def test_store_on_refuses_vault_only_agent(self):
        self.store_on()
        self.use(*agent(VAULT_ONLY))
        with self.assertRaisesRegex(CredentialError, RESTART):
            BrokerOAuthStore("xero-demo", path=self.vault)
        with self.assertRaisesRegex(CredentialError, RESTART):
            PortableVaultJsonStore("xero-demo", path=self.vault)
        with self.assertRaisesRegex(CredentialError, RESTART):
            vault_credentials._try_broker_fields("e", ["f"])

    def test_store_on_accepts_store_agent(self):
        self.store_on()
        self.use(*agent(STORE))
        self.assertTrue(BrokerOAuthStore("xero-demo", path=self.vault).store_mode())
        self.assertEqual(vault_credentials._try_broker_fields("e", ["f"]), {"f": "fictional"})

    def test_store_off_unchanged(self):
        self.store_on(False)
        self.use(*agent(VAULT_ONLY))
        self.assertFalse(BrokerOAuthStore("xero-demo", path=self.vault).store_mode())
        self.assertEqual(vault_credentials._try_broker_fields("e", ["f"]), {"f": "fictional"})

    def vaultctl(self, *argv):
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["vaultctl", *argv]), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            return vaultctl.main(), err.getvalue()

    def test_vaultctl_refuses(self):
        self.store_on()
        self.use(mock.patch.object(vaultctl, "broker_status", return_value=VAULT_ONLY),
                 mock.patch.object(vaultctl, "broker_unlocked", return_value=True),
                 mock.patch.object(vaultctl, "broker_request", side_effect=AssertionError("used")))
        for argv in (["status"], ["access-token", "--entry", "e"], ["run", "--entry", "e", "--map", "A=f", "--", "x"]):
            code, err = self.vaultctl(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(RESTART, err)

    def test_vaultctl_status_with_store_agent(self):
        self.store_on()
        self.use(mock.patch.object(vaultctl, "broker_status", return_value=STORE))
        self.assertEqual(self.vaultctl("status")[0], 0)


class MalformedConfiguration(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def write(self, text):
        path = self.root / store_ops.CONFIG_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")

    def test_fatal_never_store_off(self):
        self.assertFalse(broker_backend.store_enabled(self.root))
        self.write('{"enabled": false}')
        self.assertFalse(broker_backend.store_enabled(self.root))
        for text in ("not json", '{"enabled": true}', '{"person": "alec", "surprise": 1}', "[1]"):
            self.write(text)
            with self.assertRaises(SecretStoreError, msg=text):
                broker_backend.backend_if_enabled(self.root)
            self.assertTrue(portable_vault.secret_store_enabled(self.root), text)


class RelayIgnoredInStoreMode(Patched):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.vault = folder / "credentials.vault"
        config = folder / "token-relay.json"
        config.write_text(json.dumps({"backend": "github", "repository": "example/relay",
                                      "entries": ["xero-demo"]}), "utf-8")
        self.config = config
        self.broker = mock.Mock(path="broker://x", rotation_lock_path=folder / "l.lock")
        self.broker.store_mode.return_value = True
        self.broker.refresh_lock.return_value = "journal lock"
        self.use(mock.patch.object(portable_vault, "BrokerOAuthStore", return_value=self.broker),
                 mock.patch.object(token_relay, "resolve_config", return_value=(config, [config])))

    def test_no_relay_lease_journal_used(self):
        self.store_on()
        self.use(mock.patch.object(token_relay, "load_config", side_effect=AssertionError("relay read")),
                 mock.patch.object(token_relay, "RelayedStore", side_effect=AssertionError("relay built")))
        store = PortableVaultJsonStore("xero-demo", path=self.vault)
        self.assertIsNone(store._relay)
        self.assertEqual(store.rotation_lock(refresh=True), "journal lock")
        self.broker.refresh_lock.assert_called_once()

    def test_store_off_keeps_relay(self):
        self.store_on(False)
        self.use(mock.patch.object(token_relay, "load_config",
                                   return_value=mock.Mock(entries=["xero-demo"], lease_seconds=300)),
                 mock.patch.object(token_relay, "make_backend", return_value=mock.Mock()),
                 mock.patch.object(token_relay, "RelayedStore", return_value="relayed"))
        self.assertEqual(PortableVaultJsonStore("xero-demo", path=self.vault)._relay, "relayed")

    def test_status_reports_relay_ignored(self):
        backend = mock.Mock()
        backend.status.return_value = {"backend": "store", "store": "ok"}
        status = VaultAgent(self.vault, store=backend).status()
        self.assertIn("ignored", status["token_relay"])
        self.assertNotIn("token_relay", VaultAgent(self.vault).status())


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class PackageTimer(StoreFixture):
    def marker(self):
        path = self.a._package_path()
        return path, path.with_name(path.name + ".policy")

    def current(self):
        path, marker = self.marker()
        return store_ops.marker_current(marker, path, self.a.policy.hash, self.a._identity().ed25519.public_key())

    def test_timer_runs_at_least_daily_on_a_fake_clock(self):
        clock, ticks = FakeClock(), []
        backend = mock.Mock(package_tick=lambda: ticks.append(clock.now))
        timer = broker_backend.PackageTimer(backend, clock=clock)
        self.assertLessEqual(timer.interval, 24 * 3600)
        waits = []

        def wait(seconds):
            waits.append(seconds)
            clock.now += seconds

        timer.run(stopped=lambda: clock.now >= 1000.0 + 3 * 86400, wait=wait)
        self.assertGreaterEqual(len(ticks), 3)
        self.assertTrue(all(b - a <= 24 * 3600 for a, b in zip(ticks, ticks[1:])))

    def test_tick_refreshes_a_stale_or_mismatched_package_without_a_request(self):
        path, marker = self.marker()
        store_ops.write_marker(marker, path, "0" * 64, self.a._identity().ed25519)
        self.assertFalse(self.current())
        broker_backend.PackageTimer(self.ba, clock=FakeClock()).tick()
        self.assertTrue(self.current())
        old = time.time() - 8 * 86400
        os.utime(path, (old, old))
        broker_backend.PackageTimer(self.ba, clock=FakeClock()).tick()
        self.assertLess(time.time() - path.stat().st_mtime, 3600)

    def test_policy_changed_elsewhere_is_pulled(self):
        new = self.make_store("C")
        rid = enrol.request(new, self.fingerprint)
        self.assertEqual(enrol.approve_step(self.b, rid), "answered")
        enrol.prove(new, rid, display=lambda _title, _words: True)
        self.assertEqual(enrol.approve_step(self.b, rid, display=lambda _t, _w: True), "approved")
        before = self.a.policy.hash
        broker_backend.PackageTimer(self.ba, clock=FakeClock()).tick()
        self.assertNotEqual(self.a.policy.hash, before)
        self.assertTrue(self.current())

    def test_failure_kept_shown_and_retried(self):
        path, marker = self.marker()
        store_ops.write_marker(marker, path, "0" * 64, self.a._identity().ed25519)
        clock = FakeClock()
        timer = broker_backend.PackageTimer(self.ba, clock=clock)
        with mock.patch.object(self.a, "refresh_recovery_package", side_effect=OSError("offline drive")):
            timer.tick()
        self.assertIn("refresh failed", self.ba.status()["store"])
        self.assertIn("upkeep failed", store_ops.package_health(self.a.config))
        clock.now += timer.interval
        timer.tick()
        self.assertTrue(self.current())
        self.assertIsNone(self.a.package_error)
        self.assertIsNone(store_ops.package_health(self.a.config))

    def test_agent_starts_the_timer_only_for_the_store(self):
        self.assertTrue(VaultAgent(store=self.ba)._package_timer())
        self.assertIsNone(VaultAgent()._package_timer())


if __name__ == "__main__":
    unittest.main()
