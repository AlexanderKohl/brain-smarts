#!/usr/bin/env python3
"""
Search the owner's Gmail for an ABR authentication GUID email and store it in the vault.

Prefer an unlocked Vault Agent (`vaultctl unlock`) so Google OAuth and vault writes
go through the broker. Mapped Google client fields may still be injected via
vaultctl/vault_credentials run without exporting the master passphrase.
Never prints the full GUID - only the last 4 characters for owner confirmation.

Owner configuration (optional) is read from `/memory/skills/abr-access/config/gmail_import.json`
under the brain root (the nearest ancestor holding CONTRACT.md): `default_account` (the Google
account alias), `default_queries` / `focused_queries` (replace the generic lists below) and
`noise_subject_pattern` (subjects to demote). Without it the generic defaults apply and
`--account` must be given.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any



def _brain_root(start: Path) -> Path:
    """The brain root: the nearest ancestor holding CONTRACT.md (CONTRACT section 1)."""
    for parent in [start, *start.parents]:
        if (parent / "CONTRACT.md").is_file():
            return parent
    return start.parents[3]  # outside a brain checkout: the old fixed depth


# Ensure google-workspace-access scripts are importable when launched from this skill.
_REPO_ROOT = _brain_root(Path(__file__).resolve().parent)
_CONFIG_FILE = _REPO_ROOT / "memory" / "skills" / "abr-access" / "config" / "gmail_import.json"
_GWS_SCRIPTS = _REPO_ROOT / "shared" / "skills" / "google-workspace-access" / "scripts"
_CRED_SCRIPTS = _REPO_ROOT / "shared" / "skills" / "manage-credentials" / "scripts"
for path in (_GWS_SCRIPTS, _CRED_SCRIPTS, Path(__file__).resolve().parent):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from abr_client import DEFAULT_VAULT_ENTRY, DEFAULT_VAULT_FIELD, guid_tail  # noqa: E402
from google_oauth import GoogleConnection  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402

# Reuse Gmail decode helpers without going through the CLI.
import google_gmail as gmail_mod  # noqa: E402

GUID_RE = re.compile(
    r"(?i)(?:authentication\s+guid|guid|globally unique identifier)"
    r"[^\n0-9a-fA-F]{0,80}"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
BARE_GUID_RE = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)

# Broad discovery (noisy — many false positives). Prefer --focused for storage.
DEFAULT_QUERIES = [
    # Prefer official ABR / DISR registration channels first.
    "from:(servicenowcloud.com.au) (GUID OR \"web service\" OR INC)",
    "subject:(\"Web service registration\") GUID",
    "from:(abr.business.gov.au OR abnlookup OR business.gov.au OR ato.gov.au) (GUID OR WebServices OR \"web services\" OR authentication)",
    "subject:(ABN Lookup OR \"authentication GUID\" OR \"Registered Party\") (GUID OR authentication OR WebServices)",
    '"authentication GUID"',
    '"Registered Party" GUID',
    "ABN Lookup web services",
    "authentication guid ABR",
    "ABN Lookup GUID",
    '"ABN Lookup" GUID older_than:1y',
    "WebServices GUID business.gov.au",
    # Broad fallback last (noisy: unrelated threads often mention abr.business.gov.au).
    "abr.business.gov.au",
    "ABR GUID",
]

# Subjects that commonly contain unrelated UUID/GUID noise when searching ABR terms.
# Mailbox-specific: the owner's pattern comes from the config file. Default matches nothing.
_NOISE_SUBJECT_RE = re.compile(r"(?!x)x")
_OFFICIAL_FROM_RE = re.compile(
    r"(?i)(servicenow|diser@|abnlookup\.support@industry\.gov\.au|"
    r"abr\.business\.gov\.au|abn.?lookup|business\.gov\.au|ato\.gov\.au|industry\.gov\.au)"
)
_OFFICIAL_SUBJECT_RE = re.compile(
    r"(?i)(web\s*service\s*registration|INC0\d+|authentication\s*guid|"
    r"registered\s*party|abn\s*lookup\s*web\s*service)"
)

# High-signal queries for the actual ABR registration / GUID email.
FOCUSED_QUERIES = [
    "authentication guid ABR",
    "subject:(ABN Lookup OR ABR OR WebServices) (GUID OR authentication)",
    '"authentication GUID" (ABN OR ABR OR "web services" OR business.gov.au)',
    "from:(abr.business.gov.au OR abnlookup OR ato.gov.au) (GUID OR authentication OR WebServices)",
    "ABN Lookup web services GUID",
    '"Your authentication GUID"',
    '"ABN Lookup web services" GUID',
    '"Web service registration" GUID',
]


def _load_config() -> dict[str, Any]:
    """Owner configuration from the memory layer, or {} when absent."""
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise SystemExit(f"{_CONFIG_FILE} must hold a JSON object.")
    return data

ABR_CONTEXT_RE = re.compile(
    r"(?is)(authentication\s+guid|abn\s+lookup|registered\s+party|"
    r"abr\.business\.gov\.au|web\s+services\s+registration|"
    r"globally\s+unique\s+identifier)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _search(service: Any, query: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "userId": "me",
            "q": query,
            "maxResults": min(page_size, 100),
        }
        if page_token:
            kwargs["pageToken"] = page_token
        response = service.users().messages().list(**kwargs).execute()
        batch = response.get("messages") or []
        messages.extend(batch)
        page_token = response.get("nextPageToken")
        if not page_token or len(messages) >= 1000:
            break
    return messages


def _read_decoded(service: Any, message_id: str) -> dict[str, Any]:
    message = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    return gmail_mod._decoded_message(message, include_html=False)


def _extract_guids(text: str, *, require_abr_context: bool = False) -> list[str]:
    blob = text or ""
    found: list[str] = []
    for match in GUID_RE.finditer(blob):
        found.append(match.group(1))
    if not found:
        for match in BARE_GUID_RE.finditer(blob):
            # When requiring ABR context, only keep bare GUIDs near ABR wording.
            if require_abr_context:
                start = max(0, match.start() - 240)
                end = min(len(blob), match.end() + 240)
                window = blob[start:end]
                if not ABR_CONTEXT_RE.search(window):
                    continue
            found.append(match.group(1))
    # Preserve order, unique, case-normalise to lowercase for storage consistency
    ordered: list[str] = []
    seen: set[str] = set()
    for item in found:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def _store_guid(guid: str, *, entry: str, field: str) -> None:
    scripts = _REPO_ROOT / "shared" / "skills" / "manage-credentials" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from vault_broker_client import broker_request, broker_unlocked

        if broker_unlocked():
            broker_request("set_text", entry=entry, field=field, value=guid)
            return
    except Exception:
        pass
    passphrase = os.environ.get("PORTABLE_VAULT_PASSPHRASE")
    if not passphrase:
        raise CredentialError(
            "Vault Agent is locked/unavailable. "
            "Start the Portable Vault tray app and unlock it from the tray menu."
        )
    vault = PortableVault()
    vault.set(entry, field, guid, "text", passphrase)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ABR authentication GUID from Gmail into the portable vault."
    )
    config = _load_config()
    global _NOISE_SUBJECT_RE
    if config.get("noise_subject_pattern"):
        _NOISE_SUBJECT_RE = re.compile(config["noise_subject_pattern"])
    parser.add_argument(
        "--account",
        default=config.get("default_account"),
        required=not config.get("default_account"),
        help="Google account alias (default: default_account in the owner config)",
    )
    parser.add_argument("--entry", default=DEFAULT_VAULT_ENTRY)
    parser.add_argument("--field", default=DEFAULT_VAULT_FIELD)
    parser.add_argument(
        "--result",
        default=str(
            _REPO_ROOT
            / "temp"
            / "abr-access"
            / "guid_import_result.json"
        ),
        help="Non-secret result JSON path (no full GUID)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and report only; do not write the vault",
    )
    parser.add_argument(
        "--store-first",
        action="store_true",
        help="If multiple GUIDs found, store the first without asking (default: store only when exactly one unique GUID)",
    )
    parser.add_argument(
        "--focused",
        action="store_true",
        help="Use high-signal ABR registration queries only and require ABR context near GUIDs",
    )
    args = parser.parse_args()

    service = GoogleConnection.from_environment(args.account).build_service(
        "gmail", "v1"
    )

    hits: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    query_stats: list[dict[str, Any]] = []
    queries = (
        (config.get("focused_queries") or FOCUSED_QUERIES)
        if args.focused
        else (config.get("default_queries") or DEFAULT_QUERIES)
    )

    for query in queries:
        try:
            messages = _search(service, query)
        except Exception as exc:  # noqa: BLE001 — report per-query and continue
            query_stats.append(
                {"query": query, "error": str(exc), "message_count": 0}
            )
            continue
        query_stats.append({"query": query, "message_count": len(messages)})
        for item in messages:
            mid = item.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            try:
                decoded = _read_decoded(service, mid)
            except Exception as exc:  # noqa: BLE001
                hits.append(
                    {
                        "id": mid,
                        "error": str(exc),
                        "query_matched": query,
                    }
                )
                continue
            subject = decoded.get("Subject") or ""
            from_addr = decoded.get("From") or ""
            date = decoded.get("Date") or ""
            body = decoded.get("text") or ""
            snippet = decoded.get("snippet") or ""
            blob = "\n".join([subject, from_addr, snippet, body])
            guids = _extract_guids(blob, require_abr_context=bool(args.focused))
            # Prefer messages that look ABR-related
            lowered = blob.lower()
            abr_signal = any(
                token in lowered
                for token in (
                    "authentication guid",
                    "abn lookup",
                    "abr.business.gov.au",
                    "registered party",
                    "web services registration",
                    "web service registration",
                    "globally unique identifier",
                )
            )
            noise_subject = bool(_NOISE_SUBJECT_RE.search(subject))
            official_from = bool(_OFFICIAL_FROM_RE.search(from_addr))
            official_subject = bool(_OFFICIAL_SUBJECT_RE.search(subject))
            rank_score = 0
            if official_from:
                rank_score += 50
            if official_subject:
                rank_score += 40
            if abr_signal:
                rank_score += 10
            if noise_subject:
                rank_score -= 80
            if args.focused and not abr_signal and not guids:
                # Still record query hits briefly for debugging, but skip noise.
                continue
            hits.append(
                {
                    "id": mid,
                    "subject": subject,
                    "from": from_addr,
                    "date": date,
                    "abr_signal": abr_signal,
                    "noise_subject": noise_subject,
                    "official_from": official_from,
                    "official_subject": official_subject,
                    "rank_score": rank_score,
                    "guid_count": len(guids),
                    "guid_tails": [guid_tail(g) for g in guids],
                    "query_matched": query,
                }
            )
            # Attach private guids only in-memory for selection
            hits[-1]["_guids"] = guids

    # Rank: official registration mail first; demote NDIS/noise subjects.
    candidates = [h for h in hits if h.get("_guids")]
    candidates.sort(
        key=lambda h: (
            -int(h.get("rank_score") or 0),
            not h.get("abr_signal"),
            -h.get("guid_count", 0),
        )
    )

    unique_guids: list[str] = []
    seen_g: set[str] = set()
    for hit in candidates:
        if hit.get("noise_subject") and not (
            hit.get("official_from") or hit.get("official_subject")
        ):
            continue
        for g in hit.get("_guids") or []:
            if g not in seen_g:
                seen_g.add(g)
                unique_guids.append(g)
    if not unique_guids:
        for hit in candidates:
            for g in hit.get("_guids") or []:
                if g not in seen_g:
                    seen_g.add(g)
                    unique_guids.append(g)

    stored = False
    store_error: str | None = None
    chosen_tail: str | None = None
    if unique_guids and not args.dry_run:
        if len(unique_guids) == 1 or args.store_first:
            chosen = unique_guids[0]
            chosen_tail = guid_tail(chosen)
            try:
                _store_guid(chosen, entry=args.entry, field=args.field)
                stored = True
            except (CredentialError, OSError, ValueError) as exc:
                store_error = str(exc)
        else:
            store_error = (
                f"Found {len(unique_guids)} distinct GUIDs; not storing. "
                "Re-run with --store-first after reviewing guid_tails, or provide the GUID manually via put-entry."
            )

    # Strip private fields before writing/printing
    public_hits = []
    for hit in hits:
        public = {k: v for k, v in hit.items() if not k.startswith("_")}
        public_hits.append(public)

    result = {
        "ok": stored or (args.dry_run and bool(unique_guids)),
        "account": args.account,
        "vault_entry": args.entry,
        "vault_field": args.field,
        "queried_at": _utc_now(),
        "query_stats": query_stats,
        "messages_examined": len(hits),
        "messages_with_guid": len(candidates),
        "unique_guid_count": len(unique_guids),
        "guid_tails_all": [guid_tail(g) for g in unique_guids],
        "stored": stored,
        "stored_guid_tail": chosen_tail,
        "dry_run": args.dry_run,
        "store_error": store_error,
        "promising_messages": [
            h
            for h in public_hits
            if h.get("abr_signal") or h.get("guid_count", 0) > 0
        ][:40],
    }

    out_path = Path(args.result)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not unique_guids:
        return 3
    if store_error and not stored and not args.dry_run:
        return 4
    return 0 if (stored or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
