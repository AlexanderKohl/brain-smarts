"""Where the token relay finds token-relay.json, and the refusal when it finds none.

A session copy holds no vault and no relay config of its own: the shared checkout does. These
tests build that layout in a temporary folder (a session root and a main root, each with a
CONTRACT.md; the session's OWNER.md names the main root as brain_root) and check that the relay
config beside the vault in use is found, never only the one beside the script's own root, and that
a token carrying a relay version with no config found is refused a refresh. A fake Vault Agent is
a dictionary; the relay runs on its in-memory backend. No network, no subprocess, no real vault.
Every value is invented.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portable_vault  # noqa: E402
import token_relay  # noqa: E402
import token_relay_backend as trb  # noqa: E402
import vault_broker_client  # noqa: E402

ENTRY = "example-oauth"
FIELD = "oauth_token_json"
KEY_TEXT = base64.b64encode(bytes(range(32))).decode("ascii")
DATA = Path("memory") / "projects" / "credential-management" / "data"


def token(number: int, *, expires_in: float = 3600.0, version: int | None = None) -> dict:
    value = {
        "access_token": f"example-access-{number}",
        "refresh_token": f"example-refresh-{number}",
        "expires_at": time.time() + expires_in,
        "obtained_at": time.time(),
    }
    if version is not None:
        value["_relay_version"] = version
    return value


class SessionCopyLayout(unittest.TestCase):
    """session/ is the brain root the scripts run from; main/ is the shared checkout."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.session = self.folder / "session"
        self.main = self.folder / "main"
        for root in (self.session, self.main):
            (root / DATA).mkdir(parents=True)
            (root / "CONTRACT.md").write_text("example contract\n", encoding="utf-8")
        self.main_vault = self.main / DATA / "credentials.vault"
        self.backend = trb.MemoryBackend()
        self.agent: dict | None = None  # None: no Vault Agent; else the fake agent's fields
        environment = {
            name: value
            for name, value in os.environ.items()
            if name not in ("PORTABLE_VAULT_PATH", "PORTABLE_VAULT_PASSPHRASE")
        }
        for patch in (
            mock.patch.object(portable_vault, "find_brain_root", lambda start=None: self.session),
            mock.patch.object(vault_broker_client, "broker_unlocked", lambda: self.agent is not None),
            mock.patch.object(vault_broker_client, "broker_status", self.fake_status),
            mock.patch.object(vault_broker_client, "broker_request", self.fake_request),
            mock.patch.object(token_relay, "make_backend", lambda config: self.backend),
            mock.patch("subprocess.run", side_effect=AssertionError("no subprocess may run")),
            mock.patch.dict(os.environ, environment, clear=True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    # -- fakes and layout helpers --

    def fake_status(self) -> dict:
        if self.agent is None:
            raise vault_broker_client.BrokerUnavailable("no agent in this test")
        return {"unlocked": True, "vault_path": str(self.main_vault)}

    def fake_request(self, operation: str, **payload):
        if self.agent is None:
            raise vault_broker_client.BrokerUnavailable("no agent in this test")
        if operation == "status":
            return self.fake_status()
        if operation == "ping":
            return "pong"
        if operation == "get_json":
            return dict(self.agent.get(payload["entry"], {}).get(payload["field"], {}))
        if operation == "set_json":
            self.agent.setdefault(payload["entry"], {})[payload["field"]] = dict(payload["value"])
            return None
        if operation == "get_fields":
            fields = self.agent.get(payload["entry"], {})
            return {name: fields.get(name) for name in payload["fields"]}
        raise AssertionError(f"unexpected broker operation {operation}")

    def start_agent(self, value: dict) -> None:
        self.agent = {ENTRY: {FIELD: value}, "token-relay": {"relay_key": KEY_TEXT}}

    def write_owner(self, brain_root: Path) -> None:
        (self.session / "memory" / "OWNER.md").write_text(
            f"---\nowner_name: Example Owner\nbrain_root: {brain_root}\n---\n\n# Owner\n",
            encoding="utf-8",
        )

    def write_config(self, root: Path) -> Path:
        path = root / DATA / "token-relay.json"
        config = {"backend": "github", "repository": "example-owner/example-relay", "entries": [ENTRY]}
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    # -- lookup --

    def test_agent_vault_config_is_used_from_a_session_copy(self):
        main_config = self.write_config(self.main)
        self.start_agent(token(1, version=4))
        store = portable_vault.PortableVaultJsonStore(ENTRY)
        self.assertEqual(store.relay_config_path, main_config)
        self.assertEqual(store.relay_config_looked[0], main_config)
        self.assertIsInstance(store._relay, token_relay.RelayedStore)

    def test_owner_brain_root_config_is_used_without_an_agent(self):
        main_config = self.write_config(self.main)
        self.write_owner(self.main)
        found, looked = token_relay.resolve_config()
        self.assertEqual(found, main_config)
        self.assertEqual(looked, [self.session / DATA / "token-relay.json", main_config])

    def test_config_beside_the_script_root_alone_is_not_what_decides(self):
        # The incident: nothing beside the session copy's own default vault, config in main.
        self.write_config(self.main)
        self.start_agent(token(1, version=4))
        self.assertFalse((self.session / DATA / "token-relay.json").exists())
        self.assertIsNotNone(token_relay.resolve_config()[0])

    def test_a_named_vault_does_not_fall_back_to_the_owner_brain_root(self):
        self.write_config(self.main)
        self.write_owner(self.main)
        elsewhere = self.folder / "elsewhere" / "credentials.vault"
        found, looked = token_relay.resolve_config(elsewhere, use_agent=False)
        self.assertIsNone(found)
        self.assertEqual(looked, [elsewhere.parent / "token-relay.json"])

    # -- fail closed --

    def test_relay_marked_token_without_config_is_refused_and_nothing_is_sent(self):
        self.start_agent(token(1, version=4))
        store = portable_vault.PortableVaultJsonStore(ENTRY)
        self.assertIsNone(store._relay)
        self.assertIsNone(store.relay_config_path)
        for arguments in ({"refresh": True}, {"new_authorisation": True}, {"leeway_seconds": 7200}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(portable_vault.CredentialError) as caught:
                    store.rotation_lock(**arguments)
                message = str(caught.exception)
                self.assertIn("refused", message)
                self.assertIn("version 4", message)
                self.assertIn(str(self.main / DATA / "token-relay.json"), message)
                self.assertIn(str(self.session / DATA / "token-relay.json"), message)
                self.assertNotIn("example-refresh", message)
        self.assertEqual(self.agent[ENTRY][FIELD]["refresh_token"], "example-refresh-1")
        self.assertEqual(self.agent[ENTRY][FIELD]["_relay_version"], 4)
        self.assertEqual(self.backend.files, {})

    def test_relay_marked_token_still_valid_or_plain_lock_is_not_refused(self):
        self.start_agent(token(1, version=4))
        store = portable_vault.PortableVaultJsonStore(ENTRY)
        with store.rotation_lock(leeway_seconds=90):
            pass
        with store.rotation_lock():
            pass

    def test_token_never_relayed_refreshes_locally_as_before(self):
        self.start_agent(token(1))
        store = portable_vault.PortableVaultJsonStore(ENTRY)
        with store.rotation_lock(refresh=True, leeway_seconds=7200):
            store.save(token(2))
        self.assertEqual(store.load()["refresh_token"], "example-refresh-2")
        self.assertEqual(self.backend.files, {})


if __name__ == "__main__":
    unittest.main()
