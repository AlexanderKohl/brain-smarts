"""`ingest_raw.py migrate`: sources move out of /memory/sources/ into the store of the node they
belong to (CONTRACT §11.1, P13; build plan section 5, step S).

    migrate --node NODE --dry-run          the list for NODE: every record whose project_refs name
                                           that node only, flagged for a repository
    migrate --node NODE [--list FILE]      move them; a memory node needs no list, a pointer node
                                           moves only what the owner cleared on its list
    migrate --decide FILE --all move --private 3,9 --hold 12
    migrate --reverse LEDGER               move a recorded move back

The list protocol is the tasks skill's (`task_migrate_lists`, one for tasks and sources): a dry
run writes `/temp/migration/sources-<node>.md` and `.json`, the owner answers in the conversation,
`--decide` records it, and a move follows `--list FILE`, refused when the records changed since
(the fingerprint) or any item has no decision. Silence moves nothing. A source moves whole: its
raw file cannot be edited, so `--private-lines` does not apply; a source with something private
is marked private (the pointer node's own raw/ and sources/) or held.

A move of one source: its raw folder `<store>/raw/YYYY/MM/<source-id>/` is copied unchanged and
the copy's SHA-256 checked against the record's `raw_sha256` before the original is removed; the
record (and a derivative reconvert.py wrote beside it) goes to the `sources/` beside that raw
store, its paths rewritten to the store's own form, `updated` set and, in a repository,
`project_refs` led by `<repository>:brain` with no /memory/ reference left, and its manifest
without `original_path` or any other machine path (raw_stores.repository_manifest). A reference
to the record in the target node's `sources/` is replaced by the record itself; one in a pointer
node whose source moves into the repository is removed (P17). Then every reference to the old
paths is rewritten: across memory (`<repository>:brain/...` for a repository, CONTRACT §16.2) and
in the repository's `brain/`. Raw stores, `LOG.md` files and migration ledgers are history and are
never rewritten; a task record changed this way gets an attributed History entry (P23) and its
store's STATE.md is generated again. A file to rewrite that carries a Git conflict marker refuses
the move. The dry run flags a repository-bound source as a new one is flagged
(raw_stores.source_flags). Everything is checked before the first write. The ledger `/memory/systems/raw-file-management/migrations/
<stamp>-sources-<node>.json` is what `--reverse` reads. Commits stay with the conductor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import raw_stores  # noqa: E402  (puts the tasks skill's scripts on sys.path)
import task_stores  # noqa: E402
from ingest_raw import append_log, find_root, memory_root, resolve_node, root_path, sha256_file  # noqa: E402
from raw_stores import MEMORY_PATH, RawStore  # noqa: E402
from task_git import WriteRefused, conflicted, ready_to_write  # noqa: E402
from task_history import apply_change, brain_author  # noqa: E402
from task_migrate_lists import decide, load_cleared, write_list  # noqa: E402
from task_records import FRONT_MATTER_RE, parse_front_matter, set_fields, slugify, write_atomic  # noqa: E402
from task_write import regenerate, stamp  # noqa: E402

PROPOSAL = "PROPOSAL-shared-project-tasks-in-the-repository"
KIND = "sources"
SUFFIXES = frozenset({".md", ".json", ".txt", ".yaml", ".yml"})
NEVER_REWRITE_DIRS = frozenset({".git", "raw", "migrations", "node_modules", "img"})
NEVER_REWRITE_FILES = frozenset({"LOG.md"})


class Refused(Exception):
    """A migration that must not run as asked; nothing was written."""


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read(path: Path) -> str:
    """A file's text exactly as it is, line ends included."""
    return path.read_bytes().decode("utf-8")


def edit(text: str, change) -> str:
    """`change` applied to the text with LF line ends; a CRLF file keeps CRLF."""
    crlf = "\r\n" in text
    out = change(text.replace("\r\n", "\n"))
    return out.replace("\n", "\r\n") if crlf else out


def substitute(text: str, pairs: list[list[str]]) -> str:
    for old, new in pairs:
        text = re.sub(re.escape(old) + r"(?![\w.-])", lambda _m, new=new: new, text)
    return text


# ---------------------------------------------------------------- what moves


def _source(root: Path, record: Path) -> Optional[dict]:
    text = read(record)
    meta = parse_front_matter(text) or {}
    if meta.get("type") != "source_document":
        return None
    refs = meta.get("project_refs") or []
    refs = [refs] if isinstance(refs, str) else list(refs)
    raw_ref = str(meta.get("raw_source") or "")
    problems = ["it has a Git conflict marker: resolve it by hand first"] if conflicted(text) else []
    raw_root = (memory_root(root) / "raw").resolve()
    raw_file = (root / raw_ref.lstrip("/")).resolve() if raw_ref else raw_root
    raw_ok = raw_ref.startswith("/memory/raw/") and raw_file.parent.is_relative_to(raw_root) \
        and raw_file.parent != raw_root
    if not raw_ok:
        problems.append(f"its raw file {raw_ref or '(none)'} is not in a /memory/raw/ folder of its own")
    elif not raw_file.is_file():
        problems.append(f"its raw file {raw_ref} is missing")
    elif sha256_file(raw_file) != meta.get("raw_sha256"):
        problems.append(f"its raw file {raw_ref} no longer matches raw_sha256")
    derivative = record.with_name(f"{meta.get('id', record.stem)}.reconverted.md")
    return {"id": str(meta.get("id") or record.stem), "title": str(meta.get("title") or record.stem),
            "record": record, "text": text, "refs": refs, "raw_ref": raw_ref, "raw_file": raw_file,
            "raw_folder": raw_file.parent, "sha": str(meta.get("raw_sha256") or ""),
            "derivative": derivative if derivative.is_file() else None, "problems": problems,
            "raw_ok": raw_ok, "size": raw_file.stat().st_size if raw_ok and raw_file.is_file() else 0,
            "filename": str(meta.get("source_filename") or raw_file.name),
            "status": str(meta.get("conversion_status") or "")}


def sources_for(root: Path, node: str) -> list[dict]:
    """The records in /memory/sources/ whose every project reference is in `node`, by file name."""
    folder = memory_root(root) / "sources"
    found = []
    for record in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if record.stem.endswith(".reconverted"):
            continue
        source = _source(root, record)
        if source and source["refs"] and {task_stores.node_of(root, r) for r in source["refs"]} == {node}:
            found.append(source)
    return found


def item_hash(source: dict) -> str:
    parts = [source["text"], source["sha"]]
    if source["derivative"]:
        parts.append(read(source["derivative"]))
    return sha_text("\n\0".join(parts))


def plan(root: Path, source: dict, store: RawStore, at: str) -> dict:
    """Where one source goes and the texts it will have; problems listed, nothing written."""
    if not source["raw_ok"]:
        return {"source": source, "store": store, "text": source["text"], "derivative": None,
                "problems": list(source["problems"])}
    rel = source["raw_folder"].relative_to((memory_root(root) / "raw").resolve())
    new_folder = store.raw / rel
    new_record = store.sources / source["record"].name
    old_record_ref = root_path(root, source["record"])
    old_folder_ref = root_path(root, source["raw_folder"])
    own = [[old_record_ref, store.ref(root, new_record)], [old_folder_ref, store.ref(root, new_folder)]]
    mem = [[old_record_ref, store.memory_ref(root, new_record)], [old_folder_ref, store.memory_ref(root, new_folder)]]
    problems = list(source["problems"])
    fields: dict = {"updated": at}
    if store.kind == "repository":
        fields["project_refs"] = [f"{store.repository}:brain"] + [r for r in source["refs"] if not r.startswith("/memory/")]
    text = edit(source["text"], lambda t: set_fields(substitute(t, own), fields))
    derivative = None
    if source["derivative"]:
        derivative = {"from": source["derivative"], "to": store.sources / source["derivative"].name,
                      "text": edit(read(source["derivative"]),
                                   lambda t: set_fields(substitute(t, own), {"updated": at}))}
        if derivative["to"].exists():
            problems.append(f"{store.memory_ref(root, derivative['to'])} exists already")
    if new_folder.exists():
        problems.append(f"{store.memory_ref(root, new_folder)} exists already")
    replaced = None
    if new_record.exists():
        meta = parse_front_matter(read(new_record)) or {}
        if meta.get("type") == "source_reference" and meta.get("canonical_source_md") == old_record_ref:
            replaced = read(new_record)
        else:
            problems.append(f"{store.memory_ref(root, new_record)} exists already")
    stubs = []
    if store.kind == "repository":
        lines = [n for n, line in enumerate(text.splitlines(), 1) if MEMORY_PATH.search(line)]
        if derivative and MEMORY_PATH.search(derivative["text"]):
            lines.append("its derivative")
        if lines:
            problems.append(f"it would still name /memory/ in {store.repository} (lines {', '.join(map(str, lines))}): "
                            "mark it private or hold it")
        stubs = pointer_stubs(root, store.node, old_record_ref)
        manifest = source["raw_folder"] / "manifest.json"
        try:
            if manifest.is_file():
                json.loads(read(manifest))
        except (UnicodeDecodeError, json.JSONDecodeError):
            problems.append(f"its {root_path(root, manifest)} cannot be read, so its machine path cannot be left out")
    return {"source": source, "store": store, "folder": new_folder, "record": new_record, "text": text,
            "derivative": derivative, "replaced": replaced, "stubs": stubs, "own": own, "mem": mem,
            "problems": problems}


def pointer_stubs(root: Path, node: Optional[str], record_ref: str) -> list[Path]:
    """The source_reference files in a pointer node's sources/ that point at a record moving into
    the repository: the pointer node keeps no copy of the project's sources (P17), so they go."""
    folder = root / str(node or "").strip("/") / "sources"
    found = []
    for path in sorted(folder.glob("*.md")) if node and folder.is_dir() else []:
        meta = parse_front_matter(read(path)) or {}
        if meta.get("type") == "source_reference" and meta.get("canonical_source_md") == record_ref:
            found.append(path)
    return found


def list_items(root: Path, node: str, sources: list[dict], store: RawStore, at: str) -> list[dict]:
    terms = raw_stores.personal_terms(root) if store.kind == "repository" else []
    items = []
    for source in sources:
        planned = plan(root, source, store, at)
        notes = [f"raw file {source['size']} bytes"] + (["moves with its derivative"] if source["derivative"] else [])
        notes += [f"cannot move: {p}" for p in planned["problems"]]
        flagged = []
        if store.kind == "repository":
            body = FRONT_MATTER_RE.sub("", planned["text"], count=1)
            derivative = FRONT_MATTER_RE.sub("", planned["derivative"]["text"], count=1) if planned["derivative"] else None
            for found in raw_stores.source_flags(root, source["filename"], source["title"], body, source["status"],
                                                 derivative=derivative, terms=terms):
                if found["line"] is None:      # not a line of the record: said beside the item
                    notes.append(f"flagged ({found['where']}): {', '.join(found['flags'])}")
                else:
                    flagged.append({k: found[k] for k in ("line", "text", "flags")})
        items.append({"id": source["id"], "title": source["title"], "folder": "sources",
                      "path": root_path(root, source["record"]), "sha256": item_hash(source),
                      "notes": notes, "flags": flagged})
    return items


# ---------------------------------------------------------------- rewriting references


def text_files(base: Path):
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in NEVER_REWRITE_DIRS and not d.startswith("."))
        for name in sorted(files):
            if Path(name).suffix.lower() in SUFFIXES and name not in NEVER_REWRITE_FILES:
                yield Path(folder) / name


def conflicts(base: Path, show, pairs: list[list[str]]) -> list[str]:
    """The files a rewrite would change that carry a Git conflict marker (P23: resolved by hand)."""
    found = []
    for path in text_files(base):
        try:
            text = read(path)
        except (OSError, UnicodeDecodeError):
            continue
        if conflicted(text) and substitute(text, pairs) != text:
            found.append(show(path))
    return found


def refuse_conflicts(found: list[str]) -> None:
    if found:
        raise Refused("these files name a moved source and carry a Git conflict marker: "
                      + ", ".join(sorted(set(found))) + "; resolve them by hand (P23); nothing was moved")


def regenerate_states(root: Path, entries: list[dict]) -> list[str]:
    """Generate again the STATE.md of every task store whose records were rewritten (P23)."""
    paths = []
    for entry in entries:
        if entry.get("task"):
            try:
                paths.append(_resolve(root, entry["path"]).resolve())
            except Refused:
                continue
    said = []
    for store in task_stores.stores(root):
        if store.reachable and store.path.is_dir() and any(p.is_relative_to(store.path.resolve()) for p in paths):
            said += regenerate(store)
    return said


def rewrite(base: Path, show, pairs: list[list[str]], author: str, at: str, what: str,
            restore: Optional[dict] = None) -> list[dict]:
    """Rewrite every reference under `base`; a task gets an attributed History entry.

    `restore` maps a shown path to its ledger entry: a file unchanged since the move gets its
    original `updated` back, so a move and its reverse leave it byte-identical."""
    done = []
    for path in text_files(base):
        try:
            text = read(path)
        except (OSError, UnicodeDecodeError):
            continue
        if substitute(text, pairs) == text or conflicted(text):   # a conflicted file was refused beforehand
            continue
        meta = parse_front_matter(text) if path.suffix.lower() == ".md" else None
        earlier = (restore or {}).get(show(path))
        task = bool(meta) and meta.get("type") == "task"
        same = earlier is not None and earlier.get("after") == sha_text(text) and earlier.get("updated")

        def change(lf: str) -> str:
            lf = substitute(lf, pairs)
            if task:
                return apply_change(lf, {}, what, author, at)
            if meta and "updated" in meta:
                return set_fields(lf, {"updated": earlier["updated"] if same else at})
            return lf
        new = edit(text, change)
        write_atomic(path, new)
        done.append({"path": show(path), "pairs": pairs, "after": sha_text(new), "task": task,
                     "updated": meta.get("updated") if meta and not task else None})
    return done


def _ledger_path(root: Path, at: str, node: str) -> Path:
    digits = re.sub(r"[^0-9]", "", at)[:14]
    return memory_root(root) / "systems" / "raw-file-management" / "migrations" / f"{digits}-{slugify(KIND + '-' + node)}.json"


# ---------------------------------------------------------------- move


def _node(root: Path, value: str) -> str:
    node = root_path(root, resolve_node(root, value))
    if not task_stores.is_node(root, root / node.strip("/")):
        raise Refused(f"{node} is not a node (its README.md has no `type: node_readme`)")
    return node


def _stores(root: Path, node: str) -> tuple[RawStore, Optional[RawStore]]:
    pointer = raw_stores.is_pointer(root, node)
    main = raw_stores.choose(root, node, False)
    return main, (raw_stores.choose(root, node, True) if pointer else None)


def dry_run(root: Path, node: str, at: str) -> list[str]:
    main, _private = _stores(root, node)
    sources = sources_for(root, node)
    items = list_items(root, node, sources, main, at)
    said = []
    if main.kind == "repository":
        weight = sum(s["size"] for s in sources)
        said.append(f"into {main.repository}: {raw_stores.visibility(main)}; {weight} bytes of raw files")
    md, _ = write_list(root, KIND, node, items, note=" ".join(said))
    return said + [f"{len(items)} source(s) on the list for {node}: {root_path(root, md)}"]


def move(root: Path, node: str, listing: Optional[dict], at: str, offline: bool) -> list[str]:
    author = brain_author(root)
    main, private = _stores(root, node)
    sources = sources_for(root, node)
    if main.kind == "repository" and listing is None:
        raise Refused(f"sources move into {main.repository} only from a list the owner cleared: run --dry-run, "
                      "record the answers with --decide, then --list FILE")
    if listing is not None:
        listing = load_cleared(listing, KIND, node, list_items(root, node, sources, main, at))
        decisions = {i["id"]: i for i in listing["items"]}
    else:
        decisions = {s["id"]: {"decision": "move", "n": n} for n, s in enumerate(sources, 1)}
    planned, said = [], []
    for source in sources:
        item = decisions[source["id"]]
        if item["decision"] == "hold":
            said.append(f"held {source['id']}")
            continue
        if item.get("private_lines"):
            raise Refused(f"item {item['n']}: a source moves whole; mark it private or hold it")
        if item["decision"] == "private" and private is None:
            raise Refused(f"item {item['n']}: {node} is not a pointer node, so its sources are private already")
        store = private if item["decision"] == "private" else main
        step = plan(root, source, store, at)
        if step["problems"]:
            raise Refused(f"{source['id']} cannot move: {'; '.join(step['problems'])}; nothing was moved")
        planned.append(step)
    found = []
    for step in planned:
        found += conflicts(memory_root(root), lambda p: root_path(root, p), step["mem"])
        if step["store"].kind == "repository":
            found += conflicts(step["store"].checkout / "brain", lambda p, s=step["store"]: s.memory_ref(root, p),
                               step["own"])
    refuse_conflicts(found)
    if any(p["store"].kind == "repository" for p in planned):
        if not main.reachable:
            raise Refused(f"{main.label} cannot be written: {main.reason}")
        said.append(f"into {main.repository}: {raw_stores.visibility(main)}")
        said += ready_to_write(main.writable(), offline=offline)
    moves = [move_one(root, step, at) for step in planned]
    for step, entry in zip(planned, moves):
        store = step["store"]
        what = f"source {entry['id']} moved into {store.label} ({PROPOSAL})"
        entry["rewritten"] = rewrite(memory_root(root), lambda p: root_path(root, p), step["mem"], author, at, what)
        if store.kind == "repository":
            entry["rewritten"] += rewrite(store.checkout / "brain", lambda p, s=store: s.memory_ref(root, p),
                                          step["own"], author, at, what)
        said.append(f"moved {entry['id']}: {entry['record']['to']}")
    said += regenerate_states(root, [e for m in moves for e in m["rewritten"]])
    if moves:
        ledger = _ledger_path(root, at, node)
        write_atomic(ledger, json.dumps({"kind": KIND, "target": node, "at": at, "moves": moves}, indent=2,
                                        ensure_ascii=False) + "\n")
        _log(root, node, main, planned, at, f"Moved {len(moves)} source(s) out of `/memory/sources/` ({PROPOSAL}).")
        said.append(f"ledger: {root_path(root, ledger)}")
    return said


def move_one(root: Path, step: dict, at: str) -> dict:
    """Copy the raw folder, check the copy's hash, write the record, then remove the originals."""
    source, store = step["source"], step["store"]
    shutil.copytree(source["raw_folder"], step["folder"], copy_function=shutil.copy2)
    if sha256_file(step["folder"] / source["raw_file"].name) != source["sha"]:
        shutil.rmtree(step["folder"])
        raise Refused(f"the copy of {source['raw_ref']} does not match raw_sha256; it was removed and the original kept")
    manifest = step["folder"] / "manifest.json"
    original_manifest = None
    if store.kind == "repository" and manifest.is_file():
        # The memory manifest names the machine path the file came from; the repository's never does.
        original_manifest = read(manifest)
        data = json.loads(original_manifest)
        write_atomic(manifest, json.dumps(raw_stores.repository_manifest(data), indent=2, ensure_ascii=False) + "\n")
    write_atomic(step["record"], step["text"])
    derivative = None
    if step["derivative"]:
        write_atomic(step["derivative"]["to"], step["derivative"]["text"])
        derivative = {"from": root_path(root, step["derivative"]["from"]),
                      "to": store.memory_ref(root, step["derivative"]["to"]),
                      "after": sha_text(step["derivative"]["text"]),
                      "updated": (parse_front_matter(read(step["derivative"]["from"])) or {}).get("updated")}
        step["derivative"]["from"].unlink()
    source["record"].unlink()
    shutil.rmtree(source["raw_folder"])
    removed = []
    for stub in step.get("stubs", []):
        removed.append({"path": root_path(root, stub), "text": read(stub)})
        stub.unlink()
    meta = parse_front_matter(source["text"]) or {}
    replaced = None
    if step["replaced"] is not None:
        replaced = {"path": store.memory_ref(root, step["record"]), "text": step["replaced"]}
    return {"id": source["id"], "store": store.kind, "repository": store.repository,
            "record": {"from": root_path(root, source["record"]), "to": store.memory_ref(root, step["record"]),
                       "after": sha_text(step["text"]), "updated": meta.get("updated"),
                       "project_refs": source["refs"]},
            "raw": {"from": root_path(root, source["raw_folder"]), "to": store.memory_ref(root, step["folder"]),
                    "file": source["raw_file"].name},
            "sha256": source["sha"], "derivative": derivative, "replaced_reference": replaced,
            "removed_references": removed, "manifest": original_manifest,
            "own": step["own"], "mem": step["mem"]}


def _log(root: Path, node: str, main: RawStore, planned: list, at: str, line: str) -> None:
    append_log(memory_root(root) / "systems" / "raw-file-management" / "LOG.md", f"- {line[:-1]} for `{node}`.", at)
    append_log(root / node.strip("/") / "LOG.md", f"- {line}", at)
    if main.kind == "repository" and any(p["store"].kind == "repository" for p in planned):
        append_log(main.checkout / "brain" / "LOG.md",
                   f"- Moved sources into `brain/sources/` and `brain/raw/` ({PROPOSAL}).", at)


# ---------------------------------------------------------------- reverse


def _resolve(root: Path, shown: str) -> Path:
    if shown.startswith("/"):
        return root / shown.lstrip("/")
    repository, _, rel = shown.partition(":")
    for store in raw_stores.raw_stores(root):
        if store.kind == "repository" and store.repository == repository:
            if not store.reachable:
                raise Refused(f"{store.label} cannot be read: {store.reason}")
            return store.checkout / rel
    raise Refused(f"no pointer names the repository {repository}")


def reverse(root: Path, ledger_path: Path, at: str, offline: bool) -> list[str]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("kind") != KIND:
        raise Refused(f"{ledger_path.as_posix()} is a ledger of {ledger.get('kind')}: `tasks.py migrate --reverse` reads it")
    if ledger.get("reversed_at"):
        raise Refused(f"{ledger_path.as_posix()} was moved back already, at {ledger['reversed_at']}")
    author = brain_author(root)
    said: list[str] = []
    checks = []
    for move_ in ledger["moves"]:
        record, folder = _resolve(root, move_["record"]["to"]), _resolve(root, move_["raw"]["to"])
        if not record.is_file() or not (folder / move_["raw"]["file"]).is_file():
            raise Refused(f"{move_['id']}: {move_['record']['to']} or its raw file is missing; nothing was moved back")
        if sha256_file(folder / move_["raw"]["file"]) != move_["sha256"]:
            raise Refused(f"{move_['id']}: its raw file no longer matches its hash; nothing was moved back")
        if _resolve(root, move_["raw"]["from"]).exists() or _resolve(root, move_["record"]["from"]).exists():
            raise Refused(f"{move_['id']}: {move_['record']['from']} or {move_['raw']['from']} exists again; nothing was moved back")
        checks.append((move_, record, folder))
    inverse = [[new, old] for m in ledger["moves"] for old, new in m["mem"]]
    refuse_conflicts(conflicts(memory_root(root), lambda p: root_path(root, p), inverse))
    repositories = {m["repository"] for m in ledger["moves"] if m["store"] == "repository"}
    for store in raw_stores.raw_stores(root):
        if store.kind == "repository" and store.repository in repositories:
            said += ready_to_write(store.writable(), offline=offline)
    for move_, record, folder in reversed(checks):
        said.append(_move_back(root, move_, record, folder, author, at))
    restore = {e["path"]: e for m in ledger["moves"] for e in m.get("rewritten", [])}
    done = rewrite(memory_root(root), lambda p: root_path(root, p), inverse, author, at,
                   "sources moved back to /memory/sources/ (migrate --reverse)", restore)
    said += regenerate_states(root, done)
    for store in raw_stores.raw_stores(root):
        if store.kind == "repository" and store.repository in repositories:
            moved = [new for m in ledger["moves"] for _old, new in m["own"]]
            for path in text_files(store.checkout / "brain"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(re.search(re.escape(ref) + r"(?![\w.-])", text) for ref in moved):
                    said.append(f"still names a moved source, edit it by hand: {store.memory_ref(root, path)}")
    ledger["reversed_at"] = at
    write_atomic(ledger_path, json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
    append_log(memory_root(root) / "systems" / "raw-file-management" / "LOG.md",
               f"- Moved {len(checks)} source(s) of `{ledger['target']}` back to `/memory/sources/` (migrate --reverse).", at)
    return said


def _move_back(root: Path, move_: dict, record: Path, folder: Path, author: str, at: str) -> str:
    inverse = [[new, old] for old, new in move_["own"]]
    old_folder, old_record = _resolve(root, move_["raw"]["from"]), _resolve(root, move_["record"]["from"])
    shutil.copytree(folder, old_folder, copy_function=shutil.copy2)
    if sha256_file(old_folder / move_["raw"]["file"]) != move_["sha256"]:
        shutil.rmtree(old_folder)
        raise Refused(f"{move_['id']}: the copy back does not match its hash; it was removed")
    if move_.get("manifest") is not None:
        write_atomic(old_folder / "manifest.json", move_["manifest"])     # with its original_path again
    text = read(record)
    unchanged = sha_text(text) == move_["record"]["after"]
    fields = {"updated": move_["record"]["updated"] if unchanged else at,
              "project_refs": move_["record"]["project_refs"]}
    write_atomic(old_record, edit(text, lambda t: set_fields(substitute(t, inverse), fields)))
    if move_.get("derivative"):
        current = _resolve(root, move_["derivative"]["to"])
        dtext = read(current)
        updated = move_["derivative"]["updated"] if sha_text(dtext) == move_["derivative"]["after"] else at
        write_atomic(_resolve(root, move_["derivative"]["from"]),
                     edit(dtext, lambda t: set_fields(substitute(t, inverse), {"updated": updated})))
        current.unlink()
    record.unlink()
    shutil.rmtree(folder)
    if move_.get("replaced_reference"):
        write_atomic(_resolve(root, move_["replaced_reference"]["path"]), move_["replaced_reference"]["text"])
    for stub in move_.get("removed_references") or []:
        path = _resolve(root, stub["path"])
        if not path.exists():
            write_atomic(path, stub["text"])
    return f"moved back {move_['id']}: {move_['record']['from']}"


# ---------------------------------------------------------------- CLI


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ingest_raw.py migrate", description="Move sources into node and repository stores.")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--node", help="a node in memory: a memory node or a pointer node")
    what.add_argument("--decide", metavar="FILE", help="record the owner's answers in a dry run's list")
    what.add_argument("--reverse", metavar="LEDGER", help="move a recorded move back")
    p.add_argument("--dry-run", action="store_true", help="write the list, move nothing")
    p.add_argument("--list", metavar="FILE", help="the cleared list a move follows")
    p.add_argument("--all", choices=("hold", "move"), help="with --decide: every item")
    p.add_argument("--move", metavar="N,N", help="with --decide: these items move")
    p.add_argument("--private", metavar="N,N", help="with --decide: these go to the pointer node's own raw/ and sources/")
    p.add_argument("--hold", metavar="N,N", help="with --decide: these stay in /memory/sources/")
    p.add_argument("--offline", action="store_true", help="skip the fetch before writing a repository (owner agreed)")
    p.add_argument("--now", help="the timestamp, ISO 8601 with offset; default now")
    p.add_argument("--json", action="store_true", help="print the notes as JSON")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        root = find_root(Path.cwd())
        memory_root(root)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 6
    try:
        at, said = stamp(root, args.now)
        if args.decide:
            said += decide(Path(args.decide), all_=args.all, move=args.move, private=args.private, hold=args.hold)
        elif args.reverse:
            said += reverse(root, Path(args.reverse), at, args.offline)
        else:
            node = _node(root, args.node)
            if args.dry_run:
                said += dry_run(root, node, at)
            else:
                said += move(root, node, Path(args.list) if args.list else None, at, args.offline)
    except (Refused, WriteRefused, ValueError, LookupError, FileNotFoundError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    print(json.dumps({"notes": said}, indent=2, ensure_ascii=False) if args.json else "\n".join(said))
    return 0
