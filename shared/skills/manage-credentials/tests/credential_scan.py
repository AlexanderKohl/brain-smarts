"""The exact static checks behind tests/test_credential_paths.py (follow-up plan R11, rule 6, parts
a to d). Everything here reads the source with ast and never runs it. The tables it compares
against are in credential_inventory.py; CREDENTIAL-PATHS.md explains them in words.

What is exact here and what is not: a name is followed through `import x as y`, `from x import a
as b`, a re-export through a module of the skill, a module-level or function-level assignment
that binds a name to an imported symbol, and `getattr(obj, "literal")`. A call on a receiver the
scan cannot resolve (`store._write(...)`) is resolved by the method name only when that name is
one of the few unique method names of the primitives and sinks (METHOD_NAMES). Nothing here
follows a value handed to another function: that limit is written in CREDENTIAL-PATHS.md."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

WRITE_MODE_LETTERS = ("w", "a", "x", "+")
FILE_WRITE_CALLS = {("os", "replace"), ("os", "rename"), ("os", "fdopen"), ("tempfile", "mkstemp"),
                    ("tempfile", "NamedTemporaryFile"), ("shutil", "copyfile"), ("shutil", "copy"), ("shutil", "copy2"),
                    ("shutil", "copytree"), ("shutil", "move")}
ENVIRON_WRITE_METHODS = {"update", "pop", "setdefault", "clear", "popitem", "__setitem__", "__delitem__"}
REFLECTION_NAMES = {"eval", "exec", "__import__", "globals", "locals", "vars", "compile"}
PASSPHRASE_VARIABLE = "PORTABLE_VAULT_PASSPHRASE"


def module_rel(path: Path, scripts: Path) -> str:
    return path.relative_to(scripts).as_posix()


def rel_of_dotted(dotted: str, level: int, here: str, scripts: Path) -> str | None:
    """The scripts-relative file of a skill module named in an import, or None for an external one.
    here: the importing module's scripts-relative path."""
    if level:
        base = Path(here).parent
        for _ in range(level - 1):
            base = base.parent
        parts = [p for p in dotted.split(".") if p]
        candidate = base.joinpath(*parts) if parts else base
    else:
        candidate = Path(*dotted.split("."))
    if (scripts / candidate).with_suffix(".py").is_file():
        return candidate.with_suffix(".py").as_posix()
    if (scripts / candidate / "__init__.py").is_file():
        return (candidate / "__init__.py").as_posix()
    return None


class Binding:
    """What a local name stands for: a skill module, a name in a skill module, or an external symbol."""

    def __init__(self, kind: str, module: str, symbol: str | None = None) -> None:
        self.kind, self.module, self.symbol = kind, module, symbol  # kind: skill-module, skill-name, external

    def key(self) -> tuple:
        return (self.kind, self.module, self.symbol)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Binding) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def __repr__(self) -> str:
        return f"Binding{self.key()!r}"


class ModuleInfo:
    def __init__(self, rel: str, tree: ast.Module) -> None:
        self.rel, self.tree = rel, tree
        self.defs: dict[str, ast.AST] = {}  # top-level functions, classes and assigned names
        self.bindings: dict[str, set[Binding]] = defaultdict(set)  # local name -> what it may stand for
        self.aliased_imports: list[tuple[str, str]] = []  # (scope, text) of every import with "as"
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.defs[target.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.defs[node.target.id] = node

    def is_error_or_constant(self, name: str) -> bool:
        node = self.defs.get(name)
        if isinstance(node, ast.ClassDef):
            return all(isinstance(b, (ast.Name, ast.Attribute)) and ast.unparse(b).split(".")[-1].endswith(
                ("Error", "Exception")) for b in node.bases) and bool(node.bases)
        return isinstance(node, (ast.Assign, ast.AnnAssign))


class Skill:
    """Every module under scripts/, parsed, with its import bindings resolved."""

    def __init__(self, scripts: Path) -> None:
        self.scripts = Path(scripts)
        self.modules: dict[str, ModuleInfo] = {}
        self.unparsable: list[str] = []
        for path in sorted(p for p in self.scripts.rglob("*.py") if "__pycache__" not in p.parts):
            rel = module_rel(path, self.scripts)
            try:
                tree = ast.parse(path.read_text("utf-8"), filename=str(path))
            except SyntaxError:
                self.unparsable.append(rel)
                continue
            self.modules[rel] = ModuleInfo(rel, tree)
        for info in self.modules.values():
            self._collect_bindings(info)

    # -- bindings -----------------------------------------------------------------------------
    def _collect_bindings(self, info: ModuleInfo) -> None:
        for node in ast.walk(info.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    rel = rel_of_dotted(alias.name, 0, info.rel, self.scripts)
                    if rel is not None:
                        info.bindings[local].add(Binding("skill-module", rel))
                    else:
                        info.bindings[local].add(Binding("external", alias.name, None if alias.asname else None))
                    if alias.asname:
                        info.aliased_imports.append((alias.name, alias.asname))
            elif isinstance(node, ast.ImportFrom):
                dotted = node.module or ""
                rel = rel_of_dotted(dotted, node.level, info.rel, self.scripts)
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.asname:
                        info.aliased_imports.append((f"{dotted}.{alias.name}", alias.asname))
                    if rel is None:
                        info.bindings[local].add(Binding("external", dotted, alias.name))
                        continue
                    sub = rel_of_dotted(dotted + "." + alias.name if dotted else alias.name, node.level, info.rel,
                                        self.scripts)
                    if sub is not None:  # from secret_store import oauth_ops
                        info.bindings[local].add(Binding("skill-module", sub))
                    else:
                        info.bindings[local].add(Binding("skill-name", rel, alias.name))
        # a name bound to an imported symbol or to an attribute of one: user32 = ctypes.windll.user32
        changed = True
        while changed:
            changed = False
            for node in ast.walk(info.tree):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    continue
                target = node.targets[0].id
                for binding in self.external_chain(info, node.value):
                    if binding not in info.bindings[target]:
                        info.bindings[target].add(binding)
                        changed = True

    def external_chain(self, info: ModuleInfo, node: ast.AST) -> set[Binding]:
        """The external symbols an expression names: a Name bound to one, or an attribute chain on it."""
        chain: list[str] = []
        cur = node
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return set()
        chain.reverse()
        found = set()
        for binding in info.bindings.get(cur.id, ()):
            if binding.kind != "external":
                continue
            parts = chain
            if binding.symbol is None:  # import x.y binds x: the chain must continue with y
                mod_parts = binding.module.split(".")
                if len(mod_parts) > 1:
                    if parts[:len(mod_parts) - 1] != mod_parts[1:]:
                        continue  # this chain belongs to another dotted import of the same package
                    parts = parts[len(mod_parts) - 1:]
                symbol = ".".join(parts[:3]) if parts else None
            else:
                symbol = ".".join([binding.symbol, *parts][:3])
            found.add(Binding("external", binding.module, symbol))
        return found

    def resolve_skill(self, rel: str, name: str, depth: int = 0) -> set[tuple[str, str]]:
        """(module, name) definitions a name in module rel may stand for, following re-exports."""
        info = self.modules.get(rel)
        if info is None or depth > 6:
            return set()
        if name in info.defs:
            return {(rel, name)}
        found = set()
        for binding in info.bindings.get(name, ()):
            if binding.kind == "skill-name":
                found |= self.resolve_skill(binding.module, binding.symbol, depth + 1)
            elif binding.kind == "skill-module":
                found.add((binding.module, "<module>"))
        return found

    def resolve_external_reexport(self, rel: str, name: str, depth: int = 0) -> set[Binding]:
        """External symbols a skill-name binding re-exports (from secret_store.envelope import AESGCM)."""
        info = self.modules.get(rel)
        if info is None or depth > 6:
            return set()
        found = set()
        for binding in info.bindings.get(name, ()):
            if binding.kind == "external":
                found.add(binding)
            elif binding.kind == "skill-name":
                found |= self.resolve_external_reexport(binding.module, binding.symbol, depth + 1)
        return found


# -- the walker ---------------------------------------------------------------------------------
class _Scoped(ast.NodeVisitor):
    """Visits a module with the enclosing function and class names on a stack."""

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.classes: list[str] = []
        self.skip: set[int] = set()

    def scope_name(self) -> str:
        return ".".join(self.scope) or "<module>"

    def _function(self, node: ast.AST) -> None:
        self.scope.append(node.name)
        for annotation in _annotations(node):
            self.skip.update(id(n) for n in ast.walk(annotation))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()
        self.scope.pop()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.skip.update(id(n) for n in ast.walk(node.annotation))
        self.generic_visit(node)


def _annotations(node: ast.AST) -> list:
    args = node.args
    every = args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
    return [a.annotation for a in every if a.annotation is not None] + ([node.returns] if node.returns else [])


def _mode_of(node: ast.Call, position: int) -> str | None:
    if len(node.args) > position and isinstance(node.args[position], ast.Constant):
        return str(node.args[position].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return None


class Findings:
    """Everything one scan found, keyed by (module, scope)."""

    def __init__(self) -> None:
        self.external: dict[tuple[str, str], set[str]] = defaultdict(set)  # (external module, skill module) -> symbols
        self.forms: dict[str, set[tuple[str, str]]] = defaultdict(set)  # form -> {(module, scope)}
        self.library: dict[str, set[tuple[str, str]]] = defaultdict(set)  # attribute -> {(module, scope)}
        self.references: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)  # target -> {(module, scope)}
        self.skill_imports: dict[tuple[str, str], set[str]] = defaultdict(set)  # (importer, imported module) -> names
        self.skill_uses: dict[tuple[str, str], set[str]] = defaultdict(set)  # the attributes used on a module import
        self.operations: dict[str, set[str]] = defaultdict(set)  # parser or dispatcher -> operation names
        self.parsers: set[str] = set()  # modules that build an argparse.ArgumentParser
        self.string_names: set[tuple[str, str, str]] = set()  # (module, scope, name) a string equal to a target name


class Scanner(_Scoped):
    def __init__(self, skill: Skill, info: ModuleInfo, targets: dict[tuple[str, str], str],
                 method_names: dict[str, tuple[str, str]], library_attributes: set[str], findings: Findings) -> None:
        super().__init__()
        self.skill, self.info, self.targets = skill, info, targets
        self.method_names, self.library_attributes, self.f = method_names, library_attributes, findings
        self.rel = info.rel

    def here(self) -> tuple[str, str]:
        return (self.rel, self.scope_name())

    # -- imports ------------------------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            rel = rel_of_dotted(alias.name, 0, self.rel, self.skill.scripts)
            if rel is None:
                self.f.external[(alias.name, self.rel)]  # the module is taken, maybe without a symbol yet
            else:
                self.f.skill_imports[(self.rel, rel)].add("*")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        dotted = node.module or ""
        rel = rel_of_dotted(dotted, node.level, self.rel, self.skill.scripts)
        for alias in node.names:
            if rel is None:
                self.f.external[(dotted, self.rel)].add(alias.name)
                continue
            sub = rel_of_dotted(dotted + "." + alias.name if dotted else alias.name, node.level, self.rel,
                                self.skill.scripts)
            if sub is not None:
                self.f.skill_imports[(self.rel, sub)].add("*")
            else:
                self.f.skill_imports[(self.rel, rel)].add(alias.name)
                for found in self.skill.resolve_external_reexport(rel, alias.name):  # a re-export
                    self.f.external[(found.module, self.rel)].add(found.symbol or alias.name)
            if alias.asname and alias.asname != alias.name:
                self._reference_name(alias.asname, from_alias=True)

    # -- names and attributes -----------------------------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if id(node) in self.skip or not isinstance(node.ctx, ast.Load):
            return
        self._reference_name(node.id)
        if node.id in ("print", "input"):
            self.f.forms[node.id].add(self.here())
        if node.id in REFLECTION_NAMES:
            self.f.forms["reflection"].add(self.here())
        for binding in self.info.bindings.get(node.id, ()):
            if binding.kind == "external" and binding.symbol is not None:
                self.f.external[(binding.module, self.rel)].add(binding.symbol)

    def _reference_name(self, name: str, from_alias: bool = False) -> None:
        for module, defined in self.skill.resolve_skill(self.rel, name):
            if (module, defined) in self.targets and not (module == self.rel and defined == self.scope_name()):
                self.f.references[(module, defined)].add(self.here())

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if id(node) in self.skip:
            return
        for binding in self.skill.external_chain(self.info, node):
            if binding.symbol:
                self.f.external[(binding.module, self.rel)].add(binding.symbol)
        if node.attr in self.library_attributes:
            self.f.library[node.attr].add(self.here())
        self._reference_attribute(node)
        if isinstance(node.value, ast.Name) and node.value.id == "sys" and node.attr in ("stdout", "stderr"):
            self.f.forms["sys-stream"].add(self.here())
        if isinstance(node.value, ast.Attribute) and ast.unparse(node.value) == "sys.stdin":
            self.f.forms["stdin-read"].add(self.here())
        self.generic_visit(node)

    def _reference_attribute(self, node: ast.Attribute) -> None:
        base = node.value
        if isinstance(base, ast.Name):
            if base.id in ("self", "cls") and self.classes:
                target = (self.rel, f"{self.classes[-1]}.{node.attr}")
                if target in self.targets and target[1] != self.scope_name():
                    self.f.references[target].add(self.here())
            for binding in self.info.bindings.get(base.id, ()):
                if binding.kind == "skill-module":
                    self.f.skill_uses[(self.rel, binding.module)].add(node.attr)
                    for module, defined in self.skill.resolve_skill(binding.module, node.attr):
                        if (module, defined) in self.targets:
                            self.f.references[(module, defined)].add(self.here())
                    return
            for module, defined in self.skill.resolve_skill(self.rel, base.id):  # Class.method
                if (module, f"{defined}.{node.attr}") in self.targets:
                    self.f.references[(module, f"{defined}.{node.attr}")].add(self.here())
        target = self.method_names.get(node.attr)
        if target is not None and target in self.targets and target[1] != self.scope_name():
            self.f.references[target].add(self.here())

    # -- calls --------------------------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if isinstance(func, ast.Name):
            if name == "open":
                mode = _mode_of(node, 1)
                if mode and any(c in mode for c in WRITE_MODE_LETTERS):
                    self.f.forms["file-write"].add(self.here())
            elif name in ("getattr", "setattr", "delattr"):
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    literal = node.args[1].value
                    if literal in self.library_attributes:
                        self.f.library[literal].add(self.here())
                    for target in self.targets:
                        if target[1].split(".")[-1] == literal:
                            self.f.references[target].add(self.here())
                else:
                    self.f.forms["reflection"].add(self.here())
        elif isinstance(func, ast.Attribute):
            if name == "open":
                mode = _mode_of(node, 0)
                if mode and any(c in mode for c in WRITE_MODE_LETTERS):
                    self.f.forms["file-write"].add(self.here())
            elif name in ("write_text", "write_bytes"):
                self.f.forms["file-write"].add(self.here())
            elif isinstance(func.value, ast.Name) and (func.value.id, name) in FILE_WRITE_CALLS:
                self.f.forms["file-write"].add(self.here())
            elif isinstance(func.value, ast.Name) and func.value.id == "os" and name in ("putenv", "unsetenv"):
                self.f.forms["environment-write"].add(self.here())
            elif ast.unparse(func.value) == "os.environ" and name in ENVIRON_WRITE_METHODS:
                self.f.forms["environment-write"].add(self.here())
            elif name == "ArgumentParser":
                self.f.parsers.add(self.rel)
                self.f.operations[self.rel]
            elif name == "add_parser" and node.args and isinstance(node.args[0], ast.Constant):
                self.f.operations[self.rel].add(str(node.args[0].value))
            elif name == "add_argument":
                for keyword in node.keywords:
                    if keyword.arg == "choices" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                        for element in keyword.value.elts:
                            if isinstance(element, ast.Constant):
                                self.f.operations[self.rel].add(str(element.value))
            if name in ("write", "writelines") and ast.unparse(func.value) in ("sys.stdout", "sys.stderr"):
                self.f.forms["sys-stream-write"].add(self.here())
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and ast.unparse(target.value) == "os.environ":
                self.f.forms["environment-write"].add(self.here())
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and ast.unparse(target.value) == "os.environ":
                self.f.forms["environment-write"].add(self.here())
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        left = ast.unparse(node.left)
        if left in ("operation", "request.get('op')"):
            for comparator in node.comparators:
                elements = comparator.elts if isinstance(comparator, (ast.Tuple, ast.Set, ast.List)) else [comparator]
                for element in elements:
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        self.f.operations["agent"].add(element.value)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            if node.value == PASSPHRASE_VARIABLE:
                self.f.forms["passphrase-variable"].add(self.here())
            for target in self.targets:
                if node.value.strip() == target[1].split(".")[-1] and not target[1].split(".")[-1].startswith("__"):
                    self.f.string_names.add((self.rel, self.scope_name(), node.value.strip()))


def agent_operation_sets(skill: Skill) -> set[str]:
    """The names in the frozenset literals VAULT_OPS and STORE_OPS of broker_backend.py."""
    found: set[str] = set()
    info = skill.modules.get("secret_store/broker_backend.py")
    if info is None:
        return found
    for node in info.tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("VAULT_OPS", "STORE_OPS")
                                                for t in node.targets):
            for constant in ast.walk(node.value):
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str):
                    found.add(constant.value)
    return found


def scan(scripts: Path, targets: dict[tuple[str, str], str], method_names: dict[str, tuple[str, str]],
         library_attributes: set[str]) -> tuple[Skill, Findings]:
    skill = Skill(scripts)
    findings = Findings()
    for info in skill.modules.values():
        Scanner(skill, info, targets, method_names, library_attributes, findings).visit(info.tree)
    findings.operations["agent"] |= agent_operation_sets(skill)
    return skill, findings
