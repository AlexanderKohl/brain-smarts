"""Pure merge helpers for host_wiring.py: placeholder filling, JSON settings merge, TOML merge."""
from __future__ import annotations

import json
import re
import tomllib
from typing import Any


def fill(value: Any, mapping: dict[str, str]) -> Any:
    """Replace each placeholder in every string of a parsed JSON value (or in a plain string)."""
    if isinstance(value, str):
        for key, text in mapping.items():
            value = value.replace(key, text)
        return value
    if isinstance(value, list):
        return [fill(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, mapping) for k, v in value.items()}
    return value


def merge_json(existing: dict | None, template: dict) -> tuple[dict, list[str]]:
    """SETUP.md F.1: lists in `permissions` are unioned and sorted; a value the person has is kept.

    Returns the merged object and a conflict line for each kept value that differs from the template's.
    """
    merged = json.loads(json.dumps(existing)) if existing else {}
    conflicts: list[str] = []
    perms = merged.setdefault("permissions", {})
    for key, value in template.get("permissions", {}).items():
        if isinstance(value, list) and isinstance(perms.get(key, []), list):
            perms[key] = sorted(set(perms.get(key, [])) | set(value))
        elif key not in perms:
            perms[key] = value
        elif perms[key] != value:
            conflicts.append(f"permissions.{key}: kept {json.dumps(perms[key])}, template has {json.dumps(value)}")
    for key, value in template.items():
        if key == "permissions":
            continue
        if key not in merged:
            merged[key] = value
        elif merged[key] != value:
            conflicts.append(f"{key}: kept {json.dumps(merged[key])}, template has {json.dumps(value)}")
    return merged, conflicts


def dump_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


# --- TOML -------------------------------------------------------------------------------------

_HEADER = re.compile(r"^\s*\[[^\[].*\]\s*(#.*)?$")
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(name: str) -> str:
    if _BARE.match(name):
        return name
    return json.dumps(name) if "'" in name else "'" + name + "'"


def _value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v) if "'" in v or "\n" in v else "'" + v + "'"
    if isinstance(v, list):
        return "[" + ", ".join(_value(i) for i in v) + "]"
    return str(v)


def _header_path(text: str) -> tuple[str, ...] | None:
    """The table path a `[a.b]` line names, or None for a line that is not a table header."""
    if not _HEADER.match(text):
        return None
    try:
        node: Any = tomllib.loads(text.strip() + "\n")
    except tomllib.TOMLDecodeError:
        return None
    path: list[str] = []
    while isinstance(node, dict) and len(node) == 1:
        (k, node), = node.items()
        path.append(k)
    return tuple(path)


def _flatten(data: dict, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str, Any]]:
    """(table path, key, value) for each non-table entry."""
    out = []
    for k, v in data.items():
        if isinstance(v, dict):
            out.extend(_flatten(v, prefix + (k,)))
        else:
            out.append((prefix, k, v))
    return out


def _lookup(data: dict, path: tuple[str, ...]) -> Any:
    for part in path:
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def merge_toml(existing: str, template: str) -> tuple[str, list[str]]:
    """SETUP.md F.3: top-level keys above the first [table]; no key or table is written twice.

    Returns the merged text (it must parse) and a conflict line for each existing value that differs.
    """
    have = tomllib.loads(existing) if existing.strip() else {}
    want = tomllib.loads(template)
    lines = existing.splitlines()
    conflicts: list[str] = []
    top: list[str] = []
    inserts: dict[tuple[str, ...], list[str]] = {}
    new_tables: dict[tuple[str, ...], list[str]] = {}
    for path, key, value in _flatten(want):
        table = _lookup(have, path) if path else have
        shown = ".".join(path + (key,))
        if isinstance(table, dict) and key in table:
            if table[key] != value:
                conflicts.append(f"{shown}: kept {_value(table[key])}, template has {_value(value)}")
            continue
        entry = f"{_key(key)} = {_value(value)}"
        if not path:
            top.append(entry)
        elif isinstance(table, dict):
            inserts.setdefault(path, []).append(entry)
        else:
            new_tables.setdefault(path, []).append(entry)
    if top:
        first = next((i for i, text in enumerate(lines) if _HEADER.match(text)), len(lines))
        block = top + ([""] if first < len(lines) else [])
        if first == len(lines) and lines and lines[-1].strip():
            block = [""] + block
        lines[first:first] = block
    for path, extra in inserts.items():
        at = next((i for i, text in enumerate(lines) if _header_path(text) == path), None)
        if at is None:                                   # table written another way (dotted keys, inline)
            conflicts.append(f"{'.'.join(path)}: table is written another way; {len(extra)} key(s) not added")
            continue
        lines[at + 1:at + 1] = extra
    for path, extra in new_tables.items():
        lines += ([""] if lines and lines[-1].strip() else []) + [f"[{'.'.join(_key(p) for p in path)}]"] + extra
    text = "\n".join(lines) + "\n" if lines else ""
    tomllib.loads(text)
    return text, conflicts
