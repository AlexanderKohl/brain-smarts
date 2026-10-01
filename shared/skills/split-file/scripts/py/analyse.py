"""The structure of a Python module, for drawing up a destination table before a split.

  python analyse.py <file>            each top-level statement: lines, kind, names declared, and the
                                      other top-level names it refers to
  python analyse.py <file> --graph [--flag RE]
                                      the definitions in an order where each comes after what it
                                      needs, with how many others use each; names matching RE are
                                      marked *
Add --json for machine-readable output. References are over-counted on purpose.

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import splitlib as S  # noqa: E402


def top_level(path: Path) -> list[dict]:
    text, _, lines = S.read_source(path)
    stmts = S.statements(ast.parse(text), lines)
    top = {n for s in stmts for n in s.declares}
    return [{
        "first": s.first, "start": s.start, "end": s.end, "kind": s.kind, "declares": s.declares,
        "refs": sorted((S.names_read(s.node) & top) - set(s.declares)),
        "head": lines[s.start - 1].strip()[:90],
    } for s in stmts]


def graph(stmts: list[dict], flag: re.Pattern | None) -> list[dict]:
    defs = [s for s in stmts if s["kind"] in ("def", "class", "assign")]
    by_name = {n: s for s in defs for n in s["declares"]}
    used_by: dict[str, set[str]] = {}
    for s in stmts:
        for r in s["refs"]:
            if r in by_name and by_name[r] is not s:
                used_by.setdefault(r, set()).add(s["declares"][0] if s["declares"] else f"line {s['start']}")
    done: list[int] = []
    order: list[dict] = []

    def visit(s: dict, stack: set[int]) -> None:
        if id(s) in done or id(s) in stack:
            return
        stack.add(id(s))
        for r in s["refs"]:
            if r in by_name:
                visit(by_name[r], stack)
        done.append(id(s))
        order.append(s)

    for s in defs:
        visit(s, set())
    return [{
        "start": s["start"], "lines": s["end"] - s["first"] + 1, "names": s["declares"],
        "flagged": bool(flag and flag.search(",".join(s["declares"]))),
        "needs": [r for r in s["refs"] if r in by_name],
        "used_by": sorted(used_by.get(s["declares"][0], set())),
    } for s in order]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file")
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--flag")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    stmts = top_level(Path(args.file))
    if args.graph:
        rows = graph(stmts, re.compile(args.flag, re.I) if args.flag else None)
        if args.json:
            print(json.dumps(rows, indent=1))
        for r in [] if args.json else rows:
            print(f"{r['start']:5} {r['lines']:4} {'*' if r['flagged'] else ' '} {','.join(r['names'])}  <- "
                  f"{', '.join(r['needs'])}  | used by {len(r['used_by'])}")
        return 0
    if args.json:
        print(json.dumps(stmts, indent=1))
        return 0
    for s in stmts:
        print(f"{s['first']:5}-{s['end']:<5} {s['kind']:8} {','.join(s['declares']) or '-'}  <- {', '.join(s['refs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
