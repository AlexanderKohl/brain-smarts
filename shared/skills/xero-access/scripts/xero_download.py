"""Download an authorised Xero API resource with provenance metadata."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from xero_oauth import XeroConnection, XeroOAuthError


ACCOUNTING_API = "https://api.xero.com/api.xro/2.0/"
ALLOWED_HOST = "api.xero.com"


def parse_query(values: list[str]) -> list[tuple[str, str]]:
    query: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Query must use key=value form: {value}")
        key, item = value.split("=", 1)
        if not key:
            raise ValueError("Query keys cannot be empty.")
        query.append((key, item))
    return query


def build_url(resource: str | None, url: str | None, query: list[str]) -> str:
    if resource:
        cleaned = resource.strip().lstrip("/")
        if not cleaned or ".." in cleaned.split("/"):
            raise ValueError("Resource must be a valid Xero Accounting API path.")
        target = urllib.parse.urljoin(ACCOUNTING_API, cleaned)
    else:
        target = str(url).strip()

    parsed = urllib.parse.urlparse(target)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise ValueError("Xero download URLs must use https://api.xero.com/.")

    existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    combined = urllib.parse.urlencode(existing + parse_query(query))
    return urllib.parse.urlunparse(parsed._replace(query=combined))


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="xero-download-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def metadata_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--resource", help="Accounting API path, for example Invoices")
    source.add_argument("--url", help="Full https://api.xero.com endpoint URL")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Query parameter in key=value form; repeat as needed",
    )
    parser.add_argument("--tenant-id", help="Select this connected Xero tenant first")
    parser.add_argument("--accept", default="application/json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--requesting-node", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    metadata_path = args.output.with_name(args.output.name + ".metadata.json")
    if not args.force:
        existing = [path for path in (args.output, metadata_path) if path.exists()]
        if existing:
            parser.error("Refusing to overwrite: " + ", ".join(map(str, existing)))

    try:
        url = build_url(args.resource, args.url, args.query)
        xero = XeroConnection.from_environment()
        if args.tenant_id:
            xero.select_tenant(args.tenant_id)
        tenant_id = xero.tenant_id()
        status, body, headers = xero.request("GET", url, accept=args.accept)
    except (ValueError, XeroOAuthError) as exc:
        parser.error(str(exc))

    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
    metadata = {
        "source_system": "Xero",
        "source_url": url,
        "retrieved_at_utc": retrieved_at,
        "tenant_id": tenant_id,
        "requesting_node": args.requesting_node,
        "method": "GET",
        "status_code": status,
        "content_type": headers.get("Content-Type"),
        "coverage": "endpoint response; pagination and filter completeness not inferred",
        "freshness": "live",
        "transformations": [],
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }
    atomic_write(args.output, body)
    atomic_write(metadata_path, metadata_bytes(metadata))
    print(f"Downloaded {len(body)} bytes to {args.output}")
    print(f"Provenance metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
