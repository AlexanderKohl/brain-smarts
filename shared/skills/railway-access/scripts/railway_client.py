"""Shared Railway GraphQL client. Fail closed without an API token."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
DEFAULT_VAULT_ENTRY = "railway-api"
DEFAULT_VAULT_FIELD = "api_token"
TOKEN_ENV = "RAILWAY_API_TOKEN"
VAULT_ENTRY_ENV = "RAILWAY_VAULT_ENTRY"
VAULT_FIELD_ENV = "RAILWAY_VAULT_FIELD"
USER_AGENT = "brain-railway-access/1.0"

_RELATIVE_RE = re.compile(
    r"^(?P<num>\d+)\s*(?P<unit>s|m|h|d|w|sec|secs|second|seconds|min|mins|"
    r"minute|minutes|hr|hrs|hour|hours|day|days|week|weeks)$",
    re.IGNORECASE,
)


class RailwayError(RuntimeError):
    """Raised when a Railway API call cannot complete safely."""


def vault_entry_name() -> str:
    return (os.environ.get(VAULT_ENTRY_ENV) or DEFAULT_VAULT_ENTRY).strip()


def vault_field_name() -> str:
    return (os.environ.get(VAULT_FIELD_ENV) or DEFAULT_VAULT_FIELD).strip()


def resolve_token() -> str:
    """Return the Railway API token from the environment. Fail closed."""
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        raise RailwayError(
            f"Missing {TOKEN_ENV}. Inject vault field "
            f"`{vault_entry_name()}#{vault_field_name()}` via manage-credentials "
            f"(`vault_credentials.py run --map {TOKEN_ENV}={vault_field_name()}`)."
        )
    if len(token) < 16:
        raise RailwayError(f"{TOKEN_ENV} looks too short to be a Railway API token.")
    return token


def token_tail(token: str, n: int = 4) -> str:
    cleaned = token.strip()
    if len(cleaned) < n:
        return "????"
    return cleaned[-n:]


def parse_time_arg(value: str | None, *, label: str) -> str | None:
    """Parse relative or ISO-8601 time into UTC ISO-8601 for Railway DateTime."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    match = _RELATIVE_RE.match(text)
    if match:
        num = int(match.group("num"))
        unit = match.group("unit").lower()
        if unit in {"s", "sec", "secs", "second", "seconds"}:
            delta = timedelta(seconds=num)
        elif unit in {"m", "min", "mins", "minute", "minutes"}:
            delta = timedelta(minutes=num)
        elif unit in {"h", "hr", "hrs", "hour", "hours"}:
            delta = timedelta(hours=num)
        elif unit in {"d", "day", "days"}:
            delta = timedelta(days=num)
        else:
            delta = timedelta(weeks=num)
        instant = datetime.now(timezone.utc) - delta
        return instant.isoformat().replace("+00:00", "Z")

    normalised = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise RailwayError(
            f"Invalid {label}={value!r}. Use relative (30s, 5m, 2h, 1d, 1w) "
            "or ISO-8601."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST a GraphQL operation. Returns the `data` object; raises on errors."""
    token = resolve_token()
    payload = json.dumps(
        {"query": query, "variables": variables or {}},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code in {401, 403}:
            raise RailwayError(
                f"Railway auth failed HTTP {exc.code} (token rejected or "
                f"insufficient scope). Body: {body}"
            ) from exc
        raise RailwayError(f"Railway HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RailwayError(f"Railway network error: {exc.reason}") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RailwayError("Railway response was not valid JSON.") from exc
    if not isinstance(envelope, dict):
        raise RailwayError("Railway response JSON root must be an object.")

    errors = envelope.get("errors")
    if errors:
        messages = []
        for item in errors:
            if isinstance(item, dict):
                messages.append(str(item.get("message") or item))
            else:
                messages.append(str(item))
        joined = "; ".join(messages) or "unknown GraphQL error"
        lower = joined.lower()
        if "unauthor" in lower or "forbidden" in lower or "not authenticated" in lower:
            raise RailwayError(f"Railway auth/GraphQL error: {joined}")
        raise RailwayError(f"Railway GraphQL error: {joined}")

    data = envelope.get("data")
    if not isinstance(data, dict):
        raise RailwayError("Railway response missing GraphQL data object.")
    return data


def list_workspaces() -> list[dict[str, Any]]:
    """Return workspaces visible to an account token via `me.workspaces`."""
    data = graphql(
        """
        query ListMyWorkspaces {
          me {
            workspaces {
              id
              name
            }
          }
        }
        """
    )
    me = data.get("me") or {}
    workspaces = me.get("workspaces") or []
    return [ws for ws in workspaces if isinstance(ws, dict) and ws.get("id")]


def list_projects_for_workspace(
    workspace_id: str,
    *,
    first: int = 100,
) -> list[dict[str, Any]]:
    """List projects in one workspace (required for modern Railway accounts)."""
    data = graphql(
        """
        query ListWorkspaceProjects($id: String!) {
          workspace(workspaceId: $id) {
            id
            name
            projects {
              edges {
                node {
                  id
                  name
                  description
                  createdAt
                  updatedAt
                }
              }
            }
          }
        }
        """,
        {"id": workspace_id},
    )
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        raise RailwayError(f"Workspace not found: {workspace_id}")
    edges = ((workspace.get("projects") or {}).get("edges")) or []
    projects: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("node"), dict):
            continue
        node = dict(edge["node"])
        node["workspace_id"] = workspace.get("id")
        node["workspace_name"] = workspace.get("name")
        projects.append(node)
    if first > 0:
        return projects[:first]
    return projects


def list_projects(
    *,
    first: int = 100,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    List projects across workspaces.

    Railway's top-level `projects` query returns empty for current accounts;
    projects must be loaded via `workspace(workspaceId: …).projects`.
    """
    if workspace_id:
        return list_projects_for_workspace(workspace_id, first=first)

    try:
        workspaces = list_workspaces()
    except RailwayError as exc:
        # Workspace tokens cannot query `me`; caller must pass workspace_id.
        raise RailwayError(
            "Could not list workspaces via `me` (common for workspace-scoped "
            "tokens). Pass --workspace-id / RAILWAY_WORKSPACE_ID, or use an "
            f"account token. Detail: {exc}"
        ) from exc

    if not workspaces:
        return []

    seen: set[str] = set()
    projects: list[dict[str, Any]] = []
    for workspace in workspaces:
        wid = str(workspace["id"])
        for project in list_projects_for_workspace(wid, first=max(first, 500)):
            pid = str(project.get("id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            projects.append(project)
            if len(projects) >= first:
                return projects
    return projects


def get_project(project_id: str) -> dict[str, Any]:
    data = graphql(
        """
        query GetProject($id: String!) {
          project(id: $id) {
            id
            name
            description
            services {
              edges {
                node {
                  id
                  name
                }
              }
            }
            environments {
              edges {
                node {
                  id
                  name
                }
              }
            }
          }
        }
        """,
        {"id": project_id},
    )
    project = data.get("project")
    if not isinstance(project, dict):
        raise RailwayError(f"Project not found: {project_id}")
    return project


def list_deployments(
    *,
    project_id: str,
    service_id: str,
    environment_id: str,
    first: int = 10,
) -> list[dict[str, Any]]:
    data = graphql(
        """
        query ListDeployments(
          $projectId: String!
          $serviceId: String!
          $environmentId: String!
          $first: Int!
        ) {
          deployments(
            first: $first
            input: {
              projectId: $projectId
              serviceId: $serviceId
              environmentId: $environmentId
            }
          ) {
            edges {
              node {
                id
                status
                createdAt
                staticUrl
                meta
              }
            }
          }
        }
        """,
        {
            "projectId": project_id,
            "serviceId": service_id,
            "environmentId": environment_id,
            "first": first,
        },
    )
    edges = ((data.get("deployments") or {}).get("edges")) or []
    return [edge["node"] for edge in edges if isinstance(edge, dict) and edge.get("node")]


def latest_successful_deployment_id(
    *,
    project_id: str,
    service_id: str,
    environment_id: str,
    scan: int = 20,
) -> str:
    deployments = list_deployments(
        project_id=project_id,
        service_id=service_id,
        environment_id=environment_id,
        first=scan,
    )
    for item in deployments:
        if str(item.get("status") or "").upper() == "SUCCESS":
            deployment_id = str(item.get("id") or "").strip()
            if deployment_id:
                return deployment_id
    if deployments:
        fallback = str(deployments[0].get("id") or "").strip()
        if fallback:
            return fallback
    raise RailwayError(
        "No deployments found for the given project/service/environment."
    )


def fetch_logs(
    *,
    deployment_id: str,
    kind: str = "deploy",
    limit: int | None = None,
    filter_expr: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    kind_key = (kind or "deploy").strip().lower()
    if kind_key in {"deploy", "deployment", "runtime"}:
        field = "deploymentLogs"
    elif kind_key == "build":
        field = "buildLogs"
    elif kind_key == "http":
        field = "httpLogs"
    else:
        raise RailwayError("kind must be deploy, build, or http.")

    # httpLogs returns richer objects and takes different time arguments:
    # its startDate/endDate are typed String (not DateTime) AND are deprecated
    # no-ops -- "This argument has no effect. Use beforeDate/anchorDate/
    # afterDate instead." Declaring them as DateTime fails GraphQL validation
    # (HTTP 400 GRAPHQL_VALIDATION_FAILED) even when passed as null, so map the
    # caller's bounds onto afterDate/beforeDate instead.
    if field == "httpLogs":
        selection = """
          timestamp
          method
          path
          httpStatus
          totalDuration
          requestId
          host
        """
        query = f"""
        query FetchHttpLogs(
          $deploymentId: String!
          $limit: Int
          $filter: String
          $afterDate: String
          $beforeDate: String
        ) {{
          httpLogs(
            deploymentId: $deploymentId
            limit: $limit
            filter: $filter
            afterDate: $afterDate
            beforeDate: $beforeDate
          ) {{
            {selection}
          }}
        }}
        """
        variables: dict[str, Any] = {
            "deploymentId": deployment_id,
            "limit": limit,
            "filter": filter_expr,
            "afterDate": start_date,
            "beforeDate": end_date,
        }
    else:
        selection = """
          timestamp
          message
          severity
          attributes { key value }
        """
        query = f"""
        query FetchLogs(
          $deploymentId: String!
          $limit: Int
          $filter: String
          $startDate: DateTime
          $endDate: DateTime
        ) {{
          {field}(
            deploymentId: $deploymentId
            limit: $limit
            filter: $filter
            startDate: $startDate
            endDate: $endDate
          ) {{
            {selection}
          }}
        }}
        """
        variables = {
            "deploymentId": deployment_id,
            "limit": limit,
            "filter": filter_expr,
            "startDate": start_date,
            "endDate": end_date,
        }

    data = graphql(query, variables)
    rows = data.get(field)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise RailwayError(f"Unexpected {field} payload shape.")
    return [row for row in rows if isinstance(row, dict)]
