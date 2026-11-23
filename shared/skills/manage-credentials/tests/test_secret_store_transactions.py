"""Transactions of the synced secrets store (review findings S5, S10, A3, A6, A9): one repository
lock spans the whole write, the expected parent is checked, crash windows between the clone, the
remote and the checkpoint recover or refuse plainly, unusable objects are never served, and the
recovery-package marker is signed. A bare local repository is the remote; every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import subprocess
import threading
import unittest
from unittest import mock

from test_secret_store_store import (OTHER, VALUE, StoreCase, setUpModule,  # noqa: F401
                                     tearDownModule)  # noqa: F401
from secret_store import SecretStoreError, accept, store as store_mod  # noqa: E402
from secret_store import repo as repo_mod  # noqa: E402
from secret_store.repo import repo_lock  # noqa: E402


class TransactionTests(StoreCase):
    def opened(self):
        first, _pinned = self.init()
        return first.open()

    def test_write_refuses_a_moved_head(self):
        first = self.opened()
        first.put_entry("Example API", {"api_key": VALUE})
        with self.assertRaises(getattr(repo_mod, "MovedHead", SecretStoreError)):
            first.repo.write({"objects/x.json": {}}, "update", expected_parent=None)

    def test_one_lock_spans_build_and_write(self):
        first = self.opened()
        seen, real = [], store_mod.build_put

        def spy(*args, **kwargs):
            def other():
                try:
                    with repo_lock(first.clone / ".git" / "secret-store.lock", timeout=0.3):
                        seen.append("acquired")
                except SecretStoreError:
                    seen.append("held")
            thread = threading.Thread(target=other)
            thread.start()
            thread.join()
            return real(*args, **kwargs)
        with mock.patch.object(store_mod, "build_put", spy):
            first.put_entry("Example API", {"api_key": VALUE})
        self.assertEqual(seen, ["held"])

    def test_crash_after_push_before_checkpoint_recovers(self):
        first = self.opened()
        first.put_entry("Example API", {"api_key": VALUE})
        with mock.patch.object(store_mod.SecretStore, "_save_checkpoint", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                first.put_entry("Example API", {"api_key": OTHER})
        again = self.store("a").open()
        self.assertEqual(again.get_fields("Example API", ["api_key"]), {"api_key": OTHER})

    def test_checkpoint_ahead_of_the_clone_is_refused(self):
        first = self.opened()
        first.put_entry("Example API", {"api_key": VALUE})
        subprocess.run(["git", "reset", "--quiet", "--hard", "HEAD~1"], cwd=str(first.clone), check=True)
        with mock.patch("secret_store.repo.SecretRepo._fetch", return_value=None):
            with self.assertRaises(SecretStoreError) as ctx:
                self.store("a").open()
        self.assertIn("ahead", str(ctx.exception))

    def test_unusable_object_is_never_served(self):
        first, pinned = self.init()
        first.open()
        first.put_entry("Sign-in", {"tenant": VALUE}, kind="oauth")
        with mock.patch.object(accept, "check_oauth_payload", return_value=False):
            second = self.store("b").open(pinned)
        with self.assertRaises(SecretStoreError) as ctx:
            second.get_record("Sign-in")
        self.assertIn("not usable", str(ctx.exception))
        oid = second._index()["Sign-in"]
        self.assertEqual(second._baseline(second.checkpoint, {f"objects/{oid}.json": {"kind": "oauth"}}), {})

    def test_unsigned_package_marker_never_skips_a_package(self):
        first = self.opened()
        path = first.refresh_recovery_package(force=True)
        path.with_name(path.name + ".policy").write_text(first.policy.hash, "ascii")  # the old plain marker
        with mock.patch.object(store_mod.recovery_package, "build") as build:
            first.refresh_recovery_package()
        build.assert_called_once()


if __name__ == "__main__":
    unittest.main()
