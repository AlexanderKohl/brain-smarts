"""Protected governance (CONTRACT 13.2): a changed protected file needs an accepted proposal.

Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
preflight sees the same names.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from preflight_base import MEMORY_DIR, MEMORY_PREFIX, memory_root, Result, root_path, repository_changes, is_own_repository, git_failure


ACCEPTED_PROPOSAL_STATUSES = {"accepted", "implemented", "verified", "reverted"}


# Where accepted proposals may live, relative to the brain root (CONTRACT §13.2).
PROPOSAL_ROOTS = (
    ("governance", "proposals"),
    (MEMORY_DIR, "governance", "proposals"),
)


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

    # CONTRACT 13.2: acceptance is enforced where a change becomes active. On a proposal/*
    # branch, a file an open proposal lists is that proposal's draft diff, reported as a warning.
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True,
                            text=True).stdout.strip()
    drafted: set[str] = set()
    if branch.startswith("proposal/"):
        for path, metadata in records.items():
            if (any(proposals in path.parents for proposals in proposal_roots)
                    and metadata.get("type") == "governance_proposal"
                    and metadata.get("status") in ("proposed", "draft")
                    and isinstance(metadata.get("target_files"), list)):
                drafted.update(str(target) for target in metadata["target_files"])

    for path in sorted(protected - covered):
        if path in drafted:
            result.warnings.append(f"{path}: protected governance drafted on {branch}; not active until accepted and merged")
            continue
        result.errors.append(
            f"{path}: changed protected governance is not covered by an accepted proposal"
        )
