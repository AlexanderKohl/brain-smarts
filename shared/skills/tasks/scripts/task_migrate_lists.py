"""The list protocol of the migration (plan section 5.1), one for every kind of move.

A dry run writes `/temp/migration/<kind>-<target>.md` for the owner (numbered, open before
completed, flags inline) and `.json` for the commands (`fingerprint`: SHA-256 over the sorted
identifiers and file hashes; items with `decision: null`). The owner answers in the conversation
and the conductor records it with `migrate --decide <file> --all move --private 3,9 --hold 12
--private-lines 15:2,4`. A move takes `--list <file>` and refuses when the fingerprint no longer
matches the records (run the dry run again: an unchanged item keeps its decision, so only the
changed ones need clearing again) or any item has no decision. Silence moves nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from task_records import write_atomic

DECISIONS = ("hold", "move", "private")
FOLDER_ORDER = {"inbox": 0, "open": 1, "recurring": 2, "completed": 3}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(items: list[dict]) -> str:
    lines = sorted(f"{item['id']}:{item['sha256']}" for item in items)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def list_paths(root: Path, kind: str, target: str) -> tuple[Path, Path]:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{kind}-{target}".strip("/")).strip("-").lower()
    folder = root / "temp" / "migration"
    return folder / f"{name}.md", folder / f"{name}.json"


def _render(listing: dict) -> str:
    lines = [f"# Migration list: {listing['kind']} {listing['target']}", "",
             f"Fingerprint `{listing['fingerprint'][:16]}`. Nothing moves until every item has a decision "
             "(move, private or hold) recorded with `tasks.py migrate --decide`.", ""]
    for item in listing["items"]:
        decision = item.get("decision") or "undecided"
        lines.append(f"{item['n']}. `{item['id']}` {item['title']} ({item['folder']}) – {decision}")
        for part in item.get("parts", []):
            lines.append(f"   - part for {part['node']}: {part['title']}")
        for note in item.get("notes", []):
            lines.append(f"   - {note}")
        for flag in item.get("flags", []):
            chosen = " (to the companion file)" if flag["line"] in item.get("private_lines", []) else ""
            lines.append(f"   - line {flag['line']}: {', '.join(flag['flags'])}{chosen}: {flag['text'][:120]}")
    return "\n".join(lines) + "\n"


def write_list(root: Path, kind: str, target: str, items: list[dict], note: str = "") -> tuple[Path, Path]:
    """Number the items, carry decisions over from an earlier list for unchanged items, write both files."""
    md, js = list_paths(root, kind, target)
    earlier = {}
    if js.is_file():
        for item in json.loads(js.read_text(encoding="utf-8")).get("items", []):
            earlier[(item["id"], item["sha256"])] = item
    for n, item in enumerate(items, 1):
        item["n"] = n
        old = earlier.get((item["id"], item["sha256"]), {})
        item.setdefault("decision", old.get("decision"))
        item.setdefault("private_lines", old.get("private_lines", []))
    listing = {"kind": kind, "target": target, "fingerprint": fingerprint(items), "note": note, "items": items}
    write_atomic(js, json.dumps(listing, indent=2, ensure_ascii=False) + "\n")
    write_atomic(md, _render(listing))
    return md, js


def _numbers(text: str | None) -> list[int]:
    return [int(n) for n in re.split(r"[,\s]+", text or "") if n.strip()]


def decide(path: Path, all_: str | None = None, move: str | None = None, private: str | None = None,
           hold: str | None = None, private_lines: list[str] | None = None) -> list[str]:
    """Record the owner's answers in a list; returns what was recorded."""
    js = path.with_suffix(".json")
    listing = json.loads(js.read_text(encoding="utf-8"))
    by_n = {item["n"]: item for item in listing["items"]}
    if all_:
        for item in listing["items"]:
            item["decision"] = all_
    for decision, numbers in (("move", move), ("private", private), ("hold", hold)):
        for n in _numbers(numbers):
            if n not in by_n:
                raise ValueError(f"--{decision} {n}: the list has no item {n}")
            by_n[n]["decision"] = decision
    for spec in private_lines or []:
        item_n, _, lines = spec.partition(":")
        if not item_n.strip().isdigit() or int(item_n) not in by_n:
            raise ValueError(f"--private-lines {spec}: write <item>:<line>,<line> for an item on the list")
        by_n[int(item_n)]["private_lines"] = sorted(set(_numbers(lines)))
    if listing["kind"] == "split" and any(i.get("decision") == "private" for i in listing["items"]):
        raise ValueError("a split is moved or held; private applies to a repository list")
    write_atomic(js, json.dumps(listing, indent=2, ensure_ascii=False) + "\n")
    write_atomic(js.with_suffix(".md"), _render(listing))
    counts = {d: sum(1 for i in listing["items"] if i.get("decision") == d) for d in DECISIONS}
    undecided = sum(1 for i in listing["items"] if not i.get("decision"))
    return [f"recorded in {js.as_posix()}: " + ", ".join(f"{counts[d]} {d}" for d in DECISIONS)
            + f", {undecided} undecided"]


def load_cleared(path: Path, kind: str, target: str, current: list[dict]) -> dict:
    """The cleared list, refused when stale or when any item has no decision."""
    js = path.with_suffix(".json")
    listing = json.loads(js.read_text(encoding="utf-8"))
    if listing.get("kind") != kind or listing.get("target") != target:
        raise ValueError(f"{js.as_posix()} is the list for {listing.get('kind')} {listing.get('target')}, "
                         f"not {kind} {target}")
    if listing.get("fingerprint") != fingerprint(current):
        raise ValueError(f"{js.as_posix()} is stale: the records changed since the dry run; run the dry run "
                         "again (unchanged items keep their decisions)")
    undecided = [str(i["n"]) for i in listing["items"] if i.get("decision") not in DECISIONS]
    if undecided:
        raise ValueError(f"items {', '.join(undecided)} have no decision; nothing was moved")
    return listing


def sort_items(items: list[dict], key) -> list[dict]:
    """Open before completed, then by identifier (SMART-RULE-0027: the owner clears open work first)."""
    return sorted(items, key=lambda i: (i["folder"] == "completed", FOLDER_ORDER.get(i["folder"], 9), key(i["id"])))
