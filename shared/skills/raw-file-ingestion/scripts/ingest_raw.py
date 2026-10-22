#!/usr/bin/env python3
"""
Ingest a source file into the Portable AI Brain.

    ingest_raw.py FILE [--node NODE] [--title T] [--private | --keep-in-repository] [--offline]
    ingest_raw.py migrate ...            move sources out of /memory/sources/ (source_migrate.py)

This script:
1. Locates the brain root by finding CONTRACT.md.
2. Chooses the raw store (CONTRACT §11.1, P13; raw_stores.choose): no node, /memory/raw/; a
   memory node, its raw/; a pointer node, its repository's brain/raw/, or with --private the
   pointer node's own raw/.
3. Computes SHA-256 and looks for an identical raw file in every raw store the brain can reach;
   one found is reused, unless it is in memory and the source is bound for a repository (exit 8).
4. Before anything is written into a repository: names it and says who can read it, and flags
   the converted text, the file name and the title (raw_stores.flags). Anything flagged and
   neither --private nor --keep-in-repository given: exit 7, nothing written.
5. Copies the source byte-for-byte into <raw store>/YYYY/MM/<source-id>/ and creates the
   canonical Markdown record in the sources/ folder beside it, or keeps the record an identical
   earlier file already has.
6. Optionally creates a node-local source reference in memory.
7. Appends the event to /memory/systems/raw-file-management/LOG.md and the node's LOG.md.

convert.py turns the file into the record's Markdown. Formats it cannot read are preserved and
marked pending_conversion.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from convert import Conversion, convert  # noqa: E402
import raw_stores  # noqa: E402
from raw_stores import RawStore  # noqa: E402


def find_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    raise FileNotFoundError("Could not find CONTRACT.md in this path or its parents.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "source"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


MEMORY_DIR = "memory"


def memory_root(root: Path) -> Path:
    memory = root / MEMORY_DIR
    if not memory.is_dir():
        raise FileNotFoundError(f"Memory folder not found: {memory}. Check out the owner's memory repository there.")
    return memory


def root_path(root: Path, path: Path) -> str:
    return "/" + path.resolve().relative_to(root.resolve()).as_posix()


def resolve_node(root: Path, value: str) -> Path:
    """The target node folder for `--node`, checked before anything is written.

    Accepts a path relative to the brain root, a repository-root path (`/memory/...`), an
    absolute path inside the brain, and Windows separators. The node must be an existing
    folder inside the memory checkout: a source reference names an owner's file, so it never
    goes into the mechanics or the skill library (CONTRACT §3.4, §11.1).
    """
    text = value.strip().replace("\\", "/")
    given = Path(text)
    if given.is_absolute() and given.resolve().is_relative_to(root.resolve()):
        node = given.resolve()
    else:
        node = (root / text.lstrip("/")).resolve()
    if not node.is_relative_to(memory_root(root).resolve()):
        raise ValueError(f"target node must be inside the memory checkout ({MEMORY_DIR}/): {value}")
    if not node.is_dir():
        raise FileNotFoundError(f"target node does not exist: {value}")
    return node


def recorded_status(record: Path) -> str:
    found = re.search(r"^conversion_status:\s*(\S+)", record.read_text(encoding="utf-8"), re.M)
    return found.group(1) if found else "unknown"


def write_lf(path: Path, text: str) -> None:
    """Write with LF line ends on every platform, as the brain's other generated files are.

    Written beside the target and moved into place, so a failure never leaves half a file.
    """
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(text, encoding="utf-8", newline="\n")
    os.replace(partial, path)


def safe_convert(path: Path) -> Conversion:
    """convert(), with an unexpected error turned into a failed conversion.

    The raw file is already stored when conversion runs, so a stopped run would leave it without a
    record or a log line; this way it always gets both, and the record says what went wrong.
    """
    try:
        conversion = convert(path)
        conversion.markdown.encode("utf-8")               # a record must be writable as UTF-8
        return conversion
    except Exception as err:
        return Conversion("failed", "", [
            f"Conversion stopped with an unexpected error ({type(err).__name__}: {err}). The raw file is "
            "preserved; the error is a defect of the converter."])


def append_log(log_path: Path, line: str, timestamp: str) -> None:
    if not log_path.is_file():
        return
    data = log_path.read_bytes()
    # Keep the log's own line ends, so an appended entry never rewrites every line of it.
    newline = "\r\n" if b"\r\n" in data else "\n"
    text = data.decode("utf-8").replace("\r\n", "\n")
    heading = f"## {timestamp}"
    if heading in text:
        text = text.rstrip() + "\n" + line + "\n"
    else:
        text = text.rstrip() + f"\n\n{heading}\n\n{line}\n"
    text = re.sub(
        r"updated:\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})",
        f"updated: {timestamp}",
        text,
        count=1,
    )
    log_path.write_text(text, encoding="utf-8", newline=newline)




def write_source_record(canonical: Path, *, source_id: str, title: str, timestamp: str,
                        raw_repo_path: str, file_hash: str, source_name: str,
                        conversion: Conversion, node_ref: Optional[str] = None,
                        project_refs: Optional[list[str]] = None) -> None:
    refs = list(project_refs) if project_refs is not None else ([node_ref] if node_ref else [])
    body = [
        "---",
        f"id: {source_id}",
        f"title: {yaml_quote(title)}",
        "type: source_document",
        "schema_version: 0.2",
        "contract: /CONTRACT.md",
        "status: active",
        f"created: {timestamp}",
        f"updated: {timestamp}",
        f"raw_source: {yaml_quote(raw_repo_path)}",
        f"raw_sha256: {file_hash}",
        f"source_filename: {yaml_quote(source_name)}",
        f"conversion_status: {conversion.status}",
        "conversion_skill: /shared/skills/raw-file-ingestion",
        "project_refs:",
    ]
    body += [f"  - {ref}" for ref in refs] or ["  []"]
    body += [
        "---",
        "",
        f"# {title}",
        "",
        "## Source",
        "",
        f"- Raw file: `{raw_repo_path}`",
        f"- SHA-256: `{file_hash}`",
        f"- Conversion status: `{conversion.status}`",
        "",
        "## Conversion notes",
        "",
    ]
    body.append("\n\n".join(conversion.notes))
    body += ["", "## Extracted content", "", conversion.markdown.rstrip("\n") or "_No extracted content yet._", ""]

    canonical.parent.mkdir(parents=True, exist_ok=True)
    write_lf(canonical, "\n".join(body))


def write_reference(local: Path, *, source_id: str, node_name: str, node_ref: str, title: str, timestamp: str,
                    raw_ref: str, file_hash: str, canonical_ref: str) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    write_lf(local, f"""---
id: {source_id}-{slugify(node_name)}-reference
title: {yaml_quote(title)}
type: source_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: {timestamp}
updated: {timestamp}
raw_source: {yaml_quote(raw_ref)}
raw_sha256: {file_hash}
canonical_source_md: {yaml_quote(canonical_ref)}
project_refs:
  - {node_ref}
---

# {title}

Read `/CONTRACT.md` first.

- Canonical Markdown source: `{canonical_ref}`
- Immutable raw file: `{raw_ref}`
- SHA-256: `{file_hash}`
""")


def repository_flags(root: Path, source_name: str, title: Optional[str], conversion: Conversion) -> list[dict]:
    """What may be private in a source bound for a repository: {where, flags}, in reading order.

    A file whose content could not be read is flagged too: nothing in it was checked."""
    terms = raw_stores.personal_terms(root)
    found = []
    for where, text in (("file name", source_name), ("title", title or "")):
        hit = raw_stores.flags(text, root, terms) if text else []
        if hit:
            found.append({"where": where, "flags": hit})
    for item in raw_stores.flagged_lines(conversion.markdown, root, terms):
        found.append({"where": f"content line {item['line']}", "flags": item["flags"]})
    if conversion.status in ("pending_conversion", "failed"):
        found.append({"where": "content", "flags": [f"not read ({conversion.status}): nothing in it was checked"]})
    return found


def refuse(code: int, message: str, **extra) -> int:
    print(f"Error: {message}", file=sys.stderr)
    if extra:
        print(json.dumps({"written": False, "exit": code, **extra}, indent=2, ensure_ascii=False))
    return code


def check_repository_write(root: Path, store: RawStore, source_name: str, title: Optional[str],
                           conversion: Conversion, keep: bool, offline: bool) -> tuple[int, list[str]]:
    """The checks before anything is written into a repository: (exit code or 0, notes)."""
    from task_git import WriteRefused, ready_to_write
    notes = [f"writing into {store.repository}: {raw_stores.visibility(store)}"]
    flagged = repository_flags(root, source_name, title, conversion)
    if flagged and not keep:
        return refuse(7, f"{source_name} may hold private content and {store.repository}'s readers would see it; "
                         "nothing was written. Ask the owner: --private (the pointer node's raw/) or "
                         "--keep-in-repository.", repository=store.repository, public=store.public,
                      notes=notes, flags=flagged), notes
    if flagged:
        notes.append("kept in the repository as the owner chose, though flagged: "
                     + "; ".join(f"{f['where']}: {', '.join(f['flags'])}" for f in flagged))
    try:
        # On the store branch, fetched, not behind, nothing unmerged under brain/ (task_git).
        notes += ready_to_write(store.writable(), offline=offline)
    except WriteRefused as err:
        return refuse(9, str(err)), notes
    return 0, notes


def ingest(args) -> int:
    source = args.file.expanduser().resolve()
    if not source.is_file():
        print(f"Error: source file not found: {source}", file=sys.stderr)
        return 2

    # Everything is checked before the first write, so a refused run leaves nothing behind.
    try:
        root = find_root(Path.cwd())
        memory_root(root)
    except FileNotFoundError as err:
        return refuse(6, str(err))
    node: Optional[Path] = None
    if args.node:
        try:
            node = resolve_node(root, args.node)
        except ValueError as err:
            return refuse(4, str(err))
        except FileNotFoundError as err:
            return refuse(5, str(err))
    node_ref = root_path(root, node) if node else None
    try:
        target = raw_stores.choose(root, node_ref, args.private)
    except ValueError as err:
        return refuse(4, str(err))
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    timestamp = now.isoformat()
    file_hash = sha256_file(source)
    source_id = f"source-{file_hash[:12]}"
    title = args.title or source.stem.replace("_", " ").replace("-", " ").strip().title()

    found = raw_stores.find_duplicate(root, file_hash)
    raw_path: Optional[Path] = found[1] if found else None
    store = found[0] if found else target
    if found and target.kind == "repository" and not store.same_place(target):
        # A repository cannot resolve a path outside it (P15): the owner decides what happens.
        existing = raw_stores.find_record(store, source_id)
        shown = store.memory_ref(root, existing or raw_path)
        return refuse(8, f"{source.name} is already in {store.label} as {shown}; a record in "
                         f"{target.repository} cannot name it there. Ask the owner: ingest it with --private "
                         "to reuse it in the pointer node, or move that source with `ingest_raw.py migrate`.",
                      existing=shown, store=store.label)
    if not store.reachable:
        return refuse(9, f"{store.label} cannot be written: {store.reason}")
    existing = raw_stores.find_record(store, source_id)
    conversion = None if existing else safe_convert(raw_path or source)
    notes: list[str] = []
    if store.kind == "repository" and (raw_path is None or existing is None):
        code, notes = check_repository_write(root, store, source.name, args.title, conversion,
                                             args.keep_in_repository, args.offline)
        if code:
            return code

    reused_raw = raw_path is not None
    if raw_path is None:
        raw_dir = store.raw / f"{now.year:04d}" / f"{now.month:02d}" / source_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / source.name
        if raw_path.exists() and sha256_file(raw_path) != file_hash:
            return refuse(3, f"conflicting file already exists: {raw_path}")
        if not raw_path.exists():
            shutil.copy2(source, raw_path)
        manifest = {"source_id": source_id, "filename": raw_path.name, "sha256": file_hash, "ingested": timestamp}
        if store.kind != "repository":
            manifest["original_path"] = str(source)    # a machine path never enters a repository
        manifest["mime_type"] = mimetypes.guess_type(source.name)[0]
        write_lf(raw_path.parent / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    # One canonical record per raw file (CONTRACT §3.3, §11.1): an identical file ingested
    # again keeps the record it already has, whatever title it arrives with, so a manual or
    # specialised conversion made in that record since is never overwritten.
    if existing:
        canonical = existing
        conversion_status = recorded_status(existing)
    else:
        canonical = store.sources / f"{source_id}-{slugify(title)}.md"
        conversion_status = conversion.status
        refs = [f"{store.repository}:brain"] if store.kind == "repository" else ([node_ref] if node_ref else [])
        write_source_record(canonical, source_id=source_id, title=title, timestamp=timestamp,
                            raw_repo_path=store.ref(root, raw_path), file_hash=file_hash,
                            source_name=source.name, conversion=conversion, project_refs=refs)

    # A reference in the node when the record lives elsewhere: in the owner store (the folder is
    # in no node) or in another node's or a repository's store, reused by hash.
    node_log = None
    if node and target.kind != "repository" and (target.kind == "owner" or not store.same_place(target)):
        local = node / "sources" / canonical.name
        if not local.exists():
            write_reference(local, source_id=source_id, node_name=node.name, node_ref=node_ref, title=title,
                            timestamp=timestamp, raw_ref=store.memory_ref(root, raw_path), file_hash=file_hash,
                            canonical_ref=store.memory_ref(root, canonical))
            node_log = "Referenced existing source" if existing else "Ingested source"
    elif node and not existing and store.kind != "repository":
        node_log = "Ingested source"
    if node_log:
        append_log(node / "LOG.md", f"- {node_log} `{source.name}` as `{source_id}`.", timestamp)
    if store.kind == "repository" and not existing:
        append_log(store.checkout / "brain" / "LOG.md", f"- Ingested source `{source.name}` as `{source_id}`.",
                   timestamp)

    if existing:
        line = (f"- Ingested `{source.name}` again: identical to `{source_id}`; "
                "its raw file and source record were kept.")
    else:
        line = f"- Ingested `{source.name}` as `{source_id}` into {store.label} with status `{conversion_status}`."
    append_log(memory_root(root) / "systems" / "raw-file-management" / "LOG.md", line, timestamp)

    print(json.dumps({
        "source_id": source_id,
        "store": store.label,
        "raw_file": store.memory_ref(root, raw_path),
        "canonical_markdown": store.memory_ref(root, canonical),
        "conversion_status": conversion_status,
        "duplicate_reused": reused_raw,
        "source_record_reused": existing is not None,
        "notes": notes,
    }, indent=2, ensure_ascii=False))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["migrate"]:
        import source_migrate
        return source_migrate.main(argv[1:])
    parser = argparse.ArgumentParser(description="Ingest a file into the Portable AI Brain.",
                                     epilog="`ingest_raw.py migrate --help` moves sources between stores.")
    parser.add_argument("file", type=Path, help="File to ingest (a file named migrate: write ./migrate)")
    parser.add_argument("--node", type=str, help="Target node inside the memory checkout, e.g. memory/projects/example")
    parser.add_argument("--title", type=str, help="Human-readable title")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--private", action="store_true",
                       help="for a pointer node: keep the source in the pointer node, out of the repository")
    where.add_argument("--keep-in-repository", action="store_true",
                       help="write into the repository although something was flagged (the owner's choice)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the fetch before a write into a repository (only once the owner agrees)")
    return ingest(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
