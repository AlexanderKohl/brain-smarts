"""Call Google Calendar/Contacts with the Vault Agent's stored access token.

Does not refresh OAuth and does not open a browser. Requires the tray Vault
Agent to be unlocked. Never prints access or refresh tokens.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from _cli_common import add_account_arg, print_json
from google_contacts import (
    _merge_unique,
    _replace_front_matter_field,
    _yaml_list,
)
from google_oauth.accounts import get_account, memory_root, resolve_alias, resolve_vault_entry
from google_oauth.client import TOKEN_URL
from google_oauth.crm import load_contact_file, find_contacts, GoogleCrmError


CRED_SCRIPTS = Path(__file__).resolve().parents[2] / "manage-credentials" / "scripts"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
PEOPLE_GET_URL = "https://people.googleapis.com/v1/{resource_name}"
PEOPLE_UPDATE_URL = "https://people.googleapis.com/v1/{resource_name}:updateContact"
PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations,addresses,metadata"
USER_AGENT = "Portable-AI-Brain-GoogleTrayToken/1.0"
AU_ADDRESS_RE = re.compile(
    r"^(?P<street>.+?),\s*(?P<city>[A-Za-z][A-Za-z '.-]*?)\s+"
    r"(?P<region>[A-Z]{2,3})\s+(?P<postal>\d{4})"
    r"(?:,\s*(?P<country>.+))?$"
)


class TrayTokenError(RuntimeError):
    """Raised when the stored tray token cannot be used."""


def _now_local() -> str:
    """Current local time as ISO 8601 with seconds and offset, e.g. 2026-01-01T09:00:00+10:00."""
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _broker():
    if str(CRED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(CRED_SCRIPTS))
    from vault_broker_client import broker_request

    return broker_request


def vault_entry_for_account(account_alias: str | None) -> str:
    alias = resolve_alias(account_alias)
    return resolve_vault_entry(get_account(alias))


def _public_token_meta(
    *,
    entry: str,
    field: str,
    account_alias: str | None,
    record: dict[str, Any],
    refreshed: bool,
) -> dict[str, Any]:
    return {
        "vault_entry": entry,
        "field": field,
        "account_alias": resolve_alias(account_alias),
        "expires_at": record.get("expires_at"),
        "expires_in": record.get("expires_in"),
        "token_type": record.get("token_type"),
        "scope": record.get("scope"),
        "has_access_token": bool(record.get("access_token")),
        "refreshed": refreshed,
    }


def _token_expired(record: dict[str, Any], leeway_seconds: int = 90) -> bool:
    expires_at = record.get("expires_at")
    if expires_at is None:
        return True
    try:
        expiry = float(expires_at)
    except (TypeError, ValueError):
        return True
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    return expiry <= now + leeway_seconds


def refresh_tray_access_token(
    *,
    account_alias: str | None,
    field: str = "oauth_token_json",
) -> dict[str, Any]:
    """Refresh using client_id/secret and refresh_token from the tray vault. No browser."""
    broker_request = _broker()
    entry = vault_entry_for_account(account_alias)
    fields = broker_request(
        "get_fields", entry=entry, fields=["client_id", "client_secret"]
    )
    if not isinstance(fields, dict):
        raise TrayTokenError("Vault Agent returned malformed client fields.")
    client_id = fields.get("client_id")
    client_secret = fields.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise TrayTokenError(
            f"Vault entry {entry} is missing text fields client_id/client_secret."
        )
    current = broker_request("get_json", entry=entry, field=field)
    if not isinstance(current, dict):
        raise TrayTokenError(f"Vault field {entry}#{field} is not a JSON object.")
    refresh_token = current.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise TrayTokenError(f"No refresh token is stored for {entry}#{field}.")
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    ).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        method="POST",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise TrayTokenError(
            "Stored Google refresh token was rejected "
            f"(HTTP {exc.code}). Tray vault credentials were used; no browser "
            f"connect was started. Google said: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TrayTokenError(f"Could not reach Google token endpoint: {exc.reason}") from exc
    updated = json.loads(data)
    if "error" in updated:
        raise TrayTokenError(
            "Stored Google refresh token was rejected. Tray vault credentials "
            f"were used; no browser connect was started. Google said: "
            f"{updated.get('error_description') or updated['error']}"
        )
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    updated["obtained_at"] = now
    updated["expires_at"] = now + int(updated.get("expires_in", 3600))
    if not updated.get("refresh_token"):
        updated["refresh_token"] = refresh_token
    if current.get("scope") and not updated.get("scope"):
        updated["scope"] = current.get("scope")
    for key in ("account_alias", "account_email"):
        if current.get(key) and not updated.get(key):
            updated[key] = current.get(key)
    broker_request("set_json", entry=entry, field=field, value=updated)
    return updated


def load_tray_access_token(
    *,
    account_alias: str | None,
    field: str = "oauth_token_json",
) -> tuple[str, dict[str, Any]]:
    """Return (access_token, public_meta). Never include the token in meta."""
    broker_request = _broker()
    entry = vault_entry_for_account(account_alias)
    record = broker_request("get_json", entry=entry, field=field)
    if not isinstance(record, dict):
        raise TrayTokenError("Vault Agent returned a malformed token payload.")
    refreshed = False
    refresh_error: str | None = None
    if _token_expired(record):
        try:
            record = refresh_tray_access_token(
                account_alias=account_alias, field=field
            )
            refreshed = True
        except TrayTokenError as exc:
            refresh_error = str(exc)
            if not record.get("access_token"):
                raise
    token = record.get("access_token")
    if not isinstance(token, str) or not token:
        raise TrayTokenError(f"No access token is stored for {entry}#{field}.")
    meta = _public_token_meta(
        entry=entry,
        field=field,
        account_alias=account_alias,
        record=record,
        refreshed=refreshed,
    )
    if refresh_error:
        meta["refresh_error"] = refresh_error
        meta["using_stored_access_token_after_failed_refresh"] = True
    return token, meta


def google_request(
    method: str,
    url: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, method=method, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1500]
        raise TrayTokenError(f"Google returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TrayTokenError(f"Could not reach Google: {exc.reason}") from exc
    if status not in expected:
        snippet = data.decode("utf-8", errors="replace")[:300] if data else ""
        raise TrayTokenError(f"Google returned unexpected HTTP {status}. Body: {snippet}")
    if not data:
        return {}
    return json.loads(data)


def event_text_blob(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("summary") or ""),
        str(event.get("description") or ""),
        str(event.get("location") or ""),
    ]
    for attendee in event.get("attendees") or []:
        parts.append(str(attendee.get("displayName") or ""))
        parts.append(str(attendee.get("email") or ""))
    return " ".join(parts).lower()


def event_matches(
    event: dict[str, Any],
    *,
    location_contains: str,
    person_needles: list[str],
) -> bool:
    location = str(event.get("location") or "").lower()
    if location_contains.lower() not in location:
        return False
    blob = event_text_blob(event)
    return any(needle.lower() in blob for needle in person_needles if needle.strip())


def parse_au_address(location: str) -> dict[str, str]:
    """Best-effort split of a Google Calendar location into People API address fields."""
    cleaned = " ".join((location or "").split()).strip()
    address: dict[str, str] = {"formattedValue": cleaned, "type": "home"}
    match = AU_ADDRESS_RE.match(cleaned)
    if match:
        address["streetAddress"] = match.group("street").strip()
        address["city"] = match.group("city").strip()
        address["region"] = match.group("region").strip()
        address["postalCode"] = match.group("postal").strip()
        country = (match.group("country") or "Australia").strip()
        address["country"] = country
        address["countryCode"] = "AU" if country.lower() in {"australia", "au"} else ""
        if not address["countryCode"]:
            address.pop("countryCode")
    return address


def summarise_event(event: dict[str, Any]) -> dict[str, Any]:
    start = event.get("start") or {}
    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "location": event.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "htmlLink": event.get("htmlLink"),
        "attendees": [
            item.get("email") or item.get("displayName")
            for item in (event.get("attendees") or [])
            if item.get("email") or item.get("displayName")
        ],
    }


def list_calendar_events(
    token: str,
    *,
    query: str | None,
    time_min: str | None,
    time_max: str | None,
    calendar_id: str,
    max_results: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page_token: str | None = None
    remaining = max(1, max_results)
    while remaining > 0:
        params: dict[str, str] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(min(250, remaining)),
        }
        if query:
            params["q"] = query
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if page_token:
            params["pageToken"] = page_token
        url = CALENDAR_EVENTS_URL.format(
            calendar_id=urllib.parse.quote(calendar_id, safe="@.")
        )
        payload = google_request("GET", url, token, params=params)
        batch = payload.get("items") or []
        events.extend(batch)
        remaining -= len(batch)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return events


def search_matching_events(
    token: str,
    *,
    queries: list[str],
    location_contains: str,
    person_needles: list[str],
    time_min: str | None,
    time_max: str | None,
    calendar_id: str,
    max_results: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    matched: list[dict[str, Any]] = []
    for query in queries:
        for event in list_calendar_events(
            token,
            query=query,
            time_min=time_min,
            time_max=time_max,
            calendar_id=calendar_id,
            max_results=max_results,
        ):
            event_id = str(event.get("id") or "")
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            if event_matches(
                event,
                location_contains=location_contains,
                person_needles=person_needles,
            ):
                matched.append(event)
    return matched


def update_crm_address(
    contact_path: Path,
    address: str,
    *,
    note_line: str,
) -> dict[str, Any]:
    record = load_contact_file(contact_path)
    addresses = _merge_unique(record.metadata.get("addresses") or [], [address])
    now = _now_local()
    text = contact_path.read_text(encoding="utf-8")
    text = _replace_front_matter_field(text, "addresses", _yaml_list(addresses))
    text = _replace_front_matter_field(text, "updated", now)
    if "## Identifiers" in text:
        ident_match = re.search(
            r"## Identifiers\n.*?(?=\n## |\Z)", text, flags=re.DOTALL
        )
        if ident_match:
            block = ident_match.group(0)
            address_line = (
                f"- Addresses: {', '.join(addresses)}"
                if addresses
                else "- Addresses:"
            )
            if re.search(r"(?m)^- Addresses:", block):
                block = re.sub(
                    r"(?m)^- Addresses:.*$", address_line, block, count=1
                )
            else:
                block = block.rstrip() + f"\n{address_line}\n"
            text = text[: ident_match.start()] + block + text[ident_match.end() :]
    if note_line and "## Notes" in text and note_line not in text:
        text = text.replace(
            "## Notes\n\n",
            f"## Notes\n\n- {now[:10]}: {note_line}\n\n",
            1,
        )
    contact_path.write_text(text, encoding="utf-8")
    return {
        "contact_path": str(contact_path).replace("\\", "/"),
        "addresses": addresses,
        "updated": now,
    }


def google_resource_from_contact(record, account_alias: str) -> str | None:
    prefix = f"{account_alias}:"
    for ref in record.metadata.get("google_contact_refs") or []:
        text = str(ref).strip()
        if text.startswith(prefix):
            return text[len(prefix) :]
        if text.startswith("people/"):
            return text
    return None


def get_person(token: str, resource_name: str) -> dict[str, Any]:
    url = PEOPLE_GET_URL.format(resource_name=resource_name)
    return google_request(
        "GET",
        url,
        token,
        params={"personFields": PERSON_FIELDS},
    )


def update_person_address(token: str, person: dict[str, Any], address: dict[str, str]) -> dict[str, Any]:
    resource_name = person.get("resourceName")
    etag = person.get("etag")
    if not resource_name or not etag:
        raise TrayTokenError("Google contact is missing resourceName or etag.")
    existing = list(person.get("addresses") or [])
    formatted = address.get("formattedValue") or ""
    already = any(
        str(item.get("formattedValue") or "").strip().lower() == formatted.lower()
        for item in existing
        if formatted
    )
    if not already:
        existing.append(address)
    url = PEOPLE_UPDATE_URL.format(resource_name=resource_name)
    return google_request(
        "PATCH",
        url,
        token,
        params={"updatePersonFields": "addresses"},
        body={"etag": etag, "addresses": existing},
    )


def cmd_token_meta(args: argparse.Namespace) -> int:
    _token, meta = load_tray_access_token(account_alias=args.account)
    print_json(meta)
    return 0


def cmd_calendar_search(args: argparse.Namespace) -> int:
    token, meta = load_tray_access_token(account_alias=args.account)
    events = list_calendar_events(
        token,
        query=args.query,
        time_min=args.time_min,
        time_max=args.time_max,
        calendar_id=args.calendar_id,
        max_results=args.max,
    )
    print_json(
        {
            "token": {k: v for k, v in meta.items() if k != "has_access_token"},
            "query": args.query,
            "count": len(events),
            "events": [summarise_event(item) for item in events],
        }
    )
    return 0


def cmd_apply_event_location(args: argparse.Namespace) -> int:
    if not args.i_approve_write:
        print("Refusing writes without --i-approve-write.", file=sys.stderr)
        return 3
    if not args.confirm_target:
        print(
            "Refusing Google/CRM writes without --confirm-target (CONTRACT §10.5).",
            file=sys.stderr,
        )
        return 3

    contacts = find_contacts(contact_id=args.contact_id, name=args.contact_name)
    if len(contacts) != 1:
        print_json(
            {
                "error": "CRM contact is missing or ambiguous.",
                "matches": [
                    {"id": item.contact_id, "title": item.title, "path": str(item.path)}
                    for item in contacts
                ],
            }
        )
        return 3
    contact = contacts[0]
    alias = resolve_alias(args.account)
    resource_name = args.resource_name or google_resource_from_contact(contact, alias)
    if not resource_name:
        raise TrayTokenError(
            "No Google Contacts resource name on the CRM file; pass --resource-name."
        )

    token, meta = load_tray_access_token(account_alias=args.account)
    person_needles = [item.strip() for item in args.person.split(",") if item.strip()]
    queries = [item.strip() for item in args.query.split("|") if item.strip()]
    matches = search_matching_events(
        token,
        queries=queries,
        location_contains=args.location_contains,
        person_needles=person_needles,
        time_min=args.time_min,
        time_max=args.time_max,
        calendar_id=args.calendar_id,
        max_results=args.max,
    )
    if args.event_id:
        matches = [item for item in matches if item.get("id") == args.event_id]
        if not matches:
            # Fall back to any scanned event id even if filter missed it.
            for query in queries:
                for event in list_calendar_events(
                    token,
                    query=query,
                    time_min=args.time_min,
                    time_max=args.time_max,
                    calendar_id=args.calendar_id,
                    max_results=args.max,
                ):
                    if event.get("id") == args.event_id:
                        matches = [event]
                        break
    if not matches:
        print_json(
            {
                "error": "No matching calendar event found.",
                "token": meta,
                "queries": queries,
                "location_contains": args.location_contains,
                "person": person_needles,
            }
        )
        return 4
    if len(matches) > 1:
        print_json(
            {
                "error": "Multiple matching events; pass --event-id.",
                "events": [summarise_event(item) for item in matches],
            }
        )
        return 3

    event = matches[0]
    location = str(event.get("location") or "").strip()
    if not location:
        print_json({"error": "Matched event has no location.", "event": summarise_event(event)})
        return 4
    address = parse_au_address(location)
    note = (
        f"Address taken from Google Calendar event {event.get('id')} "
        f"({event.get('summary')}) via google_tray_token.py ({alias})."
    )
    crm = update_crm_address(contact.path, location, note_line=note)

    google_result: dict[str, Any]
    try:
        person = get_person(token, resource_name)
        updated = update_person_address(token, person, address)
        google_result = {
            "updated": True,
            "resourceName": updated.get("resourceName"),
            "addresses": updated.get("addresses"),
        }
    except TrayTokenError as exc:
        google_result = {"updated": False, "error": str(exc)}

    print_json(
        {
            "action": "apply_event_location",
            "account": alias,
            "token": meta,
            "event": summarise_event(event),
            "address": address,
            "crm": crm,
            "google_contact": google_result,
        }
    )
    return 0 if google_result.get("updated") else 5


TRAY_TOKEN_CONFIG = "/memory/skills/google-workspace-access/config/tray-token.json"


def _apply_event_location_defaults() -> dict[str, str]:
    """Owner defaults for apply-event-location, kept out of the shared skill."""
    path = memory_root() / "skills" / "google-workspace-access" / "config" / "tray-token.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    section = data.get("apply_event_location") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in (section or {}).items() if v is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    meta = sub.add_parser("token-meta", help="Show stored-token metadata; never prints the token")
    add_account_arg(meta)
    meta.set_defaults(func=cmd_token_meta)

    search = sub.add_parser("calendar-search")
    add_account_arg(search)
    search.add_argument("--query")
    search.add_argument("--calendar-id", default="primary")
    search.add_argument("--time-min")
    search.add_argument("--time-max")
    search.add_argument("--max", type=int, default=50)
    search.set_defaults(func=cmd_calendar_search)

    apply_cmd = sub.add_parser(
        "apply-event-location",
        help="Copy a matching Calendar location onto a CRM contact and Google Contact",
    )
    add_account_arg(apply_cmd)
    apply_cmd.add_argument("--contact-id")
    apply_cmd.add_argument("--contact-name")
    apply_cmd.add_argument("--resource-name")
    apply_cmd.add_argument(
        "--query",
        help="Calendar search queries separated by | (default: owner configuration)",
    )
    apply_cmd.add_argument(
        "--person",
        help="Comma-separated name needles for the event (default: owner configuration)",
    )
    apply_cmd.add_argument(
        "--location-contains",
        help="Text the event location must contain (default: owner configuration)",
    )
    apply_cmd.add_argument("--event-id")
    apply_cmd.add_argument("--calendar-id", default="primary")
    apply_cmd.add_argument("--time-min", default="2025-01-01T00:00:00+10:00")
    apply_cmd.add_argument("--time-max", default="2027-12-31T23:59:59+10:00")
    apply_cmd.add_argument("--max", type=int, default=100)
    apply_cmd.add_argument("--i-approve-write", action="store_true")
    apply_cmd.add_argument("--confirm-target", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply_event_location)

    args = parser.parse_args()
    if args.command == "apply-event-location" and not (args.contact_id or args.contact_name):
        parser.error("apply-event-location requires --contact-id or --contact-name")
    if args.command == "apply-event-location":
        defaults = _apply_event_location_defaults()
        for name in ("query", "person", "location_contains"):
            if getattr(args, name) is None:
                setattr(args, name, defaults.get(name))
            if not getattr(args, name):
                parser.error(
                    f"apply-event-location requires --{name.replace('_', '-')} "
                    f"(or '{name}' under apply_event_location in {TRAY_TOKEN_CONFIG})"
                )
    try:
        return args.func(args)
    except (TrayTokenError, GoogleCrmError) as exc:
        print(f"Tray-token error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
