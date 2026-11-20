"""The skill library's connectors against the secrets store, in both roles, without importing the
library: each function below reproduces one call sequence of the adapted connectors in
library/skills (xero-access, gohighlevel-access, google-workspace-access, linkedin-access,
meta-access): on another computer, which holds no refresh token, a refresh adopts the access token
the refresher published. Computer A is the refresher, B another computer of the same person. Every
value is fictional."""
import contextlib
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


def adopt(current, leeway):
    """Another computer holds no refresh token: it adopts the access token the refresher published
    (the store waited for it), or stops with the connector's own error."""
    if current.get("access_token") and float(current.get("expires_at", 0)) > time.time() + leeway:
        return current
    raise NoRefreshToken()


def leeway_refresh(store, provider, force=False, leeway=90):
    """xero_oauth and ghl_oauth Client.refresh (access_token() calls it with the leeway)."""
    with store.rotation_lock(refresh=force, leeway_seconds=leeway):
        current = store.load()
        if not force and float(current.get("expires_at", 0)) > time.time() + leeway:
            return current
        if not current.get("refresh_token"):
            return adopt(current, leeway)
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


def adapted_refresh(store, provider):
    """google_oauth Client.refresh and linkedin_client refresh after the adaptation: a begun refresh."""
    with store.rotation_lock(refresh=True):
        current = store.load()
        if not current.get("refresh_token"):
            return adopt(current, 60)
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
        self.sign_in(self.ba, "xero-demo", self.token(expires_at=EXPIRED))
        self.a, self.b = self.client(self.ba, "A"), self.client(self.bb, "B")
        self.calls = []

    def provider(self, grant):
        self.calls.append(grant)
        return dict(NEW)

    def test_refresher_leeway_refresh_goes_through_the_journal(self):
        leeway_refresh(self.a, self.provider)
        self.assertIsNone(self.ba._journal.read(self.SIGNIN))  # published, then retired
        self.assertEqual(leeway_refresh(self.a, self.provider)["access_token"], NEW["access_token"])
        self.assertEqual(self.calls, [RT1])
        self.assertEqual(self.b.load()["access_token"], NEW["access_token"])

    def test_refresher_forced_refresh_code_exchange_plain_lock_and_settings(self):
        leeway_refresh(self.a, self.provider, force=True)
        code_exchange(self.a, self.provider)
        with self.assertRaisesRegex(CredentialError, "only inside a begun refresh"):
            plain_lock_refresh(self.a, lambda grant: self.calls.append(grant) or {**NEW, "access_token": "fictional-6"})
        # the provider was called but its token change was refused: the connector must pass refresh or leeway
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
        seen = leeway_refresh(self.b, self.provider, force=True)  # waits for A, then adopts A's newer token
        self.assertEqual((seen["access_token"], self.calls), (NEW["access_token"], []))

    def test_other_computer_adapted_refresh_adopts_the_refresher_token(self):
        self.later(lambda: leeway_refresh(self.a, lambda grant: dict(NEW)))
        seen = adapted_refresh(self.b, self.provider)
        self.assertEqual((seen["access_token"], self.calls), (NEW["access_token"], []))


class SaveConfirmation(unittest.TestCase):
    def test_failed_save_releases_the_refresh_and_keeps_the_record(self):
        from portable_vault import BrokerOAuthStore
        from vault_broker_client import store_refresh
        store = object.__new__(BrokerOAuthStore)
        store.entry, store.field, store._operation, store._saved = "xero-demo", FIELD, None, False
        calls = []

        def broker(name, **_payload):
            calls.append(name)
            if name == "begin_refresh":
                return {"operation": "op-1"}
            if name == "set_json":
                raise CredentialError("the broker refused the save")
            return {}
        store._broker_request = broker
        with self.assertRaisesRegex(CredentialError, "refused the save"):
            with store_refresh(store, contextlib.nullcontext, refresh=True):
                store.save({"access_token": "fictional-7"})
        self.assertFalse(store._saved)
        self.assertEqual(calls, ["begin_refresh", "set_json", "release_refresh"])  # never abort: the record stays


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
