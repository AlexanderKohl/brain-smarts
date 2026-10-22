#!/usr/bin/env python3
"""The joining manifest of a shared project, and whether this brain has joined it.

A shared project repository carries `brain/JOINING.md` (CONTRACT section 16.2): front matter a
script can read, under one `joining:` key, and a short human part. This module is the one
implementation that reads the manifest and decides what "joined" means (SMART-RULE-0018); it is
imported by `join.py` (this skill) and by `repository-preflight/scripts/sync.py` for its nudge.

Joined means: a pointer node for the repository exists in this brain's memory (a `README.md`
under `/memory/projects/` whose `repo_url` names the repository or whose `local_path` names the
clone), and every board the manifest lists is registered in `/memory/skills/owner-board/config/
boards.json` with the status `<clone folder>:<board status>`.

Nothing here reads a secret, a vault or a `.env` file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST = Path("brain") / "JOINING.md"
BOARDS_CONFIG = Path("memory") / "skills" / "owner-board" / "config" / "boards.json"
JOIN_COMMAND = "python shared/skills/join-project/scripts/join.py"


# -- a small YAML subset: scalars, lists of scalars, lists of one-level mappings, nested mappings --

def _scalar(text: str):
    text = text.strip()
    if text in ("", "null", "~"):
        return None
    if text in ("true", "false"):
        return text == "true"
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    return text


def _parse_block(lines: list[str], start: int, indent: int):
    """Parse the block whose lines are indented by `indent`; return (value, next index)."""
    if start >= len(lines):
        return None, start
    first = lines[start]
    if first.lstrip().startswith("- "):
        items = []
        i = start
        while i < len(lines):
            line = lines[i]
            if not line.strip() or line.lstrip().startswith("#"):
                i += 1
                continue
            own = len(line) - len(line.lstrip())
            if own != indent or not line.lstrip().startswith("- "):
                break
            body = line.lstrip()[2:]
            if re.match(r"^[A-Za-z_][\w-]*:(\s|$)", body):
                # a mapping item: its first key is on the dash line, the rest indented by two more
                sub = [" " * (indent + 2) + body] + []
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.strip() and not nxt.lstrip().startswith("#"):
                        nxt_indent = len(nxt) - len(nxt.lstrip())
                        if nxt_indent <= indent:
                            break
                    sub.append(nxt)
                    j += 1
                value, _ = _parse_block(sub, 0, indent + 2)
                items.append(value)
                i = j
            else:
                items.append(_scalar(body))
                i += 1
        return items, i
    mapping: dict = {}
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        own = len(line) - len(line.lstrip())
        if own < indent:
            break
        if own > indent:
            i += 1
            continue
        key, _, rest = line.strip().partition(":")
        if rest.strip():
            mapping[key.strip()] = _scalar(rest)
            i += 1
            continue
        # a nested block: find its indent from the next content line
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
            j += 1
        if j < len(lines) and (len(lines[j]) - len(lines[j].lstrip())) > indent:
            value, j = _parse_block(lines, j, len(lines[j]) - len(lines[j].lstrip()))
            mapping[key.strip()] = value
            i = j
        else:
            mapping[key.strip()] = None
            i = j
    return mapping, i


def front_matter(text: str) -> dict:
    """The YAML front matter of a Markdown file as a dict (the subset this skill writes)."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        return {}
    lines = match.group(1).splitlines()
    value, _ = _parse_block(lines, 0, 0)
    return value if isinstance(value, dict) else {}


# -- the manifest --

def load_manifest(repo: Path) -> dict | None:
    """The `joining:` mapping of `<repo>/brain/JOINING.md`, with the file's title; None when absent."""
    path = repo / MANIFEST
    if not path.is_file():
        return None
    meta = front_matter(path.read_text(encoding="utf-8"))
    joining = meta.get("joining")
    if not isinstance(joining, dict):
        return {"title": meta.get("title"), "error": "no `joining:` mapping in the front matter"}
    joining = dict(joining)
    joining.setdefault("title", meta.get("title"))
    joining.setdefault("boards", [])
    joining.setdefault("vault_entries", [])
    joining.setdefault("skills", [])
    joining.setdefault("library_skills", [])
    joining.setdefault("read_first", [])
    return joining


def normalise_url(url: str | None) -> str:
    url = (url or "").strip().lower().rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def repository_name(url_or_path: str) -> str:
    """The clone folder name a URL or path implies: the last path segment without `.git`."""
    tail = re.split(r"[/\\:]", str(url_or_path).rstrip("/\\"))[-1]
    return tail[:-4] if tail.endswith(".git") else tail


# -- this brain's memory --

def owner_profile(memory: Path) -> dict:
    """The scalar fields and `active_skills` of `/memory/OWNER.md`."""
    path = memory / "OWNER.md"
    if not path.is_file():
        return {}
    meta = front_matter(path.read_text(encoding="utf-8"))
    return meta if isinstance(meta, dict) else {}


def pointer_nodes(memory: Path) -> list[tuple[Path, dict]]:
    """Every README under `/memory/projects/` (up to three levels) that carries `repo_url`."""
    projects = memory / "projects"
    if not projects.is_dir():
        return []
    found = []
    for pattern in ("*/README.md", "*/*/README.md", "*/*/*/README.md"):
        for path in sorted(projects.glob(pattern)):
            meta = front_matter(path.read_text(encoding="utf-8", errors="replace"))
            if meta.get("repo_url"):
                found.append((path, meta))
    return found


def find_pointer(memory: Path, repo_url: str | None, folder_name: str) -> Path | None:
    """The pointer node for a repository: by `repo_url`, else by the clone folder in `local_path`."""
    wanted = normalise_url(repo_url)
    for path, meta in pointer_nodes(memory):
        if wanted and normalise_url(str(meta.get("repo_url"))) == wanted:
            return path.parent
    for path, meta in pointer_nodes(memory):
        if repository_name(str(meta.get("local_path") or "")).lower() == folder_name.lower():
            return path.parent
    return None


def registered_boards(root: Path) -> dict[str, str]:
    """Board id to its `status` from this brain's boards.json; empty when none is configured."""
    path = root / BOARDS_CONFIG
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return {str(b.get("id")): str(b.get("status", "")) for b in data.get("boards", []) if isinstance(b, dict)}


def expected_status(folder_name: str, board: dict) -> str:
    return f"{folder_name}:{str(board.get('status') or 'brain/status').strip('/')}"


def joined_state(root: Path, repo: Path) -> dict:
    """Where this brain stands with one cloned repository that carries a manifest."""
    manifest = load_manifest(repo)
    state = {"repo": repo, "name": repo.name, "manifest": manifest, "pointer": None, "missing_boards": []}
    if not manifest or "error" in manifest:
        return state
    state["pointer"] = find_pointer(root / "memory", manifest.get("repository"), repo.name)
    boards = registered_boards(root)
    for board in manifest.get("boards") or []:
        if not isinstance(board, dict) or not board.get("id"):
            continue
        if boards.get(str(board["id"])) != expected_status(repo.name, board):
            state["missing_boards"].append(str(board["id"]))
    return state


def not_joined(root: Path) -> list[dict]:
    """Cloned repositories under `project_repos_root` with a manifest this brain has not acted on.

    Each entry: {name, path, detail, command}. Repositories without a manifest are not listed;
    nothing is read outside `brain/JOINING.md`, this brain's memory and boards.json.
    """
    profile = owner_profile(root / "memory")
    base = str(profile.get("project_repos_root") or "").strip()
    if not base or not Path(base).is_dir():
        return []
    found = []
    for repo in sorted(Path(base).iterdir()):
        if not (repo / ".git").exists() or not (repo / MANIFEST).is_file():
            continue
        state = joined_state(root, repo)
        manifest = state["manifest"] or {}
        missing = []
        if "error" in manifest:
            missing.append("its brain/JOINING.md has " + manifest["error"])
        else:
            if state["pointer"] is None:
                missing.append("no pointer node in memory")
            if state["missing_boards"]:
                missing.append("shared board(s) not registered: " + ", ".join(state["missing_boards"]))
        if missing:
            found.append({"name": repo.name, "path": str(repo), "detail": "; ".join(missing),
                          "command": f"{JOIN_COMMAND} {repo}"})
    return found
