"""Rotating sign-in refresh: the journal's crash and lost-acknowledgement cases, the disabled
flag, refused recovery for unverified providers, and migration from the portable vault. A bare
local repository is the remote and a fake keyring the keychain. Every value is fictional."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import migrate_to_store  # noqa: E402
from portable_vault import PortableVault  # noqa: E402
from secret_store import SecretStoreError, oauth_ops  # noqa: E402
from secret_store.journal import Journal, ProviderNotCalled  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, KEY, PASS, RT1, SECRET, StoreFixture,  # noqa: E402,F401
                                      agent_request, setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

ENTRY = "xero-demo#oauth_token_json"
NEW = {"access_token": "fictional-access-3", "refresh_token": "fictional-refresh-3", "expires_at": (19 * 10**8 + 3600)}


class JournalAlone(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.key = X25519PrivateKey.generate()
        self.journal = Journal(self._tmp.name, self.key)
        self.calls = 0
        self.published = []

    def provider(self):
        self.calls += 1
        return dict(NEW)

    def refresh(self, call=None):
        return self.journal.refresh(ENTRY, 1, call or self.provider, lambda op, a: self.published.append(op),
                                    lambda op, a: False, provider="xero")

    def test_crash_during_call_leaves_entry_uncertain_and_blocked(self):
        def crashing():
            self.provider()
            raise RuntimeError("process ended")
        with self.assertRaises(RuntimeError):
            self.refresh(crashing)
        with self.assertRaisesRegex(SecretStoreError, "uncertain") as caught:
            self.refresh()
        self.assertIn("Xero has no verified provider profile", str(caught.exception))
        self.assertEqual((self.calls, self.journal.read(ENTRY)["state"]), (1, "calling"))
        with self.assertRaisesRegex(SecretStoreError, "no verified provider profile"):
            self.journal.resolve_uncertain(ENTRY, "xero")

    def test_crash_between_answer_and_journal_write_is_uncertain(self):
        original = self.journal.write

        def failing(entry, record):
            if record["state"] == "answered":
                raise OSError("power lost")
            original(entry, record)
        with mock.patch.object(self.journal, "write", side_effect=failing), self.assertRaises(OSError):
            self.refresh()
        with self.assertRaisesRegex(SecretStoreError, "uncertain"):
            Journal(self._tmp.name, self.key).refresh(ENTRY, 1, self.provider, lambda *a: None, lambda *a: False)
        self.assertEqual(self.calls, 1)

    def test_provider_not_called_leaves_no_record(self):
        def offline():
            raise ProviderNotCalled()
        with self.assertRaises(ProviderNotCalled):
            self.refresh(offline)
        self.assertIsNone(self.journal.read(ENTRY))
        self.assertEqual(self.refresh(), NEW)

    def test_disabled_flag_is_persisted_and_honoured(self):
        self.journal.set_disabled(ENTRY)
        with self.assertRaisesRegex(SecretStoreError, "switched off"):
            Journal(self._tmp.name, self.key).refresh(ENTRY, 1, self.provider, lambda *a: None, lambda *a: False)
        self.assertEqual(self.calls, 0)

    def test_journal_is_encrypted_and_retired_after_publication(self):
        self.refresh()
        self.assertEqual(self.journal.read(ENTRY)["state"], "published")
        self.assertEqual(len(self.published), 1)
        raw = self.journal.path(ENTRY).read_bytes()
        self.assertNotIn(b"fictional-refresh-3", raw)
        with self.assertRaises(SecretStoreError):
            Journal(self._tmp.name, X25519PrivateKey.generate()).read(ENTRY)


class RefreshThroughStore(StoreFixture):
    def setUp(self):
        super().setUp()
        self.ba.set_json("xero-demo", FIELD, self.token())
        self.signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        self.calls = 0

    def provider(self):
        self.calls += 1
        return dict(NEW)

    def publish(self, op, answer):
        oauth_ops.publish(self.a, self.signin, answer, op)

    def published(self, op, answer):
        return oauth_ops.is_published(self.a, self.signin, op, answer)

    def test_lost_push_acknowledgement_reconciled_by_publication_only(self):
        journal = self.ba._journal

        def lost(op, answer):
            self.publish(op, answer)
            raise SecretStoreError("push acknowledgement lost")
        with self.assertRaisesRegex(SecretStoreError, "acknowledgement lost"):
            journal.refresh(self.signin.journal_key, 1, self.provider, lost, self.published, provider="xero")
        self.assertEqual(journal.read(self.signin.journal_key)["state"], "answered")
        journal.refresh(self.signin.journal_key, 1, self.provider, self.publish, self.published, provider="xero")
        record = journal.read(self.signin.journal_key)
        self.assertEqual((self.calls, record["state"]), (1, "published"))
        obj = self.a._tree_object(self.signin.oauth_id, self.a.checkpoint)
        self.assertEqual(obj["operation"], record["operation"])
        self.assertEqual(obj["revision"], 2)

    def test_failed_publication_is_retried_without_calling_the_provider(self):
        def refused(op, answer):
            raise SecretStoreError("push did not complete")
        with self.assertRaises(SecretStoreError):
            self.ba._journal.refresh(self.signin.journal_key, 1, self.provider, refused, self.published, provider="xero")
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], "fictional-refresh-3")
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], "fictional-access-3")
        self.assertEqual(self.calls, 1)

    def test_uncertain_entry_refuses_broker_refresh_but_still_reads(self):
        def crashing():
            self.provider()
            raise RuntimeError("process ended")
        with self.assertRaises(RuntimeError):
            self.ba._journal.refresh(self.signin.journal_key, 1, crashing, self.publish, self.published, provider="xero")
        with self.assertRaisesRegex(SecretStoreError, "uncertain"):
            self.ba.set_json("xero-demo", FIELD, self.token(access_token="fictional-access-9"))
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["access_token"], AT1)


class Migration(StoreFixture):
    def setUp(self):
        super().setUp()
        self.vault = PortableVault(self.root / "vault" / "credentials.vault")
        self.vault.initialize(PASS)
        self.vault.set_fields("xero-demo", {FIELD: (self.token(), "json"), "client_id": ("fictional-id", "text"),
                                            "client_secret": (SECRET, "text")}, PASS)
        self.vault.set("plain", "api_key", KEY, "text", PASS)
        agent = VaultAgent(self.vault.path)
        agent.unlock(PASS)
        self.request = agent_request(agent)

    def migrate(self, **options):
        lines = []
        code = migrate_to_store.migrate(self.request, lambda: self.a, out=lines.append, **options)
        text = "\n".join(lines)
        for value in (SECRET, KEY, RT1, AT1, "fictional-id"):
            self.assertNotIn(value, text)
        return code, text

    def test_dry_run_lists_names_only(self):
        code, text = self.migrate(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("xero-demo: client_id (text), client_secret (text), oauth_token_json (json)", text)
        self.assertEqual(self.a.list_entries(), [])
        self.assertFalse((self.vault.path.parent / "migration-backups").exists())

    def test_real_run_backs_up_copies_and_refuses_a_second_copy(self):
        before = self.vault.path.read_bytes()
        code, _text = self.migrate()
        self.assertEqual(code, 0)
        self.assertEqual(self.vault.path.read_bytes(), before)
        backups = self.vault.path.parent / "migration-backups"
        (copy,) = backups.glob("*.vault")
        self.assertEqual(copy.read_bytes(), before)
        (record,) = backups.glob("*.migration.json")
        data = json.loads(record.read_text("utf-8"))
        self.assertEqual((data["entries"], data["backup"]), (["plain", "xero-demo"], str(copy)))
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], RT1)
        self.assertEqual(self.ba.get_fields("xero-demo", ["client_secret", "client_id"]),
                         {"client_secret": SECRET, "client_id": "fictional-id"})
        self.assertEqual(self.bb.get_fields("plain", ["api_key"]), {"api_key": KEY})
        self.assertNotIn("refresh_token", self.bb.get_json("xero-demo", FIELD))
        code, text = self.migrate()
        self.assertEqual(code, 3)
        self.assertIn("--replace", text)
        self.assertEqual(self.migrate(replace=True)[0], 0)


if __name__ == "__main__":
    unittest.main()
