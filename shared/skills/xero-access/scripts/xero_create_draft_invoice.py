"""Create one planned Xero draft sales invoice with live preflight and verification."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
import time
import urllib.parse
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from xero_oauth import XeroConnection, XeroOAuthError


API_ROOT = "https://api.xero.com/api.xro/2.0"
ACCOUNTS_URL = f"{API_ROOT}/Accounts"
CONTACTS_URL = f"{API_ROOT}/Contacts"
INVOICES_URL = f"{API_ROOT}/Invoices"


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


def decimal(value: Any, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc


def load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        plan = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The invoice plan is not valid UTF-8 JSON.") from exc
    if plan.get("schema_version") != 1:
        raise ValueError("The invoice plan schema version is unsupported.")
    organisation = plan.get("organisation")
    invoice = plan.get("invoice")
    if not isinstance(organisation, dict) or not organisation.get("tenant_id"):
        raise ValueError("The invoice plan requires an organisation tenant_id.")
    if not isinstance(invoice, dict):
        raise ValueError("The invoice plan requires an invoice object.")
    if invoice.get("Type") != "ACCREC" or invoice.get("Status") != "DRAFT":
        raise ValueError("Only DRAFT ACCREC invoice plans are accepted.")
    if invoice.get("LineAmountTypes") not in {"Inclusive", "Exclusive"}:
        raise ValueError("LineAmountTypes must be Inclusive or Exclusive.")
    if not str(invoice.get("ContactName", "")).strip():
        raise ValueError("The invoice plan requires ContactName.")
    if not isinstance(invoice.get("CreateContactIfMissing"), bool):
        raise ValueError("CreateContactIfMissing must be true or false.")
    reference = str(invoice.get("Reference", "")).strip()
    if not reference:
        raise ValueError("A stable Reference is required for idempotent reconciliation.")
    try:
        dt.date.fromisoformat(str(invoice.get("Date", "")))
    except ValueError as exc:
        raise ValueError("Invoice Date must use YYYY-MM-DD.") from exc
    lines = invoice.get("LineItems")
    if not isinstance(lines, list) or not lines:
        raise ValueError("The invoice plan requires LineItems.")
    total = Decimal("0")
    for position, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            raise ValueError(f"Line item {position} must be an object.")
        for field in (
            "Description",
            "Quantity",
            "UnitAmount",
            "AccountID",
            "AccountCode",
            "AccountName",
            "TaxType",
        ):
            if line.get(field) in (None, ""):
                raise ValueError(f"Line item {position} requires {field}.")
        quantity = decimal(line["Quantity"], f"Line item {position} Quantity")
        unit_amount = decimal(line["UnitAmount"], f"Line item {position} UnitAmount")
        total += quantity * unit_amount
    expected_total = decimal(invoice.get("ExpectedTotal"), "ExpectedTotal")
    if total != expected_total:
        raise ValueError(
            f"Line total {total} does not equal ExpectedTotal {expected_total}."
        )
    return plan, raw


def request_collection(
    connection: XeroConnection, url: str, collection_name: str
) -> list[dict[str, Any]]:
    _, body, _ = connection.request("GET", url)
    parsed = json.loads(body)
    collection = parsed.get(collection_name)
    if not isinstance(collection, list):
        raise XeroOAuthError(f"Xero {collection_name} response is malformed.")
    return collection


def find_contacts(
    connection: XeroConnection, contact_name: str
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"where": f'Name=="{contact_name}"'})
    contacts = request_collection(connection, f"{CONTACTS_URL}?{query}", "Contacts")
    return [
        contact
        for contact in contacts
        if str(contact.get("Name", "")).casefold() == contact_name.casefold()
    ]


def validate_contact(contact: dict[str, Any], contact_name: str) -> None:
    if contact.get("HasErrors"):
        errors = contact.get("ValidationErrors") or []
        messages = "; ".join(
            str(error.get("Message", "")) for error in errors if isinstance(error, dict)
        )
        raise ValueError(f"Xero returned contact validation errors: {messages}")
    if str(contact.get("Name", "")).casefold() != contact_name.casefold():
        raise ValueError("Returned Xero contact has the wrong name.")
    if not contact.get("ContactID"):
        raise ValueError(f"Xero contact has no ContactID: {contact_name}")


def ensure_contact(
    connection: XeroConnection,
    contact_name: str,
    create_if_missing: bool,
) -> tuple[dict[str, Any], str]:
    exact = find_contacts(connection, contact_name)
    if len(exact) > 1:
        raise ValueError(f"Multiple exact Xero contacts found: {contact_name}")
    if exact:
        validate_contact(exact[0], contact_name)
        return exact[0], "already_existed_exactly"
    if not create_if_missing:
        raise ValueError(f"Xero contact not found: {contact_name}")

    payload = json.dumps(
        {"Contacts": [{"Name": contact_name}]}, separators=(",", ":")
    ).encode("utf-8")
    try:
        _, body, _ = connection.request(
            "PUT",
            CONTACTS_URL,
            accept="application/json",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = json.loads(body)
        returned = response.get("Contacts")
        contact = returned[0] if isinstance(returned, list) and returned else None
        if not isinstance(contact, dict):
            raise ValueError("Xero did not return the created contact.")
        validate_contact(contact, contact_name)
        return contact, "created_and_verified"
    except (ValueError, XeroOAuthError, json.JSONDecodeError) as exc:
        exact = find_contacts(connection, contact_name)
        if len(exact) == 1:
            validate_contact(exact[0], contact_name)
            return exact[0], "created_and_reconciled"
        if len(exact) > 1:
            raise ValueError(
                f"Contact creation returned an uncertain duplicate result: {contact_name}"
            ) from exc
        raise XeroOAuthError(
            f"Contact creation could not be reconciled after: {exc}"
        ) from exc


def verify_accounts(
    connection: XeroConnection, lines: list[dict[str, Any]]
) -> None:
    accounts = request_collection(connection, ACCOUNTS_URL, "Accounts")
    by_id = {str(account.get("AccountID")): account for account in accounts}
    problems: list[str] = []
    for line in lines:
        account = by_id.get(str(line["AccountID"]))
        if not account:
            problems.append(f"AccountID missing: {line['AccountID']}")
            continue
        expected = {
            "Code": str(line["AccountCode"]),
            "Name": str(line["AccountName"]),
            "TaxType": str(line["TaxType"]),
            "Status": "ACTIVE",
        }
        differences = [
            field
            for field, value in expected.items()
            if str(account.get(field, "")) != value
        ]
        if differences:
            problems.append(
                f"Account {line['AccountCode']} differs in {', '.join(differences)}."
            )
    if problems:
        raise ValueError("Account preflight failed: " + " ".join(problems))


def normalized_line(line: dict[str, Any]) -> tuple[str, Decimal, Decimal, str, str]:
    return (
        str(line.get("Description", "")),
        decimal(line.get("Quantity", 0), "returned Quantity"),
        decimal(line.get("UnitAmount", 0), "returned UnitAmount"),
        str(line.get("AccountID", "")),
        str(line.get("TaxType", "")),
    )


def validate_invoice(
    invoice: dict[str, Any],
    plan_invoice: dict[str, Any],
    contact_id: str,
) -> None:
    if invoice.get("HasErrors"):
        errors = invoice.get("ValidationErrors") or []
        messages = "; ".join(
            str(error.get("Message", "")) for error in errors if isinstance(error, dict)
        )
        raise ValueError(f"Xero returned invoice validation errors: {messages}")
    expected = {
        "Type": "ACCREC",
        "Status": "DRAFT",
        "LineAmountTypes": plan_invoice["LineAmountTypes"],
        "Reference": plan_invoice["Reference"],
    }
    for field, value in expected.items():
        if str(invoice.get(field, "")) != str(value):
            raise ValueError(f"Returned invoice has unexpected {field}.")
    returned_contact_id = str((invoice.get("Contact") or {}).get("ContactID", ""))
    if returned_contact_id != contact_id:
        raise ValueError("Returned invoice has the wrong contact.")
    expected_lines = {
        normalized_line(
            {
                "Description": line["Description"],
                "Quantity": line["Quantity"],
                "UnitAmount": line["UnitAmount"],
                "AccountID": line["AccountID"],
                "TaxType": line["TaxType"],
            }
        )
        for line in plan_invoice["LineItems"]
    }
    returned_lines = {
        normalized_line(line) for line in invoice.get("LineItems", [])
    }
    if returned_lines != expected_lines:
        raise ValueError("Returned invoice line items do not match the approved plan.")
    expected_total = decimal(plan_invoice["ExpectedTotal"], "ExpectedTotal")
    if decimal(invoice.get("Total"), "returned Total") != expected_total:
        raise ValueError("Returned invoice total does not match the approved plan.")


def find_by_reference(
    connection: XeroConnection,
    reference: str,
    plan_invoice: dict[str, Any],
    contact_id: str,
) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {"where": f'Reference=="{reference}"', "summaryOnly": "false"}
    )
    invoices = request_collection(connection, f"{INVOICES_URL}?{query}", "Invoices")
    matching_contact = [
        invoice
        for invoice in invoices
        if str((invoice.get("Contact") or {}).get("ContactID", "")) == contact_id
        and str(invoice.get("Reference", "")) == reference
    ]
    if not matching_contact:
        return None
    if len(matching_contact) != 1:
        raise ValueError("Multiple invoices use the idempotency reference.")
    invoice = matching_contact[0]
    if not invoice.get("LineItems") and invoice.get("InvoiceID"):
        invoice = get_invoice(connection, str(invoice["InvoiceID"]))
    validate_invoice(invoice, plan_invoice, contact_id)
    return invoice


def get_invoice(connection: XeroConnection, invoice_id: str) -> dict[str, Any]:
    invoices = request_collection(
        connection, f"{INVOICES_URL}/{invoice_id}", "Invoices"
    )
    if len(invoices) != 1:
        raise ValueError(f"Could not retrieve exactly one invoice: {invoice_id}")
    return invoices[0]


def invoice_payload(
    plan_invoice: dict[str, Any], contact_id: str
) -> dict[str, Any]:
    return {
        "Type": "ACCREC",
        "Contact": {"ContactID": contact_id},
        "Date": plan_invoice["Date"],
        "LineAmountTypes": plan_invoice["LineAmountTypes"],
        "Reference": plan_invoice["Reference"],
        "Status": "DRAFT",
        "LineItems": [
            {
                "Description": line["Description"],
                "Quantity": line["Quantity"],
                "UnitAmount": line["UnitAmount"],
                "AccountID": line["AccountID"],
                "TaxType": line["TaxType"],
            }
            for line in plan_invoice["LineItems"]
        ],
    }


def result_summary(invoice: dict[str, Any], outcome: str) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "InvoiceID": invoice.get("InvoiceID"),
        "InvoiceNumber": invoice.get("InvoiceNumber"),
        "Status": invoice.get("Status"),
        "Type": invoice.get("Type"),
        "Reference": invoice.get("Reference"),
        "DateString": invoice.get("DateString"),
        "SubTotal": invoice.get("SubTotal"),
        "TotalTax": invoice.get("TotalTax"),
        "Total": invoice.get("Total"),
        "CurrencyCode": invoice.get("CurrencyCode"),
        "Contact": {
            "ContactID": (invoice.get("Contact") or {}).get("ContactID"),
            "Name": (invoice.get("Contact") or {}).get("Name"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--requesting-node", required=True)
    args = parser.parse_args()
    if args.result.exists():
        parser.error(f"Refusing to overwrite result: {args.result}")

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        plan, raw_plan = load_plan(args.plan)
        plan_invoice = plan["invoice"]
        tenant_id = str(plan["organisation"]["tenant_id"])
        connection = XeroConnection.from_environment()
        connection.select_tenant(tenant_id)
        verify_accounts(connection, plan_invoice["LineItems"])
    except (OSError, ValueError, XeroOAuthError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    result_document: dict[str, Any] = {
        "schema_version": 1,
        "operation": "create_xero_draft_invoice",
        "started_at_utc": started_at,
        "completed_at_utc": None,
        "requesting_node": args.requesting_node,
        "tenant_id": tenant_id,
        "organisation_name": plan["organisation"].get("name"),
        "plan_path": str(args.plan),
        "plan_sha256": hashlib.sha256(raw_plan).hexdigest(),
        "status": "in_progress",
        "contact": None,
        "invoice": None,
    }
    atomic_json(args.result, result_document)

    try:
        contact, contact_outcome = ensure_contact(
            connection,
            str(plan_invoice["ContactName"]),
            bool(plan_invoice["CreateContactIfMissing"]),
        )
        contact_id = str(contact["ContactID"])
        result_document["contact"] = {
            "outcome": contact_outcome,
            "ContactID": contact_id,
            "Name": contact.get("Name"),
            "ContactStatus": contact.get("ContactStatus"),
        }
        atomic_json(args.result, result_document)
        existing = find_by_reference(
            connection, str(plan_invoice["Reference"]), plan_invoice, contact_id
        )
    except (ValueError, XeroOAuthError, json.JSONDecodeError) as exc:
        result_document["status"] = "stopped_before_invoice"
        result_document["error"] = str(exc)
        result_document["completed_at_utc"] = dt.datetime.now(
            dt.timezone.utc
        ).isoformat()
        atomic_json(args.result, result_document)
        print(f"Invoice creation stopped before the invoice write: {exc}")
        return 2

    if existing:
        result_document["invoice"] = result_summary(
            existing, "already_existed_exactly"
        )
    else:
        payload = json.dumps(
            {"Invoices": [invoice_payload(plan_invoice, contact_id)]},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            _, body, _ = connection.request(
                "PUT",
                INVOICES_URL,
                accept="application/json",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = json.loads(body)
            returned = response.get("Invoices")
            invoice = returned[0] if isinstance(returned, list) and returned else None
            if not isinstance(invoice, dict) or not invoice.get("InvoiceID"):
                raise ValueError("Xero did not return a created InvoiceID.")
            invoice = get_invoice(connection, str(invoice["InvoiceID"]))
            validate_invoice(invoice, plan_invoice, contact_id)
            result_document["invoice"] = result_summary(
                invoice, "created_and_verified"
            )
        except (ValueError, XeroOAuthError, json.JSONDecodeError) as exc:
            try:
                invoice = find_by_reference(
                    connection,
                    str(plan_invoice["Reference"]),
                    plan_invoice,
                    contact_id,
                )
            except (ValueError, XeroOAuthError, json.JSONDecodeError):
                invoice = None
            if invoice:
                result_document["invoice"] = result_summary(
                    invoice, "created_and_reconciled"
                )
            else:
                result_document["status"] = "stopped_uncertain"
                result_document["error"] = (
                    "The invoice write could not be reconciled after: " + str(exc)
                )
                result_document["completed_at_utc"] = dt.datetime.now(
                    dt.timezone.utc
                ).isoformat()
                atomic_json(args.result, result_document)
                print(result_document["error"])
                return 2

    result_document["status"] = "complete"
    result_document["completed_at_utc"] = dt.datetime.now(
        dt.timezone.utc
    ).isoformat()
    atomic_json(args.result, result_document)
    summary = result_document["invoice"] or {}
    print(
        f"Xero draft invoice {summary.get('outcome')}: "
        f"{summary.get('InvoiceNumber') or summary.get('InvoiceID')} "
        f"total {summary.get('Total')}."
    )
    print(f"Result: {args.result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
