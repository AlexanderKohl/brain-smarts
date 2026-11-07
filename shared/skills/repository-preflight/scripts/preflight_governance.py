"""Protected governance (CONTRACT 13.2): each change to rule or contract wording needs an accepted
proposal whose window is open.

Moved from preflight.py. preflight.py imports these names back, so everything that uses preflight
sees the same names.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from preflight_base import (
    MEMORY_DIR, MEMORY_PREFIX, TIMESTAMP_RE, memory_root, Result, root_path, repository_changes,
    is_own_repository, git_failure, text_at,
)


ACCEPTED_PROPOSAL_STATUSES = {"accepted", "implemented", "verified", "reverted"}


# Where accepted proposals may live, relative to the brain root (CONTRACT §13.2).
PROPOSAL_ROOTS = (
    ("governance", "proposals"),
    (MEMORY_DIR, "governance", "proposals"),
)

# CONTRACT §13.2: protected governance is rule and contract wording, named by path. Scripts,
# tests, fixtures, README files and a skill's other operating detail are not.
WORDING_PATHS = {"CONTRACT.md", "BOOTSTRAP.md"}
WORDING_NAMES = {"RULES.md", "AGENTS.md", "CLAUDE.md"}           # wherever they are
WORDING_TEMPLATE_SUFFIX = "RULES.template.md"                    # a node's rules, to be copied
GOVERNANCE_FOLDERS = ("shared/schemas/", "shared/templates/")    # files named governance-*
# The one file of which only a part is wording: the statement of what the validator enforces.
VALIDATOR_STATEMENT = "shared/skills/repository-preflight/SKILL.md"
VALIDATOR_SECTION = "## Failure behaviour"

# An accepted proposal covers changes to its target files from its acceptance until an hour after
# its implementation, or for seven days when it is never marked implemented.
IMPLEMENTATION_GRACE = timedelta(hours=1)
UNIMPLEMENTED_WINDOW = timedelta(days=7)
# The tolerance CONTRACT §8.2 allows between clocks, applied before acceptance.
CLOCK_TOLERANCE = timedelta(minutes=5)
UPDATED_RE = re.compile(r"^updated:\s")
DASH_RE = re.compile("\\s*[\u2013\u2014]\\s*")


def changed_paths(root: Path) -> tuple[dict[str, tuple[Path, str, str]], list[str]]:
    """Changed paths relative to the brain root, across both repositories.

    Memory paths carry the `memory/` prefix. Returns {path: (repository, base, path in it)} and
    any problems met, one per repository that could not be read.
    """
    problems: list[str] = []
    changed: dict[str, tuple[Path, str, str]] = {}
    try:
        base, paths = repository_changes(root)
        changed.update({value: (root, base, value) for value in paths})
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
                base, paths = repository_changes(memory)
                changed.update({f"{MEMORY_DIR}/{value}": (memory, base, value) for value in paths})
            except (OSError, subprocess.CalledProcessError) as exc:
                problems.append(f"{MEMORY_PREFIX} repository: {git_failure(exc)}")
    return changed, problems


def is_protected(path: str) -> bool:
    """Rule or contract wording under CONTRACT §13.2, by brain-root-relative path."""
    # Proposal areas sit outside the inherited rule path: the whole governance/ folder of each
    # repository.
    if path.startswith(("governance/", f"{MEMORY_DIR}/governance/")):
        return False
    name = path.rsplit("/", 1)[-1]
    return (
        path in WORDING_PATHS
        or name in WORDING_NAMES
        or name.endswith(WORDING_TEMPLATE_SUFFIX)
        or (path.startswith(GOVERNANCE_FOLDERS) and name.startswith("governance-"))
        or path == VALIDATOR_STATEMENT
    )


def wording(path: str, text: str) -> str:
    """The part of a protected file that is wording, without what never needs a proposal: the
    `updated` stamp, line endings, and the choice of long dash (an em dash as a spaced en dash)."""
    if path == VALIDATOR_STATEMENT:
        start = text.find(VALIDATOR_SECTION)
        end = text.find("\n## ", start + len(VALIDATOR_SECTION)) if start >= 0 else -1
        text = "" if start < 0 else text[start:end if end >= 0 else len(text)]
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if not UPDATED_RE.match(line)]
    return DASH_RE.sub(" \u2013 ", "\n".join(lines)).strip()


def substantive(path: str, repo: Path, base: str, relative: str) -> bool:
    """True when a changed protected file's wording differs from its base version. A new file is
    substantive when it has any wording; a file that cannot be read is treated as substantive."""
    try:
        after = (repo / relative).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return True
    before = text_at(repo, base, relative)
    return wording(path, after) != ("" if before is None else wording(path, before))


def stamp(value: Any) -> datetime | None:
    """A front-matter timestamp as an aware datetime, or None when it is not one."""
    if isinstance(value, datetime):
        return value if value.tzinfo else None
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value.strip()):
        return None
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def coverage_window(metadata: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """When an accepted proposal covers changes to its target files (CONTRACT §13.2).

    From acceptance until implementation, with an hour's grace for the commits that apply and
    record it; a proposal accepted but never marked implemented stops covering after seven days.
    After that a change to the same file needs a proposal of its own.
    """
    opened = stamp(metadata.get("accepted_at"))
    if opened is None:
        return None
    ends = [s for s in (stamp(metadata.get("implemented_at")), stamp(metadata.get("reverted_at"))) if s]
    closed = max(ends) + IMPLEMENTATION_GRACE if ends else opened + UNIMPLEMENTED_WINDOW
    return opened - CLOCK_TOLERANCE, closed


def validate_governance(
    root: Path, records: dict[Path, dict[str, Any]], result: Result, now: datetime
) -> None:
    changed, problems = changed_paths(root)
    for problem in problems:
        result.warnings.append(
            f"Git change state unavailable; protected-governance coverage not checked: {problem}"
        )

    protected = {"/" + path for path, (repo, base, relative) in changed.items()
                 if is_protected(path) and substantive(path, repo, base, relative)}
    if not protected:
        return

    # Coverage is per change, not per file: a proposal covers a file it lists only while its
    # window is open, judged at `now` – the commit or the push that would make the change active.
    covered: set[str] = set()
    closed: dict[str, int] = {}
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
        if not isinstance(targets, list):
            continue
        window = coverage_window(metadata)
        if window is None:
            result.errors.append(f"{root_path(path, root)}: accepted_at is not a timestamp with a timezone")
            continue
        for target in (str(t) for t in targets):
            if window[0] <= now <= window[1]:
                covered.add(target)
            else:
                closed[target] = closed.get(target, 0) + 1

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
        earlier = closed.get(path)
        result.errors.append(
            f"{path}: changed protected governance is not covered by an accepted proposal"
            # A count, not the names: memory proposal names must not reach the mechanics manifest.
            + (f" ({earlier} accepted proposal(s) list it, but each was implemented, or accepted more "
               "than seven days ago, before this change)" if earlier else "")
        )
