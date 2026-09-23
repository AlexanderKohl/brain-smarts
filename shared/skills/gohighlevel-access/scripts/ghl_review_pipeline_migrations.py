"""Review HighLevel pipeline/stage migrations for one explicit sub-account.

Reuses the connected agency OAuth entry ``ghl-agency-oauth`` via
``HighLevelConnection.from_environment()`` and derives a temporary Location
token for the target sub-account. There is no ``--token`` flag and no Private
Integration Token path.

Run with the Vault Agent unlocked (preferred), or:

    python shared/skills/manage-credentials/scripts/vault_credentials.py run `
      --entry ghl-agency-oauth `
      --map GHL_CLIENT_ID=client_id `
      --map GHL_CLIENT_SECRET=client_secret `
      -- python shared/skills/gohighlevel-access/scripts/ghl_review_pipeline_migrations.py `
      --location-id LOCATION_ID

Example sub-account (fictional, not a default): Example Plumbing Pty Ltd
(``loc_EXAMPLE123``). The owner's known stage mappings are owner data and live at
``/memory/skills/gohighlevel-access/data/opportunity-stage-mappings.json``, found by
locating the brain root (the nearest ancestor holding ``CONTRACT.md``). Local review UI defaults to port 8769 (8765–8768
are reserved for other brain local services).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ghl_oauth import HighLevelConnection, HighLevelOAuthError
from ghl_oauth.client import API_ROOT


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = SKILL_ROOT.name


def brain_root(start: Path = SKILL_ROOT) -> Path:
    """The brain root: the nearest ancestor holding CONTRACT.md (CONTRACT section 1)."""
    for parent in [start, *start.parents]:
        if (parent / "CONTRACT.md").is_file():
            return parent
    # Outside a brain checkout: keep the old layout's answer (three levels above the skill).
    return SKILL_ROOT.parents[2]


REPO_ROOT = brain_root()
DEFAULT_OUTPUT_DIR = REPO_ROOT / "temp" / "ghl-migration-output"
# Owner configuration for a shared skill lives at /memory/skills/<skill>/ (brain-memory).
DEFAULT_MAPPINGS_FILE = REPO_ROOT / "memory" / "skills" / SKILL_NAME / "data" / "opportunity-stage-mappings.json"
# Avoid 8765–8768 (Xero, HighLevel OAuth, Google, AI session viewer).
DEFAULT_PORT = 8769


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch HighLevel pipelines and opportunities for one sub-account, "
            "summarise non-empty stages, and serve a local review UI for "
            "migration decisions. Auth uses the agency OAuth connection "
            "(Location token derived for --location-id / --name)."
        )
    )
    parser.add_argument(
        "--location-id",
        default="",
        help="Target HighLevel sub-account (location) ID.",
    )
    parser.add_argument(
        "--name",
        default="",
        help="Target sub-account name (resolved from the cached location_catalog).",
    )
    parser.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Rediscover approved subaccounts before resolving --name.",
    )
    parser.add_argument(
        "--version",
        default="",
        help=(
            "Optional Version header override. Default is the skill client "
            "resource version (2021-07-28)."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Local port for the review UI (default {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local host interface for the review UI.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=(
            "Directory for generated summary and apply result files "
            f"(default {DEFAULT_OUTPUT_DIR})."
        ),
    )
    parser.add_argument(
        "--mappings-file",
        default=str(DEFAULT_MAPPINGS_FILE),
        help="JSON file containing known source-to-target stage mappings.",
    )
    return parser


def resolve_location_id(
    connection: HighLevelConnection,
    status: dict[str, Any],
    *,
    location_id: str,
    name: str,
    refresh_catalog: bool,
) -> tuple[str, str]:
    """Return (location_id, display_name). Requires --location-id and/or --name."""
    location_id = (location_id or "").strip()
    name = (name or "").strip()
    if not location_id and not name:
        print("Provide --location-id and/or --name.", file=sys.stderr)
        raise SystemExit(2)

    if refresh_catalog:
        catalog = connection.refresh_location_catalog()
    else:
        catalog = status.get("location_catalog") or []

    if name:
        matches = [
            item
            for item in catalog
            if isinstance(item, dict) and item.get("name") == name
        ]
        if not matches:
            print(
                f"No cached sub-account named {name!r} was found. "
                "Re-run with --refresh-catalog, or pass --location-id directly.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if len(matches) > 1:
            print(
                f"Multiple sub-accounts are named {name!r}; pass --location-id "
                "to disambiguate:",
                file=sys.stderr,
            )
            for item in matches:
                print(f"  {item.get('id')}", file=sys.stderr)
            raise SystemExit(2)
        resolved_id = str(matches[0].get("id") or "").strip()
        if location_id and location_id != resolved_id:
            print(
                f"--location-id {location_id!r} does not match catalogue entry "
                f"for {name!r} ({resolved_id!r}).",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return resolved_id, name

    display = next(
        (
            str(item.get("name") or "").strip()
            for item in catalog
            if isinstance(item, dict) and item.get("id") == location_id
        ),
        "",
    )
    return location_id, display or location_id


def json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json_dump(value) + "\n", encoding="utf-8")


def normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def stage_group_key(pipeline_id: str, stage_id: str) -> str:
    return f"{pipeline_id}::{stage_id}"


def parse_runtime_error_payload(exc: Exception) -> dict[str, Any]:
    try:
        payload = json.loads(str(exc))
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {"message": str(exc)}


def build_valid_user_lookup(users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for user in users:
        user_id = user.get("id")
        if user_id:
            lookup[user_id] = user
    return lookup


def build_invalid_assigned_user_summary(
    opportunities: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid_user_lookup = build_valid_user_lookup(users)
    grouped: dict[str, dict[str, Any]] = {}

    for opportunity in opportunities:
        assigned_to = opportunity.get("assignedTo")
        if not assigned_to or assigned_to in valid_user_lookup:
            continue
        if assigned_to not in grouped:
            grouped[assigned_to] = {
                "invalidUserId": assigned_to,
                "opportunityCount": 0,
                "opportunityIds": [],
                "sampleOpportunityNames": [],
            }
        item = grouped[assigned_to]
        item["opportunityCount"] += 1
        item["opportunityIds"].append(opportunity.get("id"))
        name = opportunity.get("name")
        if name and len(item["sampleOpportunityNames"]) < 5:
            item["sampleOpportunityNames"].append(name)

    return sorted(
        grouped.values(),
        key=lambda item: (-item["opportunityCount"], item["invalidUserId"]),
    )


class ApiClient:
    """Thin wrapper around HighLevelConnection for location-scoped CRM calls."""

    def __init__(
        self,
        connection: HighLevelConnection,
        location_id: str,
        version: str = "",
    ) -> None:
        self.connection = connection
        self.location_id = location_id
        self.version = version.strip()
        self.base_url = API_ROOT.rstrip("/")

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.version:
            headers["Version"] = self.version
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            filtered_query = {
                key: value
                for key, value in query.items()
                if value is not None and value != ""
            }
            url = f"{url}?{urllib.parse.urlencode(filtered_query)}"
        return self._request_absolute_url(method, url, body=body)

    def _request_absolute_url(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers = self._headers(json_body=body is not None)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        try:
            _status, raw, _resp_headers = self.connection.request(
                method,
                url,
                location_id=self.location_id,
                body=data,
                headers=headers,
                expected=(200, 201),
            )
            payload = raw.decode("utf-8", errors="replace")
            return json.loads(payload) if payload else {}
        except HighLevelOAuthError as exc:
            raise RuntimeError(
                json.dumps(
                    {
                        "status": "highlevel_error",
                        "message": str(exc),
                    }
                )
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                json.dumps(
                    {
                        "status": "invalid_json",
                        "message": str(exc),
                    }
                )
            ) from exc

    def get_pipelines(self, location_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/opportunities/pipelines",
            query={"locationId": location_id},
        )
        if isinstance(payload, dict):
            return payload.get("pipelines", [])
        return payload

    def search_opportunities_page(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", "/opportunities/search", body=body)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected opportunities response format.")
        return payload

    def get_opportunities_page(self, query: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("GET", "/opportunities/search", query=query)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected opportunities response format.")
        return payload

    def get_opportunities_page_by_url(self, url: str) -> dict[str, Any]:
        payload = self._request_absolute_url("GET", url)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected opportunities response format.")
        return payload

    def get_users(self, location_id: str) -> list[dict[str, Any]]:
        attempts = [
            ("/users/search", {"locationId": location_id}),
            ("/users/", {"locationId": location_id}),
            ("/users", {"locationId": location_id}),
        ]
        last_error: Exception | None = None
        for path, query in attempts:
            try:
                payload = self._request("GET", path, query=query)
                if isinstance(payload, dict):
                    users = payload.get("users", [])
                elif isinstance(payload, list):
                    users = payload
                else:
                    users = []
                if users:
                    return [user for user in users if not user.get("deleted")]
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error:
            raise last_error
        return []

    def update_opportunity(
        self,
        opportunity: dict[str, Any],
        target_pipeline_id: str,
        target_stage_id: str,
        include_assigned_to: bool = True,
        assigned_to_override: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": opportunity.get("name") or "",
            "monetaryValue": opportunity.get("monetaryValue") or 0,
            "status": opportunity.get("status") or "open",
            "pipelineId": target_pipeline_id,
            "pipelineStageId": target_stage_id,
        }
        assigned_to = opportunity.get("assignedTo")
        if include_assigned_to:
            if assigned_to_override:
                body["assignedTo"] = assigned_to_override
            elif assigned_to:
                body["assignedTo"] = assigned_to
        forecast_probability = opportunity.get("forecastProbability")
        if forecast_probability is not None:
            body["forecastProbability"] = forecast_probability
        return self._request(
            "PUT",
            f"/opportunities/{opportunity['id']}",
            body=body,
        )


def fetch_all_opportunities(client: ApiClient, location_id: str) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    next_page_url: str | None = None
    used_status_all = True

    while True:
        try:
            if next_page_url:
                payload = client.get_opportunities_page_by_url(next_page_url)
            elif used_status_all:
                # GET /opportunities/search requires location_id (not locationId).
                payload = client.get_opportunities_page(
                    {"location_id": location_id, "status": "all"}
                )
            else:
                payload = client.get_opportunities_page({"location_id": location_id})
        except RuntimeError:
            if used_status_all and not next_page_url:
                used_status_all = False
                opportunities = []
                continue
            raise

        page_opportunities = payload.get("opportunities", [])
        opportunities.extend(page_opportunities)
        meta = payload.get("meta") or {}
        next_page_url = meta.get("nextPageUrl")
        if not next_page_url:
            break

    return opportunities


def load_known_mappings(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("Mappings file must contain a JSON array.")
    return payload


def build_lookup_indexes(
    pipelines: list[dict[str, Any]]
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, int],
    dict[str, int],
    dict[str, str],
    dict[tuple[str, str], dict[str, Any]],
]:
    pipelines_by_id: dict[str, dict[str, Any]] = {}
    pipeline_order: dict[str, int] = {}
    stage_order: dict[str, int] = {}
    pipeline_name_lookup: dict[str, str] = {}
    stage_lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for pipeline_index, pipeline in enumerate(pipelines):
        pipeline_id = pipeline["id"]
        pipelines_by_id[pipeline_id] = pipeline
        pipeline_order[pipeline_id] = pipeline_index
        pipeline_name_lookup[normalise_name(pipeline["name"])] = pipeline_id
        for stage_index, stage in enumerate(pipeline.get("stages", [])):
            stage_id = stage["id"]
            stage_order[stage_id] = stage_index
            stage_lookup[(pipeline_id, normalise_name(stage["name"]))] = stage

    return (
        pipelines_by_id,
        pipeline_order,
        stage_order,
        pipeline_name_lookup,
        stage_lookup,
    )


def resolve_named_stage(
    source_pipeline_name: str,
    source_stage_name: str,
    pipeline_name_lookup: dict[str, str],
    stage_lookup: dict[tuple[str, str], dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    pipeline_id = pipeline_name_lookup.get(normalise_name(source_pipeline_name))
    if not pipeline_id:
        raise RuntimeError(f"Unknown pipeline in mappings file: {source_pipeline_name}")
    stage = stage_lookup.get((pipeline_id, normalise_name(source_stage_name)))
    if not stage:
        raise RuntimeError(
            f"Unknown stage in mappings file: {source_pipeline_name} -> {source_stage_name}"
        )
    return pipeline_id, stage


def build_stage_group_summary(
    pipelines: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    known_mappings: list[dict[str, str]],
) -> dict[str, Any]:
    (
        pipelines_by_id,
        pipeline_order,
        stage_order,
        pipeline_name_lookup,
        stage_lookup,
    ) = build_lookup_indexes(pipelines)

    grouped_opportunities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for opportunity in opportunities:
        pipeline_id = opportunity.get("pipelineId")
        stage_id = opportunity.get("pipelineStageId")
        if not pipeline_id or not stage_id:
            continue
        if pipeline_id not in pipelines_by_id:
            continue
        group_key = stage_group_key(pipeline_id, stage_id)
        grouped_opportunities[group_key].append(opportunity)

    resolved_mapping_lookup: dict[str, dict[str, Any]] = {}
    for mapping in known_mappings:
        try:
            source_pipeline_id, source_stage = resolve_named_stage(
                mapping["source_pipeline"],
                mapping["source_stage"],
                pipeline_name_lookup,
                stage_lookup,
            )
            target_pipeline_id, target_stage = resolve_named_stage(
                mapping["target_pipeline"],
                mapping["target_stage"],
                pipeline_name_lookup,
                stage_lookup,
            )
        except RuntimeError as exc:
            # Known mappings are optional hints; a renamed/removed stage must not
            # prevent the review UI from starting for this sub-account.
            print(f"Skipping known mapping: {exc}", file=sys.stderr)
            continue
        group_key = stage_group_key(source_pipeline_id, source_stage["id"])
        resolved_mapping_lookup[group_key] = {
            "action": "move",
            "sourcePipelineId": source_pipeline_id,
            "sourcePipelineName": mapping["source_pipeline"],
            "sourceStageId": source_stage["id"],
            "sourceStageName": source_stage["name"],
            "targetPipelineId": target_pipeline_id,
            "targetPipelineName": mapping["target_pipeline"],
            "targetStageId": target_stage["id"],
            "targetStageName": target_stage["name"],
            "ruleSource": "known",
        }

    summary_rows: list[dict[str, Any]] = []
    for group_key, items in grouped_opportunities.items():
        pipeline_id, stage_id = group_key.split("::", 1)
        pipeline = pipelines_by_id[pipeline_id]
        stage = next(
            (candidate for candidate in pipeline.get("stages", []) if candidate["id"] == stage_id),
            None,
        )
        if not stage:
            continue
        row = {
            "groupKey": group_key,
            "sourcePipelineId": pipeline_id,
            "sourcePipelineName": pipeline["name"],
            "sourceStageId": stage_id,
            "sourceStageName": stage["name"],
            "sourceStagePosition": stage.get("position", stage_order.get(stage_id, 0)),
            "count": len(items),
            "opportunities": items,
            "decision": resolved_mapping_lookup.get(group_key),
            "needsChoice": group_key not in resolved_mapping_lookup,
        }
        summary_rows.append(row)

    summary_rows.sort(
        key=lambda row: (
            pipeline_order.get(row["sourcePipelineId"], 0),
            int(row["sourceStagePosition"]),
            row["sourceStageName"],
        )
    )

    available_targets = [
        {
            "id": pipeline["id"],
            "name": pipeline["name"],
            "stages": [
                {
                    "id": stage["id"],
                    "name": stage["name"],
                    "position": stage.get("position", 0),
                }
                for stage in pipeline.get("stages", [])
            ],
        }
        for pipeline in pipelines
    ]

    return {
        "summaryRows": summary_rows,
        "availableTargets": available_targets,
        "knownMappingCount": len(
            [row for row in summary_rows if (row.get("decision") or {}).get("ruleSource") == "known"]
        ),
        "unmappedCount": len([row for row in summary_rows if row["needsChoice"]]),
        "totalOpportunities": len(opportunities),
        "totalNonEmptyStages": len(summary_rows),
    }


def build_summary_document(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "locationId": state["locationId"],
        "locationName": state.get("locationName"),
        "totalOpportunities": state["summary"]["totalOpportunities"],
        "totalNonEmptyStages": state["summary"]["totalNonEmptyStages"],
        "knownMappingCount": state["summary"]["knownMappingCount"],
        "unmappedCount": state["summary"]["unmappedCount"],
        "rows": [
            {
                "sourcePipelineName": row["sourcePipelineName"],
                "sourceStageName": row["sourceStageName"],
                "count": row["count"],
                "decision": row["decision"] or {"action": "needs_choice"},
            }
            for row in state["summary"]["summaryRows"]
        ],
    }


def print_console_summary(state: dict[str, Any]) -> None:
    print("")
    print("Occupied pipeline stages")
    print("------------------------")
    for row in state["summary"]["summaryRows"]:
        decision = row.get("decision")
        if decision and decision.get("action") == "move":
            target_label = (
                f"{decision['targetPipelineName']} -> {decision['targetStageName']}"
            )
        else:
            target_label = "Needs choice"
        print(
            f"{row['sourcePipelineName']} -> {row['sourceStageName']}: "
            f"{row['count']} opportunity(s) | {target_label}"
        )
    print("")


def build_ui_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "locationId": state["locationId"],
        "summary": [
            {
                "groupKey": row["groupKey"],
                "sourcePipelineName": row["sourcePipelineName"],
                "sourceStageName": row["sourceStageName"],
                "count": row["count"],
                "decision": row["decision"],
                "needsChoice": row["needsChoice"],
            }
            for row in state["summary"]["summaryRows"]
        ],
        "availableTargets": state["summary"]["availableTargets"],
        "invalidAssignedUsers": state["invalidAssignedUsers"],
        "users": state["users"],
    }


def html_escape_json(value: Any) -> str:
    return json.dumps(value).replace("<", "\\u003c")


def render_index_html(state: dict[str, Any]) -> bytes:
    payload = html_escape_json(build_ui_payload(state))
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GHL Migration Review</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f3ef;
      --panel: #fffdf8;
      --line: #d8d1c3;
      --text: #1f2933;
      --muted: #52606d;
      --accent: #0f766e;
      --accent-soft: #d7f2ef;
      --warn: #b45309;
      --warn-soft: #fef3c7;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: linear-gradient(180deg, #f4efe7 0%, #f7f7f5 100%);
      color: var(--text);
    }
    .wrap {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }
    .hero {
      padding: 24px;
      margin-bottom: 20px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 28px;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .stat {
      background: #fcfaf6;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }
    .stat strong {
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }
    .panel {
      padding: 20px;
      margin-bottom: 20px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 600;
    }
    .badge-known {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .badge-choice {
      background: var(--warn-soft);
      color: var(--warn);
    }
    .choice-grid {
      display: grid;
      gap: 14px;
    }
    .choice-card {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fcfaf6;
      padding: 16px;
    }
    .choice-head {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .choice-title {
      font-weight: 700;
    }
    .choice-meta {
      color: var(--muted);
      font-size: 14px;
    }
    .controls {
      display: grid;
      grid-template-columns: 180px 1fr 1fr;
      gap: 10px;
      align-items: center;
    }
    select, button {
      font: inherit;
      border-radius: 10px;
      border: 1px solid #b9b3a7;
      padding: 10px 12px;
      background: white;
    }
    button {
      cursor: pointer;
      background: #134e4a;
      color: white;
      border-color: #134e4a;
    }
    button.secondary {
      background: white;
      color: var(--text);
      border-color: #b9b3a7;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }
    .result {
      margin-top: 16px;
      padding: 14px;
      border-radius: 12px;
      white-space: pre-wrap;
      background: #f6f8fa;
      border: 1px solid var(--line);
      display: none;
    }
    .empty {
      color: var(--muted);
    }
    @media (max-width: 760px) {
      .controls {
        grid-template-columns: 1fr;
      }
      th:nth-child(4), td:nth-child(4) {
        display: none;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>GHL migration review</h1>
      <p>Review non-empty source stages, confirm targets for anything unmapped, then apply the moves in one pass.</p>
      <div class="stats" id="stats"></div>
    </section>

    <section class="panel">
      <h2>Occupied stages</h2>
      <table>
        <thead>
          <tr>
            <th>Source pipeline</th>
            <th>Source stage</th>
            <th>Count</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody id="summary-body"></tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Unmapped stages</h2>
      <p class="empty" id="unmapped-empty" style="display:none;">Everything with opportunities already has a target mapping.</p>
      <div class="choice-grid" id="choice-grid"></div>
      <div class="actions">
        <button class="secondary" id="download-btn" type="button">Download decisions JSON</button>
        <button id="apply-btn" type="button">Apply mapped moves</button>
      </div>
      <div class="result" id="result-box"></div>
    </section>

    <section class="panel" id="assigned-user-panel" style="display:none;">
      <h2>Assigned user review</h2>
      <p class="empty" id="assigned-user-empty">Choose a replacement user for each invalid assigned user before applying the moves.</p>
      <div class="choice-grid" id="assigned-user-grid"></div>
    </section>
  </div>

  <script id="app-data" type="application/json">__APP_DATA__</script>
  <script>
    const appData = JSON.parse(document.getElementById("app-data").textContent);
    const targetsByPipeline = Object.fromEntries(
      appData.availableTargets.map((pipeline) => [pipeline.id, pipeline])
    );
    const validUsers = (appData.users || []).map((user) => ({
      id: user.id,
      name: user.name || [user.firstName, user.lastName].filter(Boolean).join(' '),
      email: user.email || '',
    }));
    const invalidAssignedUsers = appData.invalidAssignedUsers || [];

    function labelForDecision(decision) {
      if (!decision) {
        return '<span class="badge badge-choice">Needs choice</span>';
      }
      if (decision.action === 'skip') {
        return '<span class="badge badge-choice">Do not move</span>';
      }
      return `<span class="badge badge-known">${decision.targetPipelineName} -> ${decision.targetStageName}</span>`;
    }

    function renderStats() {
      const summary = appData.summary;
      const stats = [
        ['Occupied stages', summary.length],
        ['Needs choice', summary.filter((row) => row.needsChoice).length],
        ['Known rules', summary.filter((row) => row.decision && row.decision.ruleSource === 'known').length],
        ['Total opportunities', summary.reduce((total, row) => total + row.count, 0)],
      ];
      const container = document.getElementById('stats');
      container.innerHTML = stats.map(([label, value]) => `
        <div class="stat">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `).join('');
    }

    function renderSummaryTable() {
      const body = document.getElementById('summary-body');
      body.innerHTML = appData.summary.map((row) => `
        <tr>
          <td>${row.sourcePipelineName}</td>
          <td>${row.sourceStageName}</td>
          <td>${row.count}</td>
          <td>${labelForDecision(row.decision)}</td>
        </tr>
      `).join('');
    }

    function createPipelineOptions(selectedPipelineId) {
      const items = [
        '<option value="skip">Do not move</option>',
        ...appData.availableTargets.map((pipeline) => {
          const selected = pipeline.id === selectedPipelineId ? ' selected' : '';
          return `<option value="${pipeline.id}"${selected}>${pipeline.name}</option>`;
        })
      ];
      return items.join('');
    }

    function createStageOptions(pipelineId, selectedStageId) {
      if (!pipelineId || pipelineId === 'skip') {
        return '<option value="">No stage needed</option>';
      }
      const pipeline = targetsByPipeline[pipelineId];
      if (!pipeline) {
        return '<option value="">Choose a pipeline first</option>';
      }
      return pipeline.stages.map((stage) => {
        const selected = stage.id === selectedStageId ? ' selected' : '';
        return `<option value="${stage.id}"${selected}>${stage.name}</option>`;
      }).join('');
    }

    function createUserOptions(selectedUserId) {
      const items = ['<option value="">Choose a replacement user</option>'];
      for (const user of validUsers) {
        const selected = user.id === selectedUserId ? ' selected' : '';
        const label = user.email ? `${user.name || user.id} (${user.email})` : (user.name || user.id);
        items.push(`<option value="${user.id}"${selected}>${label}</option>`);
      }
      return items.join('');
    }

    function renderChoices() {
      const unresolved = appData.summary.filter((row) => row.needsChoice);
      const container = document.getElementById('choice-grid');
      const empty = document.getElementById('unmapped-empty');
      if (!unresolved.length) {
        empty.style.display = 'block';
        container.innerHTML = '';
        return;
      }
      empty.style.display = 'none';
      container.innerHTML = unresolved.map((row) => `
        <div class="choice-card" data-group-key="${row.groupKey}">
          <div class="choice-head">
            <div>
              <div class="choice-title">${row.sourcePipelineName} -> ${row.sourceStageName}</div>
              <div class="choice-meta">${row.count} opportunity(s)</div>
            </div>
            <span class="badge badge-choice">Needs choice</span>
          </div>
          <div class="controls">
            <label>
              Action
              <select class="target-pipeline">
                ${createPipelineOptions('skip')}
              </select>
            </label>
            <label>
              Pipeline
              <select class="target-pipeline-duplicate" disabled>
                <option value="">Selected above</option>
              </select>
            </label>
            <label>
              Stage
              <select class="target-stage" disabled>
                <option value="">No stage needed</option>
              </select>
            </label>
          </div>
        </div>
      `).join('');

      container.querySelectorAll('.choice-card').forEach((card) => {
        const primarySelect = card.querySelector('.target-pipeline');
        const duplicateSelect = card.querySelector('.target-pipeline-duplicate');
        const stageSelect = card.querySelector('.target-stage');
        const sync = () => {
          duplicateSelect.innerHTML = primarySelect.value === 'skip'
            ? '<option value="">Do not move</option>'
            : `<option value="${primarySelect.value}">${targetsByPipeline[primarySelect.value].name}</option>`;
          stageSelect.innerHTML = createStageOptions(primarySelect.value, stageSelect.value);
          stageSelect.disabled = primarySelect.value === 'skip';
        };
        primarySelect.addEventListener('change', sync);
        sync();
      });
    }

    function collectDecisions() {
      const unresolved = appData.summary.filter((row) => row.needsChoice);
      const decisions = {};
      for (const row of unresolved) {
        const card = document.querySelector(`[data-group-key="${row.groupKey}"]`);
        const pipelineSelect = card.querySelector('.target-pipeline');
        const stageSelect = card.querySelector('.target-stage');
        if (pipelineSelect.value === 'skip') {
          decisions[row.groupKey] = { action: 'skip' };
          continue;
        }
        if (!stageSelect.value) {
          throw new Error(`Choose a target stage for ${row.sourcePipelineName} -> ${row.sourceStageName}.`);
        }
        decisions[row.groupKey] = {
          action: 'move',
          targetPipelineId: pipelineSelect.value,
          targetStageId: stageSelect.value,
        };
      }
      return decisions;
    }

    function downloadDecisions() {
      try {
        const decisions = collectDecisions();
        const blob = new Blob([JSON.stringify(decisions, null, 2)], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'ghl-migration-decisions.json';
        link.click();
        URL.revokeObjectURL(link.href);
      } catch (error) {
        showResult(error.message, true);
      }
    }

    function showResult(message, isError) {
      const box = document.getElementById('result-box');
      box.style.display = 'block';
      box.style.borderColor = isError ? '#dc2626' : '#0f766e';
      box.textContent = message;
    }

    function renderAssignedUserFixes(items) {
      const panel = document.getElementById('assigned-user-panel');
      const grid = document.getElementById('assigned-user-grid');
      const empty = document.getElementById('assigned-user-empty');

      if (!items.length) {
        panel.style.display = 'none';
        grid.innerHTML = '';
        return;
      }

      panel.style.display = 'block';
      empty.style.display = validUsers.length ? 'block' : 'none';
      empty.textContent = validUsers.length
        ? 'Choose a replacement user for each invalid assigned user before applying the moves.'
        : 'No valid users were loaded from GHL, so assigned user replacement is not available yet.';

      grid.innerHTML = items.map((item) => `
        <div class="choice-card" data-invalid-user-id="${item.invalidUserId}">
          <div class="choice-head">
            <div>
              <div class="choice-title">Invalid assigned user: ${item.invalidUserId}</div>
              <div class="choice-meta">${item.opportunityCount} affected opportunit${item.opportunityCount === 1 ? 'y' : 'ies'}</div>
            </div>
            <span class="badge badge-choice">Invalid assigned user</span>
          </div>
          <div class="choice-meta" style="margin-bottom:10px;">Examples: ${(item.sampleOpportunityNames || []).join(', ') || 'No examples available'}</div>
          <div class="controls">
            <label>
              Replacement user
              <select class="assigned-user-select" ${validUsers.length ? '' : 'disabled'}>
                ${createUserOptions('')}
              </select>
            </label>
          </div>
        </div>
      `).join('');
    }

    function collectAssignedUserReplacements() {
      const replacements = {};
      for (const item of invalidAssignedUsers) {
        const card = document.querySelector(`[data-invalid-user-id="${item.invalidUserId}"]`);
        if (!card) {
          continue;
        }
        const select = card.querySelector('.assigned-user-select');
        if (!select.value) {
          throw new Error(`Choose a replacement user for invalid user ${item.invalidUserId}.`);
        }
        replacements[item.invalidUserId] = select.value;
      }
      return replacements;
    }

    async function applyMoves() {
      let decisions;
      let assignedUserReplacements;
      try {
        decisions = collectDecisions();
        assignedUserReplacements = collectAssignedUserReplacements();
      } catch (error) {
        showResult(error.message, true);
        return;
      }
      showResult('Applying moves, please wait...', false);
      const response = await fetch('/api/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decisions, assignedUserReplacements }),
      });
      const responseBody = await response.json();
      if (!response.ok) {
        showResult(JSON.stringify(responseBody, null, 2), true);
        return;
      }
      showResult(JSON.stringify(responseBody, null, 2), false);
    }

    document.getElementById('download-btn').addEventListener('click', downloadDecisions);
    document.getElementById('apply-btn').addEventListener('click', applyMoves);

    renderStats();
    renderSummaryTable();
    renderChoices();
    renderAssignedUserFixes(invalidAssignedUsers);
  </script>
</body>
</html>
"""
    return html.replace("__APP_DATA__", payload).encode("utf-8")


def validate_decisions(state: dict[str, Any], decisions: dict[str, Any]) -> list[dict[str, Any]]:
    available_targets = {
        pipeline["id"]: {stage["id"] for stage in pipeline["stages"]}
        for pipeline in state["summary"]["availableTargets"]
    }

    final_decisions: list[dict[str, Any]] = []
    for row in state["summary"]["summaryRows"]:
        decision = row.get("decision")
        if row["needsChoice"]:
            decision = decisions.get(row["groupKey"])
            if not decision:
                raise ValueError(
                    f"Missing decision for {row['sourcePipelineName']} -> {row['sourceStageName']}"
                )
        if decision.get("action") == "skip":
            final_decisions.append(
                {
                    "groupKey": row["groupKey"],
                    "action": "skip",
                    "sourcePipelineName": row["sourcePipelineName"],
                    "sourceStageName": row["sourceStageName"],
                    "count": row["count"],
                    "opportunities": row["opportunities"],
                }
            )
            continue
        target_pipeline_id = decision.get("targetPipelineId")
        target_stage_id = decision.get("targetStageId")
        if target_pipeline_id not in available_targets:
            raise ValueError(
                f"Unknown target pipeline for {row['sourcePipelineName']} -> {row['sourceStageName']}"
            )
        if target_stage_id not in available_targets[target_pipeline_id]:
            raise ValueError(
                f"Unknown target stage for {row['sourcePipelineName']} -> {row['sourceStageName']}"
            )
        target_pipeline = next(
            pipeline
            for pipeline in state["summary"]["availableTargets"]
            if pipeline["id"] == target_pipeline_id
        )
        target_stage = next(
            stage for stage in target_pipeline["stages"] if stage["id"] == target_stage_id
        )
        final_decisions.append(
            {
                "groupKey": row["groupKey"],
                "action": "move",
                "sourcePipelineName": row["sourcePipelineName"],
                "sourceStageName": row["sourceStageName"],
                "targetPipelineId": target_pipeline_id,
                "targetPipelineName": target_pipeline["name"],
                "targetStageId": target_stage_id,
                "targetStageName": target_stage["name"],
                "count": row["count"],
                "opportunities": row["opportunities"],
            }
        )
    return final_decisions


def validate_assigned_user_replacements(
    state: dict[str, Any], assigned_user_replacements: dict[str, str]
) -> dict[str, str]:
    invalid_user_ids = {item["invalidUserId"] for item in state["invalidAssignedUsers"]}
    valid_user_ids = state["validUserIds"]
    replacements: dict[str, str] = {}

    for invalid_user_id in invalid_user_ids:
        replacement_user_id = assigned_user_replacements.get(invalid_user_id)
        if not replacement_user_id:
            raise ValueError(f"Choose a replacement user for invalid user {invalid_user_id}.")
        if replacement_user_id not in valid_user_ids:
            raise ValueError(
                f"Replacement user {replacement_user_id} is not a valid current GHL user."
            )
        replacements[invalid_user_id] = replacement_user_id

    return replacements


def apply_moves(
    state: dict[str, Any],
    decisions: dict[str, Any],
    assigned_user_replacements: dict[str, str],
) -> dict[str, Any]:
    final_decisions = validate_decisions(state, decisions)
    replacement_lookup = validate_assigned_user_replacements(state, assigned_user_replacements)
    client: ApiClient = state["client"]
    results: list[dict[str, Any]] = []
    success_count = 0
    skipped_count = 0

    for item in final_decisions:
        if item["action"] == "skip":
            skipped_count += item["count"]
            results.append(
                {
                    "sourcePipelineName": item["sourcePipelineName"],
                    "sourceStageName": item["sourceStageName"],
                    "action": "skip",
                    "count": item["count"],
                }
            )
            continue

        moved = 0
        errors: list[dict[str, Any]] = []
        for opportunity in item["opportunities"]:
            assigned_to_override = None
            existing_assigned_to = opportunity.get("assignedTo")
            if existing_assigned_to in replacement_lookup:
                assigned_to_override = replacement_lookup[existing_assigned_to]
            try:
                client.update_opportunity(
                    opportunity=opportunity,
                    target_pipeline_id=item["targetPipelineId"],
                    target_stage_id=item["targetStageId"],
                    assigned_to_override=assigned_to_override,
                )
                moved += 1
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                parsed_error = parse_runtime_error_payload(exc)
                message = (
                    parsed_error.get("response", {}).get("message")
                    or parsed_error.get("message")
                    or str(exc)
                )
                errors.append(
                    {
                        "opportunityId": opportunity["id"],
                        "opportunityName": opportunity.get("name"),
                        "message": message,
                        "error": str(exc),
                    }
                )
        results.append(
            {
                "sourcePipelineName": item["sourcePipelineName"],
                "sourceStageName": item["sourceStageName"],
                "targetPipelineName": item["targetPipelineName"],
                "targetStageName": item["targetStageName"],
                "requested": item["count"],
                "moved": moved,
                "errors": errors,
            }
        )

    payload = {
        "locationId": state["locationId"],
        "movedOpportunities": success_count,
        "skippedOpportunities": skipped_count,
        "groupResults": results,
    }
    output_path = state["outputDir"] / "apply-results.json"
    write_json(output_path, payload)
    payload["resultsFile"] = str(output_path)
    return payload


def make_handler(state: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            encoded = (json_dump(payload) + "\n").encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                body = render_index_html(state)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/api/summary":
                self._send_json(200, build_summary_document(state))
                return

            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/apply":
                self._send_json(404, {"error": "Not found"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(raw_body) if raw_body else {}
                decisions = payload.get("decisions", {})
                assigned_user_replacements = payload.get("assignedUserReplacements", {})
                result = apply_moves(state, decisions, assigned_user_replacements)
                self._send_json(200, result)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return Handler


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    connection = HighLevelConnection.from_environment()
    status = connection.status()
    if not status.get("connected"):
        print(
            "HighLevel agency is not connected: "
            f"{status.get('error', 'no token stored')}. "
            "Run shared/skills/gohighlevel-access/scripts/ghl_connect.py first.",
            file=sys.stderr,
        )
        return 2

    location_id, location_name = resolve_location_id(
        connection,
        status,
        location_id=args.location_id,
        name=args.name,
        refresh_catalog=args.refresh_catalog,
    )
    print(f"Target HighLevel sub-account: {location_name} ({location_id})")

    client = ApiClient(
        connection=connection,
        location_id=location_id,
        version=args.version,
    )

    known_mappings = load_known_mappings(Path(args.mappings_file))
    pipelines = client.get_pipelines(location_id)
    opportunities = fetch_all_opportunities(client, location_id)
    try:
        users = client.get_users(location_id)
    except Exception:  # noqa: BLE001
        users = []
    invalid_assigned_users = build_invalid_assigned_user_summary(opportunities, users)
    summary = build_stage_group_summary(
        pipelines=pipelines,
        opportunities=opportunities,
        known_mappings=known_mappings,
    )

    state = {
        "client": client,
        "locationId": location_id,
        "locationName": location_name,
        "outputDir": output_dir,
        "allOpportunities": opportunities,
        "allOpportunitiesById": {
            opportunity["id"]: opportunity for opportunity in opportunities
        },
        "invalidAssignedUsers": invalid_assigned_users,
        "validUserIds": {user["id"] for user in users if user.get("id")},
        "users": users,
        "summary": summary,
    }

    summary_path = output_dir / "migration-summary.json"
    write_json(summary_path, build_summary_document(state))
    print_console_summary(state)
    print(f"Summary written to: {summary_path}")

    handler = make_handler(state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Review UI: {url}")
    print("Leave this process running while you review and apply the moves.")
    print("Press Ctrl+C to stop the local server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Stopping review server.")
    finally:
        server.server_close()

    return 0



if __name__ == "__main__":
    raise SystemExit(main())
