#!/usr/bin/env python3
"""Portable AI Brain repository preflight validator.

Validates the mechanics repository (the brain root, where CONTRACT.md lives) and, when it is
present, the owner's memory repository checked out at `<root>/memory/` (CONTRACT §3.5).
Repository-root paths beginning `/memory/` resolve into the memory checkout. A missing memory
checkout is a warning, not an error: the mechanics can be validated on their own.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REQUIRED_MARKDOWN_FIELDS = {
    "id",
    "title",
    "type",
    "schema_version",
    "contract",
    "created",
    "updated",
}
TASK_STATUSES = {
    "inbox",
    "ready",
    "in_progress",
    "waiting",
    "scheduled",
    "blocked",
    "completed",
    "cancelled",
}
ACCEPTED_PROPOSAL_STATUSES = {"accepted", "implemented", "verified", "reverted"}
TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)
# CONTRACT §8.2: a timestamp is never later than the moment it was written. Five minutes allow
# for clocks on different machines disagreeing slightly when repositories are synced.
FUTURE_TOLERANCE = timedelta(minutes=5)
LOG_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))", re.M)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")
FOLDER_HEADING_RE = re.compile(r"^#####\s+`([^`]+?)/`\s*$", re.MULTILINE)
IGNORED_DIRS = {".git", ".claude", "node_modules", "__pycache__", ".pytest_cache"}

MEMORY_DIR = "memory"
MEMORY_PREFIX = "/" + MEMORY_DIR + "/"
LIBRARY_DIR = "library"
LIBRARY_PREFIX = "/" + LIBRARY_DIR + "/"
# The owner value mechanics files may carry (CONTRACT §3.6).
GENERIC_OWNER = "brain-owner"
MANIFEST_NAME = "repository-manifest.json"
VALIDATOR_PATH = "/shared/skills/repository-preflight/scripts/preflight.py"
# Where accepted proposals may live, relative to the brain root (CONTRACT §13.2).
PROPOSAL_ROOTS = (
    ("governance", "proposals"),
    (MEMORY_DIR, "governance", "proposals"),
)
# Task stores: /memory/tasks/ in the three-layer layout, /tasks/ in a single-repository brain.
TASK_ROOTS = ((MEMORY_DIR, "tasks"), ("tasks",))
# The memory skeleton every new owner starts from. A mechanics file may declare a metadata
# reference into /memory/ only when this skeleton provides the target, so the mechanics work for
# any owner.
SKELETON_PARTS = ("shared", "templates", "memory-skeleton")
# Scratch folder at the brain root, git-ignored; skipped even when Git cannot be asked.
SCRATCH_DIR = "temp"
# Front-matter keys holding repository-root paths that must resolve.
REFERENCE_KEYS = {
    "project_refs",
    "knowledge_refs",
    "skill_refs",
    "source_refs",
    "raw_source",
    "canonical_source_md",
    "script_paths",
    "target_files",
}


def is_raw_evidence_path(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if not parts:
        return False
    if parts[0] == "raw":
        return True
    return len(parts) > 1 and parts[0] == MEMORY_DIR and parts[1] == "raw"


def in_memory(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return bool(parts) and parts[0] == MEMORY_DIR


def memory_root(root: Path) -> Path | None:
    candidate = root / MEMORY_DIR
    return candidate if candidate.is_dir() else None


def in_library(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return bool(parts) and parts[0] == LIBRARY_DIR


def library_root(root: Path) -> Path | None:
    candidate = root / LIBRARY_DIR
    return candidate if candidate.is_dir() else None


def layer_of(path: Path, root: Path) -> str:
    """The repository that holds `path`: memory, the skill library or the mechanics."""
    if in_memory(path, root):
        return "memory"
    if in_library(path, root):
        return "library"
    return "mechanics"


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    markdown_files: int = 0
    unique_ids: int = 0
    contract_version: str | None = None
    memory_present: bool = False
    # Per-layer counts, used for the two manifests.
    layer_markdown_files: dict[str, int] = field(default_factory=dict)
    layer_unique_ids: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors


def message_layer(message: str) -> str:
    """The repository a message belongs to. Anything that names a memory path is memory's,
    so owner paths never reach a shareable manifest; then the library's own paths."""
    if MEMORY_PREFIX in message:
        return "memory"
    return "library" if message.startswith(LIBRARY_PREFIX) else "mechanics"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"null", "~"}:
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        return value[1:-1]
    return value


def read_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening YAML delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML delimiter") from exc

    metadata: dict[str, Any] = {}
    active_list: str | None = None
    nested_metadata = False
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line == "metadata:":
            nested_metadata = True
            active_list = None
            continue
        if nested_metadata and line.startswith("  "):
            nested_line = line[2:]
            if nested_line.startswith("  - ") and active_list:
                if not isinstance(metadata[active_list], list):
                    metadata[active_list] = []
                metadata[active_list].append(parse_scalar(nested_line[4:]))
                continue
            nested_match = KEY_RE.match(nested_line)
            if not nested_match:
                active_list = None
                continue
            key, raw_value = nested_match.groups()
            raw_value = raw_value or ""
            metadata[key] = parse_scalar(raw_value)
            active_list = key if raw_value == "" else None
            continue
        nested_metadata = False
        # A list item may be indented ("  - x") or not ("- x"); both are the same YAML.
        if line.startswith("  - "):
            list_item: str | None = line[4:]
        elif line.startswith("- "):
            list_item = line[2:]
        else:
            list_item = None
        if list_item is not None and active_list:
            if not isinstance(metadata[active_list], list):
                metadata[active_list] = []
            metadata[active_list].append(parse_scalar(list_item))
            continue
        match = KEY_RE.match(line)
        if not match:
            active_list = None
            continue
        key, raw_value = match.groups()
        raw_value = raw_value or ""
        metadata[key] = parse_scalar(raw_value)
        active_list = key if raw_value == "" else None
    return metadata, text


def root_path(path: Path, root: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


def discover_root(start: Path) -> Path:
    candidate = start.resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / "CONTRACT.md").is_file():
            return directory
    for directory in (candidate, *candidate.parents):
        if (directory / "OWNER.md").is_file():
            raise FileNotFoundError(
                f"CONTRACT.md was not found, but {directory} looks like a memory checkout; "
                "clone it as the memory/ folder of a mechanics checkout and validate from there"
            )
    raise FileNotFoundError("CONTRACT.md was not found at or above the supplied path")


def git_ignored(repo: Path, relatives: list[str]) -> set[str] | None:
    """The subset of `relatives` (POSIX paths relative to `repo`) that Git ignores in `repo`,
    or None when Git cannot answer (not installed, or `repo` is not a repository)."""
    if not relatives:
        return set()
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo),
             "check-ignore", "-z", "--stdin"],
            input="\0".join(relatives) + "\0",
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    # 0: some paths ignored; 1: none ignored; anything else: Git could not answer.
    if completed.returncode not in (0, 1):
        return None
    return {value for value in completed.stdout.split("\0") if value}


def ignored_paths(root: Path, paths: list[Path]) -> set[Path]:
    """The paths Git ignores, each asked of the repository that holds it. Memory and library paths
    are asked of their own repositories, because the mechanics repository ignores both folders."""
    nested = {}
    for layer, folder in (("memory", memory_root(root)), ("library", library_root(root))):
        nested[layer] = folder if folder is not None and is_own_repository(folder) else None
    groups: dict[Path, list[Path]] = {}
    for path in paths:
        layer = layer_of(path, root)
        if layer == "mechanics":
            groups.setdefault(root, []).append(path)
        elif nested[layer] is not None:
            groups.setdefault(nested[layer], []).append(path)
    ignored: set[Path] = set()
    for repo, members in groups.items():
        relatives = {path.relative_to(repo).as_posix(): path for path in members}
        answer = git_ignored(repo, list(relatives))
        if answer is None:
            continue
        ignored.update(relatives[value] for value in answer if value in relatives)
    return ignored


def markdown_paths(root: Path) -> list[Path]:
    """Markdown files to validate: not raw evidence, not tool state, not the scratch folder and
    not anything else Git ignores in the repository that holds it."""
    candidates = [
        path
        for path in root.rglob("*.md")
        if not any(part in IGNORED_DIRS for part in path.relative_to(root).parts)
        and path.relative_to(root).parts[0] != SCRATCH_DIR
        and not is_raw_evidence_path(path, root)
    ]
    ignored = ignored_paths(root, candidates)
    return sorted(path for path in candidates if path not in ignored)


def is_template_path(path: Path, root: Path) -> bool:
    """A file under a `templates/` folder, or a `_TEMPLATE.md` copied again for every new record
    (a CRM node's contact and persona templates): its placeholders stay unfilled."""
    return "templates" in path.relative_to(root).parts or path.name == "_TEMPLATE.md"


def clock() -> datetime:
    """Now, as the validator runs; a test replaces it."""
    return datetime.now().astimezone()


def ahead_of_clock(value: str, now: datetime) -> str | None:
    """How far a timestamp is ahead of `now`, in words, when that is beyond the tolerance."""
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    gap = stamp - now
    if gap <= FUTURE_TOLERANCE:
        return None
    minutes = int(gap.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def validate_markdown(
    root: Path, paths: list[Path], result: Result
) -> dict[Path, dict[str, Any]]:
    records: dict[Path, dict[str, Any]] = {}
    id_locations: dict[str, list[str]] = {}
    layer_ids: dict[str, set[str]] = {"mechanics": set(), "memory": set(), "library": set()}
    # A single-repository brain keeps /tasks/ at the root and names its owner everywhere; the
    # owner tripwire applies only to the split layout.
    split_layout = memory_root(root) is not None or not (root / "tasks").is_dir()
    now = clock()

    for path in paths:
        display = root_path(path, root)
        layer = layer_of(path, root)
        result.layer_markdown_files[layer] = result.layer_markdown_files.get(layer, 0) + 1
        try:
            metadata, text = read_front_matter(path)
        except (OSError, UnicodeError, ValueError) as exc:
            result.errors.append(f"{display}: {exc}")
            continue

        records[path] = metadata
        missing = sorted(REQUIRED_MARKDOWN_FIELDS - metadata.keys())
        if missing:
            result.errors.append(
                f"{display}: missing required metadata: {', '.join(missing)}"
            )

        if metadata.get("contract") != "/CONTRACT.md":
            result.errors.append(f"{display}: contract must be /CONTRACT.md")

        identifier = metadata.get("id")
        if identifier:
            id_locations.setdefault(str(identifier), []).append(display)
            layer_ids[layer].add(str(identifier))

        is_template = is_template_path(path, root)
        if not is_template:
            for key in ("created", "updated"):
                value = metadata.get(key)
                if value is not None and not TIMESTAMP_RE.fullmatch(str(value)):
                    result.errors.append(
                        f"{display}: {key} must be an ISO 8601 timestamp with seconds and timezone"
                    )
                elif value is not None and (gap := ahead_of_clock(str(value), now)):
                    result.errors.append(f"{display}: {key} {value} is {gap} ahead of the clock (CONTRACT §8.2)")
            if path.name == "LOG.md":
                for found in LOG_HEADING_RE.finditer(text):
                    gap = ahead_of_clock(found.group(1), now)
                    if gap:
                        result.errors.append(
                            f"{display}: log heading {found.group(1)} is {gap} ahead of the clock (CONTRACT §8.2)")
            # CONTRACT §3.4 / §3.6: mechanics files name no owner. A cheap tripwire only;
            # it cannot find personal data in prose.
            owner = metadata.get("owner")
            if split_layout and layer != "memory" and owner not in (None, "", GENERIC_OWNER):
                result.warnings.append(
                    f"{display}: mechanics file sets owner to a value other than {GENERIC_OWNER}"
                )

        if path.name == "README.md":
            documented = set(FOLDER_HEADING_RE.findall(text))
            actual = {
                child.name
                for child in path.parent.iterdir()
                if child.is_dir()
                and child.name not in IGNORED_DIRS
                and not child.name.startswith(".")
            }
            missing_folders = sorted(actual - documented)
            if missing_folders:
                result.warnings.append(
                    f"{display}: undocumented immediate folders: {', '.join(missing_folders)}"
                )

    for identifier, locations in sorted(id_locations.items()):
        if len(locations) > 1:
            result.errors.append(
                f"duplicate id {identifier}: {', '.join(locations)}"
            )

    result.unique_ids = len(id_locations)
    result.layer_unique_ids = {layer: len(ids) for layer, ids in layer_ids.items()}
    return records


def validate_contract(
    root: Path, records: dict[Path, dict[str, Any]], result: Result
) -> None:
    contract = records.get(root / "CONTRACT.md")
    if contract is None:
        result.errors.append("/CONTRACT.md: missing or unreadable")
        return
    version = contract.get("contract_version")
    if not version or not SEMVER_RE.fullmatch(str(version)):
        result.errors.append(
            "/CONTRACT.md: contract_version must use semantic versioning, for example 0.3.0"
        )
        return
    result.contract_version = str(version)


def heading_exists(target: Path, anchor: str) -> bool:
    """True when a Markdown heading in target begins with `anchor`.

    Log entry headings begin with an ISO 8601 timestamp (CONTRACT §4) and may
    carry a title after it, so the anchor must match the whole first token.
    """
    if not target.is_file():
        return False
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    pattern = re.compile(
        r"^#{1,6}\s+" + re.escape(anchor) + r"(?:\s|$)", re.MULTILINE
    )
    return pattern.search(text) is not None


CLOSED_PROPOSAL = {"accepted", "implemented", "verified", "withdrawn", "superseded", "rejected"}


def removed_files(root: Path) -> set[str]:
    """Paths listed in /governance/removed-files.md (first column of its table)."""
    register = root / "governance" / "removed-files.md"
    if not register.is_file():
        return set()
    found = set()
    for line in register.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells and cells[0].startswith("/"):
            found.add(cells[0])
    return found


def validate_declared_references(
    root: Path, records: dict[Path, dict[str, Any]], result: Result
) -> None:
    memory_present = memory_root(root) is not None
    for path, metadata in records.items():
        display = root_path(path, root)
        is_template = is_template_path(path, root)
        for key in REFERENCE_KEYS:
            raw_values = metadata.get(key)
            if raw_values in (None, "", []):
                continue
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            for value in values:
                if not isinstance(value, str) or not value.startswith("/"):
                    if not is_template:
                        result.errors.append(
                            f"{display}: {key} value must be a repository-root path: {value}"
                        )
                    continue
                if is_template:
                    continue
                path_part, _, anchor = value.partition("#")
                # /memory/... resolves into the memory checkout, which is root/memory.
                target = root / path_part.lstrip("/")
                if path_part.startswith(MEMORY_PREFIX) and not memory_present:
                    result.warnings.append(
                        f"{display}: {key} reference {value} not checked: memory checkout absent"
                    )
                    continue
                if not target.exists():
                    if key == "target_files" and str(metadata.get("status", "")) in CLOSED_PROPOSAL:
                        # A closed proposal's target_files record history, never rewritten
                        # (CONTRACT 13.2). A file removed since is accepted only when the register
                        # of removed files says where its content went.
                        if path_part in removed_files(root):
                            continue
                        result.errors.append(
                            f"{display}: {key} names {value}, which is gone and not in /governance/removed-files.md"
                        )
                        continue
                    if is_local_only(root, target):
                        result.warnings.append(
                            f"{display}: {key} reference {value} not checked: "
                            "the target is git-ignored and absent from this checkout"
                        )
                    else:
                        result.errors.append(
                            f"{display}: broken {key} reference {value}"
                        )
                    continue
                if anchor and not heading_exists(target, anchor):
                    result.errors.append(
                        f"{display}: broken {key} anchor {value}"
                    )


def is_local_only(root: Path, target: Path) -> bool:
    """True when Git ignores `target` in the repository that would hold it: a local-only file,
    such as a traffic recording or a scratch run, that a fresh clone cannot have."""
    repo = root
    layer = layer_of(target, root)
    if layer != "mechanics":
        nested = memory_root(root) if layer == "memory" else library_root(root)
        if nested is None or not is_own_repository(nested):
            return False
        repo = nested
    return bool(git_ignored(repo, [target.relative_to(repo).as_posix()]))


def is_reference_key(key: str) -> bool:
    return key in REFERENCE_KEYS or key.endswith(("_ref", "_refs")) or key == "evidence"


def validate_mechanics_memory_references(
    root: Path, records: dict[Path, dict[str, Any]], result: Result
) -> None:
    """A mechanics file may declare a metadata reference into /memory/ only when the memory
    skeleton provides the target: a new owner's memory holds only what the skeleton creates."""
    skeleton = root.joinpath(*SKELETON_PARTS)
    if not skeleton.is_dir():
        return
    skeleton_display = root_path(skeleton, root)
    for path, metadata in records.items():
        if in_memory(path, root) or is_template_path(path, root):
            continue
        display = root_path(path, root)
        for key, raw_values in metadata.items():
            if not is_reference_key(key):
                continue
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            for value in values:
                if not isinstance(value, str) or not value.startswith(MEMORY_PREFIX):
                    continue
                inner = value.partition("#")[0][len(MEMORY_PREFIX):].strip("/")
                if inner and skeleton.joinpath(*inner.split("/")).exists():
                    continue
                result.errors.append(
                    f"{display}: {key} reference {value} is an owner-specific memory path that "
                    f"{skeleton_display}/ does not provide; move the reference to the owner's "
                    "memory copy of this file (for a knowledge entry, "
                    "/memory/skills/<skill>/knowledge/<same filename>) or add the target to "
                    "the skeleton"
                )


def validate_tasks(
    root: Path, records: dict[Path, dict[str, Any]], result: Result
) -> None:
    open_stores: list[tuple[Path, Path, list[str]]] = []
    for parts in TASK_ROOTS:
        tasks_dir = root.joinpath(*parts)
        if not tasks_dir.is_dir():
            continue
        state_path = tasks_dir / "STATE.md"
        try:
            state_lines = state_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            state_lines = []
        open_stores.append((tasks_dir / "open", state_path, state_lines))

    for path, metadata in records.items():
        if metadata.get("type") != "task":
            continue
        if is_template_path(path, root):
            continue
        display = root_path(path, root)
        status = metadata.get("status")
        if status not in TASK_STATUSES:
            result.errors.append(f"{display}: invalid task status {status}")
        if status in {"waiting", "scheduled"} and not metadata.get("next_review"):
            result.errors.append(
                f"{display}: {status} task requires next_review"
            )
        # SMART-RULE-0025: every open task is listed in its store's STATE.md with its status word.
        for open_dir, state_path, state_lines in open_stores:
            if open_dir not in path.parents or not metadata.get("id"):
                continue
            state_display = root_path(state_path, root)
            task_id = str(metadata["id"])
            listed = [line for line in state_lines if task_id in line]
            if not listed:
                result.errors.append(
                    f"{display}: open task {task_id} is not listed in {state_display}"
                )
            elif status and not any(str(status) in line for line in listed):
                result.errors.append(
                    f"{display}: {state_display} lists {task_id} without its status word {status}"
                )


def git(repo: Path, *args: str) -> list[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def repository_changes(repo: Path) -> set[str]:
    tracked = git(repo, "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard")
    return {value.replace("\\", "/") for value in tracked + untracked}


def is_own_repository(repo: Path) -> bool:
    """True when `repo` is the top level of its own Git repository, not a folder of a parent."""
    try:
        top = git(repo, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(top) and Path(top[0]).resolve() == repo.resolve()


def git_failure(exc: Exception) -> str:
    """Why Git could not answer, without the command line: it carries this machine's paths, and
    warnings are written into the committed manifest (SMART-RULE-0008)."""
    if isinstance(exc, subprocess.CalledProcessError):
        return f"git exited with status {exc.returncode}"
    return f"git could not run ({type(exc).__name__})"


def changed_paths(root: Path) -> tuple[set[str], list[str]]:
    """Changed paths relative to the brain root, across both repositories.

    Memory paths carry the `memory/` prefix. Returns the paths and any problems met, one
    per repository that could not be read.
    """
    problems: list[str] = []
    changed: set[str] = set()
    try:
        changed |= repository_changes(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        problems.append(f"mechanics repository: {git_failure(exc)}")
    memory = memory_root(root)
    if memory is not None:
        if not is_own_repository(memory):
            problems.append(
                f"{MEMORY_PREFIX} is not its own Git repository; memory governance changes not checked"
            )
        else:
            try:
                changed |= {
                    f"{MEMORY_DIR}/{value}" for value in repository_changes(memory)
                }
            except (OSError, subprocess.CalledProcessError) as exc:
                problems.append(f"{MEMORY_PREFIX} repository: {git_failure(exc)}")
    return changed, problems


def is_protected(path: str) -> bool:
    """Protected governance under CONTRACT §13.2, by brain-root-relative path."""
    # Proposal areas sit outside the inherited rule path: the whole governance/ folder of each
    # repository.
    proposal_areas = ("governance/", f"{MEMORY_DIR}/governance/")
    if path.startswith(proposal_areas):
        return False
    return (
        path == "CONTRACT.md"
        or path == "BOOTSTRAP.md"
        or path == "README.md"
        or path == "AGENTS.md"
        or path.endswith("/AGENTS.md")
        or path.endswith("/RULES.md")
        or path == "RULES.md"
        or path == "shared/templates/node-RULES.template.md"
        or path.startswith("shared/skills/repository-preflight/")
        or "governance" in path
    )


def validate_governance(
    root: Path, records: dict[Path, dict[str, Any]], result: Result
) -> None:
    changed, problems = changed_paths(root)
    for problem in problems:
        result.warnings.append(
            f"Git change state unavailable; protected-governance coverage not checked: {problem}"
        )

    protected = {"/" + path for path in changed if is_protected(path)}
    if not protected:
        return

    covered: set[str] = set()
    proposal_roots = [root.joinpath(*parts) for parts in PROPOSAL_ROOTS]
    for path, metadata in records.items():
        if not any(proposals in path.parents for proposals in proposal_roots):
            continue
        if metadata.get("type") != "governance_proposal":
            continue
        if metadata.get("status") not in ACCEPTED_PROPOSAL_STATUSES:
            continue
        if not metadata.get("accepted_by") or not metadata.get("accepted_at"):
            result.errors.append(
                f"{root_path(path, root)}: accepted proposal lacks acceptance evidence"
            )
            continue
        targets = metadata.get("target_files", [])
        if isinstance(targets, list):
            covered.update(str(target) for target in targets)

    for path in sorted(protected - covered):
        result.errors.append(
            f"{path}: changed protected governance is not covered by an accepted proposal"
        )


def manifest_paths(root: Path) -> dict[str, Path]:
    paths = {"mechanics": root / MANIFEST_NAME}
    memory = memory_root(root)
    if memory is not None:
        paths["memory"] = memory / MANIFEST_NAME
    library = library_root(root)
    if library is not None:
        paths["library"] = library / MANIFEST_NAME
    return paths


def validate_manifest(
    root: Path, result: Result, writing: bool
) -> None:
    for layer, path in manifest_paths(root).items():
        display = root_path(path, root)
        if not path.exists():
            if writing:
                continue
            if layer == "mechanics":
                result.errors.append(f"{display}: missing")
            else:
                result.warnings.append(
                    f"{display}: missing; create it with --write-manifest"
                )
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{display}: {exc}")
            continue
        if (
            not writing
            and manifest.get("contract_version") != result.contract_version
        ):
            result.errors.append(
                f"{display}: contract_version does not match /CONTRACT.md"
            )


def write_manifests(root: Path, result: Result) -> None:
    """Write one manifest per repository, each holding only its own layer's messages."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    names = {"mechanics": "Portable AI Brain – mechanics", "memory": "Portable AI Brain – memory",
             "library": "Portable AI Brain – skill library"}
    for layer, path in manifest_paths(root).items():
        created = now
        name = names[layer]
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                created = existing.get("created", created)
                name = existing.get("name", name)
            except (OSError, json.JSONDecodeError):
                pass
        manifest = {
            "name": name,
            "layer": layer,
            "created": created,
            "updated": now,
            "validated_at": now,
            "contract_version": result.contract_version,
            "markdown_files": result.layer_markdown_files.get(layer, 0),
            "unique_ids": result.layer_unique_ids.get(layer, 0),
            "validation_errors": [m for m in result.errors if message_layer(m) == layer],
            "validation_warnings": [m for m in result.warnings if message_layer(m) == layer],
            "root_contract": "/CONTRACT.md",
            "validator": VALIDATOR_PATH,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        # LF on every platform, so a rewrite on Windows is not a whole-file change.
        temporary.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(path)


def shareable_repositories(root: Path) -> list[Path]:
    """The repositories that must hold no personal data: the mechanics, and the skill library when
    it is checked out (CONTRACT §3.4)."""
    library = root / LIBRARY_DIR
    return [root] + ([library] if library.is_dir() else [])


def validate_personal_data(root: Path, result: Result) -> None:
    """SMART-RULE-0008: a shareable repository is written clean, and this confirms it. Owner terms
    come from memory at run time; without memory only the patterns run."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import personal_data

    for repo in shareable_repositories(root):
        hits, problems = personal_data.check_repository(root, repo)
        result.errors.extend(f"personal-data exemptions: {problem}" for problem in problems)
        # The value itself is withheld: errors are written into the committed manifest, and
        # repeating it there would copy the leak. File, line and kind are enough to find it;
        # `skill_exchange.py scrub <file>` prints the value on the console only.
        for file, line, kind, _value in hits:
            display = root_path(Path(file), root)
            result.errors.append(f"{display}:{line}: personal data ({kind}); value withheld")


def run(root: Path, writing: bool) -> Result:
    result = Result()
    result.memory_present = memory_root(root) is not None
    if not result.memory_present:
        result.warnings.append(
            f"{MEMORY_PREFIX} memory checkout absent; validated the mechanics repository only"
        )
    paths = markdown_paths(root)
    result.markdown_files = len(paths)
    records = validate_markdown(root, paths, result)
    validate_contract(root, records, result)
    validate_declared_references(root, records, result)
    validate_mechanics_memory_references(root, records, result)
    validate_tasks(root, records, result)
    validate_governance(root, records, result)
    validate_personal_data(root, result)
    from checks_b import validate_knowledge_provenance, validate_knowledge_review_dates, validate_pointer_files
    validate_pointer_files(root, result.errors)
    validate_knowledge_provenance(root, result.errors)
    validate_knowledge_review_dates(root, result.errors)
    validate_manifest(root, result, writing)
    if writing:
        write_manifests(root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        root = discover_root(args.root)
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    result = run(root, args.write_manifest)
    payload = {
        "status": "pass" if result.passed else "fail",
        "root": str(root),
        "contract_version": result.contract_version,
        "memory_present": result.memory_present,
        "markdown_files": result.markdown_files,
        "unique_ids": result.unique_ids,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        memory_note = "memory present" if result.memory_present else "memory absent"
        print(
            f"{payload['status'].upper()}: contract {result.contract_version}; {memory_note}; "
            f"{result.markdown_files} Markdown files; {result.unique_ids} unique IDs"
        )
        for error in result.errors:
            print(f"ERROR: {error}")
        for warning in result.warnings:
            print(f"WARNING: {warning}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
