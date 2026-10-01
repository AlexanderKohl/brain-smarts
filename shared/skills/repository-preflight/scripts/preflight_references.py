"""Checks that paths named in metadata resolve, and that mechanics files name only what every memory has.

Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
preflight sees the same names.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from preflight_base import MEMORY_PREFIX, in_memory, memory_root, library_root, layer_of, Result, root_path, git_ignored, is_template_path, is_own_repository


# The memory skeleton every new owner starts from. A mechanics file may declare a metadata
# reference into /memory/ only when this skeleton provides the target, so the mechanics work for
# any owner.
SKELETON_PARTS = ("shared", "templates", "memory-skeleton")


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
