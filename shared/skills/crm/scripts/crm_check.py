"""Read-only checks for a flat-file contact register (see /shared/skills/crm/SKILL.md).

Commands:
    find        contacts matching an email, phone, handle or name
    validate    front matter, kinds, newsletter invariants and persona references
    duplicates  contacts sharing an email or phone, or with the same normalised name

The CRM node is `--node` (a repository-root path such as /memory/projects/contacts, or an
absolute path); otherwise `crm_root` from
/memory/skills/google-workspace-access/config/crm.json; otherwise /memory/projects/contacts.
Standard library only. Nothing is written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_NODE = "/memory/projects/contacts"
GOOGLE_CONFIG = ("memory", "skills", "google-workspace-access", "config", "crm.json")
CONTACT_KINDS = {"person", "organisation", "newsletter", "system"}
READ_DETAILS = {"subject", "body", "body_and_images"}
REQUIRED = ("id", "title", "type", "contract", "created", "updated")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


# ---------------------------------------------------------------- parsing


def _scalar(value: str) -> Any:
    value = value.strip()
    if value in ("", "null", "Null", "NULL", "~"):
        return None
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_scalar(item) for item in inner.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_front_matter(text: str) -> dict[str, Any] | None:
    """The small YAML subset used by brain front matter: scalars, inline and block lists."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None
    result: dict[str, Any] = {}
    list_key: str | None = None
    for raw in match.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        if stripped.startswith("- ") and list_key is not None:
            result.setdefault(list_key, []).append(_scalar(stripped[2:]))
            continue
        if line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if value.strip() == "":
            result[key] = []
            list_key = key
            continue
        list_key = None
        result[key] = _scalar(value)
    return result


def as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def normalise_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def phone_key(value: str) -> str:
    """Last nine digits, so a national number with a trunk zero matches its international form."""
    return phone_digits(value).lstrip("0")[-9:]


@dataclass
class Record:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def rid(self) -> str:
        return str(self.meta.get("id") or self.path.stem)

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.rid)


def load(path: Path) -> Record:
    text = path.read_text(encoding="utf-8")
    meta = parse_front_matter(text)
    body = FRONT_MATTER_RE.sub("", text, count=1)
    return Record(path=path, meta=meta if meta is not None else {}, body=body)


def records(folder: Path, prefix: str) -> list[Record]:
    if not folder.is_dir():
        return []
    return [load(p) for p in sorted(folder.glob(f"{prefix}*.md")) if not p.name.startswith("_")]


# ---------------------------------------------------------------- node discovery


def brain_root(start: Path) -> Path | None:
    for parent in (start.resolve(), *start.resolve().parents):
        if (parent / "CONTRACT.md").is_file():
            return parent
    return None


MSYS_HINT = ("Git Bash rewrites an argument that starts with / into a Windows path; "
             "run the command with MSYS_NO_PATHCONV=1 in front")


def looks_path_converted(value: str | None) -> bool:
    """True for a repository-root path that Git Bash (MSYS) has turned into a Windows path."""
    return bool(value) and bool(re.match(r"^[A-Za-z]:[\/]", str(value))) and (
        bool(os.environ.get("MSYSTEM")) or bool(re.search(r"[\/]Git[\/]", str(value), re.I)))


def resolve_node(node: str | None, cwd: Path) -> Path:
    root = brain_root(cwd) or brain_root(Path(__file__).resolve().parent)
    candidate = node
    if candidate is None and root is not None:
        config = root.joinpath(*GOOGLE_CONFIG)
        if config.is_file():
            try:
                candidate = json.loads(config.read_text(encoding="utf-8")).get("crm_root")
            except (OSError, ValueError):
                candidate = None
    candidate = candidate or DEFAULT_NODE
    path = Path(candidate)
    if path.is_absolute() and path.exists():
        return path
    if candidate.startswith("/") and root is not None:
        return root / candidate.lstrip("/")
    return (cwd / candidate).resolve()


# ---------------------------------------------------------------- checks


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(node: Path) -> Report:
    report = Report()
    contacts_dir, personas_dir = node / "contacts", node / "personas"
    if not contacts_dir.is_dir():
        report.errors.append(f"{node}: no contacts/ folder")
        return report

    personas = records(personas_dir, "persona-")
    keys: set[str] = set()
    for persona in personas:
        name = persona.path.name
        _required(persona, "persona", report)
        key = str(persona.meta.get("persona_key") or "")
        if not key:
            report.errors.append(f"personas/{name}: persona_key missing")
            continue
        keys.add(key)
        if persona.path.stem != f"persona-{key}":
            report.warnings.append(f"personas/{name}: file name does not match persona_key {key}")

    for contact in records(contacts_dir, "contact-"):
        name = contact.path.name
        meta = contact.meta
        _required(contact, "contact", report)
        kind = meta.get("contact_kind") or "person"
        if kind not in CONTACT_KINDS:
            report.errors.append(f"contacts/{name}: unknown contact_kind {kind}")
        is_newsletter = kind == "newsletter" or meta.get("newsletter") is True
        detail = meta.get("newsletter_read_detail")
        reply = meta.get("preferred_reply_persona")
        if is_newsletter:
            if detail not in READ_DETAILS:
                report.errors.append(
                    f"contacts/{name}: newsletter needs newsletter_read_detail "
                    f"subject, body or body_and_images (found {detail})"
                )
            if reply is not None:
                report.warnings.append(
                    f"contacts/{name}: newsletter has preferred_reply_persona {reply}; "
                    "keep it only if the owner set it"
                )
        elif detail is not None:
            report.warnings.append(
                f"contacts/{name}: newsletter_read_detail set on a non-newsletter"
            )
        if personas_dir.is_dir():
            for ref in ([reply] if reply else []) + as_list(meta.get("receiving_personas")):
                if ref not in keys:
                    report.errors.append(f"contacts/{name}: unknown persona {ref}")
    return report


def _required(record: Record, expected_type: str, report: Report) -> None:
    folder = record.path.parent.name
    if not record.meta:
        report.errors.append(f"{folder}/{record.path.name}: missing front matter")
        return
    missing = [key for key in REQUIRED if not record.meta.get(key)]
    if missing:
        report.errors.append(
            f"{folder}/{record.path.name}: missing {', '.join(missing)}"
        )
    if record.meta.get("type") not in (None, expected_type):
        report.errors.append(
            f"{folder}/{record.path.name}: type must be {expected_type}"
        )
    if record.meta.get("id") and str(record.meta["id"]) != record.path.stem:
        report.errors.append(
            f"{folder}/{record.path.name}: id {record.meta['id']} does not match the file name"
        )


def contact_keys(record: Record) -> dict[str, set[str]]:
    meta = record.meta
    return {
        "email": {e.strip().lower() for e in as_list(meta.get("emails")) if "@" in e},
        "phone": {d for d in (phone_key(p) for p in as_list(meta.get("phones"))) if len(d) >= 6},
        "name": {normalise_name(record.title)} - {""},
        "handle": {h.strip().lower() for h in as_list(meta.get("social_accounts"))},
    }


def duplicates(node: Path) -> list[dict[str, Any]]:
    index: dict[tuple[str, str], list[str]] = {}
    for contact in records(node / "contacts", "contact-"):
        for kind, values in contact_keys(contact).items():
            if kind == "handle":
                continue
            for value in values:
                index.setdefault((kind, value), []).append(contact.rid)
    groups = [
        {"by": kind, "value": value, "contacts": sorted(ids)}
        for (kind, value), ids in index.items()
        if len(set(ids)) > 1
    ]
    return sorted(groups, key=lambda g: (g["by"], g["value"]))


def find(
    node: Path,
    *,
    email: str | None = None,
    phone: str | None = None,
    handle: str | None = None,
    name: str | None = None,
) -> list[Record]:
    email_l = (email or "").strip().lower()
    phone_d = phone_key(phone or "")
    handle_l = (handle or "").strip().lower()
    name_n = normalise_name(name or "")
    if not (email_l or phone_d or handle_l or name_n):
        return []
    found: list[Record] = []
    for contact in records(node / "contacts", "contact-"):
        keys = contact_keys(contact)
        body = contact.body.lower()
        checks = []
        if email_l:
            checks.append(email_l in keys["email"] or email_l in body)
        if phone_d:
            checks.append(phone_d in keys["phone"])
        if handle_l:
            checks.append(any(handle_l in h for h in keys["handle"]) or handle_l in body)
        if name_n:
            checks.append(name_n in normalise_name(contact.title) or name_n in contact.rid.replace("-", " "))
        if all(checks):
            found.append(contact)
    return found


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--node", help="CRM node path (repository-root or absolute)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("find", help="contacts matching every identifier given")
    f.add_argument("--email")
    f.add_argument("--phone")
    f.add_argument("--handle")
    f.add_argument("--name")
    sub.add_parser("validate", help="check contact and persona files")
    sub.add_parser("duplicates", help="list likely duplicate contacts")
    args = parser.parse_args(argv)

    node = resolve_node(args.node, cwd or Path.cwd())
    if not node.is_dir():
        hint = f" ({MSYS_HINT})" if looks_path_converted(args.node) else ""
        print(f"ERROR: CRM node not found: {node}{hint}")
        return 2

    if args.command == "find":
        hits = find(node, email=args.email, phone=args.phone, handle=args.handle, name=args.name)
        rows = [{"id": r.rid, "title": r.title, "path": r.path.as_posix()} for r in hits]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f"{row['id']}\t{row['title']}")
            print(f"{len(rows)} match(es)")
        return 0

    if args.command == "validate":
        report = validate(node)
        if args.json:
            print(json.dumps({"errors": report.errors, "warnings": report.warnings}, indent=2))
        else:
            for line in report.errors:
                print(f"ERROR: {line}")
            for line in report.warnings:
                print(f"WARN: {line}")
            print(f"{'FAIL' if report.errors else 'PASS'}: {len(report.errors)} error(s), "
                  f"{len(report.warnings)} warning(s)")
        return 1 if report.errors else 0

    groups = duplicates(node)
    if args.json:
        print(json.dumps(groups, indent=2))
    else:
        for group in groups:
            print(f"{group['by']} {group['value']}: {', '.join(group['contacts'])}")
        print(f"{len(groups)} duplicate group(s)")
    return 1 if groups else 0


if __name__ == "__main__":
    sys.exit(main())
