"""The rehearsal's step commands, run inside wrapper.py session in one computer's environment.

The parent sends one JSON line per command and reads one JSON line back: {"ok", "checked",
"data"}. The first line carries the run's seed; every invented value is derived from it here, so
the parent compares hashes and never sees a value. Recovery words stay in this process's memory.
Everything the product code prints is captured, never forwarded. Values are typed through the
injection points the code has (brain_secrets.main ask/display, init_personal words_callback),
never a window."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import re
from pathlib import Path
from typing import Any, Callable

STATIC_ENTRY, SIGNIN_ENTRY, TEAM_ENTRY, GROUP = "rehearsal-static", "rehearsal-signin", "rehearsal-team", "rehearsal"
SIGNIN_FIELD = "oauth_token_json"
OLD_STATIC, OLD_SIGNIN = "rehearsal-old-static", "rehearsal-old-signin"
TOKEN_URL_PREFIX = "https://127.0.0.1:"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Failed(Exception):
    """A check of a step did not hold."""


class Session:
    def __init__(self, seed: bytes) -> None:
        self.seed = seed
        self.words: dict[str, str] = {}
        self.person = None

    def value(self, label: str) -> str:
        return "rehearsal-" + hmac.new(self.seed, label.encode(), hashlib.sha256).hexdigest()[:32]

    def known_values(self) -> list[str]:
        import tls
        values = [self.value(x) for x in ("static", "team", "old-static", "passphrase", "old-access", "old-refresh")]
        values += [tls._derive(kind, i, self.seed) for kind in ("access", "refresh") for i in range(0, 60)]
        return values + list(self.words.values())

    # -- helpers ----------------------------------------------------------------------------------
    def _cli(self, argv: list[str], **callbacks: Any) -> tuple[int, str]:
        import brain_secrets
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = brain_secrets.main(argv, **callbacks)
        return code, out.getvalue()

    def _ask(self, label: str) -> Callable:
        return lambda _title, fields: ({name: self.value(label) for name in fields}, None)

    def _keep(self, kind: str) -> Callable[[list[str]], bool]:
        def keep(words: list[str]) -> bool:
            self.words[kind] = " ".join(words)
            return True
        return keep

    @staticmethod
    def _config() -> dict:
        from secret_store import store_ops
        return store_ops.load_config()

    def _newest_package(self) -> tuple[str, int] | None:
        folder = Path(self._config()["recovery_package_dir"])
        files = [p for p in folder.glob("*") if p.is_file()] if folder.is_dir() else []
        newest = max(files, key=lambda p: p.stat().st_mtime_ns, default=None)
        return (str(newest), newest.stat().st_mtime_ns) if newest else None

    # -- step 1 -----------------------------------------------------------------------------------
    def init(self) -> tuple[str, dict]:
        from secret_store import keys
        from secret_store.store import SecretStore
        config = self._config()
        fingerprint = SecretStore().init_personal(words_callback=self._keep("personal"))
        if not (Path(config["personal_clone"]) / ".git").is_dir():
            raise Failed("the personal clone was not made")
        keys.load_private_keys(config["person"], config["computer"])  # raises when the entry is missing
        if self._newest_package() is None:
            raise Failed("no recovery package in the run's cloud subfolder")
        return "fingerprint returned, clone made, keychain entry readable, package written", {"fingerprint": fingerprint}

    # -- step 2 -----------------------------------------------------------------------------------
    def put_static(self, group: str | None = None) -> tuple[str, dict]:
        entry, label = (TEAM_ENTRY, "team") if group else (STATIC_ENTRY, "static")
        argv = ["put", "--entry", entry, "--secret", "value"] + (["--group", group] if group else [])
        code, _ = self._cli(argv, ask=self._ask(label))
        if code != 0:
            raise Failed(f"put {entry} returned {code}")
        return f"{entry} stored through brain_secrets put", {}

    def agent_read(self, entry: str, label: str) -> tuple[str, dict]:
        from vault_broker_client import broker_request, broker_status
        status = broker_status()
        if not isinstance(status, dict) or status.get("backend") != "store":
            raise Failed("the agent does not name the store backend")
        result = broker_request("get_fields", entry=entry, fields=["value"])
        fields = result.get("fields", result) if isinstance(result, dict) else {}
        if digest(str(fields.get("value", ""))) != digest(self.value(label)):
            raise Failed(f"the hash of {entry} read through the agent does not match")
        return f"{entry} read through the agent in a second process; hashes match", {}

    # -- step 3 -----------------------------------------------------------------------------------
    @staticmethod
    def _oauth_store():
        import portable_vault
        return portable_vault.BrokerOAuthStore(SIGNIN_ENTRY, SIGNIN_FIELD)

    @staticmethod
    def _record(body: bytes) -> dict:
        import time
        parsed = json.loads(body.decode())
        return {"access_token": parsed["access_token"], "refresh_token": parsed["refresh_token"],
                "token_type": parsed.get("token_type", "Bearer"), "expires_at": time.time() + float(parsed["expires_in"])}

    def signin(self, url: str, create: bool = True) -> tuple[str, dict]:
        from token_endpoint import post_token
        if not url.startswith(TOKEN_URL_PREFIX):
            raise Failed("the token URL is not the run's own loopback endpoint")
        if create:
            code, _ = self._cli(["put", "--entry", SIGNIN_ENTRY, "--empty-json", SIGNIN_FIELD])
            if code != 0:
                raise Failed(f"put --empty-json returned {code}")
        store = self._oauth_store()
        with store.refresh_lock(store.rotation_lock, new_authorisation=True):
            _status, body = post_token(url, {}, {"grant_type": "authorization_code", "code": "rehearsal"}, timeout=10)
            store.save(self._record(body))
        token = self._oauth_store().load()
        return "first grant written as a new authorisation", {"access_hash": digest(str(token.get("access_token")))}

    def refresh(self, url: str) -> tuple[str, dict]:
        from portable_vault import CredentialError
        from secret_store.journal import ProviderNotCalled, ProviderRefused
        from token_endpoint import post_token
        if not url.startswith(TOKEN_URL_PREFIX):
            raise Failed("the token URL is not the run's own loopback endpoint")
        store = self._oauth_store()
        outcome, message = "answered", ""
        try:
            current = store.load()
            with store.refresh_lock(store.rotation_lock, refresh=True):
                _status, body = post_token(url, {}, {"grant_type": "refresh_token",
                                                     "refresh_token": str(current.get("refresh_token", ""))}, timeout=5)
                store.save(self._record(body))
        except ProviderNotCalled:
            outcome = "not_called"
        except ProviderRefused as error:
            outcome = "refused" if getattr(error, "error", "") == "invalid_grant" or "invalid_grant" in str(error) \
                else "refused_other"
        except CredentialError as error:
            outcome, message = ("needs_replace" if "replace-signin" in str(error) else "credential_error"), str(error)
        except Exception as error:  # noqa: BLE001 - a time-out or reset after the request: uncertain
            outcome, message = "uncertain", type(error).__name__
        token = self._oauth_store().load()
        return f"refresh ended {outcome}", {"outcome": outcome, "access_hash": digest(str(token.get("access_token"))),
                                            "names_replace": "replace-signin" in message}

    def replace_signin(self) -> tuple[str, dict]:
        code, text = self._cli(["replace-signin", SIGNIN_ENTRY, "--field", SIGNIN_FIELD])
        if code != 0:
            raise Failed(f"replace-signin returned {code}")
        return "replace-signin ended the uncertain sign-in in one administrator commit", {}

    # -- step 4 -----------------------------------------------------------------------------------
    def recovery_package(self, team: bool = False) -> tuple[str, dict]:
        before = self._newest_package()
        code, _ = self._cli(["recovery-package"] + (["--team"] if team else []))
        after = self._newest_package()
        if code != 0 or after is None or after == before:
            raise Failed(f"recovery-package{' --team' if team else ''} returned {code} or wrote no new file")
        return f"a new {'team ' if team else ''}package in the run's cloud subfolder", {"package": after[0]}

    # -- step 5 -----------------------------------------------------------------------------------
    def restore(self, package: str, target_root: str) -> tuple[str, dict]:
        from secret_store.store import SecretStore
        words = self.words["personal"]
        root = Path(target_root)
        words_ask = lambda _t, fields: ({fields[0]: words}, None)  # noqa: E731
        wrong = " ".join(reversed(words.split()))
        changed = root / "changed-package"
        root.mkdir(parents=True, exist_ok=True)
        data = bytearray(Path(package).read_bytes())
        data[len(data) // 2] ^= 1
        changed.write_bytes(bytes(data))
        full = root / "not-empty"
        full.mkdir()
        (full / "file.txt").write_text("x", "utf-8")
        refusals = [("wrong words", package, root / "a", lambda _t, f: ({f[0]: wrong}, None)),
                    ("changed package", str(changed), root / "b", words_ask),
                    ("non-empty target", package, full, words_ask)]
        for label, pack, target, ask in refusals:
            code, _ = self._cli(["restore", "--package", pack, "--target", str(target)], ask=ask)
            leftover = target.exists() and any(p.name != "file.txt" for p in target.iterdir())
            if code == 0 or leftover:
                raise Failed(f"restore with {label} was not refused cleanly")
        code, _ = self._cli(["restore", "--package", package, "--target", str(root / "cli")], ask=words_ask)
        if code != 0 or not (root / "cli" / ".git").exists():
            raise Failed(f"restore returned {code}")
        store = SecretStore.restore_from_package(words, package, root / "python")
        if STATIC_ENTRY not in store.list_entries():
            raise Failed(f"the restored store does not list {STATIC_ENTRY}")
        return "three refusals wrote nothing; restore succeeded and lists " + STATIC_ENTRY, {}

    # -- step 6 -----------------------------------------------------------------------------------
    def team_init(self) -> tuple[str, dict]:
        from secret_store.team import TeamStore
        config = self._config()
        fingerprint = TeamStore().init_team(config["person"], words_callback=self._keep("team"))
        for argv in (["team-groups", "--create", GROUP], ["team-groups", "--login", config["person"], "--group", GROUP]):
            code, _ = self._cli(argv)
            if code != 0:
                raise Failed(" ".join(argv[:2]) + f" returned {code}")
        return "team store made; group created and the person set in it", {"fingerprint": fingerprint}

    def enrol_request(self, fingerprint: str) -> tuple[str, dict]:
        code, text = self._cli(["enrol-request", "--team", "--fingerprint", fingerprint])
        found = re.search(r"request ([0-9a-f]{16}) written", text)
        if code != 0 or not found:
            raise Failed(f"enrol-request returned {code}")
        return "enrolment request written", {"request": found.group(1)}

    def enrol_prove(self, request: str) -> tuple[str, dict]:
        seen: dict[str, str] = {}
        code, _ = self._cli(["enrol-request", "--team", "--request", request],
                            display=lambda _t, words: seen.setdefault("hash", digest(" ".join(words))) is not None)
        if code != 0 or "hash" not in seen:
            raise Failed(f"enrol-request --request returned {code}")
        return "challenge answered; words shown to the callback", {"words_hash": seen["hash"]}

    def enrol_approve(self, request: str, words_hash: str | None = None) -> tuple[str, dict]:
        display = (lambda _t, words: digest(" ".join(words)) == words_hash) if words_hash else (lambda _t, _w: True)
        code, text = self._cli(["enrol-approve", "--team", "--request", request], display=display)
        state = "enrolled" if "The computer is enrolled." in text else "answered" if "Request answered" in text else ""
        if code != 0 or not state:
            raise Failed(f"enrol-approve returned {code}")
        return f"enrol-approve: {state}", {"state": state}

    def get_check(self, group: str) -> tuple[str, dict]:
        code, text = self._cli(["get-check", "--group", group, "--entry", TEAM_ENTRY])
        if code != 0 or "value" not in text:
            raise Failed(f"get-check returned {code} or does not name the field")
        return "get-check names the field", {}

    # -- step 7 -----------------------------------------------------------------------------------
    def old_vault(self, path: str) -> tuple[str, dict]:
        from portable_vault import PortableVault
        passphrase = self.value("passphrase")
        vault = PortableVault(path)
        vault.initialize(passphrase)
        vault.set(OLD_STATIC, "value", self.value("old-static"), "text", passphrase)
        vault.set(OLD_SIGNIN, SIGNIN_FIELD, {"access_token": self.value("old-access"),
                                            "refresh_token": self.value("old-refresh")}, "json", passphrase)
        return "throwaway old vault made with one static and one sign-in entry", {}

    def unlock(self) -> tuple[str, dict]:
        from vault_broker_client import broker_request
        broker_request("unlock", passphrase=self.value("passphrase"))
        return "the agent on the old vault is unlocked", {}

    def migrate(self, argv: list[str]) -> tuple[str, dict]:
        import migrate_to_store
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = migrate_to_store.main(argv)
        if code != 0:
            raise Failed(f"migrate_to_store {' '.join(argv)} returned {code}")
        return f"migrate_to_store {' '.join(argv) or 'migrate'} returned 0", {}

    def marker(self, path: str, present: bool) -> tuple[str, dict]:
        from portable_vault import migration_marker_path
        if migration_marker_path(path).exists() != present:
            raise Failed("the migration marker is " + ("missing" if present else "still there"))
        return "migration marker " + ("written" if present else "cleared"), {}

    def store_on_refusal(self) -> tuple[str, dict]:
        from portable_vault import CredentialError, refuse_when_store_on
        try:
            refuse_when_store_on()
        except CredentialError:
            return "a passphrase open is refused while the store is on", {}
        raise Failed("a passphrase open was not refused while the store is on")

    def stale_refusal(self) -> tuple[str, dict]:
        """A vault-backed agent refuses credential requests once the store is on (round-9 M2), and
        the migration's locked operations outside a live migration lock (M5)."""
        from portable_vault import CredentialError
        from vault_broker_client import broker_request
        for operation, payload in (("get_fields", {"entry": OLD_STATIC, "fields": ["value"]}),
                                   ("vault_scrub_signin", {"entry": OLD_SIGNIN, "field": SIGNIN_FIELD})):
            try:
                broker_request(operation, **payload)
            except CredentialError as error:
                if operation == "get_fields" and "restart" not in str(error):
                    raise Failed("get_fields was refused without the restart message") from None
                continue
            raise Failed(f"{operation} was answered by a vault-backed agent with the store on")
        return "the vault-backed agent refuses get_fields (restart message) and the scrub outside the lock", {}

    def old_static_back(self, path: str) -> tuple[str, dict]:
        from vault_broker_client import broker_request
        result = broker_request("get_fields", entry=OLD_STATIC, fields=["value"])
        fields = result.get("fields", result) if isinstance(result, dict) else {}
        if digest(str(fields.get("value", ""))) != digest(self.value("old-static")):
            raise Failed("the static entry is not back in the old vault")
        return "the static entry is back in the old vault; hashes match", {}


COMMANDS = ("agent_read", "enrol_approve", "enrol_prove", "enrol_request", "get_check", "init", "marker", "migrate",
            "old_static_back", "old_vault", "put_static", "recovery_package", "refresh", "replace_signin", "restore",
            "signin", "stale_refusal", "store_on_refusal", "team_init", "unlock")


def session(stdin: Any, stdout: Any) -> int:
    """Read the seed, then answer one JSON line per command until stdin ends."""
    import wrapper
    first = json.loads(stdin.readline() or "{}")
    state = Session(bytes.fromhex(first.get("seed", "")))
    for line in stdin:
        request = json.loads(line)
        name = request.pop("command", "")
        try:
            if name not in COMMANDS:
                raise Failed(f"unknown command {name}")
            checked, data = getattr(state, name)(**request)
            reply = {"ok": True, "checked": checked, "data": data}
        except Failed as error:
            reply = {"ok": False, "checked": str(error), "data": {}}
        except Exception as error:  # noqa: BLE001 - the type and the product's message, never a value
            reply = {"ok": False, "checked": f"{type(error).__name__}: {error}", "data": {}}
        reply["checked"] = wrapper.scrub(reply["checked"], state.known_values())[:400]
        stdout.write(json.dumps(reply) + "\n")
        stdout.flush()
    return 0
