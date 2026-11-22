"""Each static field carries its kind (follow-up plan N2): the encrypted payload of a static object
is {"schema": 2, "values": {field: text}, "kinds": {field: "text" | "json"}}. Only text and json are
kinds, a json field's text is a JSON object, and kind data that is malformed or unknown is refused
before use. An object written before this change is {field: text} with no kinds: it reads as before,
and any write to it records the kinds of the fields it writes. The payload is inside the envelope,
so the acceptance rules are unchanged."""
from __future__ import annotations

import json
from typing import Any

from .errors import SecretStoreError

KINDS = ("text", "json")
SCHEMA = 2


def _refuse(why: str) -> None:
    raise SecretStoreError(f"a static entry's field kinds are malformed ({why}); nothing was used")


def check_kind(field: str, text: Any, kind: Any) -> None:
    """The value's form agrees with its kind."""
    if kind not in KINDS:
        _refuse(f"unknown kind for {field}")
    if not isinstance(text, str):
        _refuse(f"{field} is not text")
    if kind == "json":
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if not isinstance(value, dict):
            _refuse(f"{field} is recorded as JSON but is not a JSON object")


def split(payload: Any) -> tuple[dict[str, str], dict[str, str]]:
    """(values, kinds) of a static payload, checked; kinds is {} for an object written before N2."""
    if not isinstance(payload, dict):
        _refuse("not an object")
    if "schema" not in payload:  # written before kinds were recorded: every value is text
        if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in payload.items()):
            _refuse("a value is not text")
        return dict(payload), {}
    values, kinds = payload.get("values"), payload.get("kinds")
    if set(payload) != {"schema", "values", "kinds"} or payload["schema"] != SCHEMA \
            or not isinstance(values, dict) or not isinstance(kinds, dict):
        _refuse("unknown layout")
    if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in values.items()):
        _refuse("a value is not text")
    if not set(kinds) <= set(values):
        _refuse("a kind names no field")
    for field, kind in kinds.items():
        check_kind(field, values[field], kind)
    return dict(values), dict(kinds)


def build(values: dict[str, str], kinds: dict[str, str]) -> dict:
    """The payload for these values and kinds (a field without a kind stays without one)."""
    payload = {"schema": SCHEMA, "values": dict(values), "kinds": {f: k for f, k in kinds.items() if f in values}}
    split(payload)
    return payload


def merged(previous: Any, fields: dict[str, str], kinds: dict[str, str]) -> dict:
    """previous (None for a new object) with fields written at the given kinds; every field
    written has a kind, every other field keeps its own (or none)."""
    if set(kinds) != set(fields):
        raise SecretStoreError("every static field written needs its kind, text or json")
    values, held = split(previous) if previous is not None else ({}, {})
    return build({**values, **fields}, {**held, **kinds})


def without(previous: Any, drop: set) -> dict:
    """previous less the fields in drop, the others with their kinds kept."""
    values, kinds = split(previous)
    return build({f: v for f, v in values.items() if f not in drop}, kinds)
