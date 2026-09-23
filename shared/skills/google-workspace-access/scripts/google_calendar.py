"""Google Calendar list/search and create/update events (no delete)."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from _cli_common import (
    add_account_arg,
    add_crm_args,
    print_json,
    require_side_effect_confirmation,
)
from google_oauth import GoogleConnection, GoogleOAuthError
from google_oauth.accounts import owner_timezone
from google_oauth.crm import GoogleCrmError, resolve_for_side_effect


def _service(account: str | None) -> Any:
    return GoogleConnection.from_environment(account).build_service("calendar", "v3")


def cmd_list_calendars(args: argparse.Namespace) -> int:
    service = _service(args.account)
    print_json(service.calendarList().list().execute())
    return 0


def cmd_list_events(args: argparse.Namespace) -> int:
    service = _service(args.account)
    kwargs: dict[str, Any] = {
        "calendarId": args.calendar_id,
        "maxResults": args.max,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if args.time_min:
        kwargs["timeMin"] = args.time_min
    if args.time_max:
        kwargs["timeMax"] = args.time_max
    if args.query:
        kwargs["q"] = args.query
    print_json(service.events().list(**kwargs).execute())
    return 0


def _event_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": args.summary,
        "start": {"dateTime": args.start, "timeZone": args.timezone},
        "end": {"dateTime": args.end, "timeZone": args.timezone},
    }
    if args.description:
        body["description"] = args.description
    if args.location:
        body["location"] = args.location
    if args.attendee:
        body["attendees"] = [{"email": email} for email in args.attendee]
    return body


def _resolve(args: argparse.Namespace):
    return resolve_for_side_effect(
        contact_id=args.contact_id,
        email=args.contact_email,
        name=args.contact_name,
        persona_key=args.persona,
        account_alias=args.account,
        allow_missing_contact=True,
    )


def cmd_create_event(args: argparse.Namespace) -> int:
    resolution = _resolve(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    service = _service(account_alias)
    created = (
        service.events()
        .insert(calendarId=args.calendar_id, body=_event_body(args))
        .execute()
    )
    print_json(
        {"action": "create_event", "event": created, "crm": resolution.as_dict()}
    )
    return 0


def cmd_update_event(args: argparse.Namespace) -> int:
    resolution = _resolve(args)
    require_side_effect_confirmation(
        confirm_target=args.confirm_target, resolution=resolution
    )
    account_alias = resolution.account.alias if resolution.account else args.account
    service = _service(account_alias)
    updated = (
        service.events()
        .patch(
            calendarId=args.calendar_id,
            eventId=args.event_id,
            body=_event_body(args),
        )
        .execute()
    )
    print_json(
        {"action": "update_event", "event": updated, "crm": resolution.as_dict()}
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    calendars = sub.add_parser("list-calendars")
    add_account_arg(calendars)
    calendars.set_defaults(func=cmd_list_calendars)

    events = sub.add_parser("list-events")
    add_account_arg(events)
    events.add_argument("--calendar-id", default="primary")
    events.add_argument("--query")
    events.add_argument("--time-min", help="RFC3339 lower bound")
    events.add_argument("--time-max", help="RFC3339 upper bound")
    events.add_argument("--max", type=int, default=20)
    events.set_defaults(func=cmd_list_events)

    create = sub.add_parser("create-event")
    add_account_arg(create)
    add_crm_args(create)
    create.add_argument("--calendar-id", default="primary")
    create.add_argument("--summary", required=True)
    create.add_argument("--start", required=True, help="RFC3339 start datetime")
    create.add_argument("--end", required=True, help="RFC3339 end datetime")
    create.add_argument("--timezone", default=owner_timezone(),
                        help="IANA timezone (default: timezone in /memory/OWNER.md, else UTC)")
    create.add_argument("--description")
    create.add_argument("--location")
    create.add_argument("--attendee", action="append", default=[])
    create.set_defaults(func=cmd_create_event)

    update = sub.add_parser("update-event")
    add_account_arg(update)
    add_crm_args(update)
    update.add_argument("--calendar-id", default="primary")
    update.add_argument("--event-id", required=True)
    update.add_argument("--summary", required=True)
    update.add_argument("--start", required=True)
    update.add_argument("--end", required=True)
    update.add_argument("--timezone", default=owner_timezone(),
                        help="IANA timezone (default: timezone in /memory/OWNER.md, else UTC)")
    update.add_argument("--description")
    update.add_argument("--location")
    update.add_argument("--attendee", action="append", default=[])
    update.set_defaults(func=cmd_update_event)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (GoogleOAuthError, GoogleCrmError) as exc:
        print(f"Calendar error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
