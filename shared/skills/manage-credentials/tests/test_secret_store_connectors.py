"""The skill library's production connectors against the secrets store, in both roles: xero_oauth,
ghl_oauth, google_oauth, linkedin_client and google_tray_token are imported from library/skills and
run against in-process Vault Agents serving StoreBackends. Computer A is the refresher, B another
computer of the same person (a follower, which never calls the provider). Only the provider's HTTP
answer is a stand-in. Every value is fictional."""
import contextlib
import datetime as dt
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parent.parent / "scripts"
ROOT = next(p for p in HERE.parents if (p / "CONTRACT.md").is_file())
LIBRARY = ROOT / "library" / "skills"
for folder in ("xero-access", "gohighlevel-access", "google-workspace-access", "linkedin-access"):
    sys.path.insert(0, str(LIBRARY / folder / "scripts"))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE.parent))

import google_oauth.client as google  # noqa: E402
import google_tray_token as tray  # noqa: E402
import ghl_oauth.client as ghl  # noqa: E402
import linkedin_client as linkedin  # noqa: E402
import vault_broker_client  # noqa: E402
import xero_oauth.client as xero  # noqa: E402
from portable_vault import CredentialError, PortableVault, PortableVaultJsonStore  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, PASS, RT1, AgentClients, agent_request,  # noqa: E402,F401
                                      setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

EXPIRED = 10**9
NEW_AT, NEW_RT = "fictional-access-5", "fictional-refresh-5"


def body(**extra):
    return json.dumps({"access_token": NEW_AT, "refresh_token": NEW_RT, "expires_in": 1800, **extra}).encode()


class Provider:
    """The provider's token endpoint: counts calls, answers with a new token."""

    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def request(self, *_args, **_kwargs):
        self.calls += 1
        return 200, self.answer, {}


class Connectors(AgentClients):
    def store(self, backend, computer, entry):
        path = self.root / f"{computer}.vault"
        request = agent_request(VaultAgent(path, store=backend))
        with mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True), \
                mock.patch.object(vault_broker_client, "broker_request", side_effect=request):
            return PortableVaultJsonStore(entry, FIELD, path=path)

    def pair(self, entry, record):
        self.sign_in(self.ba, entry, record)
        return self.store(self.ba, "A", entry), self.store(self.bb, "B", entry)

    def cached_follower(self, b):
        """B read the record a moment ago and keeps it for its sync interval."""
        b.load()
        self.bb.sync_seconds = 3600


class Xero(Connectors):
    def connection(self, store):
        return xero.XeroConnection(xero.XeroConfig("id-example", "fictional-secret", "http://localhost/cb"), store)

    def test_refresher_refreshes_follower_adopts_and_never_calls(self):
        a, b = self.pair("xero-demo", self.token(expires_at=EXPIRED))
        provider = Provider(body())
        with mock.patch.object(xero, "_request", side_effect=provider.request):
            self.assertEqual(self.connection(a).access_token(), NEW_AT)
            self.assertIsNone(self.ba._journal.read(self.SIGNIN))  # published, then retired
            self.assertEqual(self.connection(b).access_token(), NEW_AT)
            with self.assertRaisesRegex(CredentialError, "refreshes on A"):
                self.connection(b).exchange_code("code")
        self.assertEqual(provider.calls, 1)
        self.assertNotIn("refresh_token", b.load())

    def test_follower_forced_refresh_waits_for_the_refresher(self):
        a, b = self.pair("xero-demo", self.token(expires_at=EXPIRED))
        provider = Provider(body())
        with mock.patch.object(xero, "_request", side_effect=provider.request):
            self.later(lambda: self.connection(a).refresh(force=True))
            self.assertEqual(self.connection(b).refresh(force=True)["access_token"], NEW_AT)
        self.assertEqual(provider.calls, 1)


class HighLevel(Connectors):
    def connection(self, store):
        config = types.SimpleNamespace(client_id="id-example", client_secret="fictional-secret",
                                       redirect_uri="http://localhost/cb", oauth_version="2021-07-28")
        return ghl.HighLevelConnection(config, store)

    def test_refresher_refreshes_and_follower_adopts(self):
        record = self.token(expires_at=EXPIRED, user_type="Company", company_id="company-1")
        a, b = self.pair("gohighlevel-demo", record)
        provider = Provider(body(userType="Company", companyId="company-1"))
        with mock.patch.object(ghl, "_request", side_effect=provider.request):
            self.assertEqual(self.connection(a).refresh()["access_token"], NEW_AT)
            self.assertEqual(self.connection(b).refresh()["access_token"], NEW_AT)
        self.assertEqual((provider.calls, b.load()["company_id"]), (1, "company-1"))


class Google(Connectors):
    def connection(self, store):
        account = types.SimpleNamespace(alias="demo", email="person@example.com")
        config = types.SimpleNamespace(client_id="id-example", client_secret="fictional-secret",
                                       redirect_uri="http://localhost/cb", scopes="s", account=account)
        return google.GoogleConnection(config, store)

    def test_follower_returns_a_token_published_just_before_begin_refresh(self):
        a, b = self.pair("google-demo", self.token(expires_at=EXPIRED))
        self.cached_follower(b)
        provider = Provider(body())
        with mock.patch.object(vault_broker_client, "REFRESH_WAIT_SECONDS", 1.0), \
                mock.patch.object(google, "_request", side_effect=provider.request):
            self.connection(a).refresh()
            # before the fix B took the published token as its baseline and waited for a second
            # refresh that never came, so this raised "it has not refreshed it yet"
            self.assertEqual(self.connection(b).refresh()["access_token"], NEW_AT)
        self.assertEqual(provider.calls, 1)

    def test_tray_refresh_on_both_computers(self):
        a, b = self.pair("google-tray-demo", self.token(expires_at=EXPIRED))
        provider = Provider(body())

        def urlopen(*_args, **_kwargs):
            provider.calls += 1
            return contextlib.nullcontext(types.SimpleNamespace(read=lambda: provider.answer))

        def run(store):
            broker = lambda *_a, **_k: {"client_id": "id-example", "client_secret": "fictional-secret"}  # noqa: E731
            with mock.patch.object(tray, "_broker", return_value=broker), \
                    mock.patch.object(tray, "vault_entry_for_account", return_value="google-tray-demo"), \
                    mock.patch.object(tray, "resolve_client_entry", return_value="google-client"), \
                    mock.patch.object(tray, "get_account", return_value=None), \
                    mock.patch.object(tray, "resolve_alias", return_value="demo"), \
                    mock.patch.object(tray, "_portable_vault_token_store", return_value=store), \
                    mock.patch.object(tray.urllib.request, "urlopen", side_effect=urlopen):
                return tray.refresh_tray_access_token(account_alias="demo")
        self.later(lambda: run(a))
        self.assertEqual(run(b)["access_token"], NEW_AT)
        self.assertEqual(provider.calls, 1)


class LinkedIn(Connectors):
    def test_follower_with_an_iso_expiry_returns_the_published_token(self):
        stamp = lambda seconds: linkedin.iso(linkedin.utc_now() + dt.timedelta(seconds=seconds))  # noqa: E731
        record = {"access_token": AT1, "refresh_token": RT1, "expires_at": stamp(-60), "scopes": ["s"]}
        a, b = self.pair("linkedin-demo", record)
        self.cached_follower(b)
        calls = []

        def opener(_request, _timeout):
            calls.append(1)
            return 200, json.dumps({"access_token": NEW_AT, "expires_in": 5184000}).encode(), {}
        with mock.patch.object(vault_broker_client, "REFRESH_WAIT_SECONDS", 1.0):
            linkedin.refresh_record(a, "id-example", "fictional-secret", opener=opener)
            self.assertEqual(linkedin.refresh_record(b, "", "", opener=opener)["access_token"], NEW_AT)
        self.assertEqual(calls, [1])


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
        self.assertEqual([c for c in calls if c != "get_json"], ["begin_refresh", "set_json", "release_refresh"])


class StoreOff(AgentClients):
    def test_vault_agent_without_the_store_is_unchanged(self):
        vault = PortableVault(self.root / "V.vault")
        vault.initialize(PASS)
        vault.set("xero-demo", FIELD, self.token(expires_at=EXPIRED), "json", PASS)
        agent = VaultAgent(vault.path)
        agent.unlock(PASS)
        store = self.client(None, "V", agent=agent)
        provider = Provider(body())
        with mock.patch.object(xero, "_request", side_effect=provider.request):
            connection = xero.XeroConnection(xero.XeroConfig("id-example", "fictional-secret", "http://x/cb"), store)
            self.assertEqual(connection.access_token(), NEW_AT)
        self.assertEqual((provider.calls, vault.get("xero-demo", FIELD, PASS)["refresh_token"]), (1, NEW_RT))


if __name__ == "__main__":
    unittest.main()
