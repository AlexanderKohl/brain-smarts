"""Round-6 review fixes: oauth integrity never depends on the entry name (every profile's token
fields are protected, an unrecognised provider is bound as "unknown"); an enabled store never falls
back to the passphrase vault; a recovery package is fresh only when its signed marker matches the
current policy, a failed write is retried at the next use, and the daily due check reports a stale
or missing package. Every token is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import importlib.util
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
import portable_vault  # noqa: E402
import token_relay  # noqa: E402
import vault_credentials  # noqa: E402
from portable_vault import CredentialError, PortableVault, PortableVaultJsonStore  # noqa: E402
from secret_store import oauth_ops, policy, provider_profiles, store_ops  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402
from test_secret_store_accept import World, commit  # noqa: E402
from test_secret_store_broker import (FIELD, PASS, StoreFixture, agent_request,  # noqa: E402,F401
                                      setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

NEUTRAL = "Company Social"
META = {"user_token": "fictional-user", "user_token_expires_at": 100,
        "pages": [{"id": "page-1", "token": "fictional-page"}], "app": "settings"}
STORE_ON = "the secrets store is on; start the Vault Agent"


def scheduled_review():
    path = SCRIPTS.parent.parent / "tasks" / "scripts" / "scheduled_review.py"
    spec = importlib.util.spec_from_file_location("scheduled_review_r6", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TokenFieldsWhateverTheName(unittest.TestCase):
    def test_every_profile_token_field_for_every_provider(self):
        for provider in (None, "unknown", "xero", "google", "meta"):
            self.assertTrue({"user_token", "user_token_expires_at", "pages", "accessToken", "access_token"}
                            <= provider_profiles.token_fields(provider), provider)


class UnknownProviderAccept(unittest.TestCase):
    """o1/g1 bound to provider "unknown"; carol is a hostile member."""

    def setUp(self):
        w = self.w = World()

        def assign(d):
            d["assignments"] = {"o1": {"group": "ops", "kind": "oauth", "provider": "unknown"},
                                "g1": {"group": "ops", "kind": "grant", "provider": "unknown"}}
            d["refreshers"] = {"g1": {"person": "bob", "computer": "pc", "oauth": "o1"}}
        doc = w.next_policy(assign)
        p = policy.Policy(doc)
        self.record = dict(META, provider="unknown")
        w.apply(commit(w.obj("o1", dict(self.record), "bob-pc", p, operation="op-0"), w.obj("g1", {}, "bob-pc", p),
                       w.obj("index-ops", w.index(p, "ops"), "bob-pc", p), pol=doc))

    def test_hostile_member_cannot_change_meta_shaped_tokens(self):
        w, latest = self.w, {"o1": dict(self.record)}
        for change in ({"user_token": "fictional-hostile"}, {"user_token_expires_at": 999},
                       {"pages": [{"id": "page-1", "token": "fictional-hostile"}]}):
            with self.assertRaisesRegex(SecretStoreError, "access-token fields changed"):
                w.accept(commit(w.obj("o1", dict(self.record, **change), "carol-pc")), latest=latest)
        w.accept(commit(w.obj("o1", dict(self.record, app="other settings"), "carol-pc")), latest=latest)


class NeutralNameSignins(StoreFixture):
    def bound(self, signin):
        return self.a.policy.doc["assignments"][signin.oauth_id].get("provider")

    def test_migrated_under_a_neutral_name_binds_unknown(self):
        vault = PortableVault(self.root / "vault" / "credentials.vault")
        vault.initialize(PASS)
        vault.set_fields(NEUTRAL, {FIELD: (dict(META), "json")}, PASS)
        agent = VaultAgent(vault.path)
        agent.unlock(PASS)
        self.assertEqual(migrate_to_store.migrate(agent_request(agent), lambda: self.a, out=lambda _l: None), 0)
        signin = oauth_ops.find(self.a, NEUTRAL, FIELD)
        self.assertEqual((signin.provider, self.bound(signin)), ("unknown", "unknown"))

    def test_created_directly_binds_unknown_and_settings_keep_tokens(self):
        self.sign_in(self.ba, NEUTRAL, dict(META))
        signin = oauth_ops.find(self.a, NEUTRAL, FIELD)
        self.assertEqual((signin.provider, self.bound(signin)), ("unknown", "unknown"))
        oauth_ops.save_settings(self.a, signin, {"user_token": "fictional-hostile", "pages": [], "app": "new"})
        shared = oauth_ops.read_shared(self.a, signin)
        self.assertEqual((shared["user_token"], shared["pages"], shared["app"]),
                         ("fictional-user", META["pages"], "new"))


class StoreOnFailsClosed(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.dict(os.environ, {"PORTABLE_VAULT_PASSPHRASE": PASS})
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, text):
        path = self.folder / store_ops.CONFIG_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")

    def test_enabled_reading(self):
        self.assertFalse(portable_vault.secret_store_enabled(self.folder))
        self.config('{"enabled": false, "person": "alec"}')
        self.assertFalse(portable_vault.secret_store_enabled(self.folder))
        self.config('{"person": "alec"}')
        self.assertTrue(portable_vault.secret_store_enabled(self.folder))
        self.config("not json")  # unreadable counts as on: fail closed
        self.assertTrue(portable_vault.secret_store_enabled(self.folder))

    def test_json_store(self):
        vault = self.folder / "credentials.vault"
        with mock.patch.object(portable_vault, "BrokerOAuthStore", side_effect=CredentialError("agent down")):
            with mock.patch.object(portable_vault, "secret_store_enabled", return_value=True):
                with self.assertRaisesRegex(CredentialError, STORE_ON):
                    PortableVaultJsonStore("xero-demo", path=vault)
            with mock.patch.object(portable_vault, "secret_store_enabled", return_value=False):
                self.assertTrue(PortableVaultJsonStore("xero-demo", path=vault).path.startswith("vault://"))

    def test_vault_credentials(self):
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=True):
            with self.assertRaisesRegex(CredentialError, STORE_ON):
                vault_credentials._passphrase()
            with mock.patch.object(vault_credentials, "_try_broker_fields", return_value=None):
                with self.assertRaisesRegex(CredentialError, STORE_ON):
                    vault_credentials._credential_environment(PortableVault(self.folder / "v.vault"), "e",
                                                              ["NAME=field"], PASS)
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=False):
            self.assertEqual(vault_credentials._passphrase(), PASS)

    def test_relay_key(self):
        vault = mock.Mock()
        vault.get_fields.side_effect = LookupError("read the old vault")
        store = mock.Mock(_broker=None, vault=vault, passphrase=PASS)
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=True):
            with self.assertRaisesRegex(CredentialError, STORE_ON):
                token_relay.read_relay_key(store)
        with mock.patch.object(portable_vault, "secret_store_enabled", return_value=False):
            with self.assertRaises(LookupError):
                token_relay.read_relay_key(store)


class PackageFreshness(StoreFixture):
    def marker(self):
        path = self.a._package_path()
        return path, path.with_name(path.name + ".policy")

    def test_marker_for_another_policy_is_rebuilt_on_open(self):
        path, marker = self.marker()
        store_ops.write_marker(marker, path, "0" * 64, self.a._identity().ed25519)
        self.a.open()
        self.assertTrue(store_ops.marker_current(marker, path, self.a.policy.hash,
                                                 self.a._identity().ed25519.public_key()))

    def test_failed_write_is_retried_at_the_next_use(self):
        with mock.patch.object(self.a, "refresh_recovery_package", side_effect=OSError("offline drive")):
            self.a._package_upkeep()
        self.assertTrue(self.a.package_error)
        self.assertIn("refresh failed", self.a.status())
        self.a.list_entries()
        self.assertIsNone(self.a.package_error)

    def test_package_health_and_due_check(self):
        brain = Path(tempfile.mkdtemp())
        config = {"person": "alec", "computer": "A", "personal_clone": str(self.a.config["personal_clone"]),
                  "checkpoint_dir": str(self.a.config["checkpoint_dir"]),
                  "recovery_package_dir": str(self.a.config["recovery_package_dir"])}
        review = scheduled_review()
        self.assertIsNone(review.secrets_package(brain))  # no configuration: the store is off
        (brain / store_ops.CONFIG_RELATIVE).parent.mkdir(parents=True)
        (brain / store_ops.CONFIG_RELATIVE).write_text(json.dumps(dict(config, enabled=False)), "utf-8")
        self.assertIsNone(review.secrets_package(brain))
        (brain / store_ops.CONFIG_RELATIVE).write_text(json.dumps(config), "utf-8")
        self.assertIsNone(review.secrets_package(brain))
        path, marker = self.marker()
        old = time.time() - 8 * 86400
        os.utime(path, (old, old))
        self.assertIn("day(s) old", review.secrets_package(brain))
        os.utime(path, None)
        store_ops.write_marker(marker, path, "0" * 64, self.a._identity().ed25519)
        self.assertIn("does not match the current policy", review.secrets_package(brain))
        path.unlink()
        self.assertIn("no recovery package", review.secrets_package(brain))


if __name__ == "__main__":
    unittest.main()
