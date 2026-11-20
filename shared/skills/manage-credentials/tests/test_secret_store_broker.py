"""The secrets store through the Vault Agent: refresher and other-computer roles, a member's
settings save, grant fields, vault_credentials run in both modes and the store switched off. A
bare local repository is the remote and a fake keyring the keychain. Every value is fictional."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import keyring  # noqa: E402

import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402
from secret_store import SecretStoreError, enrol, keys, oauth_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend, backend_if_enabled, store_enabled  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402
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
        self.fingerprint = self.a.init_personal(words_callback=lambda words: True)
        self.b = self.enrol("B")
        self.ba = StoreBackend(self.a, sync_seconds=0)
        self.bb = StoreBackend(self.b, sync_seconds=0)

    def make_store(self, computer):
        base = self.root / computer
        return SecretStore(use_config_file=False, enabled=True, person="alec", computer=computer,
                           personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                           recovery_package_dir=base / "packages", personal_repo_url=str(self.bare))

    def enrol(self, computer):
        """The real enrolment exchange (enrol.py), approved by A; returns the new computer's store."""
        new = self.make_store(computer)
        rid = enrol.request(new, self.fingerprint)
        self.assertEqual(enrol.approve_step(self.a, rid), "answered")
        enrol.prove(new, rid, display=lambda _title, _words: True)
        self.assertEqual(enrol.approve_step(self.a, rid, display=lambda _title, _words: True), "approved")
        return new.open()

    def sign_in(self, backend, entry, value, field=FIELD):
        """A sign-in or refresh saved the only way a token may change: inside a begun refresh
        (a first sign-in begins with new_authorisation=True). Returns the operation id."""
        begun = backend.begin_refresh(entry, field, new_authorisation=True)
        backend.set_json(entry, field, value, operation=begun["operation"])
        return begun["operation"]

    def token(self, **extra):
        return {"access_token": AT1, "refresh_token": RT1, "expires_at": (19 * 10**8 + 0.5), "token_type": "Bearer",
                "scope": "accounting", "tenant_id": "tenant-1", **extra}


class BrokerRoles(StoreFixture):
    def test_refresher_reads_whole_record_other_computer_access_token_only(self):
        self.sign_in(self.ba, "xero-demo", self.token())
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
        self.sign_in(self.ba, "xero-demo", self.token())
        seen = self.bb.get_json("xero-demo", FIELD)
        seen.update(tenant_id="tenant-2", access_token="fictional-stale")
        self.bb.set_json("xero-demo", FIELD, seen)
        mine = self.ba.get_json("xero-demo", FIELD)
        self.assertEqual((mine["tenant_id"], mine["access_token"], mine["refresh_token"]), ("tenant-2", AT1, RT1))
        with self.assertRaisesRegex(SecretStoreError, "this sign-in refreshes on A"):
            self.bb.set_json("xero-demo", FIELD, {**seen, "refresh_token": "fictional-other"})

    def test_refresher_publication_carries_operation_and_reaches_other_computer(self):
        self.sign_in(self.ba, "xero-demo", self.token())
        operation = self.sign_in(self.ba, "xero-demo",
                                 self.token(access_token="fictional-access-2", refresh_token="fictional-r2"))
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        self.assertIsNone(self.ba._journal.read(signin.journal_key))  # retired once published
        self.assertEqual(self.a._tree_object(signin.oauth_id, self.a.checkpoint)["operation"], operation)
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], "fictional-access-2")
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], "fictional-r2")

    def test_run_maps_static_fields_and_refuses_grant_fields_elsewhere(self):
        self.sign_in(self.ba, "xero-demo", self.token())
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


class TeamConfigured(unittest.TestCase):
    def config(self, root, **extra):
        brain = root / "brain"
        path = brain / "memory" / "skills" / "manage-credentials" / "config" / "secret-store.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"enabled": True, "person": "alec", "computer": "A",
                                    "personal_clone": str(root / "p"), "team_clone": str(root / "t"),
                                    "checkpoint_dir": str(root / "c"), "recovery_package_dir": str(root / "k"),
                                    "personal_repo_url": str(root / "p.git"), **extra}), "utf-8")
        return brain

    def test_backend_constructs_and_opens_the_configured_team_store(self):
        from secret_store.team import TeamStore
        with tempfile.TemporaryDirectory() as tmp:
            backend = backend_if_enabled(self.config(Path(tmp), team_repo_url=str(Path(tmp) / "t.git")))
            self.assertIsInstance(backend.team, TeamStore)
            self.assertEqual(backend.team.clone, Path(tmp) / "t")
            with mock.patch.object(backend.store, "open") as personal, mock.patch.object(backend.team, "open") as team:
                backend._pull_all(tolerate=True)
            personal.assert_called_once_with()
            team.assert_called_once_with()

    def test_no_team_store_without_its_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(backend_if_enabled(self.config(Path(tmp))).team)


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


class AgentClients(StoreFixture):
    """A connector's PortableVaultJsonStore on computer A (the refresher) or B, each talking to its
    own in-process Vault Agent. No tests of its own."""

    @property
    def SIGNIN(self):
        """The journal key: the entry, field, repository id and grant object id."""
        return oauth_ops.find(self.ba.store, "xero-demo", FIELD).journal_key

    def setUp(self):
        super().setUp()
        for name, value in (("REFRESH_POLL_SECONDS", 0.05), ("REFRESH_WAIT_SECONDS", 10.0)):
            patcher = mock.patch.object(vault_broker_client, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def client(self, backend, computer, agent=None):
        from portable_vault import PortableVaultJsonStore
        path = self.root / f"{computer}.vault"
        request = agent_request(agent or VaultAgent(path, store=backend))
        with mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True), \
                mock.patch.object(vault_broker_client, "broker_request", side_effect=request):
            return PortableVaultJsonStore("xero-demo", FIELD, path=path)

    def later(self, action, delay=0.3):
        """Run action on another thread after delay (the refresher, while B waits)."""
        def run():
            time.sleep(delay)
            action()
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(thread.join)
        return thread


class AgentRefresh(AgentClients):
    """begin_refresh and abort_refresh through the Vault Agent, the ten-minute limit, and a
    computer that is not the refresher waiting for it."""

    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())
        self.journal = self.ba._journal
        self.request = agent_request(VaultAgent(self.root / "A.vault", store=self.ba))

    def test_save_inside_the_lock_publishes_with_the_begun_operation(self):
        store = self.client(self.ba, "A")
        with store.rotation_lock(refresh=True):
            current = store.load()
            begun = self.journal.read(self.SIGNIN)
            self.assertEqual(begun["state"], "calling")
            store.save({**current, "access_token": "fictional-access-2", "refresh_token": "fictional-r2"})
        self.assertIsNone(self.journal.read(self.SIGNIN))
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        self.assertEqual(self.a._tree_object(signin.oauth_id, self.a.checkpoint)["operation"], begun["operation"])
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], "fictional-access-2")
        self.assertEqual(self.ba._pending, {})

    def test_time_limit_leaves_the_record_uncertain(self):
        self.ba.refresh_timeout = 0.1
        begun = self.request("begin_refresh", entry="xero-demo", field=FIELD)
        deadline = time.monotonic() + 10
        while self.ba._pending and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.journal.read(self.SIGNIN)["state"], "calling")
        with self.assertRaisesRegex(CredentialError, "ran past its time limit"):
            self.request("set_json", entry="xero-demo", field=FIELD, value=self.token(), operation=begun["operation"])
        with self.assertRaisesRegex(CredentialError, "uncertain"):
            self.request("begin_refresh", entry="xero-demo", field=FIELD)
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["access_token"], AT1)

    def test_second_begin_unmarked_save_and_disabled_refresher_are_refused(self):
        begun = self.request("begin_refresh", entry="xero-demo", field=FIELD)
        self.assertEqual(begun["record"]["refresh_token"], RT1)
        with self.assertRaisesRegex(CredentialError, "already under way"):
            self.request("begin_refresh", entry="xero-demo", field=FIELD)
        with self.assertRaisesRegex(CredentialError, "only its own save"):
            self.request("set_json", entry="xero-demo", field=FIELD, value=self.token(access_token="fictional-x"))
        self.assertEqual(self.request("abort_refresh", entry="xero-demo", field=FIELD, operation=begun["operation"]),
                         {"aborted": True})
        self.journal.set_disabled(self.SIGNIN)
        with self.assertRaisesRegex(CredentialError, "switched off"):
            self.request("begin_refresh", entry="xero-demo", field=FIELD)

    def test_unmarked_token_change_is_refused_settings_are_not(self):
        for entry, value in (("xero-demo", self.token(access_token="fictional-x")),
                             ("new-signin", {"access_token": AT1, "refresh_token": RT1})):
            with self.assertRaisesRegex(SecretStoreError, "only inside a begun refresh"):
                self.ba.set_json(entry, FIELD, value)
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["access_token"], AT1)
        self.assertNotIn("new-signin", self.a.list_entries())
        self.ba.set_json("xero-demo", FIELD, self.token(tenant_id="tenant-3"))
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["tenant_id"], "tenant-3")
        self.assertIsNone(self.journal.read(self.SIGNIN))

    def test_first_signin_begins_with_new_authorisation(self):
        self.assertEqual(self.ba.begin_refresh("new-signin", FIELD), {"signin": False})
        begun = self.ba.begin_refresh("new-signin", FIELD, new_authorisation=True)
        self.ba.set_json("new-signin", FIELD, {"access_token": AT1, "refresh_token": RT1}, operation=begun["operation"])
        self.assertEqual(self.ba.get_json("new-signin", FIELD)["refresh_token"], RT1)
        self.assertEqual(self.ba._pending, {})

    def test_plain_or_fresh_lock_writes_nothing(self):
        store = self.client(self.ba, "A")
        for options in ({}, {"leeway_seconds": 60}):
            with store.rotation_lock(**options):
                self.assertEqual((self.journal.read(self.SIGNIN), self.ba._pending), (None, {}))
        with self.assertRaisesRegex(CredentialError, "only inside a begun refresh"), store.rotation_lock():
            store.save({**store.load(), "access_token": "fictional-access-2", "refresh_token": "fictional-r2"})
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], RT1)

    def test_normal_exit_without_save_stays_uncertain(self):
        store = self.client(self.ba, "A")
        with self.assertRaisesRegex(CredentialError, "ended without saving"):
            with store.rotation_lock(refresh=True):
                pass
        self.assertEqual((self.journal.read(self.SIGNIN)["state"], self.ba._pending), ("calling", {}))

    def test_other_computer_waits_for_the_refresher(self):
        a, b = self.client(self.ba, "A"), self.client(self.bb, "B")

        def refresh_on_a():
            with a.rotation_lock(refresh=True):
                a.save({**a.load(), "access_token": "fictional-access-2", "refresh_token": "fictional-r2"})
        self.later(refresh_on_a)
        with b.rotation_lock(refresh=True):
            seen = b.load()
        self.assertEqual(seen["access_token"], "fictional-access-2")
        self.assertNotIn("refresh_token", seen)

    def test_other_computer_stops_in_plain_words(self):
        b = self.client(self.bb, "B")
        with mock.patch.object(vault_broker_client, "REFRESH_WAIT_SECONDS", 0.3), \
                self.assertRaisesRegex(CredentialError, "^this sign-in refreshes on A; it has not refreshed it yet$"):
            with b.rotation_lock(refresh=True):
                self.fail("the block must not run")


if __name__ == "__main__":
    unittest.main()
