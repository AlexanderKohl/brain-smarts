"""Create planned Xero accounts with conflict checks and per-write verification."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from xero_oauth import XeroConnection, XeroOAuthError


ACCOUNTS_URL = "https://api.xero.com/api.xro/2.0/Accounts"
VALID_TYPES = {"CURRLIAB", "REVENUE"}
VALID_TAX_TYPES = {"BASEXCLUDED", "OUTPUT"}
COMPARE_FIELDS = (
    "Code",
    "Name",
    "Type",
    "TaxType",
    "Status",
    "EnablePaymentsToAccount",
    "ShowInExpenseClaims",
)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(min(0.05 * (2**attempt), 0.5))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        plan = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The account plan is not valid UTF-8 JSON.") from exc
    if plan.get("schema_version") != 1:
        raise ValueError("The account plan schema version is unsupported.")
    organisation = plan.get("organisation")
    accounts = plan.get("accounts")
    if not isinstance(organisation, dict) or not organisation.get("tenant_id"):
        raise ValueError("The account plan requires an organisation tenant_id.")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("The account plan requires at least one account.")
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    for position, account in enumerate(accounts, start=1):
        if not isinstance(account, dict):
            raise ValueError(f"Account {position} must be an object.")
        code = str(account.get("Code", "")).strip()
        name = str(account.get("Name", "")).strip()
        if not code or len(code) > 10:
            raise ValueError(f"Account {position} has an invalid Code.")
        if not name or len(name) > 150:
            raise ValueError(f"Account {position} has an invalid Name.")
        if code in seen_codes or name.casefold() in seen_names:
            raise ValueError(f"Account plan contains a duplicate code or name: {code}")
        if account.get("Type") not in VALID_TYPES:
            raise ValueError(f"Account {code} has an unsupported Type.")
        if account.get("TaxType") not in VALID_TAX_TYPES:
            raise ValueError(f"Account {code} has an unsupported TaxType.")
        seen_codes.add(code)
        seen_names.add(name.casefold())
    return plan, raw


def account_matches(existing: dict[str, Any], planned: dict[str, Any]) -> bool:
    return all(existing.get(field) == planned.get(field) for field in COMPARE_FIELDS)


def preflight(
    existing_accounts: list[dict[str, Any]],
    planned_accounts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_code = {str(account.get("Code", "")): account for account in existing_accounts}
    by_name = {
        str(account.get("Name", "")).casefold(): account for account in existing_accounts
    }
    missing: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for planned in planned_accounts:
        code = str(planned["Code"])
        name_key = str(planned["Name"]).casefold()
        code_match = by_code.get(code)
        name_match = by_name.get(name_key)
        if code_match:
            if account_matches(code_match, planned):
                existing.append(code_match)
            else:
                conflicts.append(f"Code {code} already exists with different details.")
            continue
        if name_match:
            conflicts.append(
                f"Name {planned['Name']} already exists under code {name_match.get('Code', '')}."
            )
            continue
        missing.append(planned)
    if conflicts:
        raise ValueError("Preflight conflict(s): " + " ".join(conflicts))
    return missing, existing


def get_accounts(connection: XeroConnection) -> list[dict[str, Any]]:
    _, body, _ = connection.request("GET", ACCOUNTS_URL)
    parsed = json.loads(body)
    accounts = parsed.get("Accounts")
    if not isinstance(accounts, list):
        raise XeroOAuthError("Xero Accounts response is malformed.")
    return accounts


def find_exact(
    accounts: list[dict[str, Any]], planned: dict[str, Any]
) -> dict[str, Any] | None:
    for account in accounts:
        if str(account.get("Code", "")) == str(planned["Code"]):
            return account if account_matches(account, planned) else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--requesting-node", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.result.exists() and not args.force:
        parser.error(f"Refusing to overwrite result: {args.result}")

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        plan, raw_plan = load_plan(args.plan)
        connection = XeroConnection.from_environment()
        tenant_id = str(plan["organisation"]["tenant_id"])
        connection.select_tenant(tenant_id)
        existing_accounts = get_accounts(connection)
        missing, exact_existing = preflight(existing_accounts, plan["accounts"])
    except (OSError, ValueError, XeroOAuthError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    results = [
        {
            "Code": account.get("Code"),
            "Name": account.get("Name"),
            "AccountID": account.get("AccountID"),
            "outcome": "already_existed_exactly",
        }
        for account in exact_existing
    ]
    result_document: dict[str, Any] = {
        "schema_version": 1,
        "operation": "create_xero_accounts",
        "started_at_utc": started_at,
        "completed_at_utc": None,
        "requesting_node": args.requesting_node,
        "tenant_id": tenant_id,
        "organisation_name": plan["organisation"].get("name"),
        "plan_path": str(args.plan),
        "plan_sha256": hashlib.sha256(raw_plan).hexdigest(),
        "status": "in_progress",
        "results": results,
    }
    atomic_json(args.result, result_document)

    for planned in missing:
        payload = json.dumps(planned, separators=(",", ":")).encode("utf-8")
        try:
            _, body, _ = connection.request(
                "PUT",
                ACCOUNTS_URL,
                accept="application/json",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = json.loads(body)
            returned = response.get("Accounts")
            account = returned[0] if isinstance(returned, list) and returned else None
            if not isinstance(account, dict) or not account_matches(account, planned):
                account = find_exact(get_accounts(connection), planned)
            if not account:
                raise XeroOAuthError(
                    f"Xero did not return verifiable details for account {planned['Code']}."
                )
            outcome = "created_and_verified"
        except (XeroOAuthError, json.JSONDecodeError) as exc:
            try:
                account = find_exact(get_accounts(connection), planned)
            except (XeroOAuthError, json.JSONDecodeError):
                account = None
            if account:
                outcome = "created_and_reconciled"
            else:
                result_document["status"] = "stopped_uncertain"
                result_document["error"] = (
                    f"Account {planned['Code']} could not be reconciled after: {exc}"
                )
                result_document["completed_at_utc"] = dt.datetime.now(
                    dt.timezone.utc
                ).isoformat()
                atomic_json(args.result, result_document)
                print(result_document["error"])
                return 2
        results.append(
            {
                "Code": account.get("Code"),
                "Name": account.get("Name"),
                "AccountID": account.get("AccountID"),
                "outcome": outcome,
            }
        )
        atomic_json(args.result, result_document)

    final_accounts = get_accounts(connection)
    failed_verification = [
        planned["Code"]
        for planned in plan["accounts"]
        if not find_exact(final_accounts, planned)
    ]
    if failed_verification:
        result_document["status"] = "verification_failed"
        result_document["error"] = (
            "Final verification failed for code(s): " + ", ".join(failed_verification)
        )
        exit_code = 2
    else:
        result_document["status"] = "complete"
        exit_code = 0
    result_document["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_json(args.result, result_document)
    print(
        f"Xero account creation {result_document['status']}: "
        f"{len(missing)} created, {len(exact_existing)} already matched."
    )
    print(f"Result: {args.result}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
