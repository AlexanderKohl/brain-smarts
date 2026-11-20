"""Secrets-store Git transactions and recovery packages. Two or more local clones of a bare
repository in a temporary folder; no network. Every key and value here is fictional."""
import base64
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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402

from secret_store import SecretStoreError, canonical, keys, policy, recovery_package  # noqa: E402
from secret_store.repo import Conflict, RefusedCommit, SecretRepo, repo_lock  # noqa: E402

_ENV_KEYS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
_saved_env = {}
_global_dir = None


def setUpModule():
    global _global_dir
    _global_dir = tempfile.TemporaryDirectory()
    cfg = Path(_global_dir.name) / "gitconfig"
    # autocrlf true globally proves the repository's own settings keep canonical bytes intact.
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


def accept_all(_commit, _files):
    return True


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare)], check=True)
        subprocess.run(["git", "config", "receive.denyNonFastForwards", "true"], cwd=self.bare, check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def clone(self, name):
        return SecretRepo(self.root / name, str(self.bare)).clone_or_open()

    def remote_log(self):
        out = subprocess.run(["git", "rev-list", "--parents", "main"], cwd=self.bare, capture_output=True, check=True)
        return [line.split() for line in out.stdout.decode().splitlines()]


class TransactionTests(RepoCase):
    def test_refusal_stops_at_bad_commit(self):
        a, b = self.clone("a"), self.clone("b")
        good = a.write({"objects/one.json": {"v": 1}}, "update")
        bad = a.write({"objects/two.json": {"marker": "s3cr3t-value"}}, "update")
        a.write({"objects/three.json": {"v": 3}}, "update")
        seen = []

        def verify(commit, files):
            seen.append(commit)
            return not any(v and v.get("marker") for v in files.values())

        with self.assertRaises(RefusedCommit) as caught:
            b.pull(verify)
        self.assertEqual(caught.exception.commit, bad)
        self.assertNotIn("s3cr3t", str(caught.exception))
        self.assertEqual(seen, [good, bad])
        self.assertEqual(b.head(), good)
        self.assertTrue((b.path / "objects" / "one.json").exists())
        self.assertFalse((b.path / "objects" / "two.json").exists())
        self.assertFalse((b.path / "objects" / "three.json").exists())
        self.assertIn(bad, b.status())
        self.assertIn("Refused", b.status())
        with self.assertRaises(SecretStoreError):
            b.write({"objects/four.json": {"v": 4}}, "update")

    def test_verify_gets_parsed_files_and_none_for_removal(self):
        a, b = self.clone("a"), self.clone("b")
        a.write({"x.json": {"k": "v"}}, "update")
        removal = a.write({"x.json": None}, "update")
        calls = {}
        b.pull(lambda c, files: calls.setdefault(c, files) is not None)
        self.assertEqual(calls[removal], {"x.json": None})
        self.assertEqual(list(calls.values())[0], {"x.json": {"k": "v"}})
        self.assertFalse((b.path / "x.json").exists())
        self.assertEqual(b.status(), "Up to date.")

    def test_stale_writer_gets_conflict_then_rebuilds(self):
        a, b = self.clone("a"), self.clone("b")
        a.write({"base.json": {"v": 0}}, "update")
        b.pull(accept_all)
        original_fetch = b._fetch

        def racing_fetch():
            head = original_fetch()
            if not racing_fetch.done:
                racing_fetch.done = True
                a.write({"from-a.json": {"v": 1}}, "update")
            return head
        racing_fetch.done = False
        with mock.patch.object(b, "_fetch", racing_fetch):
            result = b.write({"from-b.json": {"v": 2}}, "update")
        self.assertIsInstance(result, Conflict)
        self.assertFalse((b.path / "from-b.json").exists())
        self.assertIn("Behind", b.status())
        self.assertIsInstance(b.write({"from-b.json": {"v": 2}}, "update"), Conflict)
        b.pull(accept_all)
        self.assertIsInstance(b.write({"from-b.json": {"v": 2}}, "update"), str)
        c = self.clone("c")
        c.pull(accept_all)
        self.assertEqual(c.read("from-a.json"), {"v": 1})
        self.assertEqual(c.read("from-b.json"), {"v": 2})

    def test_concurrent_writers_never_lose_a_write_and_never_force(self):
        writers = [self.clone("w1"), self.clone("w2")]
        commands = []
        for w in writers:
            original = w._git

            def recording(*args, _orig=original, **kw):
                commands.append(args)
                return _orig(*args, **kw)
            w._git = recording
        conflicts = []

        def run(repo, tag):
            for i in range(4):
                while True:
                    repo.pull(accept_all)
                    result = repo.write({f"{tag}/{i}.json": {"i": i}}, "update")
                    if not isinstance(result, Conflict):
                        break
                    conflicts.append(tag)
        threads = [threading.Thread(target=run, args=(w, f"t{n}")) for n, w in enumerate(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120)
        check = self.clone("check")
        check.pull(accept_all)
        for n in range(2):
            for i in range(4):
                self.assertEqual(check.read(f"t{n}/{i}.json"), {"i": i})
        log = self.remote_log()
        self.assertEqual(len(log), 8)
        self.assertTrue(all(len(entry) <= 2 for entry in log), "history must stay linear")
        for args in commands:
            if args and args[0] == "push":
                self.assertFalse(any(a.startswith("+") or a.startswith("--force") or a == "-f" for a in args))
            self.assertNotIn(args[0] if args else "", ("rebase", "merge"))

    def test_line_endings_preserved_byte_for_byte(self):
        a, b = self.clone("a"), self.clone("b")
        value = {"text": "line one\r\nline two\n", "z": [1, 2]}
        commit = a.write({"objects/eol.json": value}, "update")
        expected = canonical.dumps(value)
        blob = subprocess.run(["git", "cat-file", "blob", f"{commit}:objects/eol.json"], cwd=self.bare,
                              capture_output=True, check=True).stdout
        self.assertEqual(blob, expected)
        self.assertEqual((a.path / "objects" / "eol.json").read_bytes(), expected)
        b.pull(accept_all)
        self.assertEqual((b.path / "objects" / "eol.json").read_bytes(), expected)
        self.assertEqual((b.path / ".gitattributes").read_bytes(), b"* -text\n")
        cfg = subprocess.run(["git", "config", "--local", "core.autocrlf"], cwd=b.path, capture_output=True)
        self.assertEqual(cfg.stdout.strip(), b"false")
        name = subprocess.run(["git", "config", "--local", "user.name"], cwd=b.path, capture_output=True)
        self.assertEqual(name.stdout.strip(), b"Test Person")

    def test_message_outside_allowed_set_refused(self):
        a = self.clone("a")
        with self.assertRaises(SecretStoreError):
            a.write({"x.json": {}}, "fix things")
        with self.assertRaises(SecretStoreError):
            a.write({"../x.json": {}}, "update")
        self.assertIsInstance(a.write({"x.json": {}}, "policy"), str)


LOCK_CHILD = """
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from secret_store.repo import repo_lock
log = Path(sys.argv[3])
with repo_lock(Path(sys.argv[2])):
    with open(log, "a") as f:
        f.write("start\\n")
    time.sleep(0.6)
    with open(log, "a") as f:
        f.write("end\\n")
"""


class LockTests(unittest.TestCase):
    def test_lock_serialises_two_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock, log = Path(tmp) / "repo.lock", Path(tmp) / "log.txt"
            procs = [subprocess.Popen([sys.executable, "-c", LOCK_CHILD, str(SCRIPTS), str(lock), str(log)])
                     for _ in range(2)]
            for p in procs:
                self.assertEqual(p.wait(60), 0)
            self.assertEqual(log.read_text().split(), ["start", "end", "start", "end"])

    def test_lock_released_after_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "repo.lock"
            with self.assertRaises(ValueError):
                with repo_lock(lock):
                    raise ValueError("boom")
            started = time.monotonic()
            with repo_lock(lock, timeout=2):
                pass
            self.assertLess(time.monotonic() - started, 2)


class RecoveryPackageTests(RepoCase):
    def test_round_trip_and_wrong_key(self):
        a = self.clone("a")
        signer = Ed25519PrivateKey.generate()
        root = {"repository": "repo-test-1", "policy_epoch": 1,
                "recovery": {"ed25519": base64.b64encode(keys.raw_public(signer.public_key())).decode("ascii")}}
        root["endorsement"] = policy.endorse(root, signer)
        a.write({"policy.json": root}, "policy")
        head = a.write({"objects/one.json": {"v": 1}}, "update")
        key = X25519PrivateKey.generate()
        checkpoint = canonical.dumps({"epoch": 1, "note": "fictional checkpoint"})
        out = self.root / "packages" / "team.package"
        recovery_package.build(a, checkpoint, key.public_key(), out)
        data = out.read_bytes()
        self.assertNotIn(b"fictional checkpoint", data)
        self.assertNotIn(b"repo-test-1", data)
        self.assertEqual(list(out.parent.iterdir()), [out])
        target = self.root / "restored"
        with self.assertRaises(SecretStoreError):  # not endorsed by this recovery signing key
            recovery_package.restore(out, key, self.root / "other", Ed25519PrivateKey.generate().public_key())
        self.assertFalse((self.root / "other").exists())
        self.assertEqual(recovery_package.restore(out, key, target, signer.public_key()), checkpoint)
        restored = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, check=True)
        self.assertEqual(restored.stdout.decode().strip(), head)
        self.assertEqual((target / "objects" / "one.json").read_bytes(), canonical.dumps({"v": 1}))
        with self.assertRaises(SecretStoreError):
            recovery_package.restore(out, X25519PrivateKey.generate(), self.root / "wrong", signer.public_key())
        self.assertFalse((self.root / "wrong").exists())
        tampered = bytearray(data)
        tampered[-1] ^= 1
        bad = self.root / "tampered.package"
        bad.write_bytes(bytes(tampered))
        with self.assertRaises(SecretStoreError):
            recovery_package.restore(bad, key, self.root / "t", signer.public_key())


class StatusLockTest(unittest.TestCase):
    def test_status_fetches_under_the_repository_lock(self):
        from secret_store import repo as repo_module
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            repo = repo_module.SecretRepo(Path(tmp), "fictional-remote")
            held = []

            def fetch():
                held.append(any(k[1] == threading.get_ident() for k in repo_module._HELD))
                return "c1"
            with mock.patch.object(repo, "_state", return_value={}), \
                    mock.patch.object(repo, "head", return_value="c1"), \
                    mock.patch.object(repo, "_fetch", side_effect=fetch):
                self.assertEqual(repo.status(), "Up to date.")
            self.assertEqual(held, [True])


if __name__ == "__main__":
    unittest.main()
