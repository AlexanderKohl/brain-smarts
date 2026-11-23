"""The refresh path through PortableVaultJsonStore.rotation_lock and the real broker functions:
uncertain after an exception, removal only when the provider was not called, the plain lock,
reading before calling, publication reconciliation, grant fields whatever the entry name, the
group of a revision, team routing, clear and sync, bounded locks and durable journal writes. A
bare local repository is the remote and a fake keyring the keychain. Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portable_vault  # noqa: E402
from portable_vault import CredentialError  # noqa: E402
from secret_store import SecretStoreError, oauth_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.journal import Journal, ProviderNotCalled  # noqa: E402
from test_secret_store_broker import (AT1, FIELD, KEY, RT1, SECRET, AgentClients, StoreFixture,  # noqa: E402,F401
                                      agent_request, setUpModule, tearDownModule)
from vault_agent import VaultAgent  # noqa: E402

NEW = {"access_token": "fictional-access-8", "refresh_token": "fictional-refresh-8",
       "expires_at": 19 * 10**8 + 3600, "token_type": "Bearer"}


class Locks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_journal_lock_times_out_in_plain_words(self):
        journal = Journal(self.root, X25519PrivateKey.generate())
        journal.lock_timeout = 0.3
        with ExitStack() as held:
            held.enter_context(journal.lock("e#f"))
            with self.assertRaisesRegex(SecretStoreError, "try again shortly"):
                with journal.lock("e#f"):
                    pass

    def test_vault_file_lock_times_out_in_plain_words(self):
        path = self.root / "x.lock"
        with portable_vault._file_lock(path), mock.patch.object(portable_vault, "LOCK_TIMEOUT_SECONDS", 0.3):
            with self.assertRaisesRegex(CredentialError, "Try again shortly"):
                with portable_vault._file_lock(path):
                    pass

    def test_journal_write_is_durable(self):
        from secret_store import fileio
        target = self.root / "j" / "a.journal"
        with mock.patch.object(fileio.os, "fsync", wraps=os.fsync) as fsync, \
                mock.patch.object(fileio, "_replace_write_through", wraps=fileio._replace_write_through) as through:
            fileio.write_durable(target, b"one")
            fileio.write_durable(target, b"two")
        self.assertEqual(target.read_bytes(), b"two")
        self.assertFalse(target.with_name("a.journal.tmp").exists())
        if os.name == "nt":
            self.assertEqual((fsync.call_count, through.call_count), (2, 2))
        else:
            self.assertEqual((fsync.call_count, through.call_count), (4, 0))  # the file, then its folder


class RefreshPath(AgentClients):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())
        self.journal = self.ba._journal
        self.a = self.client(self.ba, "A")

    def test_exception_after_begin_leaves_uncertain_and_releases(self):
        with self.assertRaises(TimeoutError), self.a.rotation_lock(refresh=True):
            raise TimeoutError("the answer was lost")
        self.assertEqual((self.journal.read(self.SIGNIN)["state"], self.ba._pending), ("calling", {}))
        with self.assertRaisesRegex(CredentialError, "uncertain.*sign in again in the browser"):
            with self.a.rotation_lock(refresh=True):
                self.fail("the block must not run")
        self.assertEqual(self.ba.get_json("xero-demo", FIELD)["access_token"], AT1)
        with self.assertRaisesRegex(SecretStoreError, "no verified provider profile"):
            self.journal.resolve_uncertain(self.SIGNIN, "xero")

    def test_lost_journal_answer_is_uncertain(self):
        original = self.journal.write

        def failing(entry, record):
            if record["state"] == "answered":
                raise OSError("power lost")
            original(entry, record)
        with mock.patch.object(self.journal, "write", side_effect=failing), self.assertRaises(OSError):
            with self.a.rotation_lock(leeway_seconds=10**12):
                self.a.save({**self.a.load(), **NEW})
        self.assertEqual(self.journal.read(self.SIGNIN)["state"], "calling")

    def test_provider_not_called_or_fresh_token_removes_the_record(self):
        with self.assertRaises(ProviderNotCalled), self.a.rotation_lock(refresh=True):
            raise ProviderNotCalled()
        self.assertIsNone(self.journal.read(self.SIGNIN))
        with self.a.rotation_lock(leeway_seconds=60):  # the token is fresh: nothing is begun
            self.assertIsNone(self.journal.read(self.SIGNIN))
        self.assertEqual((self.journal.read(self.SIGNIN), self.ba._pending), (None, {}))

    def test_refresh_on_the_refresher_publishes_and_retires_the_record(self):
        with self.a.rotation_lock(refresh=True):
            self.assertEqual(self.journal.read(self.SIGNIN)["state"], "calling")
            self.a.save({**self.a.load(), **NEW})
        self.assertIsNone(self.journal.read(self.SIGNIN))
        self.assertFalse(self.journal.path(self.SIGNIN).exists())
        self.assertEqual(self.bb.get_json("xero-demo", FIELD)["access_token"], NEW["access_token"])

    def test_begin_refresh_reads_before_writing_calling(self):
        request = agent_request(VaultAgent(self.root / "A2.vault", store=self.ba))
        with mock.patch.object(oauth_ops, "read", side_effect=SecretStoreError("unreadable")), \
                self.assertRaisesRegex(CredentialError, "unreadable"):
            request("begin_refresh", entry="xero-demo", field=FIELD)
        self.assertEqual((self.journal.read(self.SIGNIN), self.ba._pending), (None, {}))
        begun = request("begin_refresh", entry="xero-demo", field=FIELD)
        self.assertEqual(request("abort_refresh", entry="xero-demo", field=FIELD, operation=begun["operation"]),
                         {"aborted": True})

    def test_is_published_needs_operation_writer_and_the_whole_answer(self):
        signin = oauth_ops.find(self.ba.store, "xero-demo", FIELD)
        answer = {"access_token": AT1, "refresh_token": "fictional-refresh-new"}
        self.assertFalse(oauth_ops.is_published(self.ba.store, signin, "op-one", answer))
        oauth_ops.publish(self.ba.store, signin, answer, "op-one")
        self.assertTrue(oauth_ops.is_published(self.ba.store, signin, "op-one", answer))
        self.assertFalse(oauth_ops.is_published(self.ba.store, signin, "op-one", {**answer, "refresh_token": "x"}))
        self.assertFalse(oauth_ops.is_published(self.ba.store, signin, "op-two", answer))

    def test_reconcile_tolerates_an_unreachable_remote_and_honours_disabled(self):
        pending = {"operation": "op-pending", "entry": self.SIGNIN, "revision": 1, "state": "answered",
                   "answer": dict(NEW)}
        self.journal.write(self.SIGNIN, pending)
        st = self.ba.store
        with mock.patch.object(st, "_sync", side_effect=SecretStoreError("remote unreachable")), \
                mock.patch.object(st, "_write", side_effect=SecretStoreError("remote unreachable")):
            self.assertEqual(self.ba.get_json("xero-demo", FIELD)["access_token"], AT1)
        self.assertEqual(self.journal.read(self.SIGNIN)["state"], "answered")
        for disable in (lambda: mock.patch.object(self.ba, "_policy_disabled", return_value=True),
                        lambda: mock.patch.object(self.journal, "disabled", return_value=True)):
            with disable(), mock.patch.object(oauth_ops, "publish") as publish:
                self.ba.get_json("xero-demo", FIELD)
            publish.assert_not_called()
        self.ba.get_json("xero-demo", FIELD)
        self.assertIsNone(self.journal.read(self.SIGNIN))


class GrantFields(StoreFixture):
    NAME = "Agency account"

    def test_signin_promotes_a_static_placeholder_and_its_client_secret(self):
        self.a.put_entry(self.NAME, {FIELD: "{}", "api_key": KEY})
        self.ba.set_text(self.NAME, "client_secret", SECRET)  # a grant field goes to the grant at once
        self.sign_in(self.ba, self.NAME, {"accessToken": AT1, "refreshToken": RT1, "id_token": "fictional-id"})
        self.assertEqual(self.a.get_record(self.NAME), {"api_key": KEY})
        self.assertEqual(self.ba.get_json(self.NAME, FIELD)["refreshToken"], RT1)
        self.assertEqual(self.ba.get_fields(self.NAME, ["client_secret"]), {"client_secret": SECRET})
        theirs = self.bb.get_json(self.NAME, FIELD)
        self.assertEqual((theirs["accessToken"], "refreshToken" in theirs, "id_token" in theirs), (AT1, False, False))
        with self.assertRaisesRegex(SecretStoreError, "refreshes on A"):
            self.bb.get_fields(self.NAME, ["client_secret"])

    def test_grant_field_is_never_served_from_a_static_object(self):
        with self.assertRaisesRegex(SecretStoreError, "grant field"):
            self.a.put_entry("legacy", {"refreshToken": RT1, "api_key": KEY})
        self.a.put_entry("legacy", {"api_key": KEY})
        self.assertEqual(self.bb.get_fields("legacy", ["api_key"]), {"api_key": KEY})

    def test_grant_text_before_any_signin_creates_the_grant(self):
        self.ba.set_text(self.NAME, "clientSecret", SECRET)
        self.assertNotIn(self.NAME, self.a._index())
        self.sign_in(self.ba, self.NAME, {"access_token": AT1, "refresh_token": RT1})
        self.assertEqual(self.ba.get_fields(self.NAME, ["clientSecret"]), {"clientSecret": SECRET})
        self.assertEqual(self.ba.get_json(self.NAME, FIELD)["refresh_token"], RT1)
        with self.assertRaisesRegex(SecretStoreError, "refreshes on A"):
            self.bb.get_fields(self.NAME, ["clientSecret"])

    def test_provider_is_recorded_in_the_shared_settings(self):
        self.sign_in(self.ba, "xero-demo", self.token())
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        self.assertEqual((signin.provider, oauth_ops.read_shared(self.a, signin)[oauth_ops.PROVIDER_KEY]),
                         ("xero", "xero"))


class Groups(StoreFixture):
    def test_a_revision_takes_its_group_from_the_assignment(self):
        self.sign_in(self.ba, "xero-demo", self.token())
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        readers = self.a.policy.readers_for(signin.oauth_id)
        with mock.patch.object(self.a.policy, "assignment", return_value=("ops", "oauth")),                 mock.patch.object(self.a.policy, "readers_for", return_value=readers):
            obj = oauth_ops.seal_revision(self.a.policy, signin.oauth_id, "oauth", {}, self.a._identity().ed25519, None)
        self.assertEqual(obj["group"], "ops")

    def test_journal_key_holds_repository_and_grant(self):
        import dataclasses
        self.sign_in(self.ba, "xero-demo", self.token())
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)
        self.assertIn(self.a.policy.repository, signin.journal_key)
        self.assertIn(signin.grant_id, signin.journal_key)
        other = dataclasses.replace(signin, repository="another-repository", grant_id="another-grant")
        self.ba._ready()
        self.ba._journal.set_disabled(other.journal_key)
        self.assertNotEqual(other.journal_key, signin.journal_key)
        self.assertFalse(self.ba._journal.disabled(signin.journal_key))
        with self.assertRaisesRegex(SecretStoreError, "^refreshing xero-demo#oauth_token_json is switched off"):
            self.ba._journal.check(other.journal_key)

    def test_a_later_store_does_not_clear_an_earlier_sync_error(self):
        other = self.second_store()
        backend = StoreBackend(self.a, sync_seconds=0, team=other)
        backend._ready()
        with mock.patch.object(self.a, "_sync", side_effect=SecretStoreError("personal remote unreachable")):
            backend._pull_all(tolerate=True)
        self.assertIn("personal remote unreachable", backend.status()["store_sync"])

    def second_store(self):
        bare = self.root / "other.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(bare)],
                       check=True, capture_output=True)
        base = self.root / "C"
        other = type(self.a)(use_config_file=False, enabled=True, person="alec", computer="C",
                             personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                             recovery_package_dir=base / "packages", personal_repo_url=str(bare))
        other.init_personal(words_callback=lambda words: True)
        return other

    def test_backend_routes_by_index_and_refuses_an_ambiguous_name(self):
        bare = self.root / "other.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(bare)],
                       check=True, capture_output=True)
        base = self.root / "C"
        other = type(self.a)(use_config_file=False, enabled=True, person="alec", computer="C",
                             personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                             recovery_package_dir=base / "packages", personal_repo_url=str(bare))
        other.init_personal(words_callback=lambda words: True)
        other.put_entry("elsewhere", {"api_key": KEY})
        other.put_entry("both", {"api_key": KEY})
        self.a.put_entry("both", {"api_key": KEY})
        backend = StoreBackend(self.a, sync_seconds=0, team=other)
        self.assertEqual(backend.get_fields("elsewhere", ["api_key"]), {"api_key": KEY})
        with self.assertRaisesRegex(SecretStoreError, "ambiguous"):
            backend.get_fields("both", ["api_key"])


class ClearAndSync(AgentClients):
    def setUp(self):
        super().setUp()
        self.sign_in(self.ba, "xero-demo", self.token())

    def test_clear_removes_the_tokens_on_the_refresher_only(self):
        with self.assertRaisesRegex(CredentialError, "refreshes on A"):
            self.client(self.bb, "B").clear()
        self.client(self.ba, "A").clear()
        mine = self.ba.get_json("xero-demo", FIELD)
        self.assertEqual(("access_token" in mine, "refresh_token" in mine, mine["tenant_id"]), (False, False, "tenant-1"))

    def test_sync_pulls_the_store(self):
        slow = StoreBackend(self.b, sync_seconds=3600)
        b = self.client(slow, "B2")
        self.assertEqual(b.load()["tenant_id"], "tenant-1")
        self.sign_in(self.ba, "xero-demo", self.token(tenant_id="tenant-5"))
        self.assertEqual(b.load()["tenant_id"], "tenant-1")
        b.sync()
        self.assertEqual(b.load()["tenant_id"], "tenant-5")


if __name__ == "__main__":
    unittest.main()
