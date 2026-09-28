"""Per-file facts for Python, read with the standard library's own parser.

Reads a JSON list of repository-relative paths on stdin (and the repository root as argv[1]) and
writes one JSON object per file to stdout: functions, classes, imports (and whether they load at
start-up or inside a function), module-level variables and which functions read or change them,
same-file calls, environment reads, SQL strings, and http.server routes.

Part of the code-map skill (canonical copy: /shared/skills/code-map/). In a project this file is an
installed copy: change the skill and reinstall.
"""

import ast
import json
import os
import sys

STDLIB = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names)
SQL_METHODS = {"execute", "executemany", "executescript"}
MUTATORS = {"append", "extend", "insert", "pop", "remove", "clear", "update", "setdefault", "add", "discard", "sort", "reverse", "popitem"}
HTTP_METHODS = {"do_GET": "GET", "do_POST": "POST", "do_PUT": "PUT", "do_PATCH": "PATCH", "do_DELETE": "DELETE", "do_HEAD": "HEAD", "do_OPTIONS": "OPTIONS"}


def const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def sql_parts(node, local_strings):
    """SQL text with dynamic parts marked: a list of strings and {"dynamic": True}."""
    s = const_str(node)
    if s is not None:
        return [s]
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
            else:
                out.append({"dynamic": True})
        return out
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a = sql_parts(node.left, local_strings)
        b = sql_parts(node.right, local_strings)
        return (a or [{"dynamic": True}]) + (b or [{"dynamic": True}])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return sql_parts(node.left, local_strings)
    if isinstance(node, ast.Name) and node.id in local_strings:
        return [local_strings[node.id]]
    return None


def env_name(node):
    """os.environ['X'] / os.environ.get('X') / os.getenv('X') / environ.get('X') -> ('X', None) or (None, text)."""
    def is_environ(n):
        return (isinstance(n, ast.Attribute) and n.attr == "environ" and isinstance(n.value, ast.Name) and n.value.id == "os") or (
            isinstance(n, ast.Name) and n.id == "environ")
    if isinstance(node, ast.Subscript) and is_environ(node.value):
        key = node.slice
        s = const_str(key)
        return (s, None) if s is not None else (None, "os.environ[...]")
    if isinstance(node, ast.Call):
        f = node.func
        getter = (isinstance(f, ast.Attribute) and f.attr in ("get", "setdefault") and is_environ(f.value)) or (
            isinstance(f, ast.Attribute) and f.attr == "getenv" and isinstance(f.value, ast.Name) and f.value.id == "os") or (
            isinstance(f, ast.Name) and f.id == "getenv")
        if getter:
            s = const_str(node.args[0]) if node.args else None
            return (s, None) if s is not None else (None, "os.getenv(...)")
    return None


class FileFacts:
    def __init__(self, path, tree, lines):
        self.path = path
        self.tree = tree
        self.out = {"file": path, "lines": lines, "functions": [], "classes": [], "variables": [], "imports": [],
                    "calls": [], "varRefs": [], "env": [], "sql": [], "routes": []}
        self.module_vars = {}
        self.module_functions = set()
        self.module_strings = {}

    def run(self):
        body = self.tree.body
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.module_functions.add(stmt.name)
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for t in targets:
                    for name in self.names_in(t):
                        container = isinstance(stmt.value, (ast.List, ast.Dict, ast.Set, ast.Call)) if stmt.value is not None else False
                        self.module_vars.setdefault(name, {"name": name, "line": stmt.lineno, "container": container})
                        s = const_str(stmt.value) if stmt.value is not None else None
                        if s is not None:
                            self.module_strings[name] = s
        self.out["variables"] = sorted(self.module_vars.values(), key=lambda v: v["line"])
        self.walk_block(body, owner=None, cls=None, in_function=False)
        self.find_routes()
        return self.out

    @staticmethod
    def names_in(target):
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            return [n for e in target.elts for n in FileFacts.names_in(e)]
        return []

    def walk_block(self, stmts, owner, cls, in_function):
        """Module level and class bodies only; a function's body is read by function_body."""
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{cls}.{stmt.name}" if cls else stmt.name
                end = getattr(stmt, "end_lineno", stmt.lineno)
                self.out["functions"].append({"name": stmt.name, "qualified": qualified, "line": stmt.lineno, "endLine": end,
                                              "length": end - stmt.lineno + 1, "kind": "method" if cls else "function",
                                              "className": cls, "params": len(stmt.args.args)})
                self.function_body(stmt, qualified, cls)
            elif isinstance(stmt, ast.ClassDef):
                end = getattr(stmt, "end_lineno", stmt.lineno)
                methods = [{"name": s.name, "line": s.lineno, "static": any(isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod") for d in s.decorator_list)}
                           for s in stmt.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if cls is None:
                    self.out["classes"].append({"name": stmt.name, "line": stmt.lineno, "endLine": end,
                                                "bases": [ast.unparse(b) for b in stmt.bases], "methods": methods})
                self.walk_block(stmt.body, owner, stmt.name, in_function)
            else:
                self.statement(stmt, owner, cls, in_function)

    def statement(self, node, owner, cls, in_function):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imports(node, owner, in_function)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.walk_block([child], owner, cls, in_function)
            elif isinstance(child, ast.stmt):
                self.statement(child, owner, cls, in_function)
            else:
                self.expression(child, owner, cls, None)

    def imports(self, node, owner, in_function):
        load = "deferred" if in_function else "startup"
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                self.out["imports"].append({"module": alias.name, "names": [], "level": 0, "load": load, "line": node.lineno,
                                            "owner": owner, "stdlib": top in STDLIB})
        else:
            module = node.module or ""
            top = module.split(".")[0]
            self.out["imports"].append({"module": module, "names": [a.name for a in node.names], "level": node.level, "load": load,
                                        "line": node.lineno, "owner": owner, "stdlib": node.level == 0 and top in STDLIB})

    def function_body(self, fn, owner, cls):
        local = set()
        declared_global = set()
        local_strings = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Global):
                declared_global.update(n.names)
            elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    for name in self.names_in(t):
                        local.add(name)
                        s = const_str(n.value) if getattr(n, "value", None) is not None else None
                        if s is not None:
                            local_strings[name] = s
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                local.update(self.names_in(n.target))
            elif isinstance(n, ast.arg):
                local.add(n.arg)
        local -= declared_global
        # One pass over the whole function, nested functions and classes included: they belong to it.
        strings = {**self.module_strings, **local_strings}
        for n in ast.walk(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                self.imports(n, owner, True)
                continue
            self.var_ref(n, owner, local, declared_global)
            self.expression(n, owner, cls, strings, walk=False)

    def var_ref(self, n, owner, local, declared_global):
        if isinstance(n, ast.Name) and n.id in self.module_vars and n.id not in local:
            write = isinstance(n.ctx, (ast.Store, ast.Del)) and n.id in declared_global
            self.out["varRefs"].append({"owner": owner, "name": n.id, "write": write, "line": n.lineno})
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS:
            base = n.func.value
            if isinstance(base, ast.Name) and base.id in self.module_vars and base.id not in local:
                self.out["varRefs"].append({"owner": owner, "name": base.id, "write": True, "line": n.lineno})
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.Delete)):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            for t in targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in self.module_vars and t.value.id not in local:
                    self.out["varRefs"].append({"owner": owner, "name": t.value.id, "write": True, "line": n.lineno})

    def expression(self, node, owner, cls, strings, walk=True):
        nodes = ast.walk(node) if walk else [node]
        for n in nodes:
            e = env_name(n)
            if e is not None:
                name, text = e
                self.out["env"].append({"name": name, "line": n.lineno, "owner": owner, "text": text})
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in self.module_functions and owner:
                    self.out["calls"].append({"owner": owner, "target": f.id, "line": n.lineno})
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "self" and cls and owner:
                    self.out["calls"].append({"owner": owner, "target": f"{cls}.{f.attr}", "line": n.lineno})
                if isinstance(f, ast.Attribute) and f.attr in SQL_METHODS and n.args:
                    parts = sql_parts(n.args[0], strings or self.module_strings)
                    if parts is not None:
                        self.out["sql"].append({"parts": parts, "line": n.lineno, "owner": owner})

    def find_routes(self):
        for cls in ast.walk(self.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name not in HTTP_METHODS:
                    continue
                method = HTTP_METHODS[fn.name]
                derived = set()

                def is_path(n):
                    if isinstance(n, ast.Attribute) and n.attr == "path" and isinstance(n.value, ast.Name) and n.value.id == "self":
                        return True
                    if isinstance(n, ast.Name) and n.id in derived:
                        return True
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in derived:
                        return True
                    if isinstance(n, ast.Call):
                        return any(is_path(a) for a in n.args) or (isinstance(n.func, ast.Attribute) and is_path(n.func.value))
                    if isinstance(n, ast.Subscript):
                        return is_path(n.value)
                    return False

                for n in ast.walk(fn):
                    if isinstance(n, ast.Assign) and is_path(n.value):
                        for t in n.targets:
                            derived.update(self.names_in(t))
                for n in ast.walk(fn):
                    if isinstance(n, ast.Compare):
                        sides = [n.left] + list(n.comparators)
                        for op, right in zip(n.ops, n.comparators):
                            left = sides[sides.index(right) - 1]
                            path_side, other = (left, right) if is_path(left) else (right, left) if is_path(right) else (None, None)
                            if path_side is None:
                                continue
                            values = [const_str(other)] if const_str(other) is not None else [const_str(e) for e in getattr(other, "elts", [])]
                            for v in values:
                                if v and v.startswith("/"):
                                    self.out["routes"].append({"method": method, "path": v.split("?")[0], "prefix": False, "line": n.lineno, "className": cls.name})
                    elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" and is_path(n.func.value) and n.args:
                        v = const_str(n.args[0])
                        if v and v.startswith("/"):
                            self.out["routes"].append({"method": method, "path": v, "prefix": True, "line": n.lineno, "className": cls.name})


def main():
    root = sys.argv[1]
    files = json.load(sys.stdin)
    results = []
    for path in files:
        full = os.path.join(root, path)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as err:
            results.append({"file": path, "error": str(err)})
            continue
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as err:
            results.append({"file": path, "lines": lines, "error": f"SyntaxError at line {err.lineno}: {err.msg}"})
            continue
        try:
            results.append(FileFacts(path, tree, lines).run())
        except RecursionError:
            results.append({"file": path, "lines": lines, "error": "file nests too deeply to map"})
    json.dump(results, sys.stdout)


if __name__ == "__main__":
    main()
