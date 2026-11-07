"""The task-store checks of the preflight (P25) and the raw stores it skips (P24).

One implementation (SMART-RULE-0018): the record and store checks are `tasks.py check`'s own
(`task_check.check_store`), over the stores `task_stores.stores()` lists. This module adds what
needs Git or belongs to the preflight alone:

- a path Git reports as unmerged inside a store, and a conflict marker in a store file that is
  not a record (STATE.md, a README, a private note);
- a `waiting` or `scheduled` task without `next_review`;
- from the brain root, a failure in a repository's store is a warning, because that repository
  runs its own check (`preflight.py --project`); with `--project`, the one store is checked and
  its failures are errors;
- a brain kept in one repository (tasks at `/tasks/`, no memory) keeps the listing check of
  SMART-RULE-0025, since the node stores of CONTRACT §9 do not apply to it.

Messages about a repository store begin with its pointer node's `/memory/` path, so they are the
memory repository's (`message_layer`) and no project name reaches the mechanics manifest. No
message carries a path of this machine (SMART-RULE-0008).
"""

from __future__ import annotations

import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

TASKS_SCRIPTS = Path(__file__).resolve().parents[2] / "tasks" / "scripts"
if str(TASKS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TASKS_SCRIPTS))

import task_check  # noqa: E402
import task_stores  # noqa: E402
from task_git import MARKER_RE, WriteRefused, unmerged_paths  # noqa: E402
from task_records import FOLDER_STATUSES, Task, load_tasks  # noqa: E402

from preflight_base import Result, is_own_repository, is_template_path, root_path  # noqa: E402

NEEDS_REVIEW = ("waiting", "scheduled")
RAW = "raw"


# ---------------------------------------------------------------------------- raw stores (P24)

def raw_store_skipper(root: Path) -> Callable[[Path], bool]:
    """A test for "this file is immutable evidence in a raw store" at the brain root: `/raw/` in a
    brain without a separate memory, `/memory/raw/`, and the `raw/` folder of every memory node,
    pointer nodes included. Answers per folder are kept, so a large raw store costs one look."""
    memory = root / "memory"
    known: dict[Path, bool] = {}

    def is_store(folder: Path) -> bool:
        if folder not in known:
            known[folder] = folder == memory or task_stores.is_node(root, folder)
        return known[folder]

    def skip(path: Path) -> bool:
        parts = path.relative_to(root).parts
        if not parts:
            return False
        if parts[0] == RAW:
            return True
        if parts[0] != "memory":
            return False
        for index, part in enumerate(parts[:-1]):
            if part == RAW and index >= 1 and is_store(root.joinpath(*parts[:index])):
                return True
        return False

    return skip


def project_raw(checkout: Path, path: Path) -> bool:
    """With --project: the repository's `brain/raw/`."""
    parts = path.relative_to(checkout).parts
    return len(parts) > 2 and parts[0] == "brain" and parts[1] == RAW


# ---------------------------------------------------------------------------- repository references

# CONTRACT §16.2: a file outside a project repository names a file in it `<repository>:brain/<path>`,
# `<repository>` being the remote's name a pointer node gives (the same in every brain).
REPOSITORY_REF_RE = re.compile(r"^(?P<repository>[A-Za-z0-9][A-Za-z0-9._-]*):(?P<path>brain(?:/[^\s#:]+)*/?)"
                               r"(?:#(?P<anchor>.+))?$")


def repository_checkouts(root: Path) -> dict[str, tuple[Path | None, str | None]]:
    """Each repository a pointer node names: (its checkout when reachable, else None, and why not)."""
    found: dict[str, tuple[Path | None, str | None]] = {}
    for pointer in task_stores.pointers(root):
        if pointer.repository in found:
            continue
        if pointer.checkout is None:
            found[pointer.repository] = (None, "not checked out here")
        elif not (pointer.checkout / "brain").is_dir():
            found[pointer.repository] = (None, "checked out without a brain/ folder")
        else:
            found[pointer.repository] = (pointer.checkout, None)
    return found


def resolve_repository_ref(value: str, checkouts: dict) -> tuple[str, Path | None, str | None, str]:
    """(kind, target, anchor, detail) for a `<repository>:brain/<path>` value.

    kind is "malformed" (not that form), "unknown" (no pointer names the repository),
    "unreachable" (detail says why) or "resolved" (target is the file or folder it names)."""
    match = REPOSITORY_REF_RE.match(value)
    if not match:
        return "malformed", None, None, ""
    name = match.group("repository")
    entry = checkouts.get(name)
    if entry is None:
        folded = [k for k in checkouts if k.casefold() == name.casefold()]
        entry = checkouts[folded[0]] if folded else None
    if entry is None:
        return "unknown", None, None, name
    checkout, why = entry
    if checkout is None:
        return "unreachable", None, None, why or "not reachable"
    return "resolved", checkout.joinpath(*match.group("path").strip("/").split("/")), match.group("anchor"), name


# ---------------------------------------------------------------------------- the stores

def _unreachable_reason(store) -> str:
    """Why a repository store was not read, without this machine's paths."""
    if store.checkout is None:
        return "not checked out here"
    if not (store.checkout / "brain").is_dir():
        return "its checkout has no brain/ folder"
    return "its brain/JOINING.md cannot be read"


def _where(store, path: Path) -> str:
    if store.kind == "repository":
        return f"{store.repository}:brain/tasks/{path.relative_to(store.path).as_posix()}"
    return f"{store.label}/{path.relative_to(store.path).as_posix()}"


def _git_checks(store, records: list[Task], unmerged: list[Path] | None, report: task_check.Report) -> None:
    """Unmerged paths in the store, and conflict markers in its files that are not records."""
    for path in unmerged or ():
        report.errors.append(f"{_where(store, path)}: unmerged in Git; resolve it by hand (P23), then "
                             f"run `tasks.py state --store {store.label}`")
    loaded = {task.path for task in records}
    for path in sorted(store.path.rglob("*.md")):
        if path in loaded:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if MARKER_RE.search(text):
            fix = (" generate it again (`tasks.py state --store " + store.label + "`)" if path.name == "STATE.md"
                   else " resolve it by hand")
            report.errors.append(f"{_where(store, path)}: has a Git conflict marker;{fix}")


def _review_checks(store, records: list[Task], report: task_check.Report) -> None:
    for task in records:
        status = task.get("status")
        if status in NEEDS_REVIEW and not task.get("next_review"):
            report.errors.append(f"{_where(store, task.path)}: {status} task requires next_review")


def _unmerged_in(repo: Path, inside: Path, warnings: list[str], name: str) -> list[Path] | None:
    """Unmerged paths below `inside`, or None (with a warning) when Git cannot say."""
    try:
        return unmerged_paths(repo, inside)
    except (WriteRefused, OSError):
        warnings.append(f"{name}: Git could not report unmerged paths; not checked")
        return None


def check_one(root: Path, store, seen: dict[str, str], unmerged: list[Path] | None) -> task_check.Report:
    """Every P25 check of one reachable store."""
    report = task_check.Report()
    task_check.check_store(root, store, report, seen)
    records = load_tasks(store.path, owner=store) if store.path.is_dir() else []
    _review_checks(store, records, report)
    if store.path.is_dir():
        _git_checks(store, records, [p for p in (unmerged or ()) if store.path in p.parents], report)
    return report


def _memory_unmerged(root: Path, result: Result) -> list[Path] | None:
    memory = root / "memory"
    if not memory.is_dir() or not is_own_repository(memory):
        return None
    return _unmerged_in(memory, memory, result.warnings, "/memory/")


def _duplicate(message: str) -> bool:
    """`task_check`'s message for an identifier another store checked earlier also uses."""
    _where_part, _sep, rest = message.partition(": identifier ")
    return bool(rest) and " is also used by " in rest


def _same_store(store, other) -> bool:
    if other.kind != "repository" or store.checkout is None or other.checkout is None:
        return False
    return other.checkout.resolve() == store.checkout.resolve()


def _ids_elsewhere(root: Path, store) -> dict[str, str]:
    """Every identifier in every other reachable store, with where it is: `--project` checks one
    store, and a clash with another store is still a failure (proposal Risk 6)."""
    seen: dict[str, str] = {}
    for other in task_stores.stores(root):
        if _same_store(store, other) or not other.reachable or not other.path.is_dir():
            continue
        for task in load_tasks(other.path, owner=other):
            if task.meta.get("id") and task.tid not in seen:
                seen[task.tid] = _where(other, task.path)
    return seen


def _already_reported(message: str) -> bool:
    """A duplicate identifier between two memory files: the general duplicate-id check names it."""
    where, _sep, rest = message.partition(": identifier ")
    return bool(rest) and where.startswith("/memory/") and " is also used by /memory/" in rest


def validate_task_stores(root: Path, records: dict[Path, dict[str, Any]], result: Result) -> None:
    """The task-store checks from the brain root (P25)."""
    if not (root / "memory").is_dir():
        validate_single_repository_tasks(root, records, result)
        return
    seen: dict[str, str] = {}
    memory_unmerged = _memory_unmerged(root, result)
    for store in task_stores.stores(root):
        if store.kind == "repository":
            if not store.reachable:
                result.warnings.append(f"{store.node}: repository store {store.label} not checked: "
                                       f"{_unreachable_reason(store)}")
                continue
            unmerged = _unmerged_in(store.checkout, store.path, result.warnings, f"{store.node}: {store.label}")
            report = check_one(root, store, seen, unmerged)
            # The repository runs its own check; from here its failures are warnings, except an
            # identifier also used in another store: the repository alone cannot see that clash.
            result.errors += [f"{store.node}: {m}" for m in report.errors if _duplicate(m)]
            result.warnings += [f"{store.node}: {m} (checked as an error by the repository's own "
                                "`preflight.py --project`)" for m in report.errors if not _duplicate(m)]
            result.warnings += [f"{store.node}: {m}" for m in report.warnings]
            continue
        if store.kind == "owner" and not store.path.is_dir():
            result.errors.append("/memory/tasks: task store not found")
            continue
        report = check_one(root, store, seen, memory_unmerged)
        result.errors += [m for m in report.errors if not _already_reported(m)]
        result.warnings += report.warnings


# ---------------------------------------------------------------------------- --project mode

def _remote_name(checkout: Path) -> str:
    """The repository's name as a pointer gives it: the last segment of origin's URL."""
    import subprocess
    try:
        done = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        done = None
    url = done.stdout.strip() if done is not None and done.returncode == 0 else ""
    return task_stores.repository_name(url) if url else checkout.name


def project_store(root: Path, target: str):
    """The repository store `--project` names: a checkout path, or a repository name a pointer
    gives. A checkout no pointer names is checked on its own, named after its origin remote."""
    candidate = Path(target).expanduser()
    if candidate.is_dir():
        checkout = candidate.resolve()
        if not (checkout / "brain").is_dir():
            raise LookupError(f"--project {target}: the folder has no brain/ folder")
        for store in task_stores.stores(root):
            if store.kind == "repository" and store.checkout is not None and store.checkout.resolve() == checkout:
                return replace(store, path=checkout / "brain" / "tasks", checkout=checkout)
        return task_stores.Store(kind="repository", path=checkout / "brain" / "tasks", node=None,
                                 repository=_remote_name(checkout), checkout=checkout)
    named = [s for s in task_stores.stores(root) if s.kind == "repository"]
    # The remote's name first; this brain's clone folder name as well, since it may differ.
    found = [s for s in named if s.repository == target] or \
        [s for s in named if str(s.repository).casefold() == target.casefold()] or \
        [s for s in named if s.checkout is not None and s.checkout.name.casefold() == target.casefold()]
    if not found:
        raise LookupError(f"--project {target}: no pointer node names this repository and no such folder exists")
    store = found[0]
    if not store.reachable:
        raise LookupError(f"--project {target}: {_unreachable_reason(store)}")
    return store


def validate_project_store(root: Path, store, result: Result) -> None:
    """With --project: that repository's store; every failure is an error. The identifiers of
    every other reachable store are known first, so a clash with one of them fails here too."""
    if not store.path.is_dir():
        result.warnings.append(f"{store.repository}:brain/tasks: no task store yet")
        return
    unmerged = _unmerged_in(store.checkout, store.path, result.warnings, f"{store.repository}:brain/tasks")
    report = check_one(root, store, _ids_elsewhere(root, store), unmerged)
    result.errors += report.errors
    result.warnings += report.warnings


# ---------------------------------------------------------------------------- one-repository brain

def validate_single_repository_tasks(root: Path, records: dict[Path, dict[str, Any]], result: Result) -> None:
    """A brain without a separate memory keeps its tasks at /tasks/: valid states, next_review,
    and every open task listed in /tasks/STATE.md with its status word (SMART-RULE-0025)."""
    tasks_dir = root / "tasks"
    if not tasks_dir.is_dir():
        return
    state_path = tasks_dir / "STATE.md"
    try:
        state_lines = state_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        state_lines = []
    statuses = set().union(*FOLDER_STATUSES.values())
    for path, metadata in records.items():
        if metadata.get("type") != "task" or is_template_path(path, root) or tasks_dir not in path.parents:
            continue
        display = root_path(path, root)
        status = metadata.get("status")
        if status not in statuses:
            result.errors.append(f"{display}: invalid task status {status}")
        if status in NEEDS_REVIEW and not metadata.get("next_review"):
            result.errors.append(f"{display}: {status} task requires next_review")
        if (tasks_dir / "open") not in path.parents or not metadata.get("id"):
            continue
        task_id = str(metadata["id"])
        listed = [line for line in state_lines if task_id in line]
        state_display = root_path(state_path, root)
        if not listed:
            result.errors.append(f"{display}: open task {task_id} is not listed in {state_display}")
        elif status and not any(str(status) in line for line in listed):
            result.errors.append(f"{display}: {state_display} lists {task_id} without its status word {status}")
