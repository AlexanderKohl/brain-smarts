"""Non-secret Google account registry helpers for Personal CRM."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class GoogleAccountError(RuntimeError):
    """Raised when a Google account alias cannot be resolved."""


SKILL_NAME = "google-workspace-access"
CRM_CONFIG_RELATIVE = Path("skills") / SKILL_NAME / "config" / "crm.json"


def repository_root() -> Path:
    """The brain root: the nearest ancestor holding CONTRACT.md."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    # Fallback for a copy outside a brain: the historical fixed depth.
    return here.parents[5]


def memory_root() -> Path:
    """The owner's memory checkout, /memory/ under the brain root."""
    return repository_root() / "memory"


def owner_timezone(default: str = "UTC") -> str:
    """The IANA timezone named by ``timezone:`` in /memory/OWNER.md, else ``default``."""
    path = memory_root() / "OWNER.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return default
    if not text.startswith("---"):
        return default
    front = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    for line in front.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "timezone":
            value = value.strip().strip("'\"")
            return value or default
    return default


def crm_config_path() -> Path:
    return memory_root() / CRM_CONFIG_RELATIVE


def _brain_path(value: str) -> Path:
    """Resolve a configured path: absolute, or brain-root style ("/memory/...")."""
    path = Path(value)
    if path.is_absolute() and not value.startswith(("/", "\\")):
        return path
    if value.startswith(("/", "\\")):
        return repository_root() / value.lstrip("/\\")
    return memory_root() / value


def crm_config() -> dict[str, Any]:
    path = crm_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAccountError(f"Cannot read CRM configuration {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GoogleAccountError(f"CRM configuration {path} must be a JSON object.")
    return data


def crm_root() -> Path:
    """The owner's Personal CRM node (contacts/, personas/, data/).

    Order: env GOOGLE_CRM_ROOT, then ``crm_root`` in
    /memory/skills/google-workspace-access/config/crm.json.
    """
    override = os.getenv("GOOGLE_CRM_ROOT", "").strip()
    if override:
        return Path(override)
    value = str(crm_config().get("crm_root") or "").strip()
    if not value:
        raise GoogleAccountError(
            "No Personal CRM node configured. Set crm_root in "
            f"{crm_config_path()} (for example \"/memory/projects/<crm-node>\") "
            "or the GOOGLE_CRM_ROOT environment variable."
        )
    return _brain_path(value)


def default_registry_path() -> Path:
    override = os.getenv("GOOGLE_ACCOUNTS_REGISTRY", "").strip()
    if override:
        return Path(override)
    configured = str(crm_config().get("accounts_registry") or "").strip()
    if configured:
        return _brain_path(configured)
    return crm_root() / "data" / "google-accounts.json"


@dataclass(frozen=True)
class GoogleAccount:
    alias: str
    email: str
    vault_entry: str
    used_by_personas: list[str]
    status: str
    notes: str = ""

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "GoogleAccount":
        alias = str(record.get("alias") or "").strip()
        email = str(record.get("email") or "").strip()
        vault_entry = str(record.get("vault_entry") or "").strip()
        if not alias or not email or not vault_entry:
            raise GoogleAccountError(
                "Each Google account registry entry needs alias, email and vault_entry."
            )
        personas = record.get("used_by_personas") or []
        if not isinstance(personas, list):
            raise GoogleAccountError(
                f"used_by_personas for alias {alias!r} must be a list."
            )
        return cls(
            alias=alias,
            email=email,
            vault_entry=vault_entry,
            used_by_personas=[str(item) for item in personas],
            status=str(record.get("status") or "planned"),
            notes=str(record.get("notes") or ""),
        )


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or default_registry_path()
    if not registry_path.exists():
        raise GoogleAccountError(
            f"Google account registry not found: {registry_path}"
        )
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAccountError(
            f"Cannot read Google account registry {registry_path}: {exc}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise GoogleAccountError(
            "Google account registry must contain an accounts list."
        )
    return data


def list_accounts(path: Path | None = None) -> list[GoogleAccount]:
    data = load_registry(path)
    return [GoogleAccount.from_record(item) for item in data["accounts"]]


def get_account(alias: str, path: Path | None = None) -> GoogleAccount:
    cleaned = alias.strip()
    if not cleaned:
        raise GoogleAccountError("A Google account alias is required.")
    for account in list_accounts(path):
        if account.alias == cleaned:
            return account
    known = ", ".join(item.alias for item in list_accounts(path)) or "(none)"
    raise GoogleAccountError(
        f"Unknown Google account alias {cleaned!r}. Known aliases: {known}."
    )


def resolve_alias(explicit: str | None = None) -> str:
    alias = (explicit or os.getenv("GOOGLE_ACCOUNT_ALIAS", "")).strip()
    if not alias:
        raise GoogleAccountError(
            "Provide --account or set GOOGLE_ACCOUNT_ALIAS before Google operations."
        )
    return alias


def resolve_vault_entry(account: GoogleAccount) -> str:
    override = os.getenv("GOOGLE_VAULT_ENTRY", "").strip()
    return override or account.vault_entry
