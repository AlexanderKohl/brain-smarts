#!/usr/bin/env python3
"""
Convert a source record's raw file again, on purpose, without losing a hand edit.

    reconvert.py --list       records whose conversion_status is not complete
    reconvert.py SOURCE-ID    convert that record's raw file again

ingest_raw.py never rewrites an existing record, so a record made by an older converter keeps its
old content until this command is run. One rule decides what happens to it: a record whose
front-matter `updated` differs from its `created` is hand-edited and stays byte-identical; the new
derivative is written beside it as <record>.reconverted.md. Any other record is rewritten in place.
Either way every front-matter field the record had is carried through in its order; only `updated`
and `conversion_status` change, and the derivative sets `canonical_source_md` to the record.

Root discovery, conversion, record writing and logging are ingest_raw.py's own helpers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_raw import (  # noqa: E402
    append_log, find_root, memory_root, root_path, safe_convert,
    write_lf, write_source_record, yaml_quote,
)

DERIVATIVE = ".reconverted"
DERIVATIVE_ID = "-reconverted"                   # a derivative's id: the record id plus this
CHANGED = ("updated", "conversion_status")          # the fields a re-conversion sets
KEY = re.compile(r"([A-Za-z_][\w-]*):(?:\s|$)")
FORBIDDEN = re.compile(r"[/\\*?\[]")


def split_record(text: str) -> tuple[list[tuple[str, list[str]]], str]:
    """The front matter as ordered (key, lines) blocks, and the body after it.

    A block is a top-level `key:` line and the indented or list lines under it, kept verbatim.
    """
    found = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not found:
        return [], text
    blocks: list[tuple[str, list[str]]] = []
    for line in found.group(1).splitlines():
        key = KEY.match(line)
        if key or not blocks:
            blocks.append((key.group(1) if key else "", [line]))
        else:
            blocks[-1][1].append(line)
    return blocks, text[found.end():]


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def values(blocks: list[tuple[str, list[str]]]) -> dict:
    """Scalar fields as strings and `project_refs` as a list, block or inline form."""
    data: dict = {"project_refs": []}
    for key, lines in blocks:
        if not key:
            continue
        first = lines[0].split(":", 1)[1].strip()
        if key == "project_refs":
            if first.startswith("[") and first.endswith("]"):
                data[key] = [scalar(item) for item in first[1:-1].split(",") if item.strip()]
            else:
                data[key] = [scalar(m.group(1)) for line in lines[1:]
                             if (m := re.match(r"\s*-\s+(.+)", line))]
        else:
            data[key] = scalar(first)
    return data


def records(root: Path) -> list[Path]:
    """Source records, without the derivatives this command writes beside them."""
    folder = memory_root(root) / "sources"
    return [p for p in sorted(folder.glob("*.md")) if not p.stem.endswith(DERIVATIVE)]


def read_values(record: Path) -> dict:
    return values(split_record(read_record(record))[0])


def read_record(record: Path) -> str:
    """The record's text; bytes that are not UTF-8 become replacement characters, never a crash."""
    return record.read_text(encoding="utf-8", errors="replace")


def find_record(root: Path, source_id: str) -> Optional[Path]:
    """The record whose file stem or front-matter id is exactly SOURCE-ID; never a prefix match."""
    by_stem = memory_root(root) / "sources" / f"{source_id}.md"
    if by_stem.is_file() and not source_id.endswith(DERIVATIVE):
        return by_stem
    for record in records(root):
        if read_values(record).get("id") == source_id:
            return record
    return None


def list_unfinished(root: Path) -> int:
    rows = []
    for record in records(root):
        data = read_values(record)
        status = data.get("conversion_status", "unknown")
        if status != "complete":
            rows.append((data.get("id", record.stem), status, data.get("raw_source", "")))
    for row in sorted(rows):
        print("\t".join(row))
    return 0


def render(blocks: list[tuple[str, list[str]]], data: dict, *, conversion, timestamp: str,
           canonical_ref: Optional[str]) -> str:
    """write_source_record's text, its front matter merged back over the record's own.

    Every original field keeps its lines and its place; only CHANGED take the new values. Fields
    write_source_record sets that the record lacked follow. canonical_ref, for a derivative, sets
    canonical_source_md (replacing any value) and gives the derivative its own id, the
    record id plus -reconverted; without it the record's own value is kept.
    """
    refs = data["project_refs"]
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "record.md"
        write_source_record(
            target, source_id=data["id"], title=data.get("title") or data["id"],
            timestamp=timestamp, raw_repo_path=data["raw_source"],
            file_hash=data.get("raw_sha256", ""),
            source_name=data.get("source_filename") or Path(data["raw_source"]).name,
            conversion=conversion, node_ref=refs[0] if refs else None)
        fresh, body = split_record(target.read_text(encoding="utf-8"))
    new = dict(fresh)
    if canonical_ref:
        new["canonical_source_md"] = [f"canonical_source_md: {yaml_quote(canonical_ref)}"]
        fresh = [*fresh, ("canonical_source_md", new["canonical_source_md"])]
        new["id"] = [f"id: {yaml_quote(data['id'] + DERIVATIVE_ID)}"]   # never the record's own id
    changed = (*CHANGED, "canonical_source_md", "id") if canonical_ref else CHANGED
    merged = [(key, new[key] if key in changed and key in new else lines) for key, lines in blocks]
    have = {key for key, _ in merged}
    merged += [(key, lines) for key, lines in fresh if key not in have]
    head = [line for _, lines in merged for line in lines]
    return "---\n" + "\n".join(head) + "\n---\n" + body


def reconvert(root: Path, source_id: str) -> int:
    if not source_id or FORBIDDEN.search(source_id):
        print(f"Error: SOURCE-ID must be a record id or file name, without / \\ * ? or [: {source_id}",
              file=sys.stderr)
        return 2
    record = find_record(root, source_id)
    if record is None:
        print(f"Error: no source record for {source_id} under /memory/sources/", file=sys.stderr)
        return 2
    blocks, _ = split_record(read_record(record))
    data = values(blocks)
    raw_ref = data.get("raw_source", "")
    raw = root / raw_ref.lstrip("/") if raw_ref else None
    if raw is None or not raw.is_file():
        print(f"Error: raw file not found for {source_id}: {raw_ref or 'no raw_source'}", file=sys.stderr)
        return 3
    data.setdefault("id", record.stem)
    timestamp = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    conversion = safe_convert(raw)
    hand_edited = data.get("updated") != data.get("created")
    if hand_edited:
        target = record.with_name(record.stem + DERIVATIVE + ".md")
        text = render(blocks, data, conversion=conversion, timestamp=timestamp,
                      canonical_ref=root_path(root, record))
        line = (f"- Re-converted `{data['id']}`: the record is hand-edited and was kept; the new "
                f"conversion is in `{root_path(root, target)}` with status `{conversion.status}`.")
        message = "The record is hand-edited, so it was kept and the new conversion was written beside it."
    else:
        target = record
        text = render(blocks, data, conversion=conversion, timestamp=timestamp, canonical_ref=None)
        line = f"- Re-converted `{data['id']}` in place with status `{conversion.status}`."
        message = "The record was rewritten in place."
    write_lf(target, text)
    append_log(memory_root(root) / "systems" / "raw-file-management" / "LOG.md", line, timestamp)
    print(json.dumps({
        "source_id": data["id"],
        "written": root_path(root, target),
        "conversion_status": conversion.status,
        "hand_edited": hand_edited,
        "message": message,
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a source record's raw file again.")
    parser.add_argument("source_id", nargs="?",
                        help="Source ID, e.g. source-0123456789ab, or the record's file name without .md")
    parser.add_argument("--list", action="store_true", help="List records whose conversion_status is not complete")
    args = parser.parse_args()
    if args.list == (args.source_id is not None):
        parser.error("give either --list or one SOURCE-ID")
    try:
        root = find_root(Path.cwd())
        memory_root(root)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 6
    return list_unfinished(root) if args.list else reconvert(root, args.source_id.strip())


if __name__ == "__main__":
    raise SystemExit(main())
