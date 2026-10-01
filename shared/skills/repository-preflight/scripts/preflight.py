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
from preflight_base import (
    MEMORY_DIR, MEMORY_PREFIX, LIBRARY_DIR, LIBRARY_PREFIX, in_memory, memory_root, in_library,
    library_root, layer_of, Result, message_layer, root_path, git_ignored, is_template_path, git,
    repository_changes, is_own_repository, git_failure,
)
from preflight_references import (
    SKELETON_PARTS, REFERENCE_KEYS, heading_exists, CLOSED_PROPOSAL, removed_files,
    validate_declared_references, is_local_only, is_reference_key,
    validate_mechanics_memory_references,
)
from preflight_governance import (
    ACCEPTED_PROPOSAL_STATUSES, PROPOSAL_ROOTS, changed_paths, is_protected, validate_governance,
)
from preflight_manifest import (
    MANIFEST_NAME, VALIDATOR_PATH, manifest_paths, validate_manifest, write_manifests,
    shareable_repositories, validate_personal_data,
)


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

# The owner value mechanics files may carry (CONTRACT §3.6).
GENERIC_OWNER = "brain-owner"
# Task stores: /memory/tasks/ in the three-layer layout, /tasks/ in a single-repository brain.
TASK_ROOTS = ((MEMORY_DIR, "tasks"), ("tasks",))
# Scratch folder at the brain root, git-ignored; skipped even when Git cannot be asked.
SCRATCH_DIR = "temp"


def is_raw_evidence_path(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if not parts:
        return False
    if parts[0] == "raw":
        return True
    return len(parts) > 1 and parts[0] == MEMORY_DIR and parts[1] == "raw"


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


def validate_core(root: Path, errors: list[str]) -> None:
    """CONTRACT §1 and §15: the core's parts are current and short enough to be read whole, and every
    index row says when it applies."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import core

    rules = root / "RULES.md"
    # A brain whose rule index has no `Applies when` column reads the contract whole and has no core.
    if not rules.is_file() or not (root / "CONTRACT.md").is_file() or "| Applies when |" not in rules.read_text(encoding="utf-8"):
        return
    errors.extend(core.problems(rules.read_text(encoding="utf-8")))
    try:
        parts = core.render(root)
    except ValueError as exc:
        errors.append(f"/{core.PARTS[0]}: {exc}")
        return
    errors.extend(core.size_problems(parts))
    for name, text in parts.items():
        target = root / name
        if not target.is_file() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            errors.append(f"/{name}: out of date with /CONTRACT.md and /RULES.md; run core.py build")


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
    from file_sizes import validate_file_sizes
    validate_file_sizes(root, result.errors)
    validate_core(root, result.errors)
    validate_manifest(root, result, writing)
    if writing:
        write_manifests(root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--layer", choices=("mechanics", "library", "memory"),
                        help="report only this repository's errors and warnings (the pre-commit hook)")
    args = parser.parse_args()

    try:
        root = discover_root(args.root)
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    result = run(root, args.write_manifest)
    if args.layer:
        # A commit is judged on its own repository: another repository's problem, or another
        # session's, never blocks it.
        result.errors = [e for e in result.errors if message_layer(e) == args.layer]
        result.warnings = [w for w in result.warnings if message_layer(w) == args.layer]
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
