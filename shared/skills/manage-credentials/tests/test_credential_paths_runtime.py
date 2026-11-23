"""Follow-up plan R11, rule 6, part e: every primitive and sink of CREDENTIAL-PATHS.md ("Inside the
store") is wrapped with a recorder, the public operations are driven in named scenarios in this
process (stores over bare local repositories, the fake keyring, in-process agents through a fake
pipe connection, a fake token endpoint), and the test fails when a module on a recorded chain is in
the no-credential table or a recorded pair (operation, primitive or sink) is not in the list. Every
pair of the list names the scenario that produced it, or the reason no test can (a display, the
real pipe). The scenarios run once (setUpClass); the checks are separate tests. Every value is
fictional. What this does not do is written in CREDENTIAL-PATHS.md: it follows no branch no
scenario runs."""
import contextlib
import io
import os
from types import SimpleNamespace
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credential_recorder import AGENT_PROTOCOL_VERSION, PASS, SCRIPTS, Recorder, World, pipe_request  # noqa: E402
import credential_inventory as inventory  # noqa: E402
from test_secret_store_broker import setUpModule as _git_up, tearDownModule as _git_down  # noqa: E402
from test_token_endpoint import TOKEN, FakeNetwork, answer, post  # noqa: E402

import brain_secrets  # noqa: E402
import migrate_to_store  # noqa: E402
import migration_lock  # noqa: E402
import portable_vault  # noqa: E402
import token_relay  # noqa: E402
import token_relay_backend  # noqa: E402
import vault_agent_runtime  # noqa: E402
import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
import vaultctl  # noqa: E402
from portable_vault import CredentialError, PortableVault, PortableVaultJsonStore  # noqa: E402
from secret_store import provider_profiles, typed_write  # noqa: E402
from secret_store.journal import Journal  # noqa: E402
from secret_store.oauth_ops import find  # noqa: E402
from vault_agent import VaultAgent  # noqa: E402

FIELD = "oauth_token_json"
KEY = "fictional-api-key-not-real"
SECRET = "fictional-client-secret-not-real"
RELAY_KEY_TEXT = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # bytes 0..31, fictional
UNDRIVEN = {"window", "words-window", "tray-dialog",  # need a display: their callers run with injected values
            "agent-connect"}  # needs the real pipe of this user's agent, which no test touches
# excused for an operation whose agent client is the scenarios' stand-in (no state file is read there)
STAND_IN_EXCUSED = {"agent-state-read", "agent-connect"}
FIXTURE = "(fixture)"  # a recorder operation name for the scenarios' own set-up calls
# vaultctl.py access-token prints the access token and token_relay.py key-export the relay key, by design (the two
# terminal sinks); everything else stays off the terminal
SECRETS_NEVER_PRINTED = (KEY, SECRET, PASS, "fictional-refresh-1-not-real")


def setUpModule():
    _git_up()


def tearDownModule():
    _git_down()


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True  # token_relay.py key-export prints only to a terminal


class Done:
    returncode = 0


def fake_run(*_args, **_kwargs):
    return Done()


def getpass_fake(prompt: str = "") -> str:
    """The hidden prompt: the passphrase for a passphrase prompt, a value otherwise, a key text for the relay."""
    if "passphrase" in prompt.lower():
        return PASS
    if "relay key" in prompt.lower():
        return RELAY_KEY_TEXT
    return SECRET


# -- scenarios ------------------------------------------------------------------------------------
class Scenarios:
    def __init__(self, world: World, recorder: Recorder, out: io.StringIO) -> None:
        self.world, self.rec, self.out = world, recorder, out

    def cli(self, argv, expect=0, op=None, **fakes) -> str:
        before = len(self.out.getvalue())
        with self.rec.operation(f"brain_secrets.py {op or argv[0]}"):
            code = brain_secrets.main(argv, **fakes)
        text = self.out.getvalue()[before:]
        if code != expect:
            raise AssertionError(f"brain_secrets.py {argv} exited {code}, expected {expect}: {text}")
        return text

    def agent_op(self, request, op, expect_error=None, **payload):
        with self.rec.operation(f"agent {op}"):
            try:
                return request(op, **payload)
            except CredentialError as error:
                if expect_error is None or expect_error not in str(error):
                    raise

    def run_all(self) -> None:
        a = lambda: self.world.store("A")  # noqa: E731 - fresh store objects: keys loaded on first use
        b = lambda: self.world.store("B")  # noqa: E731
        ask = lambda _title, fields: ({f: KEY for f in fields}, None)  # noqa: E731
        with self.rec.named("cli-init"):
            self.cli(["init"], store_factory=a)
        with self.rec.named("cli-status"):
            self.cli(["status"], store_factory=a)
        with self.rec.named("cli-list"):
            self.cli(["list"], store_factory=a)
        with self.rec.named("cli-put"):
            self.cli(["put", "--entry", "plain", "--secret", "api_key", "--empty-json", "settings"], store_factory=a, ask=ask)
        with self.rec.named("cli-list"):
            self.cli(["list"], store_factory=a)  # with an index to open
        with self.rec.named("cli-get-check"):
            self.cli(["get-check", "--entry", "plain"], store_factory=a)
        with self.rec.named("cli-recovery-package"):
            package = self.cli(["recovery-package"], store_factory=a).split("written: ", 1)[1].strip()
        with self.rec.named("cli-grant-scan"):
            self.cli(["grant-scan"], store_factory=a)
        with self.rec.named("cli-enrol"):
            fingerprint = self.world.store("A").open()._load_pin()
            text = self.cli(["enrol-request", "--fingerprint", fingerprint], store_factory=b)
            rid = text.split("request ", 1)[1].split()[0]
            self.cli(["enrol-approve", "--request", rid], store_factory=a, display=lambda _t, _w: True)
            self.cli(["enrol-request", "--request", rid], store_factory=b, display=lambda _t, _w: True)
            self.cli(["enrol-approve", "--request", rid], store_factory=a, display=lambda _t, _w: True)
        with self.rec.named("cli-handover"):
            self.world.sign_in(self.world.backend("A"), "xero-demo", self.world.token())
            self.cli(["handover-release", "--entry", "xero-demo", "--to", "alec/B"], store_factory=a)
            self.cli(["handover-accept", "--entry", "xero-demo"], store_factory=a)
        with self.rec.named("cli-replace-signin"):
            self.world.sign_in(self.world.backend("A"), "xero-two", self.world.token())
            store = self.world.store("A").open()
            signin = find(store, "xero-two", FIELD, "personal")
            stack, _record = Journal(store.config["checkpoint_dir"], store._identity().x25519).begin(signin.journal_key, 1)
            stack.close()  # an uncertain record
            self.cli(["replace-signin", "xero-two"], store_factory=a)
        with self.rec.named("cli-unfinished"):
            self.cli(["unfinished"], store_factory=a)
            for action in ("--apply", "--discard"):
                store = self.world.store("A").open()
                records = typed_write.records(store)
                record = records.new(store.policy.repository, "personal", "plain", {"api_key": KEY}, {"api_key": "text"}, {},
                                     typed_write.base_of(store, "plain", "personal", {}), {})
                records.write({**record, "held": True})  # a record that is not held is replayed at the next sync
                self.cli(["unfinished", action, record["id"]], store_factory=a, confirm=lambda _p, i=record["id"]: i)
        with self.rec.named("cli-delete"):
            self.world.sign_in(self.world.backend("A"), "xero-del", self.world.token())
            self.cli(["delete", "--entry", "xero-del", "--field", FIELD], store_factory=a, confirm=lambda _p: "xero-del")
            self.cli(["delete", "--entry", "plain"], store_factory=a, confirm=lambda _p: "plain")
        with self.rec.named("cli-restore"):
            words = " ".join(self.world.words)
            self.cli(["restore", "--package", package, "--target", str(self.world.root / "restored")],
                     ask=lambda _t, fields: ({fields[0]: words}, None))
        with self.rec.named("cli-team"):
            admin = lambda: self.world.team("L", "alice")  # noqa: E731
            bob = lambda: self.world.team("D", "bob")  # noqa: E731
            text = self.cli(["team-init", "--owner", "example-org"], team_factory=admin)
            fingerprint = text.strip().splitlines()[-1]
            self.cli(["team-groups", "--create", "ops", "--create", "finance"], team_factory=admin)
            self.cli(["put", "--entry", "Ops API", "--secret", "api_key", "--group", "ops"], team_factory=admin, ask=ask)
            text = self.cli(["enrol-request", "--team", "--fingerprint", fingerprint], team_factory=bob)
            rid = text.split("request ", 1)[1].split()[0]
            self.cli(["enrol-approve", "--team", "--request", rid], team_factory=admin, display=lambda _t, _w: True)
            self.cli(["enrol-request", "--team", "--request", rid], team_factory=bob, display=lambda _t, _w: True)
            self.cli(["enrol-approve", "--team", "--request", rid], team_factory=admin, display=lambda _t, _w: True)
            self.cli(["team-admit", "--login", "bob", "--group", "ops"], team_factory=admin)
            self.cli(["team-groups", "--login", "bob", "--group", "finance"], team_factory=admin)  # Ops API is re-keyed
            self.cli(["put", "--entry", "Finance API", "--secret", "api_key", "--group", "finance"], team_factory=admin,
                     ask=ask)  # bob reads it, so team-remove re-keys it
            self.cli(["team-remove", "--login", "bob"], team_factory=admin)
        self.agent_store()
        self.agent_vault()
        self.migration()
        self.vaultctl()
        self.vault_credentials()
        self.token_relay()
        self.refresh_path()
        self.agent_state()
        with self.rec.named("cli-supersede"):  # last of all: the real, unverified profiles refuse the supersession
            self.world.sign_in(self.world.backend("B"), "xero-b", self.world.token())  # commit on every other computer
            with mock.patch.object(provider_profiles, "recovery_refusal", return_value=None):  # no profile is verified
                self.cli(["supersede", "--all-from", "alec/B", "--to", "alec/A", "--confirmation", "revoked at the provider"],
                         store_factory=a)

    # -- the agent, store-backed and vault-backed, through its pipe handler ----------------------------
    def agent_store(self) -> None:
        with self.rec.named("agent-store"):
            path = self.world.root / "A.vault"
            PortableVault(path).initialize(PASS)  # for unlock: the passphrase is checked against a vault
            fresh = lambda computer="A": pipe_request(VaultAgent(path, store=self.world.backend(computer)))  # noqa: E731
            op = self.agent_op
            op(fresh(), "status")
            op(fresh(), "ping")
            op(fresh(), "set_text", entry="plain2", field="api_key", value=KEY)
            op(fresh(), "get_fields", entry="plain2", fields=["api_key"])
            op(fresh(), "set_json", entry="plain2", field="settings", value={"region": "au"})
            op(fresh(), "get_json", entry="plain2", field="settings")
            request = fresh()
            begun = op(request, "begin_refresh", entry="xero-agent", field=FIELD, new_authorisation=True)
            op(request, "set_json", entry="xero-agent", field=FIELD, value=self.world.token(), operation=begun["operation"])
            op(fresh(), "get_access_token", entry="xero-agent", field=FIELD)
            request = fresh()
            begun = op(request, "begin_refresh", entry="xero-agent", field=FIELD)
            op(request, "abort_refresh", entry="xero-agent", field=FIELD, operation=begun["operation"])
            request = fresh()
            begun = op(request, "begin_refresh", entry="xero-agent", field=FIELD)
            op(request, "release_refresh", entry="xero-agent", field=FIELD, operation=begun["operation"])
            op(fresh("B"), "poll_refresh", entry="xero-agent", field=FIELD)
            op(fresh(), "clear_signin", entry="xero-agent", field=FIELD)
            op(fresh(), "sync_store")
            op(fresh(), "lock")
            op(fresh(), "unlock", passphrase=PASS)
            op(fresh(), "shutdown", expect_error="Unsupported")

    def agent_vault(self) -> Path:
        with self.rec.named("agent-vault"):
            vault = PortableVault(self.world.root / "v" / "credentials.vault")
            vault.initialize(PASS)
            vault.set_fields("xero-demo", {FIELD: (self.world.token(), "json"), "client_secret": (SECRET, "text")}, PASS)
            vault.set("plain", "api_key", KEY, "text", PASS)
            agent = VaultAgent(vault.path)  # the store is off: today's vault agent
            request, op = pipe_request(agent), self.agent_op
            op(request, "unlock", passphrase=PASS)
            op(request, "status")
            op(request, "get_fields", entry="plain", fields=["api_key"])
            op(request, "get_json", entry="xero-demo", field=FIELD)
            op(request, "get_access_token", entry="xero-demo", field=FIELD)
            op(request, "set_json", entry="xero-demo", field="settings", value={"region": "au"})
            op(request, "set_text", entry="plain", field="other", value=KEY)
            copy = vault.path.with_name("copy.vault")
            shutil.copyfile(vault.path, copy)
            with migration_lock.MigrationLock(vault.path, "migrate"):
                op(request, "vault_list_entries")
                op(request, "vault_get_fields", entry="plain", fields=["api_key"])
                op(request, "vault_get_json", entry="xero-demo", field=FIELD)
                op(request, "vault_verify_copy", path=str(copy))
                op(request, "vault_scrub_signin", entry="xero-demo", field=FIELD)
                op(request, "vault_restore_static", entry="plain", values={"api_key": {"value": KEY, "kind": "text"}})
                op(request, "vault_restore_marked_static", entry="xero-demo",
                   values={FIELD: {"value": {"region": "au"}, "kind": "json"}})  # a name the scrub marked
                op(request, "vault_clear_migration_marker")
            return vault.path

    # -- the migration and the rollback ---------------------------------------------------------------
    def migration(self) -> None:
        vault = PortableVault(self.world.root / "m" / "credentials.vault")
        vault.initialize(PASS)
        vault.set_fields("vault-xero", {FIELD: (self.world.token(), "json"), "client_secret": (SECRET, "text")}, PASS)
        vault.set("vault-plain", "api_key", KEY, "text", PASS)
        agent = VaultAgent(vault.path)
        agent.unlock(PASS)
        request = self.rec.stand_in("agent-client", pipe_request(agent))
        lines: list = []
        with self.rec.named("migrate"), self.rec.operation("migrate_to_store.py migrate"):
            assert migrate_to_store.migrate(request, lambda: self.world.store("A").open(), dry_run=True, out=lines.append) == 0
            assert migrate_to_store.migrate(request, lambda: self.world.store("A").open(), out=lines.append) == 0
        store = self.world.store("A").open()  # a static field under the migrated sign-in's name: the rollback's late field
        store.delete_entry("vault-xero", field=FIELD)  # the store no longer serves that sign-in, so it is not shadowed
        store.put_entry("vault-xero", {FIELD: "fictional-late-static-value"})
        with self.rec.named("rollback"), self.rec.operation("migrate_to_store.py rollback"):
            assert migrate_to_store.rollback(request, lambda: self.world.store("A").open(), dry_run=True, out=lines.append) == 0
            assert migrate_to_store.rollback(request, lambda: self.world.store("A").open(), out=lines.append) == 0
        self.out.write("\n".join(lines))

    # -- vaultctl.py against an in-process store-backed agent -----------------------------------------
    def vaultctl(self) -> None:
        with self.rec.named("vaultctl"):
            self.world.sign_in(self.world.backend("A"), "xero-ctl", self.world.token())  # xero-agent was cleared above
            store_agent = VaultAgent(self.world.root / "A.vault", store=self.world.backend("A"))
            vault_agent = VaultAgent(self.world.root / "A.vault")  # locked, store off: unlock asks for the passphrase
            for agent, commands in ((vault_agent, (["unlock"],)),
                                    (store_agent, (["status"], ["lock"], ["access-token", "--entry", "xero-ctl"],
                                                   ["secret-put", "--entry", "plain3", "--field", "api_key"],
                                                   ["run", "--entry", "plain2", "--map", "API_KEY=api_key", "--", "child"]))):
                standin = self.rec.stand_in("agent-client", pipe_request(agent))
                patches = [mock.patch.object(vaultctl, "broker_request", standin),
                           mock.patch.object(vaultctl, "broker_status", lambda: standin("status")),
                           mock.patch.object(vaultctl, "broker_unlocked", lambda: bool(standin("status").get("unlocked"))),
                           mock.patch.object(vaultctl.getpass, "getpass", getpass_fake),
                           mock.patch.object(vaultctl, "subprocess", SimpleNamespace(run=fake_run))]  # the child only
                with contextlib.ExitStack() as stack:
                    for patcher in patches:
                        stack.enter_context(patcher)
                    for argv in commands:
                        self._vaultctl(argv)

    def _vaultctl(self, argv) -> None:
        with mock.patch.object(sys, "argv", ["vaultctl.py", *argv]), self.rec.operation(f"vaultctl.py {argv[0]}"):
            code = vaultctl.main()
        assert code == 0, (argv, code, self.out.getvalue()[-400:])

    # -- vault_credentials.py on a vault of its own, the store off --------------------------------------
    def vault_credentials(self) -> None:
        with self.rec.named("vault-credentials"):
            path = self.world.root / "c" / "credentials.vault"
            base = ["vault_credentials.py", "--vault", str(path)]
            agent = None

            def run(argv, expect=0):
                with mock.patch.object(sys, "argv", base + argv), self.rec.operation(f"vault_credentials.py {argv[0]}"):
                    code = vault_credentials.main()
                assert code == expect, (argv, code, self.out.getvalue()[-400:])
            with mock.patch.object(vault_credentials, "_keyboard", return_value=True), \
                    mock.patch.object(vault_credentials.getpass, "getpass", getpass_fake), \
                    mock.patch("builtins.input", lambda prompt: prompt.split("Type ", 1)[1].split(" to ", 1)[0]), \
                    mock.patch.object(vault_credentials, "subprocess", SimpleNamespace(run=fake_run)), \
                    mock.patch.object(vault_broker_client, "broker_unlocked", return_value=False):
                run(["init"])
                run(["check"])
                run(["list"])
                run(["init-json", "--entry", "xero-demo"])
                run(["put", "--entry", "plain", "--field", "api_key"])
                run(["put-entry", "--entry", "entry2", "--secret", "a", "--secret", "b", "--empty-json", "settings"])
                run(["change-passphrase"])
                run(["delete-field", "--entry", "entry2", "--field", "b"])
                run(["delete-entry", "--entry", "entry2"])
                run(["run", "--entry", "plain", "--map", "API_KEY=api_key", "--", "child"])
                run(["session", "--entry", "plain", "--map", "API_KEY=api_key", "--", "shell"])
                agent = VaultAgent(path)
                agent.unlock(PASS)
                standin = self.rec.stand_in("agent-client", pipe_request(agent))
                with mock.patch.object(vault_broker_client, "broker_request", standin), \
                        mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True):
                    run(["put", "--entry", "plain", "--field", "second"])
                    run(["run", "--entry", "plain", "--map", "API_KEY=api_key", "--", "child"])

    # -- token_relay.py on its own vault, the store off, the relay on an in-memory backend -------------
    def token_relay(self) -> None:
        with self.rec.named("token-relay"):
            folder = self.world.root / "relay"
            folder.mkdir()
            path = folder / "credentials.vault"
            vault = PortableVault(path)
            vault.initialize(PASS)
            vault.set_fields("example-oauth", {FIELD: (self.world.token(), "json")}, PASS)
            vault.set("token-relay", "relay_key", RELAY_KEY_TEXT, "text", PASS)
            (folder / "token-relay.json").write_text(json.dumps(
                {"backend": "github", "repository": "example-owner/example-relay", "entries": ["example-oauth"]}), "utf-8")
            backend = token_relay_backend.MemoryBackend()

            def run(argv, expect=0):
                with self.rec.operation(f"token_relay.py {argv[0]}"):
                    code = token_relay.main(["--vault", str(path), *argv])
                assert code == expect, (argv, code, self.out.getvalue()[-400:])
            with mock.patch.object(token_relay, "make_backend", lambda _config: backend), \
                    mock.patch.dict("os.environ", {"PORTABLE_VAULT_PASSPHRASE": PASS}), \
                    mock.patch.object(vault_broker_client, "broker_unlocked", return_value=False), \
                    mock.patch.object(token_relay.getpass, "getpass", getpass_fake):
                run(["status"])
                run(["seed", "--entry", "example-oauth"])
                agent = VaultAgent(path)
                agent.unlock(PASS)
                standin = self.rec.stand_in("agent-client", pipe_request(agent))
                with mock.patch.object(vault_broker_client, "broker_request", standin), \
                        mock.patch.object(vault_broker_client, "broker_status", lambda: standin("status")), \
                        mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True):
                    run(["key-new", "--replace"])
                    run(["key-import", "--replace"])
                    run(["key-export"])

    # -- a connector's refresh through the store: the token endpoint and the journal -------------------
    def refresh_path(self) -> None:
        self.world.sign_in(self.world.backend("A"), "xero-refresh", self.world.token())  # a fixture, not the operation
        path = self.world.root / "A.vault"
        standin = self.rec.stand_in("agent-client", pipe_request(VaultAgent(path, store=self.world.backend("A"))))
        with self.rec.named("refresh-path"), self.rec.operation("refresh path"):
            with mock.patch.object(vault_broker_client, "broker_unlocked", return_value=True), \
                    mock.patch.object(vault_broker_client, "broker_request", standin):
                client = PortableVaultJsonStore("xero-refresh", FIELD, path=path)  # xero-agent is held uncertain above
                with client.rotation_lock(refresh=True), FakeNetwork(reply=answer(200, TOKEN)):
                    fresh = json.loads(post()[1])
                    client.save({**client.load(), "access_token": fresh["access_token"],
                                 "refresh_token": fresh["refresh_token"]})

    # -- the agent's state file, in a temporary folder: the token and key written and read back ----------
    def agent_state(self) -> None:
        folder = self.world.root / "runtime"
        # The real proof of a private folder and file runs here (follow-up plan R15, rule 9).
        with self.rec.named("agent-state"), mock.patch.object(vault_agent_runtime, "runtime_base", lambda: folder), \
                self.rec.operation("the agent's state file"):
            agent = VaultAgent(self.world.root / "A.vault")  # makes the token and the pipe key
            payload = {"pid": os.getpid(), "address": "fictional-address", "authkey": agent._authkey.hex(),
                       "token": agent._auth_token, "vault_path": str(agent.vault.path), "protocol": AGENT_PROTOCOL_VERSION}
            vault_agent_runtime.write_state(payload)
            assert vault_agent_runtime.read_state() == payload
            vault_agent_runtime.clear_state(only_pid=os.getpid())
            assert vault_agent_runtime.read_state() is None
            assert not (folder / "agent-state.json").exists()


# -- the checks --------------------------------------------------------------------------------------
def listed_pairs() -> dict[str, tuple[set[str], set[str]]]:
    """operation -> (the ids its scenario must produce, the ids other branches may add)."""
    found = {}
    for parser, operations in inventory.OPERATIONS.items():
        for operation, (uses, may, _scenario, _note) in operations.items():
            found[f"{parser} {operation}"] = (set(uses), set(may))
    for operation, (uses, may, _scenario, _note) in inventory.EXTRA_OPERATIONS.items():
        found[operation] = (set(uses), set(may))
    return found


def chain_problems(records, credential: dict, no_credential: dict) -> list[str]:
    problems = []
    for operation, endpoint_id, chain in records:
        for module, function in chain:
            if module in no_credential:
                problems.append(f"{operation}: {module} {function} is on the chain to {endpoint_id} but is in the "
                                "no-credential table")
            elif module not in credential and module != "<none>":
                problems.append(f"{operation}: {module} {function} is on the chain to {endpoint_id} but in neither table")
    return sorted(set(problems))


def pair_problems(recorded: dict[str, set[str]], listed: dict[str, tuple[set[str], set[str]]],
                  undriven: set[str]) -> list[str]:
    problems = []
    for operation, found in sorted(recorded.items()):
        if operation == FIXTURE:
            continue
        if operation not in listed:
            problems.append(f"{operation}: not in the list of operations")
            continue
        extra = found - listed[operation][0] - listed[operation][1]
        if extra:
            problems.append(f"{operation}: recorded {sorted(extra)}, not in the list")
    for operation, (uses, _may) in sorted(listed.items()):
        missing = uses - recorded.get(operation, set()) - undriven
        if "agent-client" in uses:  # the stand-in answers in-process: no state file is read, no key spent
            missing -= STAND_IN_EXCUSED
        if missing and operation in recorded:
            problems.append(f"{operation}: the list names {sorted(missing)}, no scenario produced it")
    return problems


class RuntimePaths(unittest.TestCase):
    failures: list = []
    recorder = Recorder()

    @classmethod
    def setUpClass(cls):
        cls.out = Tty()
        cls.world = World()
        cls.recorder.install(inventory.ENDPOINTS)
        acl = mock.patch.object(portable_vault, "_apply_windows_user_acl", lambda _path: None)
        acl.start()
        try:
            with contextlib.redirect_stdout(cls.out), contextlib.redirect_stderr(cls.out):
                Scenarios(cls.world, cls.recorder, cls.out).run_all()
        except Exception as error:  # noqa: BLE001 - reported by test_every_scenario_ran
            cls.failures.append(f"{type(error).__name__}: {error}")
        finally:
            acl.stop()
            cls.recorder.uninstall()

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def test_every_scenario_ran(self):
        self.assertEqual(self.failures, [], "\n".join(self.failures) + "\n" + self.out.getvalue()[-2000:])
        self.assertEqual(sorted(self.recorder.unavailable), [], self.recorder.unavailable)
        self.assertNotEqual(self.recorder.records, [])

    def test_no_value_was_printed(self):
        text = self.out.getvalue()
        for secret in SECRETS_NEVER_PRINTED:
            self.assertNotIn(secret, text)

    def test_every_module_on_a_recorded_chain_is_in_the_credential_table(self):
        problems = chain_problems(self.recorder.records, inventory.CREDENTIAL, inventory.NO_CREDENTIAL)
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_every_recorded_pair_is_in_the_list_and_every_listed_pair_was_produced(self):
        problems = pair_problems(self.recorder.pairs(), listed_pairs(), UNDRIVEN)
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_every_listed_operation_names_its_scenario_or_the_reason(self):
        for parser, operations in inventory.OPERATIONS.items():
            for operation, (uses, may, scenario, note) in operations.items():
                name = f"{parser} {operation}"
                if scenario is None:
                    self.assertGreater(len(note.split()), 5, f"{name}: give the reason no scenario can run it")
                    self.assertNotIn(name, self.recorder.operations_run, f"{name} ran, so name its scenario")
                    continue
                for one in scenario.split(", "):
                    self.assertIn(name, self.recorder.scenarios.get(one, set()), f"{name}: scenario {one} did not run it")
                if set(uses) & UNDRIVEN or may:
                    self.assertGreater(len(note.split()), 3, f"{name}: say why a listed id has no scenario")
        for operation, (_uses, _may, scenario, _note) in inventory.EXTRA_OPERATIONS.items():
            self.assertIn(operation, self.recorder.scenarios.get(scenario, set()))

    def test_the_checks_fail_on_a_patched_table_or_a_foreign_chain(self):
        """The reviewer's module: a no-credential helper on the chain to an opener, caught by its frame."""
        chain = (("brain_secrets.py", "main"), ("secret_store/store.py", "SecretStore.status"),
                 ("secret_store/status_extra.py", "describe"), ("secret_store/oauth_ops.py", "read_shared"),
                 ("secret_store/envelope.py", "open_"))
        records = [("brain_secrets.py status", "open", chain)]
        self.assertEqual(chain_problems(records, inventory.CREDENTIAL, inventory.NO_CREDENTIAL),
                         ["brain_secrets.py status: secret_store/status_extra.py describe is on the chain to open but in "
                          "neither table"])
        listed = {**inventory.NO_CREDENTIAL, "secret_store/status_extra.py": "describes"}
        self.assertEqual(chain_problems(records, inventory.CREDENTIAL, listed),
                         ["brain_secrets.py status: secret_store/status_extra.py describe is on the chain to open but is "
                          "in the no-credential table"])
        init = set(inventory.OPERATIONS["brain_secrets.py"]["init"][0])
        pairs = pair_problems({"brain_secrets.py init": init | {"open"}}, listed_pairs(), UNDRIVEN)
        self.assertEqual(pairs, ["brain_secrets.py init: recorded ['open'], not in the list"])
        stale = pair_problems({"brain_secrets.py list": {"keychain-read"}}, listed_pairs(), UNDRIVEN)
        self.assertEqual(stale, ["brain_secrets.py list: the list names ['hpke-open', 'open'], no scenario produced it"])
        self.assertEqual(pair_problems({"agent get_everything": {"open"}}, listed_pairs(), UNDRIVEN),
                         ["agent get_everything: not in the list of operations"])


if __name__ == "__main__":
    unittest.main()
