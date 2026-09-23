"""Google Contacts search/read (People API) and CRM identifier sync helper."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from _cli_common import add_account_arg, print_json
from google_oauth import GoogleConnection, GoogleOAuthError
from google_oauth.accounts import resolve_alias
from google_oauth.crm import (
    GoogleCrmError,
    contacts_dir,
    find_contacts,
    iter_contacts,
    load_contact_file,
)


# personFields / readMask paths only — resourceName is a top-level Person field
# returned automatically; including it yields HttpError 400 (invalid mask path).
PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations,metadata"
LIST_PAGE_SIZE_MAX = 1000


def _service(account: str | None) -> Any:
    return GoogleConnection.from_environment(account).build_service("people", "v1")


def _now_brisbane() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=10))).strftime(
        "%Y-%m-%dT%H:%M:%S+10:00"
    )


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "unknown"


def _summarise_person(person: dict[str, Any]) -> dict[str, Any]:
    names = person.get("names") or []
    emails = [
        item.get("value")
        for item in (person.get("emailAddresses") or [])
        if item.get("value")
    ]
    phones = [
        item.get("value")
        for item in (person.get("phoneNumbers") or [])
        if item.get("value")
    ]
    orgs = [
        item.get("name")
        for item in (person.get("organizations") or [])
        if item.get("name")
    ]
    display = names[0].get("displayName") if names else None
    return {
        "resourceName": person.get("resourceName"),
        "displayName": display,
        "emails": emails,
        "phones": phones,
        "organizations": orgs,
    }


def _yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "\n" + "\n".join(f"  - {item}" for item in values)


def _merge_unique(existing: list[Any], incoming: list[str]) -> list[str]:
    seen: list[str] = []
    for item in list(existing or []) + incoming:
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _replace_front_matter_field(text: str, key: str, rendered: str) -> str:
    pattern = re.compile(
        rf"(?m)^({re.escape(key)}:\s*)(?:\[\].*|(?:null)|(?:~)|(?:\".*\")|(?:'.*')|"
        rf"(?:[^\n]*)|(?:\n(?:  - .+\n?)*))",
    )
    replacement = f"{key}: {rendered}"
    if pattern.search(text):
        return pattern.sub(replacement + "\n", text, count=1)
    return text.replace("\n---\n", f"\n{replacement}\n---\n", 1)


def _list_all_connections(service: Any, *, page_size: int) -> list[dict[str, Any]]:
    page_size = max(1, min(page_size, LIST_PAGE_SIZE_MAX))
    people: list[dict[str, Any]] = []
    page_token: str | None = None
    pages = 0
    while True:
        kwargs: dict[str, Any] = {
            "resourceName": "people/me",
            "personFields": PERSON_FIELDS,
            "pageSize": page_size,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        response = service.people().connections().list(**kwargs).execute()
        pages += 1
        for person in response.get("connections") or []:
            people.append(person)
        page_token = response.get("nextPageToken") or None
        if not page_token:
            break
    return people


def _match_crm_for_summary(summary: dict[str, Any]) -> Path | None:
    """Find existing CRM contact by email, google ref, or exact title."""
    emails = [str(e).strip().lower() for e in (summary.get("emails") or []) if e]
    resource = summary.get("resourceName") or ""
    display = (summary.get("displayName") or "").strip().lower()

    for record in iter_contacts():
        meta = record.metadata
        crm_emails = {
            str(e).strip().lower() for e in (meta.get("emails") or []) if e
        }
        if emails and crm_emails.intersection(emails):
            return record.path
        refs = [str(r) for r in (meta.get("google_contact_refs") or [])]
        if resource and any(resource in r for r in refs):
            return record.path
        if display and record.title.strip().lower() == display:
            return record.path
    return None


def _ensure_contact_file(
    *,
    contact_path: Path,
    title: str,
    alias: str,
    created_note: str,
) -> bool:
    """Create template-shaped contact file if missing. Returns True if created."""
    if contact_path.exists():
        return False
    now = _now_brisbane()
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    contact_path.write_text(
        f"""---
id: {contact_path.stem}
title: {title}
type: contact
schema_version: 0.2
contract: /CONTRACT.md
status: active
contact_kind: person
receiving_personas: []
preferred_reply_persona: null
newsletter: false
newsletter_read_detail: null
emails: []
phones: []
organisations: []
social_accounts: []
google_contact_refs: []
related_task_refs: []
related_project_refs: []
created: {now}
updated: {now}
---

# {title}

## Overview

{created_note}

## Identifiers

- Emails:
- Phones:
- Organisations:
- Social accounts (platform → handle or URL):
- Google Contacts (account alias → resource name):

## Relationship

(not yet recorded)

## Reply guidance

- Preferred persona / company identity: (persona_key, or null / ask)
- Receiving personas (mail To / delivery identities): (persona_key list)
- Tone / do:
- Don't:

## Newsletter handling (when `contact_kind: newsletter` or `newsletter: true`)

- `newsletter_read_detail`: `subject` (default) | `body` | `body_and_images`
- Agents default to subject-only unless this flag says otherwise.
- Do not invent a reply persona; leave `preferred_reply_persona` null for newsletters.

## Notes

- {now[:10]}: {created_note}

## Open loops

- None.
""",
        encoding="utf-8",
    )
    return True


def _merge_summary_into_contact(
    contact_path: Path,
    summary: dict[str, Any],
    *,
    alias: str,
    note_line: str | None = None,
) -> dict[str, Any]:
    """Merge Google identifiers into CRM file. Does not overwrite relationship notes."""
    ref = f"{alias}:{summary['resourceName']}"
    record = load_contact_file(contact_path)
    emails = _merge_unique(record.metadata.get("emails") or [], summary["emails"])
    phones = _merge_unique(record.metadata.get("phones") or [], summary["phones"])
    organisations = _merge_unique(
        record.metadata.get("organisations") or [], summary["organizations"]
    )
    refs = _merge_unique(record.metadata.get("google_contact_refs") or [], [ref])
    now = _now_brisbane()
    text = contact_path.read_text(encoding="utf-8")
    text = _replace_front_matter_field(text, "emails", _yaml_list(emails))
    text = _replace_front_matter_field(text, "phones", _yaml_list(phones))
    text = _replace_front_matter_field(
        text, "organisations", _yaml_list(organisations)
    )
    text = _replace_front_matter_field(
        text, "google_contact_refs", _yaml_list(refs)
    )
    text = _replace_front_matter_field(text, "updated", now)
    if "## Identifiers" in text:
        ident = (
            "## Identifiers\n\n"
            f"- Emails: {', '.join(emails) if emails else ''}\n"
            f"- Phones: {', '.join(phones) if phones else ''}\n"
            f"- Organisations: {', '.join(organisations) if organisations else ''}\n"
            "- Social accounts (platform → handle or URL):\n"
            f"- Google Contacts (account alias → resource name): {', '.join(refs)}\n"
        )
        text = re.sub(
            r"## Identifiers\n.*?(?=\n## |\Z)",
            ident + "\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    if note_line and "## Notes" in text:
        # Append dated note once if not already present.
        if note_line not in text:
            text = text.replace(
                "## Notes\n\n",
                f"## Notes\n\n- {now[:10]}: {note_line}\n\n",
                1,
            )
    contact_path.write_text(text, encoding="utf-8")
    return {
        "contact_path": str(contact_path).replace("\\", "/"),
        "emails": emails,
        "phones": phones,
        "organisations": organisations,
        "google_contact_refs": refs,
    }


def cmd_search(args: argparse.Namespace) -> int:
    service = _service(args.account)
    response = (
        service.people()
        .searchContacts(query=args.query, readMask=PERSON_FIELDS, pageSize=args.max)
        .execute()
    )
    results = []
    for item in response.get("results") or []:
        person = item.get("person") or {}
        results.append(_summarise_person(person))
    print_json({"query": args.query, "results": results})
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    service = _service(args.account)
    people = _list_all_connections(service, page_size=args.page_size)
    summaries = [_summarise_person(p) for p in people]
    print_json(
        {
            "account": resolve_alias(args.account),
            "count": len(summaries),
            "complete": True,
            "people": summaries,
        }
    )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    service = _service(args.account)
    person = (
        service.people()
        .get(resourceName=args.resource_name, personFields=PERSON_FIELDS)
        .execute()
    )
    print_json({"summary": _summarise_person(person), "person": person})
    return 0


def cmd_sync_to_crm(args: argparse.Namespace) -> int:
    """Map a Google contact into a CRM contact file identifiers section."""
    if not args.i_approve_write:
        print(
            "Refusing CRM file write without --i-approve-write.",
            file=sys.stderr,
        )
        return 3

    service = _service(args.account)
    person = (
        service.people()
        .get(resourceName=args.resource_name, personFields=PERSON_FIELDS)
        .execute()
    )
    summary = _summarise_person(person)
    alias = resolve_alias(args.account)

    contact_path: Path | None = None
    created = False
    if args.contact_id:
        matches = find_contacts(contact_id=args.contact_id)
        if not matches:
            raise GoogleCrmError(f"CRM contact not found: {args.contact_id}")
        contact_path = matches[0].path
    elif args.create_contact_id:
        contact_path = contacts_dir() / f"{args.create_contact_id}.md"
        if not args.create_contact_id.startswith("contact-"):
            contact_path = contacts_dir() / f"contact-{args.create_contact_id}.md"
        if contact_path.exists() and not args.force:
            raise GoogleCrmError(
                f"Contact file already exists: {contact_path}. Pass --force or use --contact-id."
            )
        title = summary.get("displayName") or contact_path.stem
        created = _ensure_contact_file(
            contact_path=contact_path,
            title=title,
            alias=alias,
            created_note=f"Imported identifiers from Google Contacts ({alias}).",
        )
    else:
        raise GoogleCrmError("Provide --contact-id or --create-contact-id.")

    merged = _merge_summary_into_contact(
        contact_path,
        summary,
        alias=alias,
        note_line=(
            None
            if not created
            else f"identifiers synced from Google Contacts via google-workspace-access ({alias})."
        ),
    )
    print_json(
        {
            "action": "sync_to_crm",
            "created": created,
            "google": summary,
            "merged": merged,
        }
    )
    return 0


def cmd_sync_all_to_crm(args: argparse.Namespace) -> int:
    """List all Google Contacts and merge/create CRM files (identifiers only)."""
    if not args.i_approve_write:
        print(
            "Refusing CRM file write without --i-approve-write.",
            file=sys.stderr,
        )
        return 3

    service = _service(args.account)
    alias = resolve_alias(args.account)
    people = _list_all_connections(service, page_size=args.page_size)
    created = 0
    updated = 0
    skipped = 0
    results: list[dict[str, Any]] = []

    for person in people:
        summary = _summarise_person(person)
        resource = summary.get("resourceName")
        if not resource:
            skipped += 1
            continue
        if not summary.get("emails") and not summary.get("displayName"):
            skipped += 1
            continue

        match = _match_crm_for_summary(summary)
        was_created = False
        if match is not None:
            contact_path = match
        else:
            base = _slugify(
                summary.get("displayName")
                or (summary["emails"][0].split("@")[0] if summary["emails"] else resource)
            )
            contact_path = contacts_dir() / f"contact-{base}.md"
            # Avoid collisions with unrelated existing files.
            if contact_path.exists() and _match_crm_for_summary(summary) is None:
                suffix = _slugify(resource.replace("people/", ""))[-8:]
                contact_path = contacts_dir() / f"contact-{base}-{suffix}.md"
            was_created = _ensure_contact_file(
                contact_path=contact_path,
                title=summary.get("displayName") or contact_path.stem,
                alias=alias,
                created_note=f"Imported identifiers from Google Contacts ({alias}).",
            )

        before = load_contact_file(contact_path)
        before_emails = list(before.metadata.get("emails") or [])
        before_phones = list(before.metadata.get("phones") or [])
        before_refs = list(before.metadata.get("google_contact_refs") or [])

        merged = _merge_summary_into_contact(
            contact_path,
            summary,
            alias=alias,
            note_line=(
                f"identifiers synced from Google Contacts ({alias})."
                if was_created
                else None
            ),
        )
        changed = (
            was_created
            or merged["emails"] != before_emails
            or merged["phones"] != before_phones
            or merged["google_contact_refs"] != before_refs
        )
        if was_created:
            created += 1
        elif changed:
            updated += 1
        else:
            skipped += 1
        results.append(
            {
                "resourceName": resource,
                "displayName": summary.get("displayName"),
                "contact_path": merged["contact_path"],
                "created": was_created,
                "changed": changed,
            }
        )

    print_json(
        {
            "action": "sync_all_to_crm",
            "account": alias,
            "google_contacts_listed": len(people),
            "created": created,
            "updated": updated,
            "skipped_unchanged_or_empty": skipped,
            "results": results,
        }
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    add_account_arg(search)
    search.add_argument("--query", required=True)
    search.add_argument("--max", type=int, default=10)
    search.set_defaults(func=cmd_search)

    list_cmd = sub.add_parser(
        "list",
        help="List all My Contacts (paginated people.connections.list)",
    )
    add_account_arg(list_cmd)
    list_cmd.add_argument("--page-size", type=int, default=100)
    list_cmd.set_defaults(func=cmd_list)

    get_cmd = sub.add_parser("get")
    add_account_arg(get_cmd)
    get_cmd.add_argument(
        "--resource-name",
        required=True,
        help="People API resource name, e.g. people/c123",
    )
    get_cmd.set_defaults(func=cmd_get)

    sync = sub.add_parser(
        "sync-to-crm",
        help="Merge Google Contacts identifiers into a Personal CRM contact file",
    )
    add_account_arg(sync)
    sync.add_argument("--resource-name", required=True)
    sync.add_argument("--contact-id", help="Existing CRM contact id")
    sync.add_argument(
        "--create-contact-id",
        help="Create contact-<slug>.md when missing",
    )
    sync.add_argument("--force", action="store_true")
    sync.add_argument("--i-approve-write", action="store_true")
    sync.set_defaults(func=cmd_sync_to_crm)

    sync_all = sub.add_parser(
        "sync-all-to-crm",
        help="List all Google Contacts and merge/create Personal CRM files",
    )
    add_account_arg(sync_all)
    sync_all.add_argument("--page-size", type=int, default=100)
    sync_all.add_argument("--i-approve-write", action="store_true")
    sync_all.set_defaults(func=cmd_sync_all_to_crm)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (GoogleOAuthError, GoogleCrmError) as exc:
        print(f"Contacts error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
