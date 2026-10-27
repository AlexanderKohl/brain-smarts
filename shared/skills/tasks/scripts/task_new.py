"""Creating tasks: the next identifier, the record from the template, and the store it goes in.

    next_id(root, author, year)   the highest number of that author and year, plus one
    claim_id(root, author, year)  the same, taken atomically under /memory/tasks/.claims/
    create(root, title, ...)      one task per project, each in store_for(project) (P10)

**Numbers.** A new identifier is TASK-<author>-YYYY-NNNN, the next in that author's one sequence
across every reachable store and the claims folder (one for the brain, keyed by the full
identifier). A legacy TASK-YYYY-NNNN counts toward an author's sequence when its record's
`author` is that author, and, for a record in this brain's memory that has no `author` yet,
toward this brain's own sequence: those records are this brain's, so its new numbers continue
from its highest existing one. A repository not checked out may hold a higher number; the
preflight's duplicate check catches a clash.

**Several projects.** Work for several projects becomes one task per project, each in its own
store, each listing the others in `related_tasks`, each with a History entry naming the split.
Each part's title names its node: `<title> (<node title>)`, the form the migration's split uses.

**Repository records.** The first project reference is `<repository>:brain`; another /memory/
reference goes to the companion file (task_private.py), which is made only when there is such
content; a /memory/ path anywhere else in the rendered record (title, outcome, next action,
skill_refs, waiting_on, schedule, owner, ...) is refused before a number is claimed.

**References.** Every --project value is a /memory/ path inside a node that exists
(task_stores.node_of); a reference in no node is refused, because /memory/tasks/ holds only tasks
with no project reference (P10). A repository that is public, or whose visibility the
pointer does not record, is named once per run.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import task_stores
from task_git import ready_to_write
from task_history import brain_author, entry
from task_private import add_private
from task_records import (DATE_RE, FRONT_MATTER_RE, add_history, parse_front_matter, parse_id, set_fields,
                          slugify, write_atomic)
from task_write import refuse_memory_paths, regenerate, stamp

NEW_STATUSES = ("inbox", "ready", "in_progress", "waiting", "scheduled", "blocked")
CLAIMS = ".claims"
TEMPLATE = Path("templates") / "TASK_TEMPLATE.md"
SKELETON_TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "memory-skeleton" / "tasks" / TEMPLATE
PLACEHOLDER_OWNERS = {"", "OWNER_SHORT_NAME", "null"}
# Where a field the template lacks is written (front matter order of the task schema).
ANCHORS = {"author": "owner", "schedule": "waiting_on", "related_tasks": "depends_on"}
SCHEDULE_RE = re.compile(r"^[^|]*\S[^|]*\|[^|]*\S[^|]*\|[^|]*\S[^|]*$")
MSYS_HINT = ("Git Bash rewrites an argument that starts with / into a Windows path; "
             "run the command with MSYS_NO_PATHCONV=1 in front")


def looks_path_converted(value: str) -> bool:
    """True for a repository-root path that Git Bash (MSYS) has turned into a Windows path."""
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) and (
        bool(os.environ.get("MSYSTEM")) or bool(re.search(r"[\\/]Git[\\/]", value, re.I)))


def check_project_ref(value: str, root: Path | None) -> None:
    """A --project value must be a repository-root path /memory/... inside a node that exists."""
    if value.startswith("/memory/") and root is not None and task_stores.node_of(root, value) is not None:
        return
    if value.startswith("/memory/"):
        raise ValueError(f"--project {value} is in no node (a folder under /memory/ with a node README)")
    hint = f" ({MSYS_HINT})" if looks_path_converted(value) else ""
    raise ValueError(f"--project {value} is not a repository-root path starting with /memory/{hint}")


def schedule_job(schedule: str | None) -> str | None:
    """The job's name, the middle part of `<app> | <job> | <cadence>`."""
    if not schedule or not SCHEDULE_RE.match(schedule):
        return None
    return schedule.split("|")[1].strip()


def check_schedule(schedule: str | None) -> None:
    if schedule and not SCHEDULE_RE.match(schedule):
        raise ValueError(f"schedule {schedule!r} is not \"<app> | <job> | <cadence>\"")


# ---------------------------------------------------------------- identifiers


def _counts(task, author: str, own: str | None) -> bool:
    if task.get("author"):
        return task.get("author") == author
    return own == author and task.store is not None and task.store.kind != "repository"


def next_id(root: Path, author: str, year: int) -> str:
    try:
        own = brain_author(root)
    except ValueError:
        own = None
    highest = 0
    for task in task_stores.load_all(root):
        parsed = parse_id(task.tid)
        if not parsed or parsed[1] != year:
            continue
        if parsed[0] == author or (parsed[0] is None and _counts(task, author, own)):
            highest = max(highest, parsed[2])
    claims = root / "memory" / "tasks" / CLAIMS
    if claims.is_dir():
        for claim in claims.iterdir():
            parsed = parse_id(claim.name)
            if parsed and parsed[1] == year and (parsed[0] == author or (parsed[0] is None and own == author)):
                highest = max(highest, parsed[2])
    return f"TASK-{author}-{year}-{highest + 1:04d}"


def claim_id(root: Path, author: str, year: int) -> str:
    """Take the next number atomically: an exclusive create of a claim file, retried on a clash.

    Reading the highest number and then writing is a check-then-act race: concurrent sessions in
    one checkout took the same number before this existed. The claims folder is ignored by Git;
    a claim only has to outlive the moment between choosing and writing."""
    claims = root / "memory" / "tasks" / CLAIMS
    claims.mkdir(parents=True, exist_ok=True)
    ignore = claims / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    for _ in range(1000):
        tid = next_id(root, author, year)
        try:
            os.close(os.open(claims / tid, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return tid
        except FileExistsError:
            continue
    raise RuntimeError("could not claim a task number after 1000 attempts")


# ---------------------------------------------------------------- the record


def template_text(root: Path) -> str:
    for path in (root / "memory" / "tasks" / TEMPLATE, SKELETON_TEMPLATE):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise ValueError(f"no task template at {(root / 'memory' / 'tasks' / TEMPLATE).as_posix()}")


def render_new(template: str, fields: dict[str, Any], history: list[str]) -> str:
    """Fill the template: front matter in the schema's order, title, Outcome, Next action, History."""
    if not FRONT_MATTER_RE.match(template):
        raise ValueError("the task template has no front matter")
    meta = {k: v for k, v in fields.items() if not k.startswith("_")}
    text = set_fields(template, meta, after=ANCHORS)
    match = FRONT_MATTER_RE.match(text)
    head, body = text[:match.end()], text[match.end():]
    body = re.sub(r"^# .*$", lambda _: f"# {fields['title']}", body, count=1, flags=re.M)
    for heading, value in (("Outcome", fields.get("_outcome")), ("Next action", fields.get("_next_action"))):
        if not value:
            continue
        if re.search(rf"^## {heading}[ \t]*$", body, flags=re.M):
            body = re.sub(rf"^## {heading}[ \t]*\r?\n", lambda m: f"{m.group(0)}\n{value}\n", body, count=1, flags=re.M)
        elif re.search(r"^## History[ \t]*$", body, flags=re.M):
            body = re.sub(r"^## History", lambda m: f"## {heading}\n\n{value}\n\n{m.group(0)}", body, count=1, flags=re.M)
        else:
            body = body.rstrip("\n") + f"\n\n## {heading}\n\n{value}\n"
    text = head + body
    for line in history:
        text = add_history(text, line)
    return text


def _owner_default(root: Path, template_owner: str | None) -> str:
    if template_owner and template_owner not in PLACEHOLDER_OWNERS:
        return template_owner
    profile = root / "memory" / "OWNER.md"
    meta = parse_front_matter(profile.read_text(encoding="utf-8")) if profile.is_file() else None
    return str((meta or {}).get("owner_short_name") or "brain-owner")


def _groups(root: Path, projects: list[str], private: bool) -> list[tuple[Any, list[str]]]:
    """(store, its references) per store, in the order the projects were given."""
    if not projects:
        return [(task_stores.store_for(root, None, private), [])]
    groups: dict[str, tuple[Any, list[str]]] = {}
    for ref in projects:
        store = task_stores.store_for(root, ref, private)
        groups.setdefault(store.label, (store, []))[1].append(ref)
    return list(groups.values())


def _repository_refs(store, refs: list[str]) -> tuple[list[str], list[str]]:
    """(project_refs for the record, /memory/ references kept for the companion file).

    The pointer node itself becomes `<repository>:brain` and is not private content; only other
    /memory/ references go to the companion file."""
    kept = [r for r in refs if not r.startswith("/memory/")]
    private = [r for r in refs if r.startswith("/memory/") and r.rstrip("/") != store.node]
    return [f"{store.repository}:brain"] + kept, private


def create(root: Path, title: str, status: str = "inbox", priority: str = "normal",
           projects: list[str] | None = None, skills: list[str] | None = None, due: str | None = None,
           next_review: str | None = None, waiting_on: str | None = None, owner: str | None = None,
           slug: str | None = None, outcome: str | None = None, next_action: str | None = None,
           now: str | None = None, year: int | None = None, team: str | None = None,
           private: bool = False, schedule: str | None = None, offline: bool = False,
           update_state: bool = True) -> tuple[list[Path], list[str]]:
    """Write one task per project (one in total without a project). Returns the paths and what was said."""
    import task_claims  # the team label check lives with the claims
    if status not in NEW_STATUSES:
        raise ValueError(f"status {status} is not one of {', '.join(NEW_STATUSES)}")
    if team:
        team = task_claims.check_team(team)
    for key, value in (("due", due), ("next_review", next_review)):
        if value and not DATE_RE.match(value):
            raise ValueError(f"{key} {value} is not a date")
    if status in ("waiting", "scheduled") and not next_review:
        raise ValueError(f"a {status} task needs --next-review (CONTRACT §9.3)")
    if status == "waiting" and not waiting_on:
        raise ValueError("a waiting task needs --waiting-on")
    check_schedule(schedule)
    for ref in projects or []:
        check_project_ref(ref, root)
    author = brain_author(root)
    template = template_text(root)
    groups = _groups(root, list(projects or []), private)
    said: list[str] = []
    for store, _refs in groups:
        if store.kind != "repository":
            continue
        said += ready_to_write(store, offline=offline)
        if store.public is not False:
            said.append(f"{store.repository} is {'public' if store.public else 'of unrecorded visibility'}: "
                        f"what is written into {store.label} can be read by everyone who can read it")
    at, notes = stamp(root, now)
    said += notes
    template_owner = (parse_front_matter(template) or {}).get("owner")

    def render(n: int, ids: list[str]) -> tuple[str, list[str]]:
        store, refs = groups[n]
        tid, others = ids[n], [i for i in ids if i != ids[n]]
        project_refs, memory_refs = (_repository_refs(store, refs) if store.kind == "repository"
                                     else (list(refs), []))
        part = title if len(groups) == 1 else f"{title} ({task_stores.node_title(root, store.node)})"
        fields: dict[str, Any] = {
            "id": tid, "title": part, "status": status, "owner": owner or _owner_default(root, template_owner),
            "author": author, "priority": priority, "created": at, "updated": at, "due": due,
            "next_review": next_review, "waiting_on": waiting_on, "schedule": schedule,
            "project_refs": project_refs, "skill_refs": list(skills or []), "related_tasks": others,
            "_outcome": outcome, "_next_action": next_action,
        }
        if team:
            fields["team"] = team
        history = [entry(at, author, f"captured with `tasks.py new` ({status})")]
        if others:
            history.append(entry(at, author, "split: part of work for several projects ("
                                 + ", ".join(sorted(ids)) + ")"))
        return render_new(template, fields, history), memory_refs

    # The whole record is checked before a number is claimed or anything is written: a /memory/
    # path in any field (skill_refs, waiting_on, schedule, owner, ...) never reaches a repository.
    probe = [f"TASK-{author}-0000-{n:04d}" for n in range(len(groups))]
    for n, (store, _refs) in enumerate(groups):
        refuse_memory_paths(store, render(n, probe)[0], "the new task")
    ids = [claim_id(root, author, year or int(at[:4])) for _ in groups]
    paths: list[Path] = []
    for n, (store, _refs) in enumerate(groups):
        tid = ids[n]
        text, memory_refs = render(n, ids)
        folder = "inbox" if status == "inbox" else "open"
        path = store.path / folder / f"{tid}-{slug or slugify(title)}.md"
        write_atomic(path, text)
        paths.append(path)
        said.append(f"created {tid}: {path}")
        if memory_refs:
            companion = add_private(root, tid, store.label, author, at,
                                    "references kept out of the repository", memory_refs=memory_refs)
            said.append(f"private: {len(memory_refs)} /memory/ reference(s) kept in {companion}")
        if update_state:
            said += regenerate(store)
    return paths, said

