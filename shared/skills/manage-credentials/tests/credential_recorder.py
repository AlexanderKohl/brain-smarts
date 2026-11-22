"""The runtime recorder behind tests/test_credential_paths_runtime.py (follow-up plan R11, rule 6,
part e), and the in-process fixtures its scenarios reuse: bare local repositories as remotes, the
fake keyring of test_secret_store_broker.py, stores and agents in this process, a fake pipe
connection for the agent. No network, no real keychain, no real vault. Every value is fictional.

The recorder wraps every primitive and sink of credential_inventory.ENDPOINTS. Each call records
the operation the scenario named, the endpoint id and the chain of the skill's own frames from the
outermost one down to the endpoint. A stand-in (an in-process request function given to the code
in place of vault_broker_client.broker_request) records as the endpoint it stands for."""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
import keyring  # noqa: E402

from portable_vault import CredentialError  # noqa: E402
from secret_store import keys  # noqa: E402
from secret_store import store as store_module  # noqa: E402
from secret_store import team as team_module  # noqa: E402
from secret_store.broker_backend import StoreBackend  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402
from secret_store.team import TeamStore  # noqa: E402
from test_secret_store_broker import FakeKeyring  # noqa: E402
from vault_agent_runtime import AGENT_PROTOCOL_VERSION  # noqa: E402

PASS = "fictional passphrase for tests only 42 xyz"


def _import(module_rel: str):
    return importlib.import_module(module_rel[:-3].replace("/", "."))


def skill_chain() -> tuple[tuple[str, str], ...]:
    """(module, function) of every frame under scripts/, outermost first."""
    chain = []
    frame = sys._getframe(1)
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        try:
            rel = path.resolve().relative_to(SCRIPTS.resolve()).as_posix()
        except ValueError:
            rel = None
        if rel is not None:
            chain.append((rel, frame.f_code.co_qualname.replace(".<locals>.", ".")))
        frame = frame.f_back
    return tuple(reversed(chain))


class Recorder:
    def __init__(self) -> None:
        self.records: list[tuple[str | None, str, tuple]] = []  # (operation, endpoint id, chain)
        self.operations_run: set[str] = set()
        self.scenarios: dict[str, set[str]] = {}  # scenario -> operations it ran
        self.current: str | None = None
        self.scenario: str | None = None
        self.unavailable: dict[str, str] = {}
        self._restore: list = []

    # -- installing ---------------------------------------------------------------------------
    def install(self, endpoints: dict) -> None:
        for endpoint_id, (module_rel, scope, _kind, _what) in endpoints.items():
            try:
                module = _import(module_rel)
            except Exception as error:  # noqa: BLE001 - a module that cannot import here (the Windows tray elsewhere)
                self.unavailable[endpoint_id] = f"{type(error).__name__}: {error}"
                continue
            owner, name = module, scope
            if "." in scope:
                owner, name = getattr(module, scope.split(".")[0]), scope.split(".")[1]
            elif isinstance(getattr(module, scope), type):
                owner, name = getattr(module, scope), "__init__"
            original = getattr(owner, name)
            wrapper = self._wrap(endpoint_id, original)
            setattr(owner, name, wrapper)
            self._restore.append((owner, name, original))
            if owner is module:  # a by-name import elsewhere still holds the original
                for loaded in list(sys.modules.values()):
                    file = getattr(loaded, "__file__", None)
                    if file and Path(file).resolve().is_relative_to(SCRIPTS.resolve()) and loaded is not module:
                        for attribute, value in list(vars(loaded).items()):
                            if value is original:
                                setattr(loaded, attribute, wrapper)
                                self._restore.append((loaded, attribute, original))

    def uninstall(self) -> None:
        for owner, name, original in reversed(self._restore):
            setattr(owner, name, original)
        self._restore.clear()

    def _wrap(self, endpoint_id: str, original):
        recorder = self

        def wrapper(*args, **kwargs):
            recorder.records.append((recorder.current or "(fixture)", endpoint_id, skill_chain()))
            return original(*args, **kwargs)
        wrapper.__name__ = getattr(original, "__name__", endpoint_id)
        wrapper.__wrapped__ = original
        return wrapper

    def stand_in(self, endpoint_id: str, function):
        """A function standing in for an endpoint the code cannot reach in-process (the agent's pipe
        client): every call is recorded as that endpoint."""
        return self._wrap(endpoint_id, function)

    # -- scenarios ----------------------------------------------------------------------------
    @contextmanager
    def operation(self, name: str):
        """name: "<parser> <operation>", for example "brain_secrets.py put" or "agent get_json"."""
        previous, self.current = self.current, name
        self.operations_run.add(name)
        if self.scenario is not None:
            self.scenarios.setdefault(self.scenario, set()).add(name)
        try:
            yield
        finally:
            self.current = previous

    @contextmanager
    def named(self, scenario: str):
        self.scenario = scenario
        self.scenarios.setdefault(scenario, set())
        try:
            yield
        finally:
            self.scenario = None

    def pairs(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for operation, endpoint_id, _chain in self.records:
            found.setdefault(operation, set()).add(endpoint_id)
        return found


# -- the agent's pipe, in-process -------------------------------------------------------------------
class FakeConnection:
    """One request over the agent's pipe: recv gives it once, then EOF; send keeps the reply."""

    def __init__(self, request: dict) -> None:
        self.request, self.sent, self.closed = request, [], False

    def recv(self):
        if self.request is None:
            raise EOFError
        request, self.request = self.request, None
        return request

    def send(self, response) -> None:
        self.sent.append(response)

    def close(self) -> None:
        self.closed = True


def pipe_request(agent):
    """broker_request bound to an in-process agent through its pipe handler (_serve_connection)."""
    def request(op, **payload):
        connection = FakeConnection({"v": AGENT_PROTOCOL_VERSION, "token": agent._auth_token, "op": op, "id": "t",
                                     **payload})
        agent._serve_connection(connection)
        response = connection.sent[0]
        if response.get("ok"):
            return response["result"]
        raise CredentialError(response.get("error"))
    return request


# -- stores over bare local repositories -----------------------------------------------------------
class World:
    """Computers of one person over a bare personal repository and a bare team repository, each
    store made fresh on request (so its keys are loaded from the fake keyring on first use)."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        self.team_bare = self.root / "team.git"
        for bare in (self.bare, self.team_bare):
            subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(bare)], check=True,
                           capture_output=True)
        self.keyring = FakeKeyring()
        name = f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"
        self.words: list[str] = []
        self._patches = [mock.patch.object(keyring, "get_keyring", return_value=self.keyring),
                         mock.patch.object(keys, "ALLOWED_BACKENDS", frozenset({name})),
                         mock.patch.object(store_module, "_default_words_window", self._words),
                         mock.patch.object(team_module, "_default_words_window", self._words)]
        for patcher in self._patches:
            patcher.start()

    def close(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        self._tmp.cleanup()

    def _words(self, words) -> bool:
        self.words = list(words)
        return True

    def store(self, computer: str, person: str = "alec") -> SecretStore:
        base = self.root / f"{person}-{computer}"
        return SecretStore(use_config_file=False, enabled=True, person=person, computer=computer,
                           personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                           recovery_package_dir=base / "packages", personal_repo_url=str(self.bare))

    def team(self, computer: str, person: str) -> TeamStore:
        base = self.root / f"{person}-{computer}"
        return TeamStore(use_config_file=False, enabled=True, person=person, computer=computer,
                         team_clone=base / "brain-team-secrets", checkpoint_dir=base / "checkpoint",
                         recovery_package_dir=base / "packages", team_repo_url=str(self.team_bare))

    def backend(self, computer: str) -> StoreBackend:
        return StoreBackend(self.store(computer), sync_seconds=0)

    @staticmethod
    def sign_in(backend: StoreBackend, entry: str, value: dict, field: str = "oauth_token_json") -> str:
        begun = backend.begin_refresh(entry, field, new_authorisation=True)
        backend.set_json(entry, field, value, operation=begun["operation"])
        return begun["operation"]

    @staticmethod
    def token(**extra) -> dict:
        return {"access_token": "fictional-access-1-not-real", "refresh_token": "fictional-refresh-1-not-real",
                "expires_at": 19 * 10**8, "token_type": "Bearer", "scope": "accounting", "tenant_id": "tenant-1", **extra}
