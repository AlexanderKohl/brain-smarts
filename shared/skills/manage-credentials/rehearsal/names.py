"""Fixed names for one rehearsal run (rehearsal plan, section 2) and the environment every child
process gets. Pure: nothing here touches the disk, the keychain or a process."""

from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AGENT_NAME = "PortableAIBrainVaultAgent"
# The keys store_ops.load_config accepts (scripts/secret_store/store_ops.py, CONFIG_KEYS).
CONFIG_KEYS = frozenset({"enabled", "person", "computer", "personal_repo_url", "personal_clone",
                         "checkpoint_dir", "recovery_package_dir", "team_repo_url", "team_clone"})
PCS = ("pc1", "pc2")
SCRIPTS_RELATIVE = Path("shared") / "skills" / "manage-credentials" / "scripts"
CONFIG_RELATIVE = Path("memory") / "skills" / "manage-credentials" / "config" / "secret-store.json"
VAULT_RELATIVE = Path("memory") / "projects" / "credential-management" / "data" / "credentials.vault"
# Removed from every child environment, compared in upper case (Windows names ignore case).
DROPPED_VARIABLES = frozenset({
    "PORTABLE_VAULT_PASSPHRASE", "PORTABLE_VAULT_PATH", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN", "GH_HOST", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "PYTHONPATH", "PYTHONHOME",
    "PYTHONSTARTUP", "XDG_RUNTIME_DIR", "GIT_DIR", "GIT_WORK_TREE",
})
SECRET_VARIABLES = ("PORTABLE_VAULT_PASSPHRASE", "GH_TOKEN", "GITHUB_TOKEN")


@dataclass(frozen=True)
class RunNames:
    run_id: str
    temp: Path
    cloud_root: Path | None

    @property
    def person(self) -> str:
        return f"rehearsal-{self.run_id}"

    def computer(self, pc: str) -> str:
        return f"rehearsal-{pc}-{self.run_id}"

    def keychain_user(self, pc: str) -> str:
        return f"{self.person}@{self.computer(pc)}"

    def brain(self, pc: str) -> Path:
        return self.temp / pc / "brain"

    def scripts(self, pc: str) -> Path:
        return self.brain(pc) / SCRIPTS_RELATIVE

    def config_path(self, pc: str) -> Path:
        return self.brain(pc) / CONFIG_RELATIVE

    def vault(self, pc: str) -> Path:
        return self.brain(pc) / VAULT_RELATIVE

    @property
    def remotes(self) -> Path:
        return self.temp / "remotes"

    def remote(self, kind: str) -> Path:
        return self.remotes / f"{kind}.git"

    def clone(self, pc: str, kind: str) -> Path:
        return self.temp / pc / "clones" / kind

    def checkpoint(self, pc: str) -> Path:
        return self.temp / pc / "checkpoint"

    def home(self, pc: str) -> Path:
        return self.temp / pc / "home"

    def local_app_data(self, pc: str) -> Path:
        return self.home(pc) / "AppData" / "Local"

    def state_file(self, pc: str) -> Path:
        return self.home(pc) / ".portable-ai-brain" / "vault-agent" / "agent-state.json"

    @property
    def recovery_dir(self) -> Path | None:
        return self.cloud_root / f"brain-rehearsal-{self.run_id}" if self.cloud_root else None

    def pipe(self, pc: str) -> str:
        return f"{DEFAULT_AGENT_NAME}-rehearsal-{self.run_id}-{pc}"

    @property
    def gh_empty(self) -> Path:
        return self.temp / "gh-empty"

    @property
    def tls_dir(self) -> Path:
        return self.temp / "tls"

    @property
    def ca_file(self) -> Path:
        return self.tls_dir / "cert.pem"

    @property
    def restore_dir(self) -> Path:
        return self.temp / "restore"


def new_names(temp_parent: str | os.PathLike | None = None, cloud_root: str | os.PathLike | None = None,
              run_id: str | None = None) -> RunNames:
    run_id = run_id or secrets.token_hex(4)
    parent = Path(temp_parent or tempfile.gettempdir())
    return RunNames(run_id, parent / f"brain-rehearsal-{run_id}", Path(cloud_root) if cloud_root else None)


def cloud_root_from(environ: dict) -> Path | None:
    """The OneDrive folder the store would use (store_ops.recovery_package_place), when it exists."""
    for key in ("OneDrive", "OneDriveConsumer"):
        value = next((v for k, v in environ.items() if k.upper() == key.upper()), None)
        if value and Path(value).is_dir():
            return Path(value)
    return None


def config_for(n: RunNames, pc: str, enabled: bool = True) -> dict:
    """secret-store.json for one rehearsal computer: every path the store would default is named."""
    return {
        "enabled": enabled,
        "person": n.person,
        "computer": n.computer(pc),
        "personal_repo_url": str(n.remote("personal")),
        "team_repo_url": str(n.remote("team")),
        "personal_clone": str(n.clone(pc, "personal")),
        "team_clone": str(n.clone(pc, "team")),
        "checkpoint_dir": str(n.checkpoint(pc)),
        "recovery_package_dir": str(n.recovery_dir) if n.recovery_dir else "",
    }


def child_env(base: dict, n: RunNames, pc: str) -> dict:
    """The environment of every child process for one rehearsal computer (plan section 2)."""
    env = {k: v for k, v in base.items() if k.upper() not in DROPPED_VARIABLES}
    home = str(n.home(pc))
    env.update({
        "USERPROFILE": home,
        "HOME": home,
        "LOCALAPPDATA": str(n.local_app_data(pc)),
        "GH_CONFIG_DIR": str(n.gh_empty),
        "GIT_AUTHOR_NAME": "rehearsal", "GIT_AUTHOR_EMAIL": "rehearsal@example.com",
        "GIT_COMMITTER_NAME": "rehearsal", "GIT_COMMITTER_EMAIL": "rehearsal@example.com",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_PROXY": "127.0.0.1,localhost",
        "PYTHONIOENCODING": "utf-8",
        "REHEARSAL_PIPE_NAME": n.pipe(pc),
        "REHEARSAL_CA_FILE": str(n.ca_file),
        "REHEARSAL_SCRIPTS": str(n.scripts(pc)),
    })
    return env
