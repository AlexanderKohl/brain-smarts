"""`tasks.py check`: the record checks and the store-level checks of P25 that need no Git.

Per record: front matter, the required fields (`author` among them), `type`, the identifier and
the file name, the status against its folder, dates, `schedule`, a conflict marker or an
unreadable file, an `updated` later than the newest attributed History entry (an edit nobody is
named for), a first project reference that does not name the node holding the record (in
/memory/tasks/, any project reference that names a node), and, outside completed/, references
that name more than one node. Per store: a /memory/ path in a repository's brain/tasks/, and a
STATE.md that differs from the generated one. Across the stores checked: an identifier used
twice. Unmerged paths are Git's to report (task_git, the preflight).

Errors and warnings are listed by store in `stores()` order, then by file path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import task_claims
import task_state
import task_stores
from task_history import newest_attributed, parse_stamp
from task_new import SCHEDULE_RE
from task_private import MEMORY_PATH
from task_records import FOLDER_STATUSES, ID_RE, Task, load_tasks

REQUIRED = ("id", "title", "type", "contract", "status", "owner", "author", "created", "updated")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _ref_node(root: Path, ref: str) -> str | None:
    if ":" in ref and not ref.startswith("/"):
        return "repository " + ref.split(":", 1)[0]
    return task_stores.node_of(root, ref)


def _check_record(root: Path, store, task: Task, where: str, report: Report) -> None:
    if task.problem:
        report.errors.append(f"{where}: {task.problem}")
        if task.problem.startswith("unreadable"):
            return
    if not task.meta:
        report.errors.append(f"{where}: missing front matter")
        return
    missing = [key for key in REQUIRED if not task.get(key)]
    if missing:
        report.errors.append(f"{where}: missing {', '.join(missing)}")
    if task.get("type") not in (None, "task"):
        report.errors.append(f"{where}: type must be task")
    tid = task.get("id")
    if tid and not ID_RE.match(tid):
        report.errors.append(f"{where}: id {tid} is not TASK-<author>-YYYY-NNNN or TASK-YYYY-NNNN")
    elif tid and not task.path.stem.startswith(tid):
        report.errors.append(f"{where}: file name does not start with {tid}")
    status = task.get("status")
    if status and status not in FOLDER_STATUSES[task.folder]:
        allowed = ", ".join(sorted(FOLDER_STATUSES[task.folder]))
        report.errors.append(f"{where}: status {status} does not belong in {task.folder}/ ({allowed})")
    for key in ("due", "next_review"):
        if task.get(key) and task.day(key) is None:
            report.errors.append(f"{where}: {key} {task.get(key)} is not a date")
    if task.get("schedule") and not SCHEDULE_RE.match(task.get("schedule")):
        report.errors.append(f"{where}: schedule is not \"<app> | <job> | <cadence>\"")
    text = task.path.read_text(encoding="utf-8")
    newest = newest_attributed(text)
    updated = parse_stamp(task.get("updated") or "")
    if newest is None:
        report.errors.append(f"{where}: no History entry `- <timestamp> – <author>: <what changed>`")
    elif updated is not None and updated > newest.at:
        report.errors.append(f"{where}: updated {task.get('updated')} is later than its newest attributed "
                             "History entry (an edit nobody is named for)")
    refs = task.refs()
    nodes = [n for n in (_ref_node(root, r) for r in refs) if n]
    if store.kind == "owner" and nodes:
        report.errors.append(f"{where}: names {nodes[0]}, so it belongs in that node's store, not /memory/tasks")
    elif store.kind in ("memory-node", "pointer-private") and (not refs or _ref_node(root, refs[0]) != store.node):
        report.errors.append(f"{where}: its first project reference does not name {store.node}")
    elif store.kind == "repository" and (not refs or refs[0] != f"{store.repository}:brain"):
        report.errors.append(f"{where}: its first project reference is not {store.repository}:brain")
    if task.folder != "completed" and len(set(nodes)) > 1:
        report.errors.append(f"{where}: names more than one node ({', '.join(sorted(set(nodes)))}); work for "
                             "several projects is split (CONTRACT §9)")
    if status == "waiting" and not task.get("waiting_on"):
        report.warnings.append(f"{where}: waiting without waiting_on")
    if not task.get("priority") and task.folder != "completed":
        report.warnings.append(f"{where}: no priority")
    report.warnings += task_claims.warnings(task, where)


def check_store(root: Path, store, report: Report, seen: dict[str, str]) -> None:
    prefix = store.label
    if not store.reachable:
        report.warnings.append(f"{prefix}: not checked ({store.reason})")
        return
    if not store.path.is_dir():
        if store.kind == "owner":
            report.errors.append(f"{prefix}: task store not found at {store.path.as_posix()}")
        return
    for task in load_tasks(store.path, owner=store):
        where = f"{prefix}/{task.folder}/{task.path.name}" if store.kind != "repository" else \
            f"{store.repository}:brain/tasks/{task.folder}/{task.path.name}"
        _check_record(root, store, task, where, report)
        if task.meta.get("id"):
            if task.tid in seen:
                report.errors.append(f"{where}: identifier {task.tid} is also used by {seen[task.tid]}")
            else:
                seen[task.tid] = where
    if store.kind == "repository":
        for path in sorted(store.path.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if MEMORY_PATH.search(text):
                report.errors.append(f"{store.repository}:brain/tasks/{path.relative_to(store.path).as_posix()}: "
                                     "names a /memory/ path")
    if task_state.differs(store):
        report.errors.append(f"{prefix}/STATE.md: differs from the generated one; run `tasks.py state --store {prefix}`")


def check(root: Path, label: str | None = None) -> Report:
    report = Report()
    seen: dict[str, str] = {}
    chosen = [task_stores.store_by_label(root, label)] if label else task_stores.stores(root)
    for store in chosen:
        check_store(root, store, report, seen)
    return report
