"""`tasks.py migrate`: tasks move from /memory/tasks/ into node and repository stores (plan 5).

    migrate --split --dry-run              every open task naming several nodes, with its parts
    migrate --split --list FILE            make the cleared splits, in place in their store
    migrate --node NODE [--dry-run]        a memory node's tasks into NODE/tasks/ (nothing leaves memory)
    migrate --owner-store [--dry-run]      `author` and an attributed entry on the tasks with no project
    migrate --repo REPOSITORY --dry-run    the move list (owner store and pointer-private store), lines flagged
    migrate --repo REPOSITORY --list FILE  move what the owner cleared: move, private or hold
    migrate --decide FILE --all move --private 3,9 --hold 12 --private-lines 15:2,4
    migrate --reverse LEDGER               move a node or repository move back

Each move keeps the identifier and the file name, adds `author` when the record has none, and
adds an attributed History entry naming the proposal, through apply_change. A move writes the
target before removing the source, regenerates both STATE.md files and writes a ledger
`/memory/tasks/migrations/<stamp>-<target>.json` that `--reverse` reads. A repository move first
checks the store may be written (task_git); a record bound for a repository loses its /memory/
references and the lines the owner marked private to the companion file, and any /memory/ path
still left refuses the whole move before anything is written. Commits stay with the conductor:
memory and each repository separately.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import task_private
import task_stores
from task_git import conflicted, ready_to_write
from task_history import apply_change, brain_author
from task_migrate_lists import decide, file_hash, load_cleared, sort_items, write_list
from task_new import ANCHORS, claim_id
from task_private import MEMORY_PATH, add_private, flags
from task_records import FRONT_MATTER_RE, id_sort_key, load_tasks, move_record, set_fields, slugify, write_atomic
from task_write import regenerate, stamp

PROPOSAL = "PROPOSAL-shared-project-tasks-in-the-repository"
LIST_FIELDS = ("depends_on", "related_tasks", "skill_refs")
# Front-matter values a repository's readers see, flagged on the move list like body lines.
FLAGGED_FIELDS = ("claimed_by", "depends_on", "schedule", "skill_refs", "team", "title", "waiting_on")


def add_parser(sub) -> None:
    m = sub.add_parser("migrate", help="move tasks into node and repository stores")
    what = m.add_mutually_exclusive_group(required=True)
    what.add_argument("--split", action="store_true", help="split open tasks that name several nodes")
    what.add_argument("--node", help="a memory node, /memory/...")
    what.add_argument("--owner-store", action="store_true", help="author and an entry on tasks with no project")
    what.add_argument("--repo", metavar="REPOSITORY", help="the repository's name, as the pointer's repo_url ends")
    what.add_argument("--decide", metavar="FILE", help="record the owner's answers in a dry run's list")
    what.add_argument("--reverse", metavar="LEDGER", help="move a recorded move back")
    m.add_argument("--dry-run", action="store_true", help="write the list, move nothing")
    m.add_argument("--list", metavar="FILE", help="the cleared list a move follows")
    m.add_argument("--all", choices=("hold", "move"), help="with --decide: every item")
    m.add_argument("--move", metavar="N,N", help="with --decide: these items move")
    m.add_argument("--private", metavar="N,N", help="with --decide: these go to the pointer node's private store")
    m.add_argument("--hold", metavar="N,N", help="with --decide: these stay where they are")
    m.add_argument("--private-lines", action="append", metavar="N:L,L", help="with --decide: lines to the companion file")
    m.add_argument("--now", help="the timestamp, ISO 8601 with offset; default now")


def _show(root: Path, path: Path) -> str:
    try:
        return "/" + path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _resolve(root: Path, shown: str) -> Path:
    """A path as `_show` wrote it. `/memory/...` and other paths whose first folder is one of the
    brain root's are root-relative on every system (on Linux and macOS they also look absolute);
    anything else, such as a checkout outside the brain, is taken as it stands."""
    first = shown.lstrip("/").split("/", 1)[0]
    if shown.startswith("/") and first and (root / first).is_dir():
        return root / shown.lstrip("/")
    return Path(shown)


def _memory_records(root: Path) -> list:
    return [t for t in task_stores.load_all(root) if t.store.kind != "repository"]


def _body(text: str) -> tuple[str, str]:
    match = FRONT_MATTER_RE.match(text)
    return (text[:match.end()], text[match.end():]) if match else ("", text)


def _moved(text: str, what: str, author: str, at: str, fields: dict | None = None, has_author: bool = False) -> str:
    fields = dict(fields or {})
    if not has_author:
        fields["author"] = author
    return apply_change(text, fields, what, author, at, after=ANCHORS)


def _refuse_broken(tasks: list, verb: str = "moved") -> None:
    """Refuse the whole step when any record it would move or rewrite cannot be read or carries a
    Git conflict marker, before anything is written (as --reverse does)."""
    broken = [t.path.as_posix() for t in tasks
              if t.problem or conflicted(t.path.read_text(encoding="utf-8"))]
    if broken:
        raise ValueError(f"{', '.join(broken)}: a Git conflict marker or an unreadable record; resolve it by "
                         f"hand first; nothing was {verb}")


def _ledger(root: Path, at: str, kind: str, target: str, moves: list[dict]) -> Path:
    digits = re.sub(r"[^0-9]", "", at)[:14]
    path = root / "memory" / "tasks" / "migrations" / f"{digits}-{slugify(kind + '-' + target)}.json"
    write_atomic(path, json.dumps({"kind": kind, "target": target, "at": at, "moves": moves}, indent=2) + "\n")
    return path


# ---------------------------------------------------------------- split


def _groups(root: Path, refs: list[str]) -> list[tuple[str | None, list[str]]]:
    groups: dict[str | None, list[str]] = {}
    for ref in refs:
        groups.setdefault(task_stores.node_of(root, ref), []).append(ref)
    return list(groups.items())


def split_items(root: Path) -> list[dict]:
    items = []
    for task in _memory_records(root):
        nodes = [(n, refs) for n, refs in _groups(root, task.refs()) if n]
        if task.folder == "completed" or len(nodes) < 2:
            continue
        title = task.get("title") or task.tid
        parts = [{"node": n, "title": f"{title} ({task_stores.node_title(root, n)})", "refs": refs}
                 for n, refs in nodes[1:]]
        items.append({"id": task.tid, "title": title, "folder": task.folder, "path": _show(root, task.path),
                      "sha256": file_hash(task.path), "parts": parts, "keeps": nodes[0][0]})
    return sort_items(items, id_sort_key)


def _outcome_part(body: str, tid: str, node: str) -> str:
    """The body with its Outcome prefixed "The part of `<id>` for `<node>`."."""
    prefix = f"The part of `{tid}` for `{node}`."
    found = re.search(r"^## Outcome[ \t]*\r?\n", body, flags=re.M)
    if not found:
        return f"\n## Outcome\n\n{prefix}\n" + body
    rest = body[found.end():]
    following = re.search(r"^## ", rest, flags=re.M)
    section = rest[:following.start()] if following else rest
    text = section.strip()
    return body[:found.end()] + f"\n{prefix}" + (f" {text}" if text else "") + "\n\n" + rest[len(section):]


def apply_split(root: Path, listing: dict, now: str | None) -> list[str]:
    author = brain_author(root)
    at, said = stamp(root, now)
    moves = []
    chosen = {item["id"]: task_stores.find(root, item["id"]) for item in listing["items"] if item["decision"] == "move"}
    _refuse_broken(list(chosen.values()), "split")
    for item in listing["items"]:
        if item["decision"] != "move":
            said.append(f"held {item['id']}")
            continue
        task = chosen[item["id"]]
        text = task.path.read_text(encoding="utf-8")
        ids = [claim_id(root, author, int(at[:4])) for _ in item["parts"]]
        keep = [r for n, refs in _groups(root, task.refs()) if n in (None, item["keeps"]) for r in refs]
        what = "split: part of work for several projects (" + ", ".join(sorted([task.tid] + ids)) + ")"
        head, body = _body(text)
        for tid, part in zip(ids, item["parts"]):
            others = [i for i in [task.tid] + ids if i != tid]
            fields = {"id": tid, "title": part["title"], "project_refs": part["refs"], "related_tasks": others,
                      "created": at, "author": author, "claimed_by": None, "claimed_at": None}
            part_body = re.sub(r"^# .*$", lambda _: f"# {part['title']}", _outcome_part(body, task.tid, part["node"]),
                               count=1, flags=re.M)
            # The part keeps every History entry of the record it came from (CONTRACT §9.3 item 10).
            part_text = apply_change(set_fields(head + part_body, fields, after=ANCHORS), {}, what, author, at)
            path = task.store.path / task.folder / f"{tid}-{slugify(part['title'])}.md"
            write_atomic(path, part_text)
            said.append(f"created {tid}: {_show(root, path)}")
        fields = {"project_refs": keep, "related_tasks": ids}
        write_atomic(task.path, _moved(text, what, author, at, fields, bool(task.get("author"))))
        said.append(f"split {task.tid}: kept for {item['keeps']}, parts {', '.join(ids)}")
        moves.append({"id": task.tid, "parts": ids})
        said += regenerate(task.store)
    if moves:
        said.append(f"ledger: {_show(root, _ledger(root, at, 'split', 'all', moves))}")
    return said


# ---------------------------------------------------------------- node and owner store


def node_items(root: Path, node: str) -> list:
    owner = task_stores.owner_store(root)
    return [t for t in load_tasks(owner.path, owner=owner)
            if t.refs() and task_stores.node_of(root, t.refs()[0]) == node]


def repo_records(root: Path, node: str) -> list:
    """What a repository move considers: the pointer node's tasks in the owner store, then the
    records already in its private store, so a "private" decision can still be moved later."""
    private = task_stores.store_for(root, node, private=True)
    return node_items(root, node) + load_tasks(private.path, owner=private)


def _move(root: Path, task, target_store, what: str, author: str, at: str, fields: dict | None = None,
          text: str | None = None) -> Path:
    source = task.path
    body = _moved(text if text is not None else source.read_text(encoding="utf-8"), what, author, at, fields,
                  bool(task.get("author")))
    return move_record(source, target_store.path / task.folder / source.name, body)


def migrate_node(root: Path, node: str, dry_run: bool, now: str | None) -> list[str]:
    store = task_stores.store_for(root, node)
    if store.kind != "memory-node" or store.node != node:
        raise ValueError(f"{node} is not a memory node (a pointer moves with --repo; a deeper node by its own path)")
    tasks = sorted(node_items(root, node), key=lambda t: id_sort_key(t.tid))
    if dry_run:
        items = [{"id": t.tid, "title": t.get("title") or t.tid, "folder": t.folder, "path": _show(root, t.path),
                  "sha256": file_hash(t.path)} for t in tasks]
        md, _ = write_list(root, "node", node, sort_items(items, id_sort_key))
        return [f"{len(items)} task(s) would move into {store.label}: {_show(root, md)}"]
    _refuse_broken(tasks)
    author = brain_author(root)
    at, said = stamp(root, now)
    moves = []
    for task in tasks:
        path = _move(root, task, store, f"moved into the node's tasks/ ({PROPOSAL})", author, at)
        moves.append({"id": task.tid, "from": _show(root, task.path), "to": _show(root, path)})
        said.append(f"moved {task.tid}: {_show(root, path)}")
    if moves:
        said += regenerate(task_stores.owner_store(root)) + regenerate(store)
        said.append(f"ledger: {_show(root, _ledger(root, at, 'node', node, moves))}")
    else:
        said.append(f"nothing to move into {store.label}")
    return said


def migrate_owner_store(root: Path, dry_run: bool, now: str | None) -> list[str]:
    owner = task_stores.owner_store(root)
    tasks = [t for t in load_tasks(owner.path, owner=owner)
             if not t.get("author") and not any(task_stores.node_of(root, r) for r in t.refs())]
    if dry_run:
        return [f"{len(tasks)} task(s) with no project would gain author and an attributed entry"]
    _refuse_broken(tasks, "changed")
    author = brain_author(root)
    at, said = stamp(root, now)
    for task in tasks:
        write_atomic(task.path, _moved(task.path.read_text(encoding="utf-8"),
                                       f"author recorded ({PROPOSAL})", author, at))
    return said + [f"{len(tasks)} task(s) in {owner.label} now name their author"] + (regenerate(owner) if tasks else [])


# ---------------------------------------------------------------- repository


def _pointer_nodes(root: Path, repository: str) -> list[str]:
    nodes = [p.node for p in task_stores.pointers(root) if p.repository.lower() == repository.lower()]
    if not nodes:
        raise ValueError(f"no pointer node names the repository {repository}")
    if len(nodes) > 1:
        raise ValueError(f"{', '.join(nodes)} all point at {repository}; one pointer per repository first")
    return nodes


def repo_items(root: Path, repository: str) -> tuple[list, list[dict]]:
    node = _pointer_nodes(root, repository)[0]
    try:
        terms = task_private._personal_data().owner_terms(root)
    except ImportError:
        terms = []
    tasks, items = [], []
    for task in repo_records(root, node):
        text = task.path.read_text(encoding="utf-8")
        _, body = _body(text)
        found = [{"line": n, "text": line.strip(), "flags": flags(line, root, terms)}
                 for n, line in enumerate(body.splitlines(), 1) if line.strip()]
        notes = []
        if MEMORY_PATH.search(task.get("title") or ""):
            notes.append("the title names /memory/: edit the record before it can move")
        refs = [r for key in LIST_FIELDS for r in task.refs(key) if r.startswith("/memory/")]
        refs += [r for r in task.refs()[1:] if r.startswith("/memory/")]
        if refs:
            notes.append(f"{len(refs)} /memory/ reference(s) go to the companion file")
        for key in FLAGGED_FIELDS:
            value = " ".join(task.refs(key))
            marked = flags(value, root, terms) if value else []
            if marked:
                notes.append(f"front matter {key}: {', '.join(marked)} (edit the record, or keep it private)")
        tasks.append(task)
        items.append({"id": task.tid, "title": task.get("title") or task.tid, "folder": task.folder,
                      "path": _show(root, task.path), "sha256": file_hash(task.path), "notes": notes,
                      "flags": [f for f in found if f["flags"]]})
    return tasks, sort_items(items, id_sort_key)


def _for_repository(task, store, private_lines: list[int]) -> tuple[str, list[str], list[str], dict]:
    """(record text without private lines and /memory/ references, those lines, those references,
    the fields as they were, for --reverse)."""
    text = task.path.read_text(encoding="utf-8")
    head, body = _body(text)
    lines = body.splitlines()
    kept = [line for n, line in enumerate(lines, 1) if n not in private_lines]
    private = [line for n, line in enumerate(lines, 1) if n in private_lines]
    refs = task.refs()
    original = {"project_refs": refs}
    memory_refs = [r for r in refs if r.startswith("/memory/") and r.rstrip("/") != store.node]
    fields: dict = {"project_refs": [f"{store.repository}:brain"] + [r for r in refs if not r.startswith("/memory/")]}
    for key in LIST_FIELDS:
        values = task.refs(key)
        if any(v.startswith("/memory/") for v in values):
            original[key] = values
            memory_refs += [v for v in values if v.startswith("/memory/")]
            fields[key] = [v for v in values if not v.startswith("/memory/")]
    out = set_fields(head + "\n".join(kept) + ("\n" if body.endswith("\n") else ""), fields)
    return out, private, list(dict.fromkeys(memory_refs)), original


def apply_repo(root: Path, repository: str, listing: dict, now: str | None, offline: bool) -> list[str]:
    node = _pointer_nodes(root, repository)[0]
    repo = task_stores.store_for(root, node)
    private_store = task_stores.store_for(root, node, private=True)
    author = brain_author(root)
    at, said = stamp(root, now)
    by_id = {t.tid: t for t in repo_records(root, node)}
    _refuse_broken([by_id[i["id"]] for i in listing["items"] if i["decision"] in ("move", "private")])
    planned = []
    for item in listing["items"]:
        task = by_id[item["id"]]
        if item["decision"] != "move":
            planned.append((item, task, None))
            continue
        text, lines, refs, original = _for_repository(task, repo, item.get("private_lines", []))
        probe = apply_change(text, {}, f"moved into {repo.label} ({PROPOSAL})", author, at)
        if MEMORY_PATH.search(probe):
            bad = [n for n, line in enumerate(_body(task.path.read_text(encoding="utf-8"))[1].splitlines(), 1)
                   if MEMORY_PATH.search(line) and n not in item.get("private_lines", [])]
            raise ValueError(f"item {item['n']} ({task.tid}) still names /memory/ (lines {', '.join(map(str, bad)) or 'in its front matter'}); "
                             f"mark them with --private-lines {item['n']}:{','.join(map(str, bad))}, or hold it; nothing was moved")
        planned.append((item, task, (text, lines, refs, original)))
    if any(p[2] is not None for p in planned):     # before any write into the repository
        said += ready_to_write(repo, offline=offline)
    moves = []
    for item, task, prepared in planned:
        if item["decision"] == "hold":
            said.append(f"held {task.tid}")
            continue
        if item["decision"] == "private":
            if task.store is not None and task.store.kind == "pointer-private":
                said.append(f"already private {task.tid}")       # already there: nothing to move
                continue
            path = _move(root, task, private_store, f"moved into the pointer node's private tasks/ ({PROPOSAL})",
                         author, at)
            moves.append({"id": task.tid, "from": _show(root, task.path), "to": _show(root, path), "store": "private"})
            said.append(f"kept private {task.tid}: {_show(root, path)}")
            continue
        text, lines, refs, original = prepared
        path = _move(root, task, repo, f"moved into {repo.label} ({PROPOSAL})", author, at, text=text)
        companion = None
        if lines or refs:
            companion = _show(root, add_private(root, task.tid, repo.label, author, at,
                                                f"kept out of {repo.label} when it moved ({PROPOSAL})",
                                                lines=lines, memory_refs=refs))
        moves.append({"id": task.tid, "from": _show(root, task.path), "to": _show(root, path), "store": "repository",
                      "restore": original, "private_lines": lines, "companion": companion})
        said.append(f"moved {task.tid}: {repo.label}/{task.folder}/{path.name}")
    kinds = {m["store"] for m in moves}
    if moves:
        said += regenerate(task_stores.owner_store(root))
    if "repository" in kinds:
        said += regenerate(repo)
    left_private = any(item["decision"] == "move" and task.store is not None and task.store.kind == "pointer-private"
                       for item, task, _ in planned)
    if "private" in kinds or left_private:
        said += regenerate(private_store)
    if moves:
        said.append(f"ledger: {_show(root, _ledger(root, at, 'repository', repository, moves))}")
    return said


# ---------------------------------------------------------------- reverse


def reverse(root: Path, ledger_path: Path, now: str | None, offline: bool) -> list[str]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger["kind"] == "split":
        raise ValueError("a split is not joined again: its parts stay separate tasks, each naming the others")
    author = brain_author(root)
    at, said = stamp(root, now)
    owner = task_stores.owner_store(root)
    touched = {owner.label: owner}
    found = []
    for move in ledger["moves"]:
        try:
            found.append((move, task_stores.find(root, move["id"])))
        except LookupError as err:
            said.append(f"not moved back: {err}")
    # Every record and every repository store is checked before any record moves, so a refusal
    # leaves the move whole rather than half reversed.
    _refuse_broken([task for _move, task in found], "moved back")
    for store in {t.store.label: t.store for _m, t in found if t.store.kind == "repository"}.values():
        said += ready_to_write(store, offline=offline)
    for move, task in found:
        touched[task.store.label] = task.store
        text = task.path.read_text(encoding="utf-8")
        fields = dict(move.get("restore") or {})
        if move.get("private_lines"):
            restored = "\n".join(move["private_lines"])
            text = re.sub(r"^## History[ \t]*$", lambda m: f"## Private notes (restored)\n\n{restored}\n\n{m.group(0)}",
                          text, count=1, flags=re.M)
        source = _resolve(root, move["from"])
        target = source.parent.parent / task.folder / source.name
        body = apply_change(text, fields, f"moved back to {_show(root, target.parent.parent)} (migrate --reverse)",
                            author, at)
        move_record(task.path, target, body)
        said.append(f"moved back {task.tid}: {_show(root, target)}"
                    + (f" (its companion file {move['companion']} stays)" if move.get("companion") else ""))
    if found:
        for store in touched.values():
            if store.path.is_dir():
                said += regenerate(store)
    if ledger["kind"] == "repository":
        repo = next((s for s in task_stores.stores(root) if s.kind == "repository"
                     and s.repository.lower() == ledger["target"].lower()), None)
        if repo is not None and repo.reachable:
            others = [t.tid for t in load_tasks(repo.path) if t.get("author") and t.get("author") != author]
            if others:
                said.append(f"left in {repo.label}, created by other brains: {', '.join(sorted(others, key=id_sort_key))}")
    return said


# ---------------------------------------------------------------- CLI


def run(args, root: Path) -> int:
    if args.decide:
        said = decide(Path(args.decide), all_=args.all, move=args.move, private=args.private, hold=args.hold,
                      private_lines=args.private_lines)
    elif args.reverse:
        said = reverse(root, Path(args.reverse), args.now, args.offline)
    elif args.node:
        said = migrate_node(root, args.node, args.dry_run, args.now)
    elif args.owner_store:
        said = migrate_owner_store(root, args.dry_run, args.now)
    elif args.split:
        items = split_items(root)
        if args.dry_run:
            md, _ = write_list(root, "split", "all", items)
            said = [f"{len(items)} task(s) would be split: {_show(root, md)}"]
        elif not args.list:
            raise ValueError("a split follows a cleared list: run --dry-run, record the answers with --decide, "
                             "then --list FILE")
        else:
            said = apply_split(root, load_cleared(Path(args.list), "split", "all", items), args.now)
    else:
        _, items = repo_items(root, args.repo)
        if args.dry_run:
            md, _ = write_list(root, "repository", args.repo, items)
            said = [f"{len(items)} task(s) on the list for {args.repo}: {_show(root, md)}"]
        elif not args.list:
            raise ValueError("a repository move follows a cleared list: run --dry-run, record the answers with "
                             "--decide, then --list FILE")
        else:
            said = apply_repo(root, args.repo, load_cleared(Path(args.list), "repository", args.repo, items),
                              args.now, args.offline)
    print(json.dumps({"notes": said}, indent=2) if getattr(args, "json", False) else "\n".join(said))
    return 0
