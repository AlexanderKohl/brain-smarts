"""Personal CRM contact and persona resolution for Google side effects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .accounts import GoogleAccount, GoogleAccountError, crm_root, get_account


class GoogleCrmError(RuntimeError):
    """Raised when CRM contact or persona resolution fails."""


FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def personal_crm_root() -> Path:
    """The owner's CRM node, configured under /memory/skills/google-workspace-access/config/."""
    try:
        return crm_root()
    except GoogleAccountError as exc:
        raise GoogleCrmError(str(exc)) from exc


def contacts_dir() -> Path:
    return personal_crm_root() / "contacts"


def personas_dir() -> Path:
    return personal_crm_root() / "personas"


def _parse_simple_front_matter(text: str) -> dict[str, Any]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") or line.startswith("- "):
            if current_list_key is None:
                continue
            value = line.split("- ", 1)[1].strip().strip("'\"")
            result.setdefault(current_list_key, []).append(value)
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_list_key = None
        if value == "" or value == "[]":
            result[key] = []
            current_list_key = key
            continue
        if value in ("null", "Null", "~"):
            result[key] = None
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                result[key] = [
                    item.strip().strip("'\"") for item in inner.split(",")
                ]
            continue
        result[key] = value.strip("'\"")
    return result


@dataclass
class ContactRecord:
    path: Path
    metadata: dict[str, Any]
    body: str

    @property
    def contact_id(self) -> str:
        return str(self.metadata.get("id") or self.path.stem)

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.contact_id)

    @property
    def preferred_reply_persona(self) -> str | None:
        value = self.metadata.get("preferred_reply_persona")
        if value in (None, "", "null"):
            return None
        return str(value)


@dataclass
class PersonaRecord:
    path: Path
    metadata: dict[str, Any]
    body: str

    @property
    def persona_key(self) -> str:
        return str(
            self.metadata.get("persona_key")
            or self.path.stem.removeprefix("persona-")
        )

    @property
    def google_account_alias(self) -> str | None:
        value = self.metadata.get("google_account_alias")
        if value in (None, "", "null"):
            return None
        return str(value)

    @property
    def primary_from_email(self) -> str | None:
        value = self.metadata.get("primary_from_email")
        if value in (None, "", "null"):
            return None
        return str(value)


@dataclass
class CrmResolution:
    contact: ContactRecord | None
    persona: PersonaRecord | None
    account: GoogleAccount | None
    confirmation_required: bool
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "contact": None
            if self.contact is None
            else {
                "id": self.contact.contact_id,
                "title": self.contact.title,
                "path": str(self.contact.path).replace("\\", "/"),
                "preferred_reply_persona": self.contact.preferred_reply_persona,
            },
            "persona": None
            if self.persona is None
            else {
                "persona_key": self.persona.persona_key,
                "path": str(self.persona.path).replace("\\", "/"),
                "google_account_alias": self.persona.google_account_alias,
                "primary_from_email": self.persona.primary_from_email,
            },
            "account": None
            if self.account is None
            else {
                "alias": self.account.alias,
                "email": self.account.email,
                "vault_entry": self.account.vault_entry,
                "status": self.account.status,
            },
            "confirmation_required": self.confirmation_required,
            "notes": self.notes,
        }


def load_contact_file(path: Path) -> ContactRecord:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GoogleCrmError(f"Cannot read contact file {path}: {exc}") from exc
    metadata = _parse_simple_front_matter(text)
    body = FRONT_MATTER_RE.sub("", text, count=1)
    return ContactRecord(path=path, metadata=metadata, body=body)


def load_persona_file(path: Path) -> PersonaRecord:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GoogleCrmError(f"Cannot read persona file {path}: {exc}") from exc
    metadata = _parse_simple_front_matter(text)
    body = FRONT_MATTER_RE.sub("", text, count=1)
    return PersonaRecord(path=path, metadata=metadata, body=body)


def iter_contacts() -> list[ContactRecord]:
    root = contacts_dir()
    if not root.exists():
        return []
    records: list[ContactRecord] = []
    for path in sorted(root.glob("contact-*.md")):
        if path.name.startswith("_"):
            continue
        records.append(load_contact_file(path))
    return records


def find_contacts(
    *,
    email: str | None = None,
    name: str | None = None,
    contact_id: str | None = None,
) -> list[ContactRecord]:
    if contact_id:
        path = contacts_dir() / f"{contact_id}.md"
        if not path.exists() and not contact_id.startswith("contact-"):
            path = contacts_dir() / f"contact-{contact_id}.md"
        if path.exists():
            return [load_contact_file(path)]
        return []

    email_l = (email or "").strip().lower()
    name_l = (name or "").strip().lower()
    matches: list[ContactRecord] = []
    for record in iter_contacts():
        emails = [
            str(item).lower()
            for item in (record.metadata.get("emails") or [])
            if item
        ]
        title = record.title.lower()
        cid = record.contact_id.lower()
        email_ok = not email_l or email_l in emails or email_l in record.body.lower()
        name_ok = not name_l or name_l in title or name_l in cid
        if email_ok and name_ok and (email_l or name_l):
            matches.append(record)
    return matches


def load_persona(persona_key: str) -> PersonaRecord:
    key = persona_key.strip()
    if not key:
        raise GoogleCrmError("A persona_key is required.")
    candidates = [
        personas_dir() / f"persona-{key}.md",
        personas_dir() / f"{key}.md",
    ]
    for path in candidates:
        if path.exists():
            return load_persona_file(path)
    raise GoogleCrmError(
        f"Persona file not found for key {key!r} under {personas_dir()}."
    )


def resolve_for_side_effect(
    *,
    contact_id: str | None = None,
    email: str | None = None,
    name: str | None = None,
    persona_key: str | None = None,
    account_alias: str | None = None,
    allow_missing_contact: bool = False,
) -> CrmResolution:
    """Resolve contact → persona → google_account_alias before side effects.

    CONTRACT §10.5: when more than one plausible target exists, confirmation is
    required and the caller must stop and ask the owner.
    """
    notes: list[str] = []
    confirmation_required = False
    contact: ContactRecord | None = None
    persona: PersonaRecord | None = None
    account: GoogleAccount | None = None

    contacts = find_contacts(email=email, name=name, contact_id=contact_id)
    if len(contacts) > 1:
        confirmation_required = True
        notes.append(
            "Multiple CRM contacts matched; present candidates and ask the owner."
        )
        return CrmResolution(
            contact=None,
            persona=None,
            account=None,
            confirmation_required=True,
            notes=notes
            + [
                f"{item.contact_id}: {item.title} ({item.path.name})"
                for item in contacts
            ],
        )
    if len(contacts) == 1:
        contact = contacts[0]
    elif not allow_missing_contact and (email or name or contact_id):
        raise GoogleCrmError(
            "No matching CRM contact file found. Create or identify the contact first."
        )
    elif not allow_missing_contact:
        notes.append(
            "No contact filter supplied; resolve or create the contact before "
            "person-linked side effects."
        )
        confirmation_required = True

    resolved_persona_key = persona_key
    if contact and not resolved_persona_key:
        resolved_persona_key = contact.preferred_reply_persona
    if not resolved_persona_key:
        confirmation_required = True
        notes.append(
            "No preferred_reply_persona on the contact and no --persona supplied; "
            "ask which persona/company identity to use."
        )
    else:
        persona = load_persona(resolved_persona_key)

    resolved_alias = account_alias
    if persona and not resolved_alias:
        resolved_alias = persona.google_account_alias
    if not resolved_alias:
        confirmation_required = True
        notes.append(
            "No google_account_alias resolved from persona; ask which Google "
            "account alias to use (CONTRACT §10.5)."
        )
    else:
        try:
            account = get_account(resolved_alias)
        except GoogleAccountError as exc:
            raise GoogleCrmError(str(exc)) from exc
        if account_alias and persona and persona.google_account_alias:
            if account_alias != persona.google_account_alias:
                confirmation_required = True
                notes.append(
                    f"Requested account alias {account_alias!r} differs from "
                    f"persona alias {persona.google_account_alias!r}; confirm "
                    "with the owner before proceeding."
                )

    return CrmResolution(
        contact=contact,
        persona=persona,
        account=account,
        confirmation_required=confirmation_required,
        notes=notes,
    )
