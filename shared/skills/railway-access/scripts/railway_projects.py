#!/usr/bin/env python3
"""List Railway projects (optional nested services/environments)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from railway_client import (  # noqa: E402
    RailwayError,
    get_project,
    list_projects,
    list_workspaces,
    resolve_token,
    token_tail,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="List Railway projects via GraphQL.")
    parser.add_argument("--first", type=int, default=100, help="Max projects to return.")
    parser.add_argument(
        "--workspace-id",
        help="Limit to one workspace (required for workspace-scoped tokens).",
    )
    parser.add_argument(
        "--list-workspaces",
        action="store_true",
        help="List workspaces visible to an account token, then exit.",
    )
    parser.add_argument(
        "--project-id",
        help="If set, return one project with services and environments.",
    )
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="For each listed project, also fetch services and environments.",
    )
    args = parser.parse_args()

    try:
        token = resolve_token()
        if args.list_workspaces:
            workspaces = list_workspaces()
            payload = {
                "token_tail": token_tail(token),
                "count": len(workspaces),
                "workspaces": workspaces,
            }
        elif args.project_id:
            project = get_project(args.project_id)
            payload = {
                "token_tail": token_tail(token),
                "project": _shape_project(project),
            }
        else:
            projects = list_projects(
                first=max(1, min(args.first, 500)),
                workspace_id=(args.workspace_id or None),
            )
            if args.include_details:
                detailed = []
                for item in projects:
                    shaped = _shape_project(get_project(item["id"]))
                    shaped["workspace_id"] = item.get("workspace_id")
                    shaped["workspace_name"] = item.get("workspace_name")
                    detailed.append(shaped)
                projects_out = detailed
            else:
                projects_out = projects
            payload = {
                "token_tail": token_tail(token),
                "count": len(projects_out),
                "projects": projects_out,
            }
    except RailwayError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **payload}, indent=2))
    return 0


def _shape_project(project: dict) -> dict:
    services = []
    for edge in ((project.get("services") or {}).get("edges")) or []:
        node = edge.get("node") if isinstance(edge, dict) else None
        if isinstance(node, dict):
            services.append(node)
    environments = []
    for edge in ((project.get("environments") or {}).get("edges")) or []:
        node = edge.get("node") if isinstance(edge, dict) else None
        if isinstance(node, dict):
            environments.append(node)
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description"),
        "createdAt": project.get("createdAt"),
        "updatedAt": project.get("updatedAt"),
        "services": services,
        "environments": environments,
    }


if __name__ == "__main__":
    raise SystemExit(main())
