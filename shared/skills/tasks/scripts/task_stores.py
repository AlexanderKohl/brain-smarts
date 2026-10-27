"""Every task store the brain can reach, and which one a task belongs in (CONTRACT §9, P10).

Kinds of store, in the fixed order `stores()` lists them (SMART-RULE-0027, a domain order):

    owner            /memory/tasks/: the tasks with no project reference
    memory-node      <node>/tasks/ of a node in memory, by node path
    pointer-private  <pointer node>/tasks/: the owner's private tasks about a repository project
    repository       <checkout>/brain/tasks/ of a project repository, by repository name

A **node** is a folder under /memory/ whose README.md has `type: node_readme`, other than
/memory/ and /memory/projects/ themselves, a folder below one named tasks, skills, data,
sources, raw or status, and a README whose `node_type` is collection, skill_library or
project_library. A **pointer** is a node whose README carries `repo_url` (whatever its
`node_type` says).

Two names for a repository: a record in a repository names it `<repository>:brain`, where
`<repository>` is the remote's name (the last segment of `repo_url` without .git), because that
name is the same in every brain. The clone's folder name may differ between brains, so it is
used only in per-brain configuration such as boards.json (SMART-RULE-0033).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from task_records import Task, load_tasks, parse_front_matter

StoreKind = Literal["owner", "memory-node", "pointer-private", "repository"]
KIND_ORDER = {"owner": 0, "memory-node": 1, "pointer-private": 2, "repository": 3}
NOT_NODE_FOLDERS = frozenset({"tasks", "skills", "data", "sources", "raw", "status"})
NOT_NODE_TYPES = frozenset({"collection", "skill_library", "project_library"})
SKIP_WALK = frozenset({".git", "raw", "node_modules", "img"})
JOIN_SCRIPTS = Path(__file__).resolve().parents[2] / "join-project" / "scripts"


@dataclass(frozen=True)
class Pointer:
    node: str                 # "/memory/projects/..." of the pointer node
    readme: Path
    repository: str           # the remote's name: last segment of repo_url without .git
    checkout: Path | None     # local_path: absolute as is; relative under project_repos_root;
                              # missing: project_repos_root / repository; None when no folder exists
    branch: str               # the store branch: brain/JOINING.md working_branch, else default_branch
    public: bool | None = None   # repo_visibility: public True, private False, unknown None
    problem: str | None = None   # an unreadable brain/JOINING.md: the store is then unreachable


@dataclass(frozen=True)
class Store:
    kind: StoreKind
    path: Path                # the tasks/ folder (it may not exist yet)
    node: str | None          # owning node; the pointer node for repository and pointer-private; None for owner
    repository: str | None = None    # repository and pointer-private only
    checkout: Path | None = None     # repository only
    branch: str | None = None        # repository only
    reachable: bool = True           # False: repository not checked out; listed, never read or written
    reason: str | None = None        # why it is not reachable
    public: bool | None = None       # repository only: repo_visibility

    @property
    def label(self) -> str:
        if self.kind == "repository":
            return f"{self.repository}:brain/tasks"
        if self.kind == "owner":
            return "/memory/tasks"
        return f"{self.node}/tasks"


def _meta(readme: Path) -> dict:
    """The front matter of a README; an unreadable one reads as empty (it then names no node)."""
    try:
        return parse_front_matter(readme.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError):
        return {}


def repository_name(url: str) -> str:
    tail = re.split(r"[/\\:]", str(url).strip().rstrip("/\\"))[-1]
    return tail[:-4] if tail.lower().endswith(".git") else tail


def _profile(root: Path) -> dict:
    path = root / "memory" / "OWNER.md"
    return _meta(path) if path.is_file() else {}


def _working_branch(checkout: Path) -> str | None:
    """`working_branch` from brain/JOINING.md, read by join-project's own manifest reader."""
    if not (checkout / "brain" / "JOINING.md").is_file():
        return None
    if str(JOIN_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(JOIN_SCRIPTS))
    import joining  # lazy: joining.py imports this module for its pointer list
    manifest = joining.load_manifest(checkout) or {}
    if "error" in manifest:
        raise ValueError(f"{(checkout / 'brain' / 'JOINING.md').as_posix()}: {manifest['error']}")
    value = manifest.get("working_branch")
    return str(value).strip() if value else None


def _checkout(meta: dict, repository: str, base: str) -> Path | None:
    local = str(meta.get("local_path") or "").strip()
    if local and Path(local).is_absolute():
        candidate = Path(local)
    elif base:
        candidate = Path(base) / (local or repository)
    else:
        return None
    return candidate if candidate.is_dir() else None


def _rel(root: Path, path: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


def _walk_readmes(memory: Path):
    """Every README.md under a folder, skipping Git, raw stores and image folders."""
    for folder, dirs, files in os.walk(memory):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_WALK and not d.startswith("."))
        if "README.md" in files:
            yield Path(folder) / "README.md"


def pointers(root: Path) -> list[Pointer]:
    """Every README under /memory/projects/, at any depth, that carries repo_url; by node path."""
    projects = root / "memory" / "projects"
    if not projects.is_dir():
        return []
    base = str(_profile(root).get("project_repos_root") or "").strip()
    found: list[Pointer] = []
    for readme in _walk_readmes(projects):
        if readme.parent == projects or not _is_node_folder(root, readme.parent):
            continue
        try:
            meta = _meta(readme)
        except (OSError, UnicodeDecodeError):
            continue
        if not meta.get("repo_url"):
            continue
        repository = repository_name(str(meta["repo_url"]))
        checkout = _checkout(meta, repository, base)
        branch, problem = None, None
        if checkout is not None:
            try:
                branch = _working_branch(checkout)
            except (OSError, UnicodeDecodeError, ValueError) as err:
                problem = f"brain/JOINING.md cannot be read: {err}"
        visibility = str(meta.get("repo_visibility") or "").strip().lower()
        found.append(Pointer(node=_rel(root, readme.parent), readme=readme, repository=repository,
                             checkout=checkout, branch=branch or str(meta.get("default_branch") or ""),
                             public={"public": True, "private": False}.get(visibility), problem=problem))
    return sorted(found, key=lambda p: p.node)


def _is_node_folder(root: Path, folder: Path) -> bool:
    memory = root / "memory"
    try:
        parts = folder.relative_to(memory).parts
    except ValueError:
        return False
    if not parts or parts == ("projects",) or any(p in NOT_NODE_FOLDERS for p in parts):
        return False
    return True


def is_node(root: Path, folder: Path) -> bool:
    """A folder is a node by the rule in the module docstring."""
    readme = folder / "README.md"
    if not _is_node_folder(root, folder) or not readme.is_file():
        return False
    meta = _meta(readme)
    return meta.get("type") == "node_readme" and meta.get("node_type") not in NOT_NODE_TYPES


def node_of(root: Path, ref: str) -> str | None:
    """The deepest node a reference is in, as "/memory/..."; None outside /memory/ or above any node."""
    ref = str(ref or "").strip()
    if not ref.startswith("/memory/"):
        return None
    path = root / ref.strip("/")
    folder = path if path.is_dir() else path.parent
    memory = root / "memory"
    while folder != memory and memory in folder.parents:
        if is_node(root, folder):
            return _rel(root, folder)
        folder = folder.parent
    return None


def _pointer_by_node(root: Path) -> dict[str, Pointer]:
    return {p.node: p for p in pointers(root)}


def _repository_store(pointer: Pointer) -> Store:
    checkout, reason = pointer.checkout, pointer.problem
    reachable = checkout is not None and (checkout / "brain").is_dir() and reason is None
    if reason is None and not reachable:
        reason = ("not checked out here" if checkout is None else f"{checkout.as_posix()} has no brain/ folder")
    path = (checkout / "brain" / "tasks") if checkout is not None else Path(pointer.repository) / "brain" / "tasks"
    return Store(kind="repository", path=path, node=pointer.node, repository=pointer.repository,
                 checkout=checkout, branch=pointer.branch, reachable=reachable, reason=reason,
                 public=pointer.public)


def owner_store(root: Path) -> Store:
    return Store(kind="owner", path=root / "memory" / "tasks", node=None)


def stores(root: Path) -> list[Store]:
    """Owner; memory nodes by path; pointer-private by path; repositories by name.

    Memory-node and pointer-private stores are listed when their tasks/ folder exists; a
    repository store is listed for every distinct repository a pointer names, reachable when
    its checkout has brain/."""
    found = [owner_store(root)]
    by_node = _pointer_by_node(root)
    memory = root / "memory"
    nodes, private = [], []
    if memory.is_dir():
        for readme in _walk_readmes(memory):
            folder = readme.parent
            if not (folder / "tasks").is_dir() or not is_node(root, folder):
                continue
            node = _rel(root, folder)
            if node in by_node:
                p = by_node[node]
                private.append(Store(kind="pointer-private", path=folder / "tasks", node=node,
                                     repository=p.repository))
            else:
                nodes.append(Store(kind="memory-node", path=folder / "tasks", node=node))
    repos: dict[str, Store] = {}
    for pointer in by_node.values():       # a repository's name is matched without case
        if pointer.repository.lower() not in repos:
            repos[pointer.repository.lower()] = _repository_store(pointer)
    found += sorted(nodes, key=lambda s: s.node or "") + sorted(private, key=lambda s: s.node or "")
    found += [repos[name] for name in sorted(repos)]
    return found


def store_by_label(root: Path, label: str) -> Store:
    for store in stores(root):
        if store.label == label or store.label == label.rstrip("/") + "/tasks":
            return store
    raise LookupError(f"no task store {label}; `tasks.py check` lists them")


def store_for(root: Path, ref: str | None, private: bool = False) -> Store:
    """The store a new task with this first project reference belongs in.

    No reference gives the owner store. A reference that names no node is refused: /memory/tasks/
    holds only tasks with no project reference (P10), so it cannot take one that has a reference."""
    if not ref:
        if private:
            raise ValueError("--private needs a --project that names a pointer node")
        return owner_store(root)
    node = node_of(root, ref)
    if node is None:
        raise ValueError(f"{ref} is in no node (a folder under /memory/ with a node README); name the node, "
                         "or give no project for a task that belongs to none")
    by_node = _pointer_by_node(root)
    if node not in by_node:
        if private:
            raise ValueError(f"--private: {node} is not a pointer node; a task in memory is already private")
        return Store(kind="memory-node", path=root / node.strip("/") / "tasks", node=node)
    pointer = by_node[node]
    others = sorted(p.node for p in by_node.values()
                    if p.repository.lower() == pointer.repository.lower() and p.node != node)
    if others:
        raise ValueError(f"{node} and {', '.join(others)} both point at the repository {pointer.repository}; "
                         "one of them must stop being a pointer first")
    if private:
        return Store(kind="pointer-private", path=root / node.strip("/") / "tasks", node=node,
                     repository=pointer.repository)
    return _repository_store(pointer)


def load_all(root: Path, include_unreachable: bool = False) -> list[Task]:
    """Every record of every reachable store, each carrying its store."""
    tasks: list[Task] = []
    for store in stores(root):
        if store.reachable and store.path.is_dir():
            tasks += load_tasks(store.path, owner=store)
    return tasks


def unreachable(root: Path) -> list[Store]:
    return [s for s in stores(root) if not s.reachable]


def find(root: Path, tid: str) -> Task:
    """The one record of a task across every reachable store.

    LookupError when there is none (naming the stores it could not read); ValueError when the
    identifier is in two places, naming both, so the extra copy is removed by hand."""
    found = [t for t in load_all(root) if t.tid == tid]
    if not found:
        missing = unreachable(root)
        tail = ("; not read: " + ", ".join(f"{s.label} ({s.reason})" for s in missing)) if missing else ""
        raise LookupError(f"no task {tid} in any reachable store{tail}")
    if len(found) > 1:
        raise ValueError(f"{tid} is in more than one place: " + ", ".join(t.path.as_posix() for t in found)
                         + "; remove the extra copy by hand")
    return found[0]


def node_title(root: Path, node: str) -> str:
    readme = root / node.strip("/") / "README.md"
    title = _meta(readme).get("title") if readme.is_file() else None
    return str(title or node.rstrip("/").rsplit("/", 1)[-1])
