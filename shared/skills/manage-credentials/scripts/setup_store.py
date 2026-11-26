"""Set up the synced secrets store on this computer in one command, and join a team store.

  python setup_store.py [--join TEAM_REPOSITORY_URL] [--fingerprint F] [--no-sync]

Each step says what it does and how long it took, and a step already done is skipped, so the
command can simply be run again after an interruption. In order:

 1. Bring the brain up to date (repository-preflight sync.py), unless --no-sync.
 2. Install the store's requirements (requirements.txt) that are missing; an installed package keeps
    its version.
 3. Read this computer's GitHub login through gh: the person's name in every store.
 4. When the old vault has not been migrated: have the Vault Agent running and unlocked on it (the
    agent's own passphrase window; the passphrase never passes through this command).
 5. Switch the store on in this brain's configuration.
 6. Create the personal store; its recovery words are shown once, in a local window.
 7. Move the old vault's entries into the store (migrate_to_store.py), the names listed first.
 8. With --join: accept the GitHub invitation (waiting for it when it has not come yet), add the team
    repository to the configuration, take the team fingerprint from the administrator's message,
    request enrolment, show the six words to send back, and wait until the administrator's
    computer has enrolled and admitted this one (brain_secrets.py invite).
 9. Restart the Vault Agent when it does not yet serve the store (and, with --join, the team store):
    the person quits it from its tray icon, and this command starts it again.

It never runs the rehearsal (rehearsal/README.md): that tests a new version of the store's code,
before its first real cut-over, and is the work of whoever changed it. No secret value is printed."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import child_process  # noqa: E402
import team_github  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
AGENT_WAIT = 15 * 60  # seconds to wait for the person to unlock or quit the Vault Agent
POLL = 2.0


class SetupError(RuntimeError):
    """A step that cannot go on; the message says what the person does next."""


class Setup:
    """The steps, with the outside world behind small methods a test can replace."""

    def __init__(self, root: Path, say: Callable[[str], None] = print, ask: Callable[[str], str] = input,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 github: Any = team_github) -> None:
        self.root, self.say, self.ask, self.clock, self.sleep, self.github = root, say, ask, clock, sleep, github
        self.number = 0

    # -- the outside world ------------------------------------------------------------------------
    def run(self, command: list[str]) -> int:
        """A child without a console of its own (child_process): its output is captured and shown here."""
        result = child_process.run(command, cwd=str(self.root), capture_output=True)
        for stream in (result.stdout, result.stderr):
            for line in stream.decode("utf-8", "replace").splitlines():
                if line.strip():
                    self.say("    " + line.rstrip())
        return result.returncode

    def agent_status(self) -> dict | None:
        from vault_broker_client import BrokerUnavailable, broker_status
        from portable_vault import CredentialError
        try:
            return broker_status()
        except (BrokerUnavailable, CredentialError, OSError):
            return None

    def start_agent(self) -> None:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = str(pythonw if pythonw.exists() else sys.executable)
        child_process.popen([interpreter, str(SCRIPTS / "vault_tray.py")], cwd=str(self.root))

    def migrate(self, argv: list[str]) -> int:
        import migrate_to_store
        return migrate_to_store.main(argv)

    def stores(self) -> tuple[Any, Any]:
        from secret_store.store import SecretStore
        from secret_store.team import TeamStore
        return SecretStore(brain_root=self.root), TeamStore(brain_root=self.root)

    # -- helpers ----------------------------------------------------------------------------------
    @contextmanager
    def step(self, text: str) -> Iterator[None]:
        self.number += 1
        started = self.clock()
        self.say(f"[{self.number}] {text}")
        yield
        self.say(f"    done in {self.clock() - started:.0f} s")

    def skip(self, text: str) -> None:
        self.number += 1
        self.say(f"[{self.number}] {text}: already done")

    def wait_for(self, done: Callable[[], bool], what: str, limit: float = AGENT_WAIT) -> None:
        deadline = self.clock() + limit
        while not done():
            if self.clock() > deadline:
                raise SetupError(f"gave up waiting for {what}; run this command again when ready")
            self.sleep(POLL)

    @property
    def config_path(self) -> Path:
        from secret_store.store_ops import CONFIG_RELATIVE
        return self.root / CONFIG_RELATIVE

    def config(self) -> dict:
        if not self.config_path.is_file():
            return {}
        try:
            data = json.loads(self.config_path.read_text("utf-8"))
        except (OSError, ValueError):
            raise SetupError(f"{self.config_path} cannot be read; fix or remove it, then run again") from None
        if not isinstance(data, dict):
            raise SetupError(f"{self.config_path} is not a JSON object; fix or remove it, then run again")
        return data

    def set_config(self, **values: Any) -> None:
        data = {**self.config(), **values}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")  # UTF-8 without a BOM

    def vault(self) -> Path:
        from portable_vault import default_vault_path
        return default_vault_path()

    def migrated(self) -> bool:
        return any((self.vault().parent / "migration-backups").glob("*.migration.json"))

    # -- the steps --------------------------------------------------------------------------------
    def sync(self) -> None:
        with self.step("Bringing the brain up to date"):
            if self.run([sys.executable, str(self.root / "shared/skills/repository-preflight/scripts/sync.py")]) != 0:
                raise SetupError("the brain could not be brought up to date (see the lines above); "
                                 "fix that, or run again with --no-sync")

    def missing_requirements(self) -> list[str]:
        """The lines of requirements.txt whose package is not installed at all. An installed package is
        left at its version, even outside the range, so that another program's newer one is never
        downgraded (pip install -r would)."""
        from importlib import metadata
        missing = []
        for line in (SCRIPTS.parent / "requirements.txt").read_text("utf-8").splitlines():
            requirement = line.split("#")[0].strip()
            name = re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0]
            if not name:
                continue
            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                missing.append(requirement)
        return missing

    def requirements(self) -> None:
        missing = self.missing_requirements()
        if not missing:
            self.skip("Installing the store's requirements")
            return
        with self.step("Installing the store's requirements: " + ", ".join(missing)):
            if self.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                         *missing]) != 0:
                raise SetupError("the requirements could not be installed (see the lines above)")

    def person(self) -> str:
        with self.step("Reading your GitHub login"):
            name = self.github.login()
            known = self.config().get("person")
            if known and known != name:
                raise SetupError(f"this brain's store is set up for {known}, but gh is signed in as {name}; "
                                 "sign gh in as the store's person (gh auth login)")
            self.say(f"    {name}")
            return name

    def unlock_old_vault(self) -> None:
        status = self.agent_status()
        if status is not None and status.get("backend") == "store":
            raise SetupError("the Vault Agent already serves the store, but the old vault was never migrated; "
                             "see 'The cut-over' in the credential skill (SKILL.md) before going on")
        with self.step("Unlocking the old vault in the Vault Agent"):
            if status is None:
                if self.config().get("enabled"):  # an earlier run stopped between switching on and moving
                    self.set_config(enabled=False)  # the agent must start on the old vault (the cut-over, step 1)
                self.start_agent()
                self.say("    The Vault Agent is starting: type the old vault's passphrase in its window.")
            elif not status.get("unlocked"):
                self.say("    Unlock the Vault Agent from its tray icon with the old vault's passphrase.")
            self.wait_for(lambda: bool((self.agent_status() or {}).get("unlocked")), "the Vault Agent to unlock")

    def switch_on(self, person: str) -> None:
        data = self.config()
        if data.get("enabled", bool(data)) and data.get("person") == person:
            self.skip("Switching the store on")
            return
        with self.step("Switching the store on"):
            self.set_config(enabled=True, person=person)

    def personal_store(self) -> None:
        personal, _team = self.stores()
        if personal.checkpoint_path.exists() or (personal.clone / ".git").exists():
            self.skip("Creating your personal store")
            return
        with self.step("Creating your personal store (write the recovery words down when the window shows them)"):
            fingerprint = personal.init_personal()
            self.say(f"    Personal fingerprint, for your next computer: {fingerprint}")

    def move_entries(self) -> None:
        with self.step("Moving the old vault's entries into the store"):
            for argv in (["--dry-run"], []):
                code = self.migrate(argv)
                if code != 0:
                    raise SetupError(f"the migration stopped (code {code}; see the lines above). Nothing more "
                                     "was changed; run this command again once it is fixed")

    def join(self, url: str, fingerprint: str | None) -> list[str]:
        repository = self.github.repository_of(url)
        if self.github.can_write(repository):
            self.skip(f"Getting access to {repository} on GitHub")
        else:
            with self.step(f"Getting access to {repository} on GitHub"):
                if not self.github.accept(repository):
                    self.say("    Waiting for the GitHub invitation (the administrator runs brain_secrets.py invite).")
                    self.wait_for(lambda: self.github.accept(repository) or self.github.can_write(repository),
                                  "the GitHub invitation", limit=2 * 60 * 60)
        known = self.config().get("team_repo_url")
        if known and known != url:
            raise SetupError(f"this brain is already joined to {known}; one team store per brain")
        if not known:
            self.set_config(team_repo_url=url)
        _personal, team = self.stores()
        if not team.pin_path.exists() and not fingerprint:
            fingerprint = self.ask("Paste the team fingerprint from the administrator's message: ").strip()
            if not fingerprint:
                raise SetupError("no fingerprint was given; nothing was requested")
        from secret_store import invite
        with self.step("Joining the team store (a words window opens: send its six words to the administrator)"):
            groups = invite.join_team(team, fingerprint, say=lambda text: self.say("    " + text))
            self.say(f"    You are in: {', '.join(groups)}")
            return groups

    def restart_agent(self, team: bool) -> None:
        def serving() -> bool:
            status = self.agent_status() or {}
            return status.get("backend") == "store" and (not team or "team" in status.get("recovery_packages", {}))
        if serving():
            self.skip("Restarting the Vault Agent on the store")
            return
        with self.step("Restarting the Vault Agent on the store"):
            if self.agent_status() is not None:
                self.say("    Quit the Vault Agent: right-click its icon by the clock and choose Quit. "
                         "It starts again by itself.")
                self.wait_for(lambda: self.agent_status() is None, "the Vault Agent to quit")
            self.start_agent()
            self.wait_for(serving, "the Vault Agent to start on the store", limit=120)

    def entries(self, groups: list[str]) -> None:
        personal, team = self.stores()
        count = len(personal.open().list_entries())
        self.say(f"Your store holds {count} entries.")
        for group in groups:
            names = sorted({name.partition("#")[0] for name in team.open().list_entries(group)})
            self.say(f"Team group {group}: " + (", ".join(names) if names else "no entries yet"))


def _brain_root() -> Path:
    """The folder above this skill that holds CONTRACT.md (standard library only: it runs before the
    requirements are installed)."""
    for folder in SCRIPTS.parents:
        if (folder / "CONTRACT.md").is_file():
            return folder
    raise SystemExit("setup_store.py must run inside a brain (no CONTRACT.md above it)")


def main(argv: list[str] | None = None, setup: Setup | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--join", metavar="TEAM_REPOSITORY_URL", help="the team repository in the invitation message")
    parser.add_argument("--fingerprint", help="the team fingerprint (asked for when not given)")
    parser.add_argument("--no-sync", action="store_true", help="do not bring the brain up to date first")
    args = parser.parse_args(argv)
    setup = setup or Setup(_brain_root())
    started, errors = setup.clock(), (SetupError, team_github.GitHubError)
    try:
        if not args.no_sync:
            setup.sync()
        setup.requirements()
        from portable_vault import CredentialError  # needs the requirements
        from secret_store import SecretStoreError
        errors = (*errors, SecretStoreError, CredentialError)
        person = setup.person()
        old = setup.vault().exists() and not setup.migrated()
        if old:
            setup.unlock_old_vault()
        setup.switch_on(person)
        setup.personal_store()
        if old:
            setup.move_entries()
        groups = setup.join(args.join, args.fingerprint) if args.join else []
        setup.restart_agent(team=bool(args.join))
        setup.entries(groups)
    except Exception as error:  # noqa: BLE001 - only the expected kinds are reported plainly
        if not isinstance(error, errors):
            raise
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 1
    setup.say(f"The secrets store is set up ({setup.clock() - started:.0f} s in all).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
