#!/usr/bin/env python3
"""
Ingest a source file into the Portable AI Brain.

This script:
1. Locates the brain root by finding CONTRACT.md.
2. Copies the source byte-for-byte into /memory/raw/YYYY/MM/<source-id>/.
3. Computes SHA-256 and detects existing identical raw files.
4. Creates a canonical Markdown record under /memory/sources/, or keeps the
   record an identical earlier file already has.
5. Optionally creates a project-local source reference.
6. Appends the event to /memory/systems/raw-file-management/LOG.md.

Raw files, source records and the ingestion log are owner data, so they live
in the memory checkout at <brain root>/memory/.

convert.py turns the raw file into the record's Markdown. Formats it cannot
read are preserved and marked pending_conversion.
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


def find_duplicate(root: Path, file_hash: str) -> Optional[Path]:
    raw_root = memory_root(root) / "raw"
    if not raw_root.exists():
        return None
    for manifest in raw_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("sha256") == file_hash:
            candidate = manifest.parent / data.get("filename", "")
            if candidate.is_file():
                return candidate
    return None


def find_source_record(root: Path, source_id: str) -> Optional[Path]:
    """The canonical source record an identical earlier file already has, if any."""
    sources = memory_root(root) / "sources"
    for candidate in sorted(sources.glob(f"{source_id}*.md")):
        if candidate.stem == source_id or candidate.stem.startswith(source_id + "-"):
            return candidate
    return None


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
                        conversion: Conversion, node_ref: Optional[str]) -> None:
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
    if node_ref:
        body.append(f"  - {node_ref}")
    else:
        body.append("  []")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a file into the Portable AI Brain.")
    parser.add_argument("file", type=Path, help="File to ingest")
    parser.add_argument("--node", type=str, help="Target node inside the memory checkout, e.g. memory/projects/example")
    parser.add_argument("--title", type=str, help="Human-readable title")
    args = parser.parse_args()

    source = args.file.expanduser().resolve()
    if not source.is_file():
        print(f"Error: source file not found: {source}", file=sys.stderr)
        return 2

    # Everything is checked before the first write, so a refused run leaves nothing behind.
    try:
        root = find_root(Path.cwd())
        memory_root(root)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 6
    node: Optional[Path] = None
    if args.node:
        try:
            node = resolve_node(root, args.node)
        except ValueError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 4
        except FileNotFoundError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 5
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    timestamp = now.isoformat()
    today_dt = now.date()
    file_hash = sha256_file(source)
    source_id = f"source-{file_hash[:12]}"
    title = args.title or source.stem.replace("_", " ").replace("-", " ").strip().title()

    duplicate = find_duplicate(root, file_hash)
    if duplicate:
        raw_path = duplicate
    else:
        raw_dir = memory_root(root) / "raw" / f"{today_dt.year:04d}" / f"{today_dt.month:02d}" / source_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / source.name
        if raw_path.exists() and sha256_file(raw_path) != file_hash:
            print(f"Error: conflicting file already exists: {raw_path}", file=sys.stderr)
            return 3
        if not raw_path.exists():
            shutil.copy2(source, raw_path)
        manifest = {
            "source_id": source_id,
            "filename": raw_path.name,
            "sha256": file_hash,
            "ingested": timestamp,
            "original_path": str(source),
            "mime_type": mimetypes.guess_type(source.name)[0],
        }
        write_lf(raw_path.parent / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    # One canonical record per raw file (CONTRACT §3.3, §11.1): an identical file ingested
    # again keeps the record it already has, whatever title it arrives with, so a manual or
    # specialised conversion made in that record since is never overwritten.
    existing = find_source_record(root, source_id)
    raw_repo_path = root_path(root, raw_path)
    if existing:
        canonical = existing
        conversion_status = recorded_status(existing)
    else:
        canonical = memory_root(root) / "sources" / f"{source_id}-{slugify(title)}.md"
        conversion = safe_convert(raw_path)
        conversion_status = conversion.status
        write_source_record(
            canonical, source_id=source_id, title=title, timestamp=timestamp,
            raw_repo_path=raw_repo_path, file_hash=file_hash, source_name=source.name,
            conversion=conversion,
            node_ref=root_path(root, node) if node else None,
        )
    canonical_repo_path = root_path(root, canonical)

    if node:
        local_dir = node / "sources"
        local_dir.mkdir(parents=True, exist_ok=True)
        local = local_dir / canonical.name
        if not local.exists():
            local_text = f"""---
id: {source_id}-{slugify(node.name)}-reference
title: {yaml_quote(title)}
type: source_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: {timestamp}
updated: {timestamp}
raw_source: {yaml_quote(raw_repo_path)}
raw_sha256: {file_hash}
canonical_source_md: {yaml_quote(canonical_repo_path)}
project_refs:
  - {root_path(root, node)}
---

# {title}

Read `/CONTRACT.md` first.

- Canonical Markdown source: `{canonical_repo_path}`
- Immutable raw file: `{raw_repo_path}`
- SHA-256: `{file_hash}`
"""
            write_lf(local, local_text)
            verb = "Referenced existing source" if existing else "Ingested source"
            append_log(node / "LOG.md", f"- {verb} `{source.name}` as `{source_id}`.", timestamp)

    if existing:
        line = (f"- Ingested `{source.name}` again: identical to `{source_id}`; "
                "its raw file and source record were kept.")
    else:
        line = f"- Ingested `{source.name}` as `{source_id}` with status `{conversion_status}`."
    append_log(memory_root(root) / "systems" / "raw-file-management" / "LOG.md", line, timestamp)

    print(json.dumps({
        "source_id": source_id,
        "raw_file": raw_repo_path,
        "canonical_markdown": canonical_repo_path,
        "conversion_status": conversion_status,
        "duplicate_reused": duplicate is not None,
        "source_record_reused": existing is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
