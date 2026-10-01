"""Shared parsing for the Python split tools: the top-level statements of a module, with their line
ranges, the names each declares and reads, and what kind of statement each is.

Names read are over-counted on purpose (shadowing is ignored), so a move never loses a name it needs;
the cost is an occasional refusal that a person resolves by moving more.

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

# Calls whose result depends only on their arguments and which change nothing, so a value made with
# them can be made at another moment, or made again in another file of the same folder.
PURE_CALLS = {
    "Path", "pathlib.Path", "PurePath", "PurePosixPath", "PureWindowsPath", "re.compile", "frozenset",
    "set", "tuple", "list", "dict", "str", "int", "float", "bool", "bytes", "sorted", "len", "range",
    "os.path.join", "os.path.dirname", "os.path.abspath", "os.path.realpath", "os.path.basename",
    "namedtuple", "collections.namedtuple", "field", "dataclasses.field", "TypeVar", "typing.TypeVar",
    "object", "shutil.which", "os.environ.get", "os.getenv", "date", "datetime", "datetime.date",
    "datetime.datetime", "timedelta", "datetime.timedelta", "Decimal", "decimal.Decimal",
    "__import__",
}
PURE_METHODS = {"resolve", "absolute", "joinpath", "with_suffix", "with_name", "expanduser", "as_posix",
                "lower", "upper", "strip", "split", "join", "format", "replace", "encode", "decode",
                "date"}
# Decorators that only wrap or describe what they decorate, and register nothing elsewhere.
PURE_DECORATORS = re.compile(
    r"^(staticmethod|classmethod|property|(dataclasses\.)?dataclass|(functools\.)?(lru_cache|cache|wraps|"
    r"total_ordering|cached_property)|(contextlib\.)?contextmanager|(abc\.)?abstractmethod|"
    r"(unittest\.)?(skip|skipIf|skipUnless|expectedFailure)|(unittest\.)?(mock\.)?patch(\.object|\.dict)?|"
    r"(typing\.)?(overload|final))$"
)
# Names that mean something else in another file. __file__ is allowed only where it names the
# folder (see file_bound).
FILE_BOUND = {"__name__", "__spec__", "__package__", "__loader__", "__builtins__", "__doc__", "__cached__"}


@dataclass
class Stmt:
    node: ast.stmt
    first: int  # first line, with decorators and the comment lines directly above
    start: int
    end: int
    declares: list[str] = field(default_factory=list)
    kind: str = "other"  # def, class, assign, import, future, guarded, path, other


def read_source(path: Path) -> tuple[str, str, list[str]]:
    """The file's text with LF line endings, the line ending to write back, and its lines."""
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    return text, eol, text.split("\n")


def write_text(path: Path, text: str, eol: str) -> None:
    path.write_bytes(text.replace("\n", eol).encode("utf-8"))


def dotted(node: ast.AST) -> str | None:
    """`a.b.c` for a chain of names and attributes, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for t in target.elts for n in target_names(t)]
    if isinstance(target, ast.Starred):
        return target_names(target.value)
    return []


def import_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.asname or a.name.split(".")[0] for a in node.names]
    return [a.asname or a.name for a in node.names if a.name != "*"]


def _is_path_setup(node: ast.stmt) -> bool:
    """`sys.path.insert(…)`, `sys.path.append(…)` and the like."""
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and (dotted(node.value.func) or "").startswith("sys.path."))


def _declares(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [n for t in node.targets for n in target_names(t)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return target_names(node.target)
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return import_names(node)
    if isinstance(node, (ast.If, ast.Try)):
        out: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                out += import_names(child)
            elif isinstance(child, ast.Assign):
                out += [n for t in child.targets for n in target_names(t)]
        return sorted(set(out))
    return []


def _guarded_imports(node: ast.stmt) -> bool:
    """An `if`/`try` at top level holding only imports and plain assignments: an optional import."""
    if not isinstance(node, (ast.If, ast.Try)):
        return False
    for child in ast.walk(node):
        if child is node or isinstance(child, (ast.expr, ast.expr_context, ast.alias, ast.excepthandler,
                                                ast.operator, ast.cmpop, ast.boolop, ast.unaryop)):
            continue
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
            continue
        if not isinstance(child, (ast.Import, ast.ImportFrom, ast.Assign, ast.Pass)):
            return False
    return True


def statements(tree: ast.Module, lines: list[str]) -> list[Stmt]:
    out = []
    previous_end = 0
    for node in tree.body:
        start = node.lineno
        first = min([start] + [d.lineno for d in getattr(node, "decorator_list", [])])
        # Comment lines directly above (no blank line between) belong to the statement.
        while first - 1 > previous_end and lines[first - 2].lstrip().startswith("#"):
            first -= 1
        stmt = Stmt(node, first, start, node.end_lineno, _declares(node))
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            stmt.kind = "future"
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            stmt.kind = "import"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stmt.kind = "def"
        elif isinstance(node, ast.ClassDef):
            stmt.kind = "class"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            stmt.kind = "assign"
        elif _guarded_imports(node):
            stmt.kind = "guarded"
        elif _is_path_setup(node):
            stmt.kind = "path"
        out.append(stmt)
        previous_end = node.end_lineno
    return out


def names_read(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Store)}


def names_stored(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def globals_declared(node: ast.AST) -> set[str]:
    return {name for n in ast.walk(node) if isinstance(n, ast.Global) for name in n.names}


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def file_bound(node: ast.AST) -> set[str]:
    """Names in the node that mean something else in another file: module attributes such as
    __name__, globals() and vars(), and __file__ unless it only names the folder
    (os.path.dirname(__file__), Path(__file__).parent, Path(__file__).resolve().parents[1] …)."""
    found = set()
    parents = _parents(node)
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in FILE_BOUND:
            found.add(n.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("globals", "vars") and not n.args:
            found.add(f"{n.func.id}()")
        if isinstance(n, ast.Name) and n.id == "__file__" and not _names_folder(n, parents):
            found.add("__file__")
    return found


def _names_folder(name: ast.Name, parents: dict[ast.AST, ast.AST]) -> bool:
    node: ast.AST = name
    parent = parents.get(node)
    # Path(__file__), os.path.abspath(__file__) and the like: the same file's full name.
    while isinstance(parent, ast.Call) and node in parent.args and dotted(parent.func) in (
            "Path", "pathlib.Path", "os.path.abspath", "os.path.realpath"):
        node, parent = parent, parents.get(parent)
        # .resolve() / .absolute()
        while (isinstance(parent, ast.Attribute) and parent.attr in ("resolve", "absolute")
               and isinstance(parents.get(parent), ast.Call)):
            node = parents[parent]
            parent = parents.get(node)
    if isinstance(parent, ast.Attribute) and parent.attr in ("parent", "parents"):
        return True
    return isinstance(parent, ast.Call) and node in parent.args and dotted(parent.func) == "os.path.dirname"


def is_pure(node: ast.AST | None) -> bool:
    """Whether evaluating an expression changes nothing and gives the same value at another moment."""
    if node is None or isinstance(node, (ast.Constant, ast.Name, ast.Lambda)):
        return True
    if isinstance(node, ast.Attribute):
        return is_pure(node.value)
    if isinstance(node, ast.Subscript):
        return is_pure(node.value) and is_pure(node.slice)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(is_pure(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(is_pure(k) and is_pure(v) for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.BinOp):
        return is_pure(node.left) and is_pure(node.right)
    if isinstance(node, ast.UnaryOp):
        return is_pure(node.operand)
    if isinstance(node, (ast.BoolOp,)):
        return all(is_pure(v) for v in node.values)
    if isinstance(node, ast.Compare):
        return is_pure(node.left) and all(is_pure(c) for c in node.comparators)
    if isinstance(node, ast.IfExp):
        return is_pure(node.test) and is_pure(node.body) and is_pure(node.orelse)
    if isinstance(node, ast.JoinedStr):
        return all(is_pure(v) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return is_pure(node.value)
    if isinstance(node, ast.Starred):
        return is_pure(node.value)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        parts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        for gen in node.generators:
            parts += [gen.iter, *gen.ifs]
        return all(is_pure(p) for p in parts)
    if isinstance(node, ast.Call):
        name = dotted(node.func)
        args_pure = all(is_pure(a) for a in node.args) and all(is_pure(k.value) for k in node.keywords)
        if name in PURE_CALLS:
            return args_pure
        if isinstance(node.func, ast.Attribute) and node.func.attr in PURE_METHODS:
            return is_pure(node.func.value) and args_pure
    return False


def pure_decorators(node: ast.stmt) -> list[str]:
    """The decorators of a definition that may run code with effects elsewhere."""
    out = []
    for d in getattr(node, "decorator_list", []):
        target = d.func if isinstance(d, ast.Call) else d
        name = dotted(target) or ast.unparse(target)
        args_ok = not isinstance(d, ast.Call) or all(is_pure(a) for a in d.args) and all(is_pure(k.value) for k in d.keywords)
        if not (PURE_DECORATORS.match(name) and args_ok):
            out.append(ast.unparse(d))
    return out


def load_effects(stmt: Stmt) -> list[str]:
    """What a statement runs when the module loads, beyond defining its names."""
    node = stmt.node
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        effects = pure_decorators(node)
        effects += [ast.unparse(d) for d in node.args.defaults + [d for d in node.args.kw_defaults if d] if not is_pure(d)]
        return effects
    if isinstance(node, ast.ClassDef):
        effects = pure_decorators(node) + [ast.unparse(b) for b in node.bases if not is_pure(b)]
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)) and not is_pure(item.value):
                effects.append(ast.unparse(item.value)[:60])
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                effects += pure_decorators(item)
            elif not isinstance(item, (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef, ast.Pass, ast.Expr)):
                effects.append(ast.unparse(item).split("\n")[0][:60])
        return effects
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return [] if is_pure(node.value) else [ast.unparse(node.value).split("\n")[0][:60]]
    return [ast.unparse(node).split("\n")[0][:60]]


def narrowed_import(stmt: Stmt, needed: set[str], line_text: str) -> str:
    """An import statement cut down to the names needed, keeping a trailing `# noqa` comment."""
    node = stmt.node
    keep = [a for a in node.names if (a.asname or (a.name.split(".")[0] if isinstance(node, ast.Import) else a.name)) in needed]
    if isinstance(node, ast.Import):
        text = ast.unparse(ast.Import(names=keep))
    else:
        text = ast.unparse(ast.ImportFrom(module=node.module, names=keep, level=node.level))
    m = re.search(r"#\s*noqa[^\n]*$", line_text)
    return f"{text}  {m.group(0)}" if m else text


def name_list(prefix: str, names: list[str], limit: int = 100) -> str:
    """`from x import a, b`, in parentheses over several filled lines when it would pass the limit."""
    one = f"{prefix}{', '.join(names)}"
    if len(one) <= limit:
        return one
    out = [f"{prefix}("]
    line = "   "
    for n in names:
        if len(line) + len(n) + 2 > limit:
            out.append(line)
            line = "   "
        line += f" {n},"
    return "\n".join([*out, line, ")"])
