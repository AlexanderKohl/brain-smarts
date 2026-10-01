"""Where each repository of the brain is, the git helpers, and the result every check writes to.

Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
preflight sees the same names.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


MEMORY_DIR = "memory"
MEMORY_PREFIX = "/" + MEMORY_DIR + "/"
LIBRARY_DIR = "library"
LIBRARY_PREFIX = "/" + LIBRARY_DIR + "/"


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


def root_path(path: Path, root: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


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


def is_template_path(path: Path, root: Path) -> bool:
    """A file under a `templates/` folder, or a `_TEMPLATE.md` copied again for every new record
    (a CRM node's contact and persona templates): its placeholders stay unfilled."""
    return "templates" in path.relative_to(root).parts or path.name == "_TEMPLATE.md"


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
