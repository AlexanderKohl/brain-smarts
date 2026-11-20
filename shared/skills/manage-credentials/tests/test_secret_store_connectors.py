"""The skill library's connectors against the secrets store, in both roles, without importing the
library: each function below reproduces one call sequence found by grep in library/skills (xero-
access, gohighlevel-access, google-workspace-access, linkedin-access, meta-access). Computer A is
the refresher, B another computer of the same person. Every value is fictional."""
import sys
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from portable_vault import CredentialError, PortableVault  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, PASS, RT1, AgentClients, setUpModule,  # noqa: E402,F401
                                      tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

EXPIRED = 10**9
NEW = {"access_token": "fictional-access-5", "refresh_token": "fictional-refresh-5",
       "expires_at": 19 * 10**8 + 7200, "token_type": "Bearer"}


class NoRefreshToken(Exception):
    """The connector's own "No refresh token is stored" error."""


def leeway_refresh(store, provider, force=False, leeway=90):
    """xero_oauth and ghl_oauth Client.refresh (access_token() calls it with the leeway)."""
    with store.rotation_lock(refresh=force, leeway_seconds=leeway):
        current = store.load()
        if not force and float(current.get("expires_at", 0)) > time.time() + leeway:
            return current
        if not current.get("refresh_token"):
            raise NoRefreshToken()
        updated = provider(current["refresh_token"])
        updated["tenant_id"] = current.get("tenant_id")
        store.save(updated)
    return updated


def code_exchange(store, provider):
    """xero_oauth and ghl_oauth Client.exchange_code."""
    with store.rotation_lock(refresh=True, new_authorisation=True):
        token = provider("code")
        token["tenant_id"] = store.load().get("tenant_id")
        store.save(token)
    return token


def plain_lock_refresh(store, provider):
    """google_oauth Client.refresh and linkedin_client refresh: a plain rotation_lock()."""
    with store.rotation_lock():
        current = store.load()
        if not current.get("refresh_token"):
            raise NoRefreshToken()
        updated = provider(current["refresh_token"])
        store.save(updated)
    return updated


def settings_save(store, tenant):
    """xero select_tenant, and meta_connect saving its record: a plain lock, load, change, save."""
    with store.rotation_lock():
        token = store.load()
        token["tenant_id"] = tenant
        store.save(token)


class ConnectorPatterns(AgentClients):
    def setUp(self):
        super().setUp()
        self.ba.set_json("xero-demo", FIELD, self.token(expires_at=EXPIRED))
        self.a, self.b = self.client(self.ba, "A"), self.client(self.bb, "B")
        self.calls = []

    def provider(self, grant):
        self.calls.append(grant)
        return dict(NEW)

    def test_refresher_leeway_refresh_goes_through_the_journal(self):
        leeway_refresh(self.a, self.provider)
        self.assertEqual(self.ba._journal.read(self.SIGNIN)["state"], "published")
        self.assertEqual(leeway_refresh(self.a, self.provider)["access_token"], NEW["access_token"])
        self.assertEqual(self.calls, [RT1])
        self.assertEqual(self.b.load()["access_token"], NEW["access_token"])

    def test_refresher_forced_refresh_code_exchange_plain_lock_and_settings(self):
        leeway_refresh(self.a, self.provider, force=True)
        code_exchange(self.a, self.provider)
        plain_lock_refresh(self.a, self.provider)
        settings_save(self.a, "tenant-9")
        self.assertEqual(self.calls, [RT1, "code", NEW["refresh_token"]])
        self.assertEqual((self.b.load()["tenant_id"], self.ba._pending), ("tenant-9", {}))

    def test_other_computer_leeway_refresh_waits_and_never_calls(self):
        self.later(lambda: leeway_refresh(self.a, self.provider))
        mine = []
        seen = leeway_refresh(self.b, lambda grant: mine.append(grant) or dict(NEW))
        self.assertEqual((seen["access_token"], mine, self.calls), (NEW["access_token"], [], [RT1]))
        self.assertNotIn("refresh_token", self.b.load())
        self.assertEqual(leeway_refresh(self.b, mine.append)["access_token"], NEW["access_token"])
        self.assertEqual(mine, [])

    def test_other_computer_settings_save_and_load_only(self):
        settings_save(self.b, "tenant-7")
        self.assertEqual((self.a.load()["tenant_id"], self.a.load()["refresh_token"]), ("tenant-7", RT1))
        self.assertEqual(self.b.load()["access_token"], AT1)

    def test_other_computer_forced_refresh_and_code_exchange_never_call(self):
        with self.assertRaisesRegex(CredentialError, "this sign-in refreshes on A"):
            code_exchange(self.b, self.provider)
        self.later(lambda: leeway_refresh(self.a, lambda grant: dict(NEW)))
        with self.assertRaises(NoRefreshToken):  # waits for A, then the forced body finds no refresh token
            leeway_refresh(self.b, self.provider, force=True)
        self.assertEqual(self.calls, [])

    def test_other_computer_plain_lock_refresh_needs_the_connector_change(self):
        with self.assertRaises(NoRefreshToken):
            plain_lock_refresh(self.b, self.provider)
        self.assertEqual(self.calls, [])


class StoreOffPatterns(AgentClients):
    def test_vault_agent_without_the_store_is_unchanged(self):
        vault = PortableVault(self.root / "V.vault")
        vault.initialize(PASS)
        vault.set("xero-demo", FIELD, self.token(expires_at=EXPIRED), "json", PASS)
        agent = VaultAgent(vault.path)
        agent.unlock(PASS)
        store = self.client(None, "V", agent=agent)
        calls = []
        leeway_refresh(store, lambda grant: calls.append(grant) or dict(NEW))
        plain_lock_refresh(store, lambda grant: calls.append(grant) or dict(NEW))
        self.assertEqual(calls, [RT1, NEW["refresh_token"]])
        self.assertEqual(vault.get("xero-demo", FIELD, PASS)["access_token"], NEW["access_token"])
        self.assertEqual(store.load()["access_token"], NEW["access_token"])
        self.assertNotEqual(AT1, NEW["access_token"])


if __name__ == "__main__":
    unittest.main()
