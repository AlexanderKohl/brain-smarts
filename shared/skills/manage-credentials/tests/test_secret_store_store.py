"""Personal secrets store: init, put, get, list, delete, a second clone, tamper refusal, recovery
and the command line. A bare local repository is the remote; a fake keyring and a fake words
callback stand in for the keychain and the window. No network, no real keychain, no real memory
configuration. Every key and value here is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import base64
import contextlib
import importlib.util
import io
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

from secret_store import SecretStoreError, keys, recovery  # noqa: E402
from secret_store.repo import RefusedCommit  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402

VALUE = "fictional-value-7Q2xZ-not-a-secret"
OTHER = "fictional-other-K9pL-not-a-secret"
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
    """In-memory stand-in for the keychain, allowlisted for these tests only."""

    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, password):
        self.items[(service, user)] = password


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        git("init", "--quiet", "--bare", "--initial-branch=main", str(self.bare), cwd=self.root)
        git("config", "receive.denyNonFastForwards", "true", cwd=self.bare)
        fake = FakeKeyring()
        name = f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"
        for patcher in (mock.patch.object(keyring, "get_keyring", return_value=fake),
                        mock.patch.object(keys, "ALLOWED_BACKENDS", frozenset({name}))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.out, self.err = io.StringIO(), io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(self.out))
        stack.enter_context(contextlib.redirect_stderr(self.err))
        self.addCleanup(stack.close)
        self.words = []

    def tearDown(self):
        captured = self.out.getvalue() + self.err.getvalue()
        for secret in (VALUE, OTHER, " ".join(self.words)):
            if secret:
                self.assertNotIn(secret, captured)

    def store(self, name, **extra):
        return SecretStore(use_config_file=False, enabled=True, person="tester", computer="laptop",
                           personal_clone=self.root / name / "clone", checkpoint_dir=self.root / name / "state",
                           recovery_package_dir=self.root / name / "packages",
                           personal_repo_url=str(self.bare), **extra)

    def _words(self, words):
        self.words = list(words)
        return True

    def init(self):
        first = self.store("a")
        pinned = first.init_personal(remote_url=str(self.bare), words_callback=self._words)
        return first, pinned


class PersonalStoreTests(StoreCase):
    def test_store_off_without_configuration(self):
        off = SecretStore(use_config_file=False)
        self.assertIn("off", off.status())
        with self.assertRaises(SecretStoreError):
            off.open()

    def test_init_refused_when_words_not_confirmed(self):
        with self.assertRaises(SecretStoreError):
            self.store("a").init_personal(remote_url=str(self.bare), words_callback=lambda words: False)
        self.assertFalse((self.root / "a" / "clone").exists())

    def test_init_put_get_list_delete(self):
        first, _pinned = self.init()
        self.assertEqual(len(self.words), 24)
        first.open()
        self.assertEqual(first.list_entries(), [])
        first.put_entry("Example API", {"api_key": VALUE})
        self.assertEqual(first.get_fields("Example API", ["api_key"]), {"api_key": VALUE})
        first.put_entry("Example API", {"client_id": OTHER})
        self.assertEqual(first.get_record("Example API"), {"api_key": VALUE, "client_id": OTHER})
        self.assertEqual(first.list_entries(), ["Example API"])
        with self.assertRaises(SecretStoreError):
            first.get_fields("Example API", ["missing_field"])
        first.delete_entry("Example API")
        self.assertEqual(first.list_entries(), [])
        with self.assertRaises(SecretStoreError):
            first.get_record("Example API")
        reopened = self.store("a").open()
        self.assertEqual(reopened.list_entries(), [])
        reopened.put_entry("Example API", {"api_key": OTHER})  # a new id; the old one stays retired
        self.assertEqual(reopened.get_fields("Example API", ["api_key"]), {"api_key": OTHER})
        self.assertIn("Up to date", reopened.status())

    def test_second_clone_sees_changes(self):
        first, pinned = self.init()
        first.open().put_entry("Example API", {"api_key": VALUE})
        with self.assertRaises(SecretStoreError):
            self.store("c").open()  # no pinned trust root fingerprint
        second = self.store("b").open(pinned)
        self.assertEqual(second.get_fields("Example API", ["api_key"]), {"api_key": VALUE})
        second.put_entry("Second", {"token": OTHER})
        first.open()
        self.assertEqual(first.list_entries(), ["Example API", "Second"])
        self.assertEqual(first.get_fields("Second", ["token"]), {"token": OTHER})
        first.delete_entry("Second")
        self.assertEqual(self.store("b").open().list_entries(), ["Example API"])

    def test_tampered_commit_is_refused_and_the_store_stops(self):
        first, pinned = self.init()
        first.open().put_entry("Example API", {"api_key": VALUE})
        attacker = self.root / "attacker"
        git("clone", "--quiet", str(self.bare), str(attacker), cwd=self.root)
        target = next(p for p in (attacker / "objects").glob("*.json") if not p.name.startswith("index-"))
        obj = json.loads(target.read_text("utf-8"))
        obj["ciphertext"] = base64.b64encode(b"x" * 48).decode("ascii")
        target.write_text(json.dumps(obj), "utf-8")
        git("commit", "--quiet", "-am", "update", cwd=attacker)
        git("push", "--quiet", "origin", "main", cwd=attacker)
        with self.assertRaises(RefusedCommit):
            self.store("b").open(pinned)
        with self.assertRaises(SecretStoreError):
            first.put_entry("Another", {"api_key": OTHER})
        self.assertIn("Refused", first.status())
        with self.assertRaises(SecretStoreError):
            self.store("a").open()

    def test_recovery_package_restores_with_words_alone(self):
        first, _pinned = self.init()
        first.open().put_entry("Example API", {"api_key": VALUE})
        package = first.refresh_recovery_package()
        self.assertTrue(package.exists())
        restored = SecretStore.restore_from_package(" ".join(self.words), package, self.root / "fresh")
        self.assertEqual(restored.list_entries(), ["Example API"])
        self.assertEqual(restored.get_fields("Example API", ["api_key"]), {"api_key": VALUE})
        with self.assertRaises(SecretStoreError):
            SecretStore.restore_from_package(recovery.generate_mnemonic(), package, self.root / "wrong")

    def test_command_line_names_fields_only(self):
        self.init()
        spec = importlib.util.spec_from_file_location("secrets_cli", SCRIPTS / "brain_secrets.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        factory = lambda: self.store("a")  # noqa: E731
        ask = lambda title, fields: ({"password": VALUE}, None)  # noqa: E731
        self.assertEqual(cli.main(["put", "--entry", "CLI Entry", "--secret", "password", "--empty-json",
                                   "settings"], store_factory=factory, ask=ask), 0)
        self.assertEqual(cli.main(["get-check", "--entry", "CLI Entry"], store_factory=factory), 0)
        self.assertEqual(cli.main(["list"], store_factory=factory), 0)
        self.assertEqual(self.store("a").open().get_record("CLI Entry"), {"password": VALUE, "settings": "{}"})
        self.assertEqual(cli.main(["delete", "--entry", "CLI Entry"], store_factory=factory,
                                  confirm=lambda prompt: "wrong"), 1)
        self.assertEqual(cli.main(["delete", "--entry", "CLI Entry"], store_factory=factory,
                                  confirm=lambda prompt: "CLI Entry"), 0)
        self.assertEqual(cli.main(["status"], store_factory=factory), 0)
        self.assertEqual(cli.main(["get-check", "--entry", "CLI Entry"], store_factory=factory), 1)
        output = self.out.getvalue()
        self.assertIn("password, settings", output)
        self.assertIn("Deleted CLI Entry.", output)



class StaticGrantFieldTests(StoreCase):
    def test_put_entry_refuses_grant_fields_in_a_static_object(self):
        first, _pinned = self.init()
        first.open()
        for name in ("refreshToken", "refresh_token", "client_secret"):
            with self.assertRaisesRegex(SecretStoreError, "grant field"):
                first.put_entry("Legacy", {name: VALUE, "api_key": OTHER})
        self.assertNotIn("Legacy", first.list_entries())

    def test_scan_reports_static_objects_holding_grant_fields(self):
        from secret_store.store_ops import build_put
        first, _pinned = self.init()
        first.open().put_entry("Clean", {"api_key": VALUE})
        self.assertEqual(first.static_grant_exposures(), [])
        first._write(lambda: build_put(first.policy, first.checkpoint.objects, first._index(), "Legacy",
                                       {"client_secret": VALUE, "api_key": OTHER}, "static",
                                       first._identity().ed25519))
        self.assertEqual(first.static_grant_exposures(), ["personal/Legacy: client_secret"])


if __name__ == "__main__":
    unittest.main()
