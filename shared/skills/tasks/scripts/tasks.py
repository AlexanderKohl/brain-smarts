"""Task stores of the brain (see /shared/skills/tasks/SKILL.md, CONTRACT §9).

Commands:
    review   tasks that need attention today, across every reachable store
    check    record and store checks of every store, or one (`--store LABEL`)
    next-id  the next free TASK-<author>-YYYY-NNNN number
    new      one task per project, each in its project's store (task_new.py), and its board
    done     complete a task: status, History, move to completed/
    do-now   ask for a task now: priority high, status ready (unless in progress), History
    note     a History entry; `--run JOB` records a scheduled run; `--private` writes the
             companion file in memory instead of the record
    edit     change allowed fields, with a History entry naming each `key: old -> new`
    claim    a team thread takes a card: in_progress, claimed_by and claimed_at (task_claims.py)
    release  the thread lets it go: claimed_by and claimed_at cleared, ready (task_claims.py)
    state    regenerate STATE.md of every store, or one
    migrate  the move of tasks into node and repository stores (task_migrate.py)

`--tasks` names the owner store (default /memory/tasks); the brain above it is searched for
every other store (task_stores.py). A task is found in whichever store holds it. Every change
names this brain's author in its History entry and sets `updated` to the same timestamp
(task_history.py); a repository store is fetched first and refused when it is behind, on another
branch or unmerged (task_git.py; `--offline` only after the owner agrees). Each store's STATE.md
is generated (task_state.py). Commits stay with the conductor; in a repository they follow that
repository's Git rules (CONTRACT §16.3). Standard library only.

`complete`, `do_now` and `add_note` are also the functions the owner board applies the owner's
saved task actions through, so a task changes one way only.

Git Bash on Windows rewrites an argument that starts with `/` into a Windows path, so
`--project /memory/...` would arrive as `C:/Program Files/Git/memory/...`. `new` refuses such a
value; run the command with `MSYS_NO_PATHCONV=1` in front.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import task_claims
import task_migrate
import task_stores
from task_check import REQUIRED, Report, check  # noqa: F401  (Report, REQUIRED: re-exported)
from task_git import WriteRefused
from task_history import author_name, brain_author, owner_now  # noqa: F401  (owner_now: re-exported)
from task_new import (NEW_STATUSES, MSYS_HINT, claim_id, create, looks_path_converted,  # noqa: F401
                      next_id, schedule_job)
from task_private import add_private
from task_records import (DATE_RE, FOLDER_STATUSES, ID_RE, Task, load_tasks, parse_front_matter,  # noqa: F401
                          parse_id)
from task_write import brain_root, change, decode_image, locate, regenerate, stamp  # noqa: F401
from state_table import review

DEFAULT_STORE = "/memory/tasks"
BOARD_SCRIPT = Path(__file__).resolve().parents[2] / "owner-board" / "scripts" / "task_board.py"  # a core sibling
EDITABLE = ("depends_on", "due", "next_review", "owner", "priority", "related_tasks", "schedule", "skill_refs",
            "status", "team", "waiting_on")
LIST_FIELDS = ("depends_on", "related_tasks", "skill_refs")
NOT_EDITABLE = {"id": "an identifier never changes", "author": "the author never changes",
                "created": "the creation time never changes",
                "project_refs": "a change of project is a change of store: `tasks.py migrate`"}


def resolve_store(store: str | None, cwd: Path) -> Path:
    candidate = store or DEFAULT_STORE
    path = Path(candidate)
    if path.is_absolute() and path.exists():
        return path
    root = brain_root(cwd) or brain_root(Path(__file__).resolve().parent)
    if candidate.startswith("/") and root is not None:
        return root / candidate.lstrip("/")
    return (cwd / candidate).resolve()


def find_task(store: Path, tid: str) -> Task:
    """A task in any store of the brain that holds this owner store."""
    return locate(store, tid)[1]


# ---------------------------------------------------------------- done, do-now, note, edit


def complete(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
             now: str | None = None, shot_stamp: str | None = None, offline: bool = False) -> tuple[Path, list[str]]:
    """Mark a task completed: status, a History entry with the note, the record moved to its
    store's completed/, a claim on it cleared, STATE.md regenerated."""
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}")
    fields = dict(task_claims.cleared(task), status="completed")
    path, said = change(root, task, fields, "done (completed)", note=note, shots=shots, shot_stamp=shot_stamp,
                        folder="completed", now=now, offline=offline)
    return path, [f"completed {tid}: {path}"] + said


def do_now(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
           now: str | None = None, shot_stamp: str | None = None, offline: bool = False) -> tuple[Path, list[str]]:
    """Ask for a task now: priority high; status ready unless already in progress (an inbox task
    moves to open/); a History entry with the note."""
    root, task = locate(store, tid)
    if task.folder == "completed":
        raise ValueError(f"{tid} is already {task.get('status') or 'completed'}; reopen it by hand")
    status = "in_progress" if task.get("status") == "in_progress" else "ready"
    fields: dict = {"priority": "high", "status": status}
    if status != "in_progress":
        fields.update(task_claims.cleared(task))   # a card that is not in progress is held by nobody
    folder = "recurring" if task.folder == "recurring" else "open"
    path, said = change(root, task, fields, f"asked for now (priority high, {status})", note=note, shots=shots,
                        shot_stamp=shot_stamp, folder=folder, now=now, offline=offline)
    return path, [f"do now {tid}: {path}"] + said


def add_note(store: Path, tid: str, note: str | None = None, shots: list[str] | None = None,
             now: str | None = None, shot_stamp: str | None = None, offline: bool = False,
             run: str | None = None, private: bool = False) -> tuple[Path, list[str]]:
    """A History entry with the note (and screenshots); `run` records the outcome of a scheduled
    run (P11); `private` appends to the companion file in memory and leaves the record alone."""
    root, task = locate(store, tid)
    text = (note or "").strip()
    if private:
        if not text:
            raise ValueError(f"{tid}: an empty private note")
        if task.store is None or task.store.kind != "repository":
            raise ValueError(f"{tid} is in memory, which is already private; add an ordinary note")
        at, said = stamp(root, now)
        path = add_private(root, tid, task.store.label, brain_author(root), at, "private note", lines=[text])
        return path, said + [f"private note on {tid}: {path} (the record is unchanged)"]
    if run:
        if not text:
            raise ValueError(f"{tid}: a run needs --note with its outcome")
        job = schedule_job(task.get("schedule"))
        path, said = change(root, task, {}, f"run of `{run}`: {text}", now=now, offline=offline)
        if job != run:
            said.append(f"warning: {tid} schedules {job or 'no job'}, not {run}")
        return path, [f"run of {run} on {tid}: {path}"] + said
    if not text and not any(decode_image(s) for s in shots or []):
        raise ValueError(f"{tid}: an empty note")
    path, said = change(root, task, {}, "note", note=note, shots=shots, shot_stamp=shot_stamp, now=now,
                        offline=offline)
    return path, [f"note on {tid}: {path}"] + said


def _edit_value(key: str, value: str):
    if key in LIST_FIELDS:
        return [v.strip() for v in value.split(",") if v.strip()]
    return None if value.strip() in ("", "null") else value.strip()


def edit(store: Path, tid: str, sets: list[str], why: str, now: str | None = None,
         offline: bool = False) -> tuple[Path, list[str]]:
    """Change allowed fields; the History entry lists each `key: old -> new` and the reason."""
    if not (why or "").strip():
        raise ValueError("edit needs --note with the reason")
    changes: dict = {}
    for item in sets:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep:
            raise ValueError(f"--set {item}: write key=value")
        if key in NOT_EDITABLE:
            raise ValueError(f"--set {key}: {NOT_EDITABLE[key]}")
        if key not in EDITABLE:
            raise ValueError(f"--set {key}: not an editable field ({', '.join(EDITABLE)})")
        changes[key] = _edit_value(key, value)
    root, task = locate(store, tid)
    if "status" in changes and changes["status"] not in FOLDER_STATUSES[task.folder]:
        raise ValueError(f"status {changes['status']} does not belong in {task.folder}/; use done, do-now or "
                         "claim to move a task between folders")
    for key in ("due", "next_review"):
        if changes.get(key) and not DATE_RE.match(changes[key]):
            raise ValueError(f"{key} {changes[key]} is not a date")
    if "schedule" in changes and changes["schedule"] and schedule_job(changes["schedule"]) is None:
        raise ValueError(f"schedule {changes['schedule']!r} is not \"<app> | <job> | <cadence>\"")
    if "team" in changes and changes["team"]:
        changes["team"] = task_claims.check_team(changes["team"])

    def shown(value) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(value) + "]"
        return "null" if value in (None, "") else str(value)

    what = "edit: " + "; ".join(f"{k}: {shown(task.meta.get(k))} -> {shown(v)}" for k, v in sorted(changes.items()))
    path, said = change(root, task, changes, what, note=why, now=now, offline=offline)
    return path, [f"edited {tid}: {path}"] + said


ACTIONS = {"done": complete, "do_now": do_now, "note": add_note}


def refresh_board(path: Path, store: Path) -> list[str]:
    """Regenerate the owner board that shows the task, when the owner board is set up.

    Runs the owner-board skill's own script, so the routing lives in one place. Without that
    skill, or without its configuration, the task still stands and this says what to run.
    """
    root = brain_root(store)
    if not BOARD_SCRIPT.is_file() or root is None:
        return ["board: the owner-board skill is not installed; nothing to refresh"]
    command = [sys.executable, str(BOARD_SCRIPT), "--root", str(root), "--no-fetch", "build", "--for", str(path)]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    if done.returncode == 0:
        return ["board: " + line for line in lines]
    return ["board: not refreshed (" + ("; ".join(lines) or f"exit {done.returncode}") + ")",
            f"board: after fixing it, run python {BOARD_SCRIPT.as_posix()} build --for {path.name}"]


# ---------------------------------------------------------------- CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", help="the owner store (repository-root or absolute; default /memory/tasks)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--offline", action="store_true",
                        help="write a repository store without fetching it; only after the owner agrees")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("review", help="tasks that need attention")
    r.add_argument("--today", help="YYYY-MM-DD, default the local date")
    r.add_argument("--horizon", type=int, default=7, help="days ahead for deadlines (default 7)")
    r.add_argument("--all", action="store_true", help="also tasks in repositories that other brains own")
    for name, text in (("check", "validate task records and stores"), ("state", "regenerate STATE.md")):
        s = sub.add_parser(name, help=text)
        s.add_argument("--store", metavar="LABEL", help="one store, as `check` names it")
    n = sub.add_parser("next-id", help="next free task number")
    n.add_argument("--year", type=int, help="default the current year")
    n.add_argument("--author", help="default this brain's author name")
    c = sub.add_parser("new", help="create one task per project and show it on its board")
    c.add_argument("--title", required=True, help="the outcome or next action, in the owner's words")
    c.add_argument("--status", default="inbox", choices=NEW_STATUSES, help="default inbox (captured, not yet processed)")
    c.add_argument("--priority", default="normal", help="default normal")
    c.add_argument("--project", action="append", default=[], metavar="NODE",
                   help="a project reference such as /memory/projects/<node>, repeatable: one task per project, "
                        "each in its node's store (Git Bash: put MSYS_NO_PATHCONV=1 in front)")
    c.add_argument("--private", action="store_true", help="a pointer node's private store instead of its repository")
    c.add_argument("--skill", action="append", default=[], metavar="SKILL", help="a skill_refs entry, repeatable")
    c.add_argument("--due", help="YYYY-MM-DD, only for a real deadline")
    c.add_argument("--next-review", help="YYYY-MM-DD; required for waiting and scheduled")
    c.add_argument("--waiting-on", help="who or what is expected to move it; required for waiting")
    c.add_argument("--schedule", help='"<app> | <job> | <cadence>" when an app or the system runs work for it')
    c.add_argument("--team", metavar="LABEL", help="the team thread that works the card: a short lowercase label")
    c.add_argument("--owner", help="default the template's owner, else owner_short_name in /memory/OWNER.md")
    c.add_argument("--slug", help="file name after the id; default from the title")
    c.add_argument("--outcome", help="text for the Outcome section")
    c.add_argument("--next-action", help="text for the Next action section")
    c.add_argument("--now", help="the creation timestamp, ISO 8601 with offset; default now")
    c.add_argument("--no-state", action="store_true", help="do not regenerate STATE.md")
    c.add_argument("--no-board", action="store_true", help="do not refresh the owner board")
    for name, text in (("done", "complete a task and move it to completed/"),
                       ("do-now", "ask for a task now: priority high, status ready unless in progress"),
                       ("note", "add a note to a task's History"),
                       ("edit", "change allowed fields, with the reason"),
                       ("claim", "a team thread takes a card: in_progress, claimed_by, claimed_at"),
                       ("release", "the thread lets a card go: claim cleared, status ready")):
        a = sub.add_parser(name, help=text)
        a.add_argument("task", help="the task id")
        a.add_argument("--note", required=name in ("note", "edit"), help="kept verbatim in History")
        a.add_argument("--now", help="the timestamp, ISO 8601 with offset; default now")
        a.add_argument("--no-board", action="store_true", help="do not refresh the owner board")
        if name == "note":
            a.add_argument("--run", metavar="JOB", help="record the outcome of a run of this scheduled job")
            a.add_argument("--private", action="store_true", help="the companion file in memory, not the record")
        if name == "edit":
            a.add_argument("--set", action="append", default=[], required=True, metavar="KEY=VALUE",
                           help="repeatable; list fields take comma-separated values")
        if name == "claim":
            a.add_argument("--by", required=True, metavar="SESSION NAME", help="the session taking the card")
            a.add_argument("--team", metavar="LABEL", help="also set the card's team: a short lowercase label")
    task_migrate.add_parser(sub)
    return parser


def _say(args, paths: list[Path], said: list[str]) -> None:
    if args.json:
        print(json.dumps({"path": paths[0].as_posix() if paths else None, "paths": [p.as_posix() for p in paths],
                          "notes": said}, indent=2))
    else:
        print("\n".join(said))


def _review(args, root: Path) -> int:
    today = date.fromisoformat(args.today) if args.today else date.today()
    own = brain_author(root) if not args.all else None
    tasks = [t for t in task_stores.load_all(root)
             if args.all or t.store.kind != "repository" or author_name(t.get("owner") or "") == own]
    rows = review(tasks, today, args.horizon)
    missing = task_stores.unreachable(root)
    if args.json:
        print(json.dumps(rows, indent=2))
        for store in missing:      # stderr, so the JSON on stdout keeps one shape
            print(f"Not read: {store.label} ({store.reason})", file=sys.stderr)
        return 0
    print(f"Task review {today.isoformat()} (deadlines within {args.horizon} days)\n")
    print("| Task | Status | Priority | Why | Waiting on | Title | Store |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        cells = [row["id"], row["status"], row["priority"], "; ".join(row["reasons"]),
                 row["waiting_on"] or "-", row["title"], row["store"]]
        print("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")
    print(f"\n{len(rows)} task(s) need attention")
    for store in missing:
        print(f"Not read: {store.label} ({store.reason})")
    return 0


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    store = resolve_store(args.tasks, cwd or Path.cwd())
    root = brain_root(store) if store.exists() else None
    if not store.is_dir() or root is None:
        hint = f" ({MSYS_HINT})" if args.tasks and looks_path_converted(args.tasks) else ""
        print(f"ERROR: task store not found: {store}{hint}")
        return 2
    try:
        return _run(args, store, root)
    except (LookupError, ValueError, WriteRefused, OSError) as err:
        print(f"ERROR: {str(err).strip(chr(39))}")
        return 1


def _run(args, store: Path, root: Path) -> int:
    if args.command == "review":
        return _review(args, root)
    if args.command == "migrate":
        return task_migrate.run(args, root)
    if args.command == "new":
        paths, said = create(root, args.title, status=args.status, priority=args.priority, projects=args.project,
                             skills=args.skill, due=args.due, next_review=args.next_review,
                             waiting_on=args.waiting_on, owner=args.owner, slug=args.slug, outcome=args.outcome,
                             next_action=args.next_action, now=args.now, update_state=not args.no_state,
                             team=args.team, private=args.private, schedule=args.schedule, offline=args.offline)
        if not args.no_board:
            for path in paths:
                said += refresh_board(path, store)
        _say(args, paths, said)
        return 0
    if args.command in ("done", "do-now", "note", "edit", "claim", "release"):
        common = {"now": args.now, "offline": args.offline}
        if args.command == "claim":
            path, said = task_claims.claim(store, args.task, args.by, team=args.team, note=args.note, **common)
        elif args.command == "release":
            path, said = task_claims.release(store, args.task, note=args.note, **common)
        elif args.command == "edit":
            path, said = edit(store, args.task, args.set, args.note, **common)
        elif args.command == "note":
            path, said = add_note(store, args.task, note=args.note, run=args.run, private=args.private, **common)
        else:
            path, said = ACTIONS[args.command.replace("-", "_")](store, args.task, note=args.note, **common)
        if not args.no_board and not (args.command == "note" and args.private):
            said += refresh_board(path, store)
        _say(args, [path], said)
        return 0
    if args.command == "state":
        chosen = [task_stores.store_by_label(root, args.store)] if args.store else task_stores.stores(root)
        said = []
        for each in chosen:
            if each.reachable and each.path.is_dir():
                said += regenerate(each) or [f"STATE.md: {each.label} already matches its records"]
            elif not each.reachable:
                said.append(f"STATE.md: {each.label} not read ({each.reason})")
        _say(args, [], said)
        return 0
    if args.command == "check":
        report = check(root, args.store)
        if args.json:
            print(json.dumps({"errors": report.errors, "warnings": report.warnings}, indent=2))
        else:
            for line in report.errors:
                print(f"ERROR: {line}")
            for line in report.warnings:
                print(f"WARN: {line}")
            print(f"{'FAIL' if report.errors else 'PASS'}: {len(report.errors)} error(s), "
                  f"{len(report.warnings)} warning(s)")
        return 1 if report.errors else 0
    author = args.author or brain_author(root)
    print(next_id(root, author, args.year or date.today().year))
    return 0


if __name__ == "__main__":
    sys.exit(main())
