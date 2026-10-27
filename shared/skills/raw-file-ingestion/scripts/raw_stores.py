"""Which raw store a source goes to (CONTRACT §11.1, P13), and every raw store the brain can reach.

Kinds, in the order `raw_stores()` lists them (SMART-RULE-0027, a fixed domain order):

    owner            /memory/raw/ and /memory/sources/: a source that belongs to no single node
    memory-node      <node>/raw/ and <node>/sources/ of a node in memory, by node path
    pointer-private  <pointer node>/raw/ and sources/: a repository project's source marked private
    repository       <checkout>/brain/raw/ and brain/sources/ of a project repository, by name

What a node and a pointer are, a pointer's checkout, its store branch and its `repo_visibility`
come from the tasks skill's `task_stores`, the one implementation (SMART-RULE-0018), so a source
and a task about the same project land in the same place. `flags` is the tasks skill's own reader
of possibly-private text (`task_private.flags`: a /memory/ path, an amount, a contact detail, a
personal-data pattern, an owner term), which reads the repository preflight's patterns.

Two forms of a path. A record names the files of its own store: `/memory/...` in memory, and a
repository path (`brain/raw/...`) in a repository, because a /memory/ path cannot be resolved
there (P15). A file in memory that names a repository file writes `<repository>:brain/...`, where
`<repository>` is the remote's name, the same in every brain (task_stores).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

TASKS_SCRIPTS = Path(__file__).resolve().parents[2] / "tasks" / "scripts"
if str(TASKS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TASKS_SCRIPTS))

import task_stores  # noqa: E402
from task_private import MEMORY_PATH, flags  # noqa: E402,F401  (flags is this module's interface too)
from task_records import parse_front_matter  # noqa: E402

KIND_ORDER = {"owner": 0, "memory-node": 1, "pointer-private": 2, "repository": 3}


@dataclass(frozen=True)
class RawStore:
    kind: str
    raw: Path
    sources: Path
    repository: Optional[str] = None
    public: Optional[bool] = None       # repository only: repo_visibility (None: not recorded)
    node: Optional[str] = None          # the owning node; the pointer node for a repository
    checkout: Optional[Path] = None     # repository only
    tasks: Any = None                   # the task_stores.Store of the same place: branch, reachability

    @property
    def reachable(self) -> bool:
        return self.tasks.reachable if self.tasks is not None else True

    @property
    def reason(self) -> Optional[str]:
        return self.tasks.reason if self.tasks is not None else None

    @property
    def label(self) -> str:
        if self.kind == "repository":
            return f"{self.repository}:brain/raw"
        if self.kind == "owner":
            return "/memory/raw"
        return f"{self.node}/raw"

    def ref(self, root: Path, path: Path) -> str:
        """The path as this store's own records write it."""
        if self.kind == "repository":
            return path.resolve().relative_to(self.checkout.resolve()).as_posix()
        return "/" + path.resolve().relative_to(root.resolve()).as_posix()

    def memory_ref(self, root: Path, path: Path) -> str:
        """The path as a file in memory writes it."""
        if self.kind == "repository":
            return f"{self.repository}:{self.ref(root, path)}"
        return self.ref(root, path)

    def same_place(self, other: "RawStore") -> bool:
        return self.kind == other.kind and self.raw.resolve() == other.raw.resolve()

    def writable(self):
        """The task store task_git.ready_to_write checks before a write here, widened to brain/."""
        if self.kind != "repository" or self.tasks is None or self.checkout is None:
            return self.tasks
        return replace(self.tasks, path=self.checkout / "brain")


def from_task_store(root: Path, store) -> RawStore:
    if store.kind == "owner":
        memory = root / "memory"
        return RawStore("owner", memory / "raw", memory / "sources", tasks=store)
    if store.kind == "repository":
        base = (store.checkout if store.checkout is not None else Path(store.repository)) / "brain"
        return RawStore("repository", base / "raw", base / "sources", repository=store.repository,
                        public=store.public, node=store.node, checkout=store.checkout, tasks=store)
    folder = root / store.node.strip("/")
    return RawStore(store.kind, folder / "raw", folder / "sources", repository=store.repository,
                    node=store.node, tasks=store)


def is_pointer(root: Path, node: Optional[str]) -> bool:
    return bool(node) and any(p.node == node for p in task_stores.pointers(root))


def choose(root: Path, node: Optional[str], private: bool) -> RawStore:
    """The raw store a new source belongs in (P13).

    `node` is a folder in memory as `/memory/...`, or None. No node, or a folder in no node: the
    owner store. A memory node: its own. A pointer node: its repository's `brain/`, or with
    `private` the pointer node's own. ValueError for `private` without a pointer node, and for
    two pointers naming one repository."""
    owning = task_stores.node_of(root, node) if node else None
    if private and not is_pointer(root, owning):
        raise ValueError("--private needs --node naming a pointer node (a node whose README has repo_url); "
                         "a source anywhere else in memory is private already")
    return from_task_store(root, task_stores.store_for(root, owning, private=private))


def raw_stores(root: Path) -> list[RawStore]:
    """Every raw store: owner; memory nodes and pointer nodes with a raw/ folder, by path; every
    repository a pointer names, by name (an unreachable one is listed, never read)."""
    memory = root / "memory"
    found = [from_task_store(root, task_stores.owner_store(root))]
    pointer_nodes = {p.node: p for p in task_stores.pointers(root)}
    nodes: list[RawStore] = []
    if memory.is_dir():
        for folder, dirs, _files in os.walk(memory):
            dirs[:] = sorted(d for d in dirs if d not in task_stores.SKIP_WALK and not d.startswith("."))
            here = Path(folder)
            if not (here / "raw").is_dir() or not task_stores.is_node(root, here):
                continue
            node = "/" + here.relative_to(root).as_posix()
            pointer = pointer_nodes.get(node)
            kind = "pointer-private" if pointer else "memory-node"
            nodes.append(RawStore(kind, here / "raw", here / "sources", node=node,
                                  repository=pointer.repository if pointer else None))
    found += sorted(nodes, key=lambda s: (KIND_ORDER[s.kind], s.node or ""))
    found += [from_task_store(root, s) for s in task_stores.stores(root) if s.kind == "repository"]
    return found


def find_duplicate(root: Path, sha256: str) -> Optional[tuple[RawStore, Path]]:
    """The first raw file with this hash in any reachable raw store, by its manifest."""
    for store in raw_stores(root):
        if not store.reachable or not store.raw.is_dir():
            continue
        for manifest in sorted(store.raw.rglob("manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if data.get("sha256") == sha256:
                candidate = manifest.parent / str(data.get("filename", ""))
                if candidate.is_file():
                    return store, candidate
    return None


def find_record(store: RawStore, source_id: str) -> Optional[Path]:
    """The canonical record of a source in a store's sources/: never a reference to one elsewhere,
    and never a derivative reconvert.py wrote beside it."""
    if not store.sources.is_dir():
        return None
    for candidate in sorted(store.sources.glob(f"{source_id}*.md")):
        if candidate.stem != source_id and not candidate.stem.startswith(source_id + "-"):
            continue
        try:
            meta = parse_front_matter(candidate.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError):
            continue
        if meta.get("type") != "source_reference":
            return candidate
    return None


def personal_terms(root: Path) -> list[str]:
    """The owner's terms, read once for many `flags` calls."""
    try:
        import task_private
        return task_private._personal_data().owner_terms(root)
    except ImportError:
        return []


def flagged_lines(text: str, root: Path, terms: Optional[list[str]] = None) -> list[dict]:
    """Every non-blank line of a text that `flags` marks: {line, text, flags}."""
    terms = personal_terms(root) if terms is None else terms
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip():
            found = flags(line, root, terms)
            if found:
                out.append({"line": number, "text": line.strip(), "flags": found})
    return out


NOT_READ = ("pending_conversion", "failed")
MACHINE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/|~[\\/])")


def source_flags(root: Path, source_name: str, title: Optional[str], markdown: str, status: str,
                 derivative: Optional[str] = None, terms: Optional[list[str]] = None) -> list[dict]:
    """What may be private in a source bound for a repository, in reading order:
    {where, line (a content line's number, else None), text, flags}.

    The one check for a new source (ingest_raw.py) and a moved one (source_migrate.py): the file
    name, the title, every line of the converted text and of a reconverted derivative, and a file
    whose content could not be read, since nothing in it was checked."""
    terms = personal_terms(root) if terms is None else terms
    found = []
    for where, text in (("file name", source_name), ("title", title or "")):
        hit = flags(text, root, terms) if text else []
        if hit:
            found.append({"where": where, "line": None, "text": text, "flags": hit})
    for item in flagged_lines(markdown, root, terms):
        found.append({"where": f"content line {item['line']}", **item})
    for item in flagged_lines(derivative or "", root, terms):
        found.append({"where": f"derivative line {item['line']}", "line": None, "text": item["text"],
                      "flags": item["flags"]})
    if status in NOT_READ:
        found.append({"where": "content", "line": None, "text": "",
                      "flags": [f"not read ({status}): nothing in it was checked"]})
    return found


def repository_manifest(manifest: dict) -> dict:
    """A raw folder's manifest as it may stand in a repository: no machine path in it
    (`original_path` and any other value that is an absolute path)."""
    return {k: v for k, v in manifest.items()
            if k != "original_path" and not (isinstance(v, str) and MACHINE_PATH.match(v))}


def visibility(store: RawStore) -> str:
    """What to say before a write into a repository: its name and who can read it."""
    if store.public is True:
        return f"{store.repository} is public: anyone can read what is written there"
    if store.public is False:
        return f"{store.repository} is private: everyone who can read it, collaborators included, can read this"
    return (f"the visibility of {store.repository} is not recorded (repo_visibility in its pointer README): "
            "treat it as public")
