"""The guard of rehearsal plan section 3: what a child process sees (the probe, gathered by
wrapper.py inside the rehearsal environment) is judged here, item by item. Pure apart from
record_baseline, which only reads the owner's files' names, times and one pid."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from names import RunNames

DEFAULT_PIPE = r"\\.\pipe\PortableAIBrainVaultAgent"
ALLOWED_BACKENDS = frozenset({  # scripts/secret_store/keys.py, ALLOWED_BACKENDS
    "keyring.backends.Windows.WinVaultKeyring",
    "keyring.backends.macOS.Keyring",
    "keyring.backends.SecretService.Keyring",
})
OWNER_RECOVERY_FOLDER = "brain-secrets-recovery"


@dataclass(frozen=True)
class Item:
    number: int
    name: str
    ok: bool
    text: str


def under(path: object, root: Path) -> bool:
    """Whether path is root or inside it, after resolving both."""
    if not path:
        return False
    try:
        here, top = Path(str(path)).resolve(), Path(root).resolve()
    except (OSError, ValueError):
        return False
    return here == top or top in here.parents


def _same(a: object, b: Path) -> bool:
    try:
        return bool(a) and Path(str(a)).resolve() == Path(b).resolve()
    except (OSError, ValueError):
        return False


def _item(number: int, name: str, problems: list[str], fine: str) -> Item:
    return Item(number, name, not problems, "; ".join(problems) if problems else fine)


def _brain_root(probe: dict, n: RunNames, pc: str) -> Item:
    problems = [f"{label} finds a brain root outside the run folder"
                for label, key in (("portable_vault", "root_vault"), ("store_ops", "root_store"))
                if not _same(probe.get(key), n.brain(pc))]
    return _item(1, "brain root", problems, "both find_brain_root calls name the throwaway brain")


def _config(probe: dict, n: RunNames, pc: str) -> Item:
    config = probe.get("config")
    if not isinstance(config, dict) or "error" in config:
        reason = config.get("error") if isinstance(config, dict) else "no configuration"
        return Item(2, "store configuration", False, f"load_config failed: {reason}")
    problems = []
    if not str(config.get("person") or "").startswith("rehearsal-"):
        problems.append("the person is not a rehearsal person")
    if not str(config.get("computer") or "").startswith("rehearsal-pc"):
        problems.append("the computer is not a rehearsal computer")
    for key in ("personal_clone", "team_clone", "checkpoint_dir"):
        if not under(config.get(key), n.temp):
            problems.append(f"{key} is outside the run folder")
    if n.recovery_dir is None:
        problems.append("no OneDrive folder was found for the recovery package")
    elif not _same(config.get("recovery_package_dir"), n.recovery_dir):
        problems.append("recovery_package_dir is not the run's own cloud subfolder")
    for key in ("personal_repo_url", "team_repo_url"):
        value = str(config.get(key) or "")
        if not value or "://" in value or not under(value, n.remotes):
            problems.append(f"{key} is not a local bare repository of the run (gh would create a real one)")
    return _item(2, "store configuration", problems, "person, computer, clones, checkpoint, package folder and "
                 "remotes are the run's own")


def _vault(probe: dict, n: RunNames) -> Item:
    problems = []
    if not under(probe.get("vault_path"), n.temp):
        problems.append("the default vault path is outside the run folder")
    if probe.get("env_vault") and not under(probe.get("env_vault"), n.temp):
        problems.append("PORTABLE_VAULT_PATH names a vault outside the run folder")
    return _item(3, "vault path", problems, "the default vault and any PORTABLE_VAULT_PATH are under the run folder")


def _agent(probe: dict, n: RunNames, pc: str) -> Item:
    problems = []
    if not under(probe.get("runtime_base"), n.temp):
        problems.append("the agent's state file and lock would be the owner's")
    address = str(probe.get("ipc_address") or "")
    if not address or address.lower() == DEFAULT_PIPE.lower():
        problems.append("the agent pipe is the shared one")
    elif os.name == "nt" and address != rf"\\.\pipe\{n.pipe(pc)}":
        problems.append("the agent pipe is not the run's own")
    return _item(4, "agent runtime and pipe", problems, "state file under the run folder, pipe " + n.pipe(pc))


def _keychain(probe: dict, n: RunNames, check_mode: bool) -> Item:
    problems = []
    backend = str(probe.get("backend") or "")
    if backend not in ALLOWED_BACKENDS or (os.name == "nt" and not backend.endswith("WinVaultKeyring")):
        problems.append(f"keychain backend {backend or 'unknown'} is not the allowed one")
    present = probe.get("keychain")
    if present is None:
        if not check_mode:
            problems.append("the rehearsal keychain users were not checked")
        fine = "backend allowed; entries not read in --check"
    else:
        problems += [f"a keychain entry already exists for {user}" for user in sorted(present) if present[user]]
        fine = "backend allowed; no entry for either rehearsal user"
    return _item(5, "keychain", problems, fine)


def _environment(probe: dict) -> Item:
    problems = [f"{name} is set" for name in sorted(probe.get("env_secret_names") or [])]
    if probe.get("gh_status") == 0:
        problems.append("gh is signed in inside the rehearsal environment")
    return _item(6, "environment", problems, "no passphrase or GitHub token; gh is not signed in")


def evaluate(probe: dict, n: RunNames, pc: str, *, check_mode: bool) -> list[Item]:
    """Guard items 1 to 6, in the plan's order."""
    return [_brain_root(probe, n, pc), _config(probe, n, pc), _vault(probe, n), _agent(probe, n, pc),
            _keychain(probe, n, check_mode), _environment(probe)]


def first_failure(items: list[Item]) -> Item | None:
    return next((item for item in items if not item.ok), None)


# -- item 7: the owner's state, recorded before and compared after ---------------------------------
def _listing(folder: Path) -> dict | None:
    if not folder.is_dir():
        return None
    return {child.name: child.stat().st_mtime_ns for child in sorted(folder.iterdir(), key=lambda p: p.name)}


def _env(environ: dict, key: str) -> str | None:
    return next((v for k, v in environ.items() if k.upper() == key.upper()), None)


def record_baseline(environ: dict) -> dict:
    """The owner's agent state file (its time and the pid it names, never the authkey), the owner's
    recovery-package folder and checkpoint folder (names and times). Nothing is opened for writing."""
    home = Path(_env(environ, "USERPROFILE") or Path.home())
    state_file = home / ".portable-ai-brain" / "vault-agent" / "agent-state.json"
    state = None
    if state_file.is_file():
        pid = None
        try:
            pid = int(json.loads(state_file.read_text("utf-8")).get("pid") or 0)
        except (OSError, ValueError, AttributeError):
            pid = None
        state = {"mtime": state_file.stat().st_mtime_ns, "pid": pid}
    cloud = _env(environ, "OneDrive") or _env(environ, "OneDriveConsumer")
    local = Path(_env(environ, "LOCALAPPDATA") or home / "AppData" / "Local")
    return {"state": state,
            "recovery": _listing(Path(cloud) / OWNER_RECOVERY_FOLDER) if cloud else None,
            "checkpoint": _listing(local / "brain-secrets")}


def compare_baseline(before: dict, after: dict) -> list[str]:
    labels = {"state": "the owner's agent state file", "recovery": "the owner's recovery-package folder",
              "checkpoint": "the owner's checkpoint folder"}
    return [f"{labels[key]} changed" for key in ("checkpoint", "recovery", "state") if before.get(key) != after.get(key)]


def baseline_item(baseline: dict | None, error: str | None = None) -> Item:
    if baseline is None:
        return Item(7, "owner baseline", False, f"the owner's state could not be recorded ({error})")
    return Item(7, "owner baseline", True, "agent state file, recovery-package folder and checkpoint folder recorded")
