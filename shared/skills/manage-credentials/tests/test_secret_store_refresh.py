"""Rotating sign-in refresh: the journal's crash and lost-acknowledgement cases, the disabled
flag, refused recovery for unverified providers, and migration from the portable vault. A bare
local repository is the remote and a fake keyring the keychain. Every value is fictional."""
import json
import subprocess
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
        seen = []

        def publish(op, answer):
            seen.append(self.journal.path(ENTRY).read_bytes())
            with self.assertRaises(SecretStoreError):
                Journal(self._tmp.name, X25519PrivateKey.generate()).read(ENTRY)
        self.journal.refresh(ENTRY, 1, self.provider, publish, lambda op, a: False, provider="xero")
        self.assertEqual(len(seen), 1)
        self.assertNotIn(b"fictional-refresh-3", seen[0])
        self.assertIsNone(self.journal.read(ENTRY))
        self.assertFalse(self.journal.path(ENTRY).exists())


class RefreshThroughStore(StoreFixture):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())
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
        operation = journal.read(self.signin.journal_key)["operation"]
        self.assertEqual(journal.read(self.signin.journal_key)["state"], "answered")
        journal.refresh(self.signin.journal_key, 1, self.provider, self.publish, self.published, provider="xero")
        self.assertEqual((self.calls, journal.read(self.signin.journal_key)), (1, None))
        obj = self.a._tree_object(self.signin.oauth_id, self.a.checkpoint)
        self.assertEqual(obj["operation"], operation)
        self.assertEqual(obj["revision"], 2)

    def test_failed_publication_is_retried_without_calling_the_provider(self):
        def refused(op, answer):
            raise SecretStoreError("push did not complete")
        with self.assertRaises(SecretStoreError):
            self.ba._journal.refresh(self.signin.journal_key, 1, self.provider, refused, self.published, provider="xero")
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["refresh_token"], "fictional-refresh-3")
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], "fictional-access-3")
        self.assertEqual(self.calls, 1)



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

    def test_grant_fields_without_a_signin_go_to_a_grant(self):
        self.vault.set_fields("agency", {FIELD: ({}, "json"), "client_secret": (SECRET, "text"),
                                         "api_key": (KEY, "text")}, PASS)
        self.assertEqual(self.migrate()[0], 0)
        self.assertEqual(self.a.get_record("agency"), {"api_key": KEY})
        self.assertEqual(self.ba.get_fields("agency", ["client_secret", "api_key"]),
                         {"client_secret": SECRET, "api_key": KEY})
        with self.assertRaisesRegex(SecretStoreError, "refreshes on A"):
            self.bb.get_fields("agency", ["client_secret"])

    def test_real_run_backs_up_copies_and_refuses_a_second_copy(self):
        before = self.vault.path.read_bytes()
        code, _text = self.migrate()
        self.assertEqual(code, 0)
        self.assertNotEqual(self.vault.path.read_bytes(), before)  # its sign-in tokens are scrubbed (round 8)
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


class StoreGaps(StoreFixture):
    """store.py: a computer enrolled after a sign-in exists verifies the commit that re-keys it,
    and a write whose push acknowledgement is lost is accepted only when the remote has it."""

    def test_computer_enrolled_after_a_signin_verifies_the_rekey(self):
        from secret_store import keys
        from secret_store.broker_backend import StoreBackend
        from secret_store.policy import public_entry
        from secret_store.store_ops import build_policy_change
        self.sign_in(self.ba, "xero-demo", self.token())
        x, e = keys.generate_key_pairs()
        keys.store_private_keys("alec", "C", x, e)
        a = self.a

        def change(doc):
            doc["people"]["alec"]["computers"]["C"] = public_entry(x.public_key(), e.public_key())
        a._write(lambda: (build_policy_change(a.policy, a.checkpoint.objects, change, a._identity().ed25519,
                                              lambda oid: a._open_object(a._tree_object(oid, a.checkpoint))),
                          "policy"))
        theirs = StoreBackend(self.make_store("C").open(a._load_pin()), sync_seconds=0).get_json("xero-demo", FIELD)
        self.assertEqual(theirs["access_token"], AT1)
        self.assertNotIn("refresh_token", theirs)

    def _push_fails(self, lands):
        real = self.a.repo._git

        def git(*args, **kwargs):
            if args and args[0] == "push":
                if lands:
                    real(*args, **kwargs)
                return subprocess.CompletedProcess(args, 1, b"", b"connection reset")
            return real(*args, **kwargs)
        return mock.patch.object(self.a.repo, "_git", side_effect=git)

    def test_lost_push_acknowledgement_is_accepted_when_the_remote_has_the_commit(self):
        with self._push_fails(lands=True):
            self.a.put_entry("plain", {"api_key": KEY})
        self.assertEqual(self.a.get_fields("plain", ["api_key"]), {"api_key": KEY})
        self.a.put_entry("plain", {"api_key": "fictional-key-2"})
        self.assertEqual(self.b.open().get_fields("plain", ["api_key"]), {"api_key": "fictional-key-2"})

    def test_failed_push_leaves_no_local_commit_ahead_of_the_checkpoint(self):
        before = self.a.repo.head()
        with self._push_fails(lands=False), self.assertRaisesRegex(SecretStoreError, "push did not complete"):
            self.a.put_entry("plain", {"api_key": KEY})
        self.assertEqual(self.a.repo.head(), before)
        self.a.put_entry("plain", {"api_key": KEY})
        self.assertEqual(self.b.open().get_fields("plain", ["api_key"]), {"api_key": KEY})


if __name__ == "__main__":
    unittest.main()
