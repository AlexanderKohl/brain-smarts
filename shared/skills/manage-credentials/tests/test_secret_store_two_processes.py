"""Two processes on one store (plan section G): the Vault Agent holds one SecretStore instance
open while brain_secrets.py in another process writes through a second instance over the same
clone and checkpoint folder. The holder follows the newer checkpoint at its next operation (no
timed sync is waited for); an older, forked or unsigned checkpoint and a local copy that differs
from the reloaded checkpoint are still refused. A bare local repository is the remote and a fake
keyring the keychain. Every value is fictional."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import keyring  # noqa: E402

from secret_store import SecretStoreError, canonical, checkpoint, keys, signing  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.store import EMPTY_JSON, SecretStore  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402
from vault_agent_runtime import AGENT_PROTOCOL_VERSION  # noqa: E402

FIELD = "oauth_token_json"
VALUE = "fictional-value-not-real"
_ENV_KEYS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
_saved_env = {}
_global_dir = None

# The second process: the fake keyring's items from a file, then the command line's put.
CHILD = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import keyring
from secret_store import keys
from secret_store.store import SecretStore
import brain_secrets

class FakeKeyring:
    def __init__(self, items):
        self.items = {(s, u): p for s, u, p in items}
    def get_password(self, service, user):
        return self.items.get((service, user))
    def set_password(self, service, user, password):
        self.items[(service, user)] = password

config = json.loads(Path(sys.argv[2]).read_text("utf-8"))
fake = FakeKeyring(config.pop("keyring"))
keyring.get_keyring = lambda: fake
keys.ALLOWED_BACKENDS = frozenset({f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"})
factory = lambda: SecretStore(use_config_file=False, enabled=True, **{
    k: (Path(v) if k.endswith(("_clone", "_dir")) else v) for k, v in config.items()})
sys.exit(brain_secrets.main(["put", "--entry", sys.argv[3], "--empty-json", "oauth_token_json"],
                            store_factory=factory))
"""


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
    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, password):
        self.items[(service, user)] = password


def load_cli():
    spec = importlib.util.spec_from_file_location("secrets_cli_two", SCRIPTS / "brain_secrets.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


class TwoInstances(unittest.TestCase):
    """Instance a (the agent's, held open) and a second instance over the same folders."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare)],
                       check=True, capture_output=True)
        self.fake = FakeKeyring()
        name = f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"
        for patcher in (mock.patch.object(keyring, "get_keyring", return_value=self.fake),
                        mock.patch.object(keys, "ALLOWED_BACKENDS", frozenset({name}))):
            patcher.start()
            self.addCleanup(patcher.stop)
        first = self.make_store()
        first.init_personal(words_callback=lambda words: True)
        first.put_entry("before", {"api_key": VALUE})
        self.a = self.make_store().open()

    def config(self):
        base = self.root / "A"
        return {"person": "alec", "computer": "A", "personal_clone": base / "brain-secrets",
                "checkpoint_dir": base / "checkpoint", "recovery_package_dir": base / "packages",
                "personal_repo_url": str(self.bare)}

    def make_store(self):
        return SecretStore(use_config_file=False, enabled=True, **self.config())

    def remote_head(self):
        return subprocess.run(["git", "--git-dir", str(self.bare), "rev-parse", "main"],
                              capture_output=True, check=True).stdout.strip()

    # -- the holder follows ---------------------------------------------------------------------
    def test_each_instance_reads_and_writes_after_the_other_wrote(self):
        b = self.make_store().open()
        b.put_entry("from-b", {FIELD: EMPTY_JSON})
        self.assertEqual(self.a.get_record("from-b"), {FIELD: EMPTY_JSON})
        self.a.put_entry("from-a", {"api_key": VALUE})
        self.assertEqual(b.get_record("from-a"), {"api_key": VALUE})
        b.put_entry("from-b", {"note": "second"})
        self.assertEqual(self.a.list_entries(), ["before", "from-a", "from-b"])
        self.assertEqual(self.a.get_record("from-b"), {FIELD: EMPTY_JSON, "note": "second"})
        self.assertEqual(self.a.checkpoint, checkpoint.load(self.a.checkpoint_path,
                                                            self.a._identity().ed25519.public_key()))

    def test_agent_follows_a_command_line_put_then_a_new_authorisation_on_it(self):
        backend = StoreBackend(self.a, sync_seconds=3600)  # no timed sync during the test
        agent = VaultAgent(self.root / "none.vault", store=backend)

        def request(op, **payload):
            response = agent.handle({"v": AGENT_PROTOCOL_VERSION, "token": agent._auth_token, "op": op,
                                     "id": "t", **payload})
            self.assertTrue(response.get("ok"), response.get("error"))
            return response["result"]
        self.assertEqual(request("get_fields", entry="before", fields=["api_key"]), {"api_key": VALUE})
        self.assertEqual(load_cli().main(["put", "--entry", "xero-demo", "--empty-json", FIELD],
                                         store_factory=self.make_store), 0)
        self.assertEqual(request("get_fields", entry="xero-demo", fields=[FIELD]), {FIELD: EMPTY_JSON})
        begun = request("begin_refresh", entry="xero-demo", field=FIELD, new_authorisation=True)
        token = {"access_token": "fictional-access", "refresh_token": "fictional-refresh",
                 "expires_at": 19 * 10**8, "token_type": "Bearer"}
        request("set_json", entry="xero-demo", field=FIELD, value=token, operation=begun["operation"])
        self.assertEqual(backend.get_json("xero-demo", FIELD)["refresh_token"], "fictional-refresh")
        self.assertEqual(self.make_store().open().list_entries()[0:1], ["before"])

    def test_timed_sync_alone_follows_the_other_instance(self):
        backend = StoreBackend(self.a, sync_seconds=0)
        backend._ready()
        self.make_store().open().put_entry("later", {"api_key": VALUE})
        backend.sync()  # the agent's own pull, before any read
        self.assertEqual(self.a.get_record("later"), {"api_key": VALUE})

    def test_a_push_without_its_checkpoint_is_verified_and_followed(self):
        held = self.a.checkpoint_path.read_bytes()
        self.make_store().open().put_entry("pushed", {"api_key": VALUE})
        self.a.checkpoint_path.write_bytes(held)  # the writer stopped between its push and its checkpoint
        self.assertEqual(self.a.get_record("pushed"), {"api_key": VALUE})
        self.assertEqual(checkpoint.load(self.a.checkpoint_path, self.a._identity().ed25519.public_key()),
                         self.a.checkpoint)  # saved forward once the commit was verified

    def test_the_team_store_follows_a_policy_change_and_an_entry(self):
        from secret_store import team as team_ops
        team_bare = self.root / "team.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(team_bare)],
                       check=True, capture_output=True)

        def member():
            base = self.root / "T"
            return team_ops.TeamStore(use_config_file=False, enabled=True, person="alec", computer="T",
                                      team_clone=base / "team", checkpoint_dir=base / "state",
                                      recovery_package_dir=base / "packages", team_repo_url=str(team_bare))
        member().init_team("example-org", words_callback=lambda words: True,
                           gh=lambda *args: self.fail("gh must not run when a URL is configured"))
        held = member().open()
        other = member().open()
        team_ops.create_groups(other, ["ops"])  # a policy commit through the second instance
        other.put_entry("Ops API", {"api_key": VALUE}, group="ops")
        self.assertEqual(held.list_entries("ops"), ["Ops API"])
        self.assertEqual(held.policy.hash, other.policy.hash)
        held.put_entry("Ops Two", {"api_key": VALUE}, group="ops")
        self.assertEqual(other.list_entries("ops"), ["Ops API", "Ops Two"])

    # -- still refused --------------------------------------------------------------------------
    def assert_refused_and_unchanged(self, pattern):
        held, head = self.a.checkpoint, self.remote_head()
        with self.assertRaisesRegex(SecretStoreError, pattern):
            self.a.get_record("before")
        with self.assertRaisesRegex(SecretStoreError, pattern):
            self.a.put_entry("refused", {"api_key": VALUE})
        self.assertIs(self.a.checkpoint, held)
        self.assertEqual(self.remote_head(), head)

    def test_an_older_checkpoint_put_back_is_refused(self):
        older = self.a.checkpoint_path.read_bytes()
        self.make_store().open().put_entry("newer", {"api_key": VALUE})
        self.assertEqual(self.a.get_record("newer"), {"api_key": VALUE})  # a follows the newer one
        self.a.checkpoint_path.write_bytes(older)
        self.assert_refused_and_unchanged("backwards")

    def test_a_forked_checkpoint_signed_here_is_refused(self):
        cp = self.a.checkpoint
        oid = sorted(cp.objects)[0]
        forked = dict(cp.objects, **{oid: {"revision": cp.objects[oid]["revision"], "hash": "0" * 64}})
        doc = checkpoint.Checkpoint(cp.repository, cp.policy_epoch, cp.policy_hash, forked).to_doc()
        signer = self.a._identity().ed25519
        doc["writer"] = keys.key_id(signer.public_key())
        self.a.checkpoint_path.write_bytes(canonical.dumps(signing.sign(doc, signer)))
        self.assert_refused_and_unchanged("backwards or fork")

    def test_a_checkpoint_not_signed_here_is_refused(self):
        data = json.loads(self.a.checkpoint_path.read_bytes())
        data["policy_epoch"] += 1
        self.a.checkpoint_path.write_bytes(canonical.dumps(data))
        self.assert_refused_and_unchanged("signature does not verify")

    def test_a_local_copy_that_differs_from_the_reloaded_checkpoint_is_refused(self):
        b = self.make_store().open()
        index = self.a.clone / "objects" / "index-personal.json"
        old_index = index.read_bytes()
        b.put_entry("newer", {"api_key": VALUE})
        index.write_bytes(old_index)  # the working tree no longer matches the newer checkpoint
        self.assert_refused_and_unchanged("index-personal in the local copy does not match the checkpoint")

    # -- a real second process ------------------------------------------------------------------
    def test_a_second_process_writes_while_the_first_holds_its_instance(self):
        config = {k: str(v) for k, v in self.config().items()}
        config["keyring"] = [[s, u, p] for (s, u), p in self.fake.items.items()]
        (self.root / "child.json").write_text(json.dumps(config), "utf-8")
        (self.root / "child.py").write_text(CHILD, "utf-8")
        argv = [sys.executable, str(self.root / "child.py"), str(SCRIPTS), str(self.root / "child.json")]
        self.assertEqual(self.a.list_entries(), ["before"])
        with self.a.repo.lock():  # the child waits for the cross-process lock, then continues
            child = subprocess.Popen(argv + ["from-child"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and child.poll() is None:
                time.sleep(0.1)
            self.assertIsNone(child.poll(), "the child finished while this process held the lock")
        out, err = child.communicate(timeout=120)
        self.assertEqual(child.returncode, 0, err.decode("utf-8", "replace"))
        self.assertEqual(self.a.get_record("from-child"), {FIELD: EMPTY_JSON})
        self.a.put_entry("from-holder", {"api_key": VALUE})
        child = subprocess.run(argv + ["from-child-2"], capture_output=True, timeout=120)
        self.assertEqual(child.returncode, 0, child.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.a.list_entries(), ["before", "from-child", "from-child-2", "from-holder"])


if __name__ == "__main__":
    unittest.main()
