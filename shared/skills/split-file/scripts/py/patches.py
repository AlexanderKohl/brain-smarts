"""Which names of a module the tests patch: `mock.patch.object(mod, "name")`, `mock.patch("pkg.mod.name")`,
`monkeypatch.setattr(mod, "name", …)`, `setattr(mod, "name", …)` and `mod.name = …`.

A patch replaces the name in that module only. Once code has moved to another module, it reads the
name there, so a patch on the old module no longer reaches it. The move tool refuses such a move.

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import splitlib as S

SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def _aliases(tree: ast.AST, stem: str) -> set[str]:
    """The names a file binds to the module: `import mod`, `import mod as m`, `from pkg import mod`."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.asname or a.name for a in n.names if a.name == stem}
        elif isinstance(n, ast.ImportFrom):
            out |= {a.asname or a.name for a in n.names if a.name == stem}
    return out


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def patches_in(tree: ast.AST, stem: str) -> list[tuple[int, str]]:
    aliases = _aliases(tree, stem)
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            last = (S.dotted(n.func) or "").split(".")[-1]
            first = n.args[0] if n.args else None
            if last in ("object", "setattr") and len(n.args) >= 2 and isinstance(first, ast.Name) and first.id in aliases:
                name = _string(n.args[1])
                if name:
                    out.append((n.lineno, name))
            elif last in ("patch", "setattr") and first is not None and _string(first):
                parts = _string(first).split(".")
                if len(parts) >= 2 and parts[-2] == stem:
                    out.append((n.lineno, parts[-1]))
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.Delete)):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in aliases:
                    out.append((t.lineno, t.attr))
    return out


def patched_names(source: Path, dirs: list[Path], watched: set[str], skip: set[Path] = frozenset()) -> list[tuple[str, str]]:
    """(file:line, name) for every patch of a watched name on the source module, in .py files under dirs."""
    stem = source.stem
    word = re.compile(rf"\b{re.escape(stem)}\b")
    skip_resolved = {p.resolve() for p in skip} | {source.resolve()}
    out = []
    for folder in dirs:
        for path in sorted(folder.rglob("*.py")):
            if SKIP_PARTS & set(path.parts) or path.resolve() in skip_resolved:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not word.search(text):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for line, name in patches_in(tree, stem):
                if name in watched:
                    out.append((f"{path.relative_to(folder).as_posix()}:{line}", name))
    return out
