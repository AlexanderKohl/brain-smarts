"""Move whole top-level definitions out of a Python module into a new module in the same folder,
without editing them.

The new module gets copies of the imports its code uses (cut down to the names it needs), of
`from __future__` imports, and of the path setup those imports rely on (`sys.path` changes and
folder names built from `__file__`, which mean the same in the same folder). The source imports
every moved name back, so its names stay the same for everything that uses it.

With --no-load-back (for splitting a test file, whose names nothing imports), the source does not
import the moved names back, and the moved code may import names that stay in the source from it.

Refuses when the move could change behaviour:
- moved code needs a name that stays in the source as something other than an import or path setup
  (the new module would have to import the source: a cycle); move that name too, or first;
- moved code uses __name__, globals() or another name that means something else in another file,
  or __file__ other than to name the folder;
- moved code declares `global`, or code that stays declares `global` for a moved name (the two
  modules would each have their own);
- a test patches a moved name, or a name moved code reads, on the source module (the patch would
  no longer reach the moved code); tests are found under the repository root;
- a moved statement runs code with effects when the module loads (it would run when the new module
  is imported), unless --allow-load-order says that order does not matter.

Usage:
  python move.py <source.py> --to <new_module> --names a,b,c [--header TEXT] [--ref TEXT]
                 [--no-load-back] [--allow-load-order] [--tests DIR ...]

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import splitlib as S  # noqa: E402
from patches import patched_names  # noqa: E402


class Refused(Exception):
    pass


def repository_root(path: Path) -> Path:
    try:
        out = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return path.parent


def copied_statements(needed: set[str], stmts: list[S.Stmt], moving: list[S.Stmt], lines: list[str],
                      allow_source: bool) -> tuple[list[tuple[int, str]], list[str], list[str]]:
    """What the new module copies from the source, by source line: `from __future__` imports, the
    imports that provide needed names (cut down), guarded imports, and the path setup they rely on.
    Returns those, the needed names that stay behind, and the names to import from the source."""
    provider: dict[str, S.Stmt] = {}
    for s in stmts:
        if s not in moving:
            for n in s.declares:
                provider[n] = s
    setup = setup_names(stmts)
    copies: dict[int, str] = {}
    behind: list[str] = []
    from_source: list[str] = []
    by_import: dict[int, set[str]] = {}
    seen: set[str] = set()

    def text_of(s: S.Stmt) -> str:
        return "\n".join(lines[s.first - 1:s.end])

    def need(n: str) -> None:
        if n in seen:
            return
        seen.add(n)
        s = provider.get(n)
        if s is None:
            return  # a builtin such as print or len
        if s.kind == "import":
            by_import.setdefault(s.start, set()).add(n)
        elif s.kind == "guarded" or (s.kind == "assign" and n in setup):
            copies[s.first] = text_of(s)
            for m in sorted(S.names_read(s.node)):
                need(m)
        elif allow_source:
            from_source.append(n)
        else:
            behind.append(f"{n} (line {s.start})")

    for n in sorted(needed):
        need(n)
    # sys.path changes that come before a copied import go too, with what they read.
    last_import = max((s.start for s in stmts if s.start in by_import or (s.kind == "guarded" and s.first in copies)), default=0)
    for s in stmts:
        if s.kind == "path" and s.start < last_import:
            copies[s.first] = text_of(s)
            for m in sorted(S.names_read(s.node)):
                need(m)
    for s in stmts:
        if s.kind == "future":
            copies[s.first] = text_of(s)
        if s.start in by_import:
            copies[s.first] = S.narrowed_import(s, by_import[s.start], lines[s.end - 1])
    return sorted(copies.items()), sorted(behind), sorted(set(from_source))


def setup_names(stmts: list[S.Stmt]) -> set[str]:
    """Names of folder paths built from `__file__` (SCRIPTS = Path(__file__).resolve().parent, and
    names built from those): the same in any file of the same folder, so the new module makes them
    again rather than importing them. Any other value stays in one place."""
    out: set[str] = set()
    for s in stmts:
        if s.kind != "assign" or not S.is_pure(s.node.value) or S.file_bound(s.node):
            continue
        reads = S.names_read(s.node.value)
        if "__file__" in reads or reads & out:
            out.update(s.declares)
    return out


def build(args: argparse.Namespace) -> tuple[str, str, Path, str]:
    source = Path(args.source)
    module = args.to.removesuffix(".py")
    if not re.fullmatch(r"[A-Za-z_]\w*", module):
        raise Refused(f"{module} is not a plain module name")
    if module in sys.stdlib_module_names:
        raise Refused(f"{module} is the name of a standard-library module")
    target = source.with_name(f"{module}.py")
    if target.exists():
        raise Refused(f"{target} exists")
    names = [n.strip() for n in args.names.split(",") if n.strip()]

    text, eol, lines = S.read_source(source)
    tree = ast.parse(text)
    stmts = S.statements(tree, lines)
    if any(s.kind == "import" and module in s.declares for s in stmts):
        raise Refused(f"{source.name} already imports a name {module}")

    moving = [s for s in stmts if set(s.declares) & set(names)]
    problems: list[str] = []
    for s in moving:
        extra = [n for n in s.declares if n not in names]
        if extra:
            problems.append(f"the statement at line {s.start} also declares {', '.join(extra)}; name them too")
        if s.kind not in ("def", "class", "assign"):
            problems.append(f"line {s.start} is not a definition or an assignment")
    moved = {n for s in moving for n in s.declares}
    missing = [n for n in names if n not in moved]
    if missing:
        problems.append(f"not found at top level: {', '.join(missing)}")
    staying = [s for s in stmts if s not in moving]

    needed: set[str] = set()
    for s in moving:
        needed |= {n for n in S.names_read(s.node) if n not in moved}
        for n in sorted(S.file_bound(s.node)):
            problems.append(f"line {s.start} uses {n}, which means something else in another file")
        if S.globals_declared(s.node):
            problems.append(f"line {s.start} declares global {', '.join(sorted(S.globals_declared(s.node)))}")
        if not args.allow_load_order:
            for effect in S.load_effects(s):
                problems.append(f"line {s.start} runs code when loaded ({effect}); it would run when the new module is "
                                "imported; check the order does not matter, then pass --allow-load-order")
    for s in staying:
        clash = S.globals_declared(s.node) & moved
        if clash:
            problems.append(f"line {s.start} declares global {', '.join(sorted(clash))}, which moves")
    copies, behind, from_source = copied_statements(needed, stmts, moving, lines, args.no_load_back)
    for b in behind:
        problems.append(f"{b} stays in the source; move it too, or first")

    root = repository_root(source)
    test_dirs = [Path(t) for t in args.tests] if args.tests else [root]
    watched = moved | needed
    for where, name in patched_names(source, test_dirs, watched, skip={target}):
        problems.append(f"{where} patches {source.stem}.{name}; the patch would no longer reach the moved code")
    if problems:
        raise Refused("\n  " + "\n  ".join(problems))

    base = source.name
    reference = f" ({args.ref})" if args.ref else ""
    note = f"Moved unchanged from {base}{reference}."
    if not args.no_load_back:
        note += f" {base} imports these names back, so everything that uses {source.stem} sees the same names."
    doc = [f'"""{args.header or f"Split out of {base}."}', "", *textwrap.wrap(note, 100), '"""']
    # A docstring comes first; `from __future__` must follow it directly, then the other copies in
    # the source's order.
    future = [text for _, text in copies if text.startswith("from __future__")]
    rest = [text for _, text in copies if not text.startswith("from __future__")]
    if from_source:
        rest.append(S.name_list(f"from {source.stem} import ", from_source))
    head = future + ([""] if future and rest else []) + rest
    body: list[str] = []
    for s in moving:
        if body:
            body += ["", ""]
        body += lines[s.first - 1:s.end]
    module_text = "\n".join(doc + [""] + head + ["", ""] + body) + "\n"

    drop: set[int] = set()
    for s in moving:
        drop.update(range(s.first, s.end + 1))
        n = s.end + 1
        while n <= len(lines) and lines[n - 1].strip() == "":
            drop.add(n)
            n += 1
        if n > len(lines):  # the last statement: drop the blank lines before it instead
            k = s.first - 1
            while k >= 1 and lines[k - 1].strip() == "" and k not in drop:
                drop.add(k)
                k -= 1
    out: list[str] = []
    insert_after = 0
    if not args.no_load_back:
        first_use = min((s.start for s in staying if S.names_read(s.node) & moved), default=None)
        limit = first_use or len(lines) + 1
        imports = [s.end for s in staying if s.kind in ("import", "future", "guarded", "path") and s.end < limit]
        insert_after = max(imports) if imports else (first_use - 1 if first_use else 0)
        load_back = S.name_list(f"from {module} import ", [n for s in moving for n in s.declares])
        if insert_after and "noqa: E402" in lines[insert_after - 1]:
            first_line, *rest = load_back.split("\n")
            load_back = "\n".join([f"{first_line}  # noqa: E402", *rest])
    for i, line in enumerate(lines, start=1):
        if i not in drop:
            out.append(line)
        if i == insert_after and not args.no_load_back:
            out += load_back.split("\n")
    if insert_after == 0 and not args.no_load_back:
        out = load_back.split("\n") + out
    result = "\n".join(out)
    if not result.endswith("\n"):
        result += "\n"
    return module_text, result, target, eol


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source")
    parser.add_argument("--to", required=True)
    parser.add_argument("--names", required=True)
    parser.add_argument("--header")
    parser.add_argument("--ref")
    parser.add_argument("--no-load-back", action="store_true")
    parser.add_argument("--allow-load-order", action="store_true")
    parser.add_argument("--tests", action="append")
    args = parser.parse_args(argv)
    try:
        module_text, result, target, eol = build(args)
    except Refused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 1
    source = Path(args.source)
    S.write_text(target, module_text, eol)
    S.write_text(source, result, eol)
    print(f"{target.name}: {module_text.count(chr(10))} lines")
    print(f"{source.name}: now {result.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
