"""Shared ABR JSON Lookup client (ABN / ACN / name). Fail closed without GUID."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

JSON_BASE = "https://abr.business.gov.au/json"
DEFAULT_VAULT_ENTRY = "abr-webservices-guid"
DEFAULT_VAULT_FIELD = "authentication_guid"
GUID_ENV = "ABR_AUTHENTICATION_GUID"
VAULT_ENTRY_ENV = "ABR_VAULT_ENTRY"
VAULT_FIELD_ENV = "ABR_VAULT_FIELD"

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_CALLBACK_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\((.*)\)\s*;?\s*$", re.DOTALL)


class AbrError(RuntimeError):
    """Raised when an ABR Lookup call cannot complete safely."""


def vault_entry_name() -> str:
    return (os.environ.get(VAULT_ENTRY_ENV) or DEFAULT_VAULT_ENTRY).strip()


def vault_field_name() -> str:
    return (os.environ.get(VAULT_FIELD_ENV) or DEFAULT_VAULT_FIELD).strip()


def resolve_guid() -> str:
    """Return the ABR authentication GUID from the environment. Fail closed."""
    guid = (os.environ.get(GUID_ENV) or "").strip()
    if not guid:
        raise AbrError(
            f"Missing {GUID_ENV}. Inject vault field "
            f"`{vault_entry_name()}#{vault_field_name()}` via manage-credentials "
            f"(`vault_credentials.py run --map {GUID_ENV}={vault_field_name()}`)."
        )
    if not _GUID_RE.match(guid):
        raise AbrError(
            f"{GUID_ENV} is not a valid GUID shape (expected 8-4-4-4-12 hex)."
        )
    return guid


def guid_tail(guid: str, n: int = 4) -> str:
    cleaned = guid.strip()
    if len(cleaned) < n:
        return "????"
    return cleaned[-n:]


def _parse_jsonp(raw: str) -> dict[str, Any]:
    text = raw.strip()
    match = _CALLBACK_RE.match(text)
    payload = match.group(1) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AbrError("ABR response was not valid JSON/JSONP.") from exc
    if not isinstance(data, dict):
        raise AbrError("ABR response JSON root must be an object.")
    return data


def _get_json(path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{JSON_BASE}/{path}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "brain-abr-access/1.0",
            "Accept": "application/json, text/javascript, */*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise AbrError(f"ABR HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AbrError(f"ABR network error: {exc.reason}") from exc
    return _parse_jsonp(raw)


def lookup_abn(abn: str, *, include_historical: bool = False) -> dict[str, Any]:
    digits = re.sub(r"\D", "", abn or "")
    if len(digits) != 11:
        raise AbrError("ABN must be 11 digits.")
    params = {
        "abn": digits,
        "callback": "callback",
        "guid": resolve_guid(),
    }
    if include_historical:
        params["history"] = "Y"
    data = _get_json("AbnDetails.aspx", params)
    return {"query": {"abn": digits}, "result": data}


def lookup_acn(acn: str) -> dict[str, Any]:
    digits = re.sub(r"\D", "", acn or "")
    if len(digits) != 9:
        raise AbrError("ACN must be 9 digits.")
    data = _get_json(
        "AcnDetails.aspx",
        {
            "acn": digits,
            "callback": "callback",
            "guid": resolve_guid(),
        },
    )
    return {"query": {"acn": digits}, "result": data}


def search_name(name: str, *, max_results: int = 10) -> dict[str, Any]:
    cleaned = (name or "").strip()
    if not cleaned:
        raise AbrError("Name search string is required.")
    if max_results < 1 or max_results > 200:
        raise AbrError("max_results must be between 1 and 200.")
    data = _get_json(
        "MatchingNames.aspx",
        {
            "name": cleaned,
            "maxResults": str(max_results),
            "callback": "callback",
            "guid": resolve_guid(),
        },
    )
    return {
        "query": {"name": cleaned, "max_results": max_results},
        "result": data,
    }
