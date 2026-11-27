"""Set up the synced secrets store on this computer in one command, and join a team store.

  python setup_store.py [--join TEAM_REPOSITORY_URL] [--fingerprint F] [--no-sync]

Each step says what it does and how long it took, and a step already done is skipped, so the
command can simply be run again after an interruption. In order:

 1. Bring the brain up to date (repository-preflight sync.py), unless --no-sync.
 2. Install the store's requirements (requirements.txt) that are missing; an installed package keeps
    its version.
 3. Read this computer's GitHub login through gh: the person's name in every store.
 4. When the old vault has not been migrated: have the Vault Agent running and unlocked on it (on
    Windows the tray's own passphrase window; on macOS and Linux, where the agent runs without a tray,
    vaultctl.py unlock asks in this terminal; the passphrase never passes through this command).
 5. Switch the store on in this brain's configuration.
 6. Create the personal store; its recovery words are shown once, in a local window.
 7. Move the old vault's entries into the store (migrate_to_store.py), the names listed first.
 8. With --join: accept the GitHub invitation (waiting for it when it has not come yet), add the team
    repository to the configuration, take the team fingerprint from the administrator's message,
    request enrolment, show the six words to send back, and wait until the administrator's
    computer has enrolled and admitted this one (brain_secrets.py invite).
 9. Restart the Vault Agent when it does not yet serve the store (and, with --join, the team store):
    on Windows the person quits it from its tray icon; on macOS and Linux this command stops it. On
    macOS a login item (~/Library/LaunchAgents) then starts it at every login.

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
LOGIN_ITEM = "com.portableaibrain.vaultagent"


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _applies(marker: str, platform: str) -> bool:
    """The one environment marker requirements.txt uses: sys_platform == "..." or != "..."."""
    found = re.fullmatch(r"""\s*sys_platform\s*(==|!=)\s*["']([^"']+)["']\s*""", marker)
    if not found:
        raise SetupError(f"requirements.txt has a marker setup cannot read: {marker.strip()}")
    return (platform == found.group(2)) == (found.group(1) == "==")


class SetupError(RuntimeError):
    """A step that cannot go on; the message says what the person does next."""


class Setup:
    """The steps, with the outside world behind small methods a test can replace."""

    def __init__(self, root: Path, say: Callable[[str], None] = print, ask: Callable[[str], str] = input,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 github: Any = team_github, platform: str = sys.platform) -> None:
        self.root, self.say, self.ask, self.clock, self.sleep, self.github = root, say, ask, clock, sleep, github
        self.platform = platform  # "win32": the tray; anything else: the agent without a tray
        self.number = 0
        self.agent_process: Any = None  # the agent this command started without a tray, and its log
        self.agent_log: Path | None = None
        self.agent_log_start = 0

    @property
    def tray(self) -> bool:
        return self.platform == "win32"

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
        """Windows: the tray. macOS and Linux: vault_agent.py serve, in a session of its own so that it
        outlives this terminal; what it prints goes to the tray log beside its state file."""
        if self.tray:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            interpreter = str(pythonw if pythonw.exists() else sys.executable)
            child_process.popen([interpreter, str(SCRIPTS / "vault_tray.py")], cwd=str(self.root))
            return
        from vault_agent_runtime import tray_log_path
        self.agent_log = tray_log_path()
        self.agent_log_start = self.agent_log.stat().st_size if self.agent_log.exists() else 0
        with self.agent_log.open("ab") as log:
            self.agent_process = child_process.popen([sys.executable, str(SCRIPTS / "vault_agent.py"), "serve"], cwd=str(self.root),
                                stdin=child_process.DEVNULL, stdout=log, stderr=child_process.STDOUT,
                                start_new_session=True)

    def agent_ended(self) -> None:
        """Stop with the agent's own words when the agent this command started has already ended (a
        refused start: its output went to the log, not to this terminal)."""
        process = self.agent_process
        if process is None or process.poll() is None:
            return
        self.agent_process = None
        said = ""
        if self.agent_log is not None and self.agent_log.exists():
            with self.agent_log.open("rb") as log:
                log.seek(self.agent_log_start)
                said = log.read().decode("utf-8", "replace").strip()
        raise SetupError(f"the Vault Agent ended at once (code {process.returncode})"
                         + (f": {said[-1500:]}" if said else f"; see {self.agent_log}"))

    def agent_up(self) -> bool:
        self.agent_ended()
        return self.agent_status() is not None

    def stop_agent(self) -> None:
        """macOS and Linux: SIGTERM to the agent named in its state file (vault_agent.py shuts down on it),
        only when that process is a Vault Agent: a state file can outlive its agent, and its pid be reused."""
        import os
        import signal
        from vault_agent_runtime import read_state
        pid = int((read_state() or {}).get("pid") or 0)
        if pid <= 0:
            return
        shown = child_process.run(["ps", "-ww", "-p", str(pid), "-o", "command="], capture_output=True)
        if b"vault_agent.py" not in shown.stdout:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass  # gone already, or not ours to stop

    def unlock_in_terminal(self) -> int:
        """macOS and Linux: vaultctl.py unlock, with this terminal, so its hidden prompt reads the passphrase."""
        return child_process.run([sys.executable, str(SCRIPTS / "vaultctl.py"), "unlock"], cwd=str(self.root)).returncode

    def has_tk(self) -> bool:
        from importlib.util import find_spec
        return find_spec("_tkinter") is not None  # the compiled part a Python without Tk lacks

    def login_item(self) -> None:
        """macOS: a launchd login item that starts the agent at every login (the tray's Startup shortcut on
        Windows). Only written; this command starts the agent itself."""
        from vault_agent_runtime import tray_log_path
        log = str(tray_log_path())
        arguments = "".join(f"\n    <string>{_xml(item)}</string>"
                            for item in (sys.executable, str(SCRIPTS / "vault_agent.py"), "serve"))
        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f'  <key>Label</key>\n  <string>{LOGIN_ITEM}</string>\n'
            f'  <key>ProgramArguments</key>\n  <array>{arguments}\n  </array>\n'
            f'  <key>WorkingDirectory</key>\n  <string>{_xml(str(self.root))}</string>\n'
            '  <key>RunAtLoad</key>\n  <true/>\n'
            f'  <key>StandardOutPath</key>\n  <string>{_xml(log)}</string>\n'
            f'  <key>StandardErrorPath</key>\n  <string>{_xml(log)}</string>\n'
            '</dict>\n</plist>\n')
        path = Path.home() / "Library" / "LaunchAgents" / f"{LOGIN_ITEM}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plist, "utf-8")

    def migrate(self, argv: list[str]) -> int:
        import migrate_to_store
        return migrate_to_store.main(argv)

    def stores(self, force_on: bool = False) -> tuple[Any, Any]:
        """The two stores of this brain's configuration; force_on reads them even while an unfinished run
        has the store switched off (its person and addresses are still in the configuration)."""
        from secret_store.store import SecretStore
        from secret_store.team import TeamStore
        on = {"enabled": True} if force_on else {}
        return SecretStore(brain_root=self.root, **on), TeamStore(brain_root=self.root, **on)

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
        """The newest migration record of this vault names no sign-in it could not move. A record is
        written even by a run that failed its read-back (exit 4), so its presence alone is not enough."""
        vault = self.vault()
        if (vault.parent / "migration-backups" / f"{vault.stem}-joined.migration.json").exists():
            return True  # this computer joined a store made elsewhere: its old vault is never moved
        records = sorted((vault.parent / "migration-backups").glob(f"{vault.stem}-*.migration.json"),
                         key=lambda path: path.stat().st_mtime)
        if not records:
            return False
        try:
            record = json.loads(records[-1].read_text("utf-8"))
        except (OSError, ValueError):
            return False
        # The vault changed after the record (a rollback restores into it; the old vault was used again):
        # what the record says is no longer the whole story.
        return (isinstance(record, dict) and record.get("unverified_signins") == []
                and records[-1].stat().st_mtime >= vault.stat().st_mtime)

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
            requirement, _semicolon, marker = line.split("#")[0].strip().partition(";")
            requirement = requirement.strip()
            if marker and not _applies(marker, self.platform):
                continue  # the tray's packages, on a computer without the tray
            name = re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0]
            if not name:
                continue
            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                missing.append(requirement)
        return missing

    def requirements(self) -> None:
        if not self.has_tk():
            version = f"{sys.version_info.major}.{sys.version_info.minor}"
            hint = (f"brew install python-tk@{version}" if self.platform == "darwin"
                    else "install your system's python3-tk package")
            raise SetupError(f"this Python has no tkinter, which shows the store's words windows; {hint}, "
                             "then run again")
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
            if not (status or {}).get("unlocked") and self.config().get("enabled"):
                # An earlier run stopped between switching on and moving: the old vault is unlocked, or the
                # agent started, only with the store off (the cut-over, step 1); switch_on turns it on again.
                self.set_config(enabled=False)
            if status is None:
                self.start_agent()
                if self.tray:
                    self.say("    The Vault Agent is starting: type the old vault's passphrase in its window.")
            elif not status.get("unlocked") and self.tray:
                self.say("    Unlock the Vault Agent from its tray icon with the old vault's passphrase.")
            if not self.tray and not (status or {}).get("unlocked"):
                self.wait_for(self.agent_up, "the Vault Agent to start", limit=60)
                self.say("    Type the old vault's passphrase (nothing shows while you type):")
                if self.unlock_in_terminal() != 0:
                    raise SetupError("the old vault was not unlocked (see the lines above); run this command again")
            self.wait_for(lambda: bool((self.agent_status() or {}).get("unlocked")), "the Vault Agent to unlock")

    def switch_on(self, person: str) -> None:
        data = self.config()
        if data.get("enabled", bool(data)) and data.get("person") == person:
            self.skip("Switching the store on")
            return
        with self.step("Switching the store on"):
            self.set_config(enabled=True, person=person)

    def own_store_ready(self) -> bool:
        """This computer is enrolled in the person's store. A checkpoint alone is not enough: a computer
        that requested enrolment has pulled (and saved a checkpoint) before it was approved."""
        personal, _team = self.stores(force_on=True)
        if not personal.checkpoint_path.exists() or not personal.config["person"]:
            return False
        from secret_store import SecretStoreError
        try:
            opened = personal.open()
        except SecretStoreError as error:  # never read as "not enrolled": that would skip the migration
            raise SetupError(f"your store could not be read ({error}); run this command again") from None
        return (personal.config["person"], personal.config["computer"]) in opened.policy.computers

    def joins_existing_store(self, person: str) -> bool:
        """This computer is not in the person's store yet, and the store was made on another computer."""
        return not self.own_store_ready() and self.github.state(f"{person}/brain-secrets") == "used"

    def personal_store(self, person: str, joining: bool) -> None:
        personal, _team = self.stores()
        if self.own_store_ready():
            self.skip("Your personal store")
            return
        if joining:
            self.add_this_computer(f"{person}/brain-secrets")
            return
        from secret_store.team import clone_has_history
        if (personal.clone / ".git").exists() and not clone_has_history(personal.clone):
            from secret_store.recovery_package import _remove_tree
            _remove_tree(personal.clone)  # an earlier run stopped after cloning the empty repository
        with self.step("Creating your personal store (write the recovery words down when the window shows them)"):
            fingerprint = personal.init_personal()
            self.say(f"    Personal fingerprint, for your next computer: {fingerprint}")

    def add_this_computer(self, repository: str) -> None:
        from secret_store import invite
        if not self.config().get("personal_repo_url"):
            self.set_config(personal_repo_url=f"https://github.com/{repository}.git")
        personal, _team = self.stores()
        with self.step("Adding this computer to your personal store"):
            if not personal.pin_path.exists():
                self.say("    On a computer that already has your store, in its brain folder, run:")
                self.say("    python " + str(Path("shared", "skills", "manage-credentials", "scripts",
                                                 "brain_secrets.py")) + " add-computer")
                fingerprint = self.ask("Paste the personal fingerprint it shows: ").strip()
                if not fingerprint:
                    raise SetupError("no fingerprint was given; nothing was requested")
            else:
                fingerprint = None
            if self.vault().exists():
                self.mark_vault_left()  # before enrolment can finish: a stop after it never moves the old vault
            invite.join_team(personal, fingerprint, invite._show(invite.OWN_WORDS, False),
                             say=lambda text: self.say("    " + text))

    def mark_vault_left(self) -> None:
        """A computer that joined an existing store never copies its own old vault over it (that copy may
        be older than the store). A record beside the migration records says so, so that a later run
        does not move it either."""
        folder = self.vault().parent / "migration-backups"
        folder.mkdir(parents=True, exist_ok=True)
        record = {"joined_existing_store": True, "entries": [], "unverified_signins": [],
                  "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        (folder / f"{self.vault().stem}-joined.migration.json").write_text(json.dumps(record, indent=2) + "\n", "utf-8")
        self.say("    This computer's old vault is left as it is: your store already holds your entries.")

    def move_entries(self) -> None:
        personal, _team = self.stores()
        if personal.open().list_entries():
            # An earlier run stopped part-way through, or the store was written since. Setup never copies the
            # old vault over entries already there: which copy is current is the person's call.
            raise SetupError("the store already holds entries, so setup does not copy the old vault over them. "
                             "Check which copy of each entry is current, then run migrate_to_store.py --replace "
                             "yourself, or run setup again once the store holds only what you want kept "
                             "(see 'The cut-over' in the credential skill)")
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
                if self.tray:
                    self.say("    Quit the Vault Agent: right-click its icon by the clock and choose Quit. "
                             "It starts again by itself.")
                else:
                    self.stop_agent()
                self.wait_for(lambda: self.agent_status() is None, "the Vault Agent to quit",
                              limit=AGENT_WAIT if self.tray else 60)
            if self.platform == "darwin":
                self.login_item()
                self.say("    The Vault Agent now starts by itself at every login.")
            self.start_agent()
            self.wait_for(lambda: self.agent_up() and serving(), "the Vault Agent to start on the store", limit=120)

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
    parser.add_argument("--version", action="store_true", help="print the skill's version and stop")
    parser.add_argument("--verbose", action="store_true", help="with --version: the commit, branch and changes")
    args = parser.parse_args(argv)
    import skill_version
    if args.version:
        print(skill_version.identity(args.verbose))
        return 0
    setup = setup or Setup(_brain_root())
    setup.say(f"Secrets store setup, {skill_version.identity()}")
    started, errors = setup.clock(), (SetupError, team_github.GitHubError)
    try:
        if not args.no_sync:
            setup.sync()
        setup.requirements()
        from portable_vault import CredentialError  # needs the requirements
        from secret_store import SecretStoreError
        errors = (*errors, SecretStoreError, CredentialError)
        person = setup.person()
        joining = setup.joins_existing_store(person)
        old = not joining and setup.vault().exists() and not setup.migrated()
        if old:
            setup.unlock_old_vault()
        setup.switch_on(person)
        setup.personal_store(person, joining)
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
