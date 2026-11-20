"""The secrets store through the Vault Agent: refresher and other-computer roles, a member's
settings save, grant fields, vault_credentials run in both modes and the store switched off. A
bare local repository is the remote and a fake keyring the keychain. Every value is fictional."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import keyring  # noqa: E402

import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store import SecretStoreError, keys, oauth_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend, store_enabled  # noqa: E402
from secret_store.policy import public_entry  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402
from secret_store.store_ops import next_policy  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402
from vault_agent_runtime import AGENT_PROTOCOL_VERSION  # noqa: E402

FIELD = "oauth_token_json"
AT1, RT1 = "fictional-access-1-not-real", "fictional-refresh-1-not-real"
SECRET = "fictional-client-secret-not-real"
KEY = "fictional-api-key-not-real"
PASS = "fictional passphrase for tests only 42 xyz"
_ENV_KEYS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
_saved_env = {}
_global_dir = None


def setUpModule():
    global _global_dir
    _global_dir = tempfile.TemporaryDirectory()
    cfg = Path(_global_dir.name) / "gitconfig"
    cfg.write_text("[user]\n\tname = Test Person\n\temail = person@example.com\n"
                   "[core]\n\tautocrlf = true\n[init]\n\tdefaultBranch = main\n", "utf-8")
    for key in _ENV_KEYS:
        _saved_env[key] = os.environ.get(key)
    os.environ["GIT_CONFIG_GLOBAL"] = str(cfg)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


def tearDownModule():
    for key, value in _saved_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _global_dir.cleanup()


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, password):
        self.items[(service, user)] = password


def agent_request(agent):
    """broker_request bound to an in-process agent."""
    def request(op, **payload):
        response = agent.handle({"v": AGENT_PROTOCOL_VERSION, "token": agent._auth_token, "op": op, "id": "t", **payload})
        if response.get("ok"):
            return response["result"]
        raise CredentialError(response.get("error"))
    return request


class StoreFixture(unittest.TestCase):
    """Computer A (first, refresher of what it stores) and computer B of the same person."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare)],
                       check=True, capture_output=True)
        fake = FakeKeyring()
        name = f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"
        for patcher in (mock.patch.object(keyring, "get_keyring", return_value=fake),
                        mock.patch.object(keys, "ALLOWED_BACKENDS", frozenset({name}))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.a = self.make_store("A")
        fingerprint = self.a.init_personal(words_callback=lambda words: True)
        self.enrol("B")
        self.b = self.make_store("B").open(fingerprint)
        self.ba = StoreBackend(self.a, sync_seconds=0)
        self.bb = StoreBackend(self.b, sync_seconds=0)

    def make_store(self, computer):
        base = self.root / computer
        return SecretStore(use_config_file=False, enabled=True, person="alec", computer=computer,
                           personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                           recovery_package_dir=base / "packages", personal_repo_url=str(self.bare))

    def enrol(self, computer):
        x, e = keys.generate_key_pairs()
        keys.store_private_keys("alec", computer, x, e)
        a = self.a

        def change(doc):
            doc["people"]["alec"]["computers"][computer] = public_entry(x.public_key(), e.public_key())
        a._write(lambda: ({"policy.json": next_policy(a.policy, a._identity().ed25519, change)}, "policy"))

    def token(self, **extra):
        return {"access_token": AT1, "refresh_token": RT1, "expires_at": (19 * 10**8 + 0.5), "token_type": "Bearer",
                "scope": "accounting", "tenant_id": "tenant-1", **extra}


class BrokerRoles(StoreFixture):
    def test_refresher_reads_whole_record_other_computer_access_token_only(self):
        self.ba.set_json("xero-demo", FIELD, self.token())
        mine = self.ba.get_json("xero-demo", FIELD)
        self.assertEqual((mine["refresh_token"], mine["expires_at"]), (RT1, (19 * 10**8)))
        theirs = self.bb.get_json("xero-demo", FIELD)
        self.assertEqual((theirs["access_token"], theirs["tenant_id"]), (AT1, "tenant-1"))
        self.assertNotIn("refresh_token", theirs)
        request = agent_request(VaultAgent(self.root / "none.vault", store=self.bb))
        self.assertEqual(request("get_access_token", entry="xero-demo", field=FIELD)["access_token"], AT1)
        status = request("status")
        self.assertEqual((status["backend"], status["unlocked"], status["vault_unlocked"]), ("store", True, False))

    def test_member_settings_save_keeps_token_fields(self):
        self.ba.set_json("xero-demo", FIELD, self.token())
        seen = self.bb.get_json("xero-demo", FIELD)
        seen.update(tenant_id="tenant-2", access_token="fictional-stale")
        self.bb.set_json("xero-demo", FIELD, seen)
        mine = self.ba.get_json("xero-demo", FIELD)
        self.assertEqual((mine["tenant_id"], mine["access_token"], mine["refresh_token"]), ("tenant-2", AT1, RT1))
        with self.assertRaisesRegex(SecretStoreError, "this sign-in refreshes on A"):
            self.bb.set_json("xero-demo", FIELD, {**seen, "refresh_token": "fictional-other"})

    def test_refresher_publication_carries_operation_and_reaches_other_computer(self):
        self.ba.set_json("xero-demo", FIELD, self.token())
        self.ba.set_json("xero-demo", FIELD, self.token(access_token="fictional-access-2", refresh_token="fictional-r2"))
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        record = self.ba._journal.read(signin.journal_key)
        self.assertEqual(record["state"], "published")
        self.assertEqual(self.a._tree_object(signin.oauth_id, self.a.checkpoint)["operation"], record["operation"])
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], "fictional-access-2")
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], "fictional-r2")

    def test_run_maps_static_fields_and_refuses_grant_fields_elsewhere(self):
        self.ba.set_json("xero-demo", FIELD, self.token())
        self.ba.set_text("xero-demo", "client_secret", SECRET)
        self.ba.set_text("plain", "api_key", KEY)
        self.assertEqual(self.ba.get_fields("xero-demo", ["client_secret"]), {"client_secret": SECRET})
        for backend, allowed in ((self.ba, True), (self.bb, False)):
            request = agent_request(VaultAgent(self.root / "none.vault", store=backend))
            with mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True), \
                    mock.patch.object(vault_broker_client, "broker_request", side_effect=request):
                vault = PortableVault(self.root / "none.vault")
                env = vault_credentials._credential_environment(vault, "plain", ["API_KEY=api_key"], None)
                self.assertEqual(env["API_KEY"], KEY)
                if allowed:
                    env = vault_credentials._credential_environment(vault, "xero-demo", ["S=client_secret"], None)
                    self.assertEqual(env["S"], SECRET)
                else:
                    with self.assertRaisesRegex(CredentialError, "this sign-in refreshes on A"):
                        vault_credentials._credential_environment(vault, "xero-demo", ["S=client_secret"], None)


class StoreOff(unittest.TestCase):
    def test_store_off_keeps_todays_vault_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(store_enabled(root))
            config = root / "memory" / "skills" / "manage-credentials" / "config" / "secret-store.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"enabled": False, "person": "alec"}), "utf-8")
            self.assertFalse(store_enabled(root))
            vault = PortableVault(root / "credentials.vault")
            vault.initialize(PASS)
            vault.set("plain", "api_key", KEY, "text", PASS)
            agent = VaultAgent(vault.path)
            self.assertNotIn("backend", agent.status())
            agent.unlock(PASS)
            request = agent_request(agent)
            with mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True), \
                    mock.patch.object(vault_broker_client, "broker_request", side_effect=request):
                env = vault_credentials._credential_environment(vault, "plain", ["API_KEY=api_key"], None)
            self.assertEqual(env["API_KEY"], KEY)
            agent.set_json("xero-demo", FIELD, {"access_token": AT1, "refresh_token": RT1})
            self.assertEqual(agent.get_json("xero-demo", FIELD)["refresh_token"], RT1)


if __name__ == "__main__":
    unittest.main()
