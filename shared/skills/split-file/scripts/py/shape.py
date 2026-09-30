"""Shape snapshot for Python modules: what the rest of a program can see of them, so a split that only
moves code can be shown to leave it unchanged.

For each module, loaded alone in a fresh process with its own folder first on the import path:
- every name in its namespace: modules by name, functions by signature and a hash of their source,
  classes member by member (methods, static and class methods, properties, dataclass fields,
  nested classes), other values by type and a hash of their text form;
- every outbound network connection attempted while loading (there must be none).
Which module a function or class says it belongs to (__module__) is left out: that is what a move
changes. Code that reads it (pickle, logging's module field) is reviewed by hand.

With --tests, the modules are test files split among themselves: the snapshot is their test classes,
merged across the files (a class may move from one file to another), and the number of tests.

Configuration: `split-file.config.json` at the repository root (or --config), key "python":
  modules     files to describe          sysPath     folders to put on the import path too
  env         environment values         coldDirs / coldIgnore   as for the JavaScript tool

Usage:
  python shape.py [--root DIR] [--config FILE] [--modules a.py,b.py] [--tests]   print as JSON
  python shape.py … --out FILE | --compare FILE | --compare-ref REF
Exit code 1 when a comparison finds a difference.

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shapediff import diff_lines, flatten  # noqa: E402

LOCAL = {"localhost", "127.0.0.1", "::1", ""}
SKIP_CLASS = {"__module__", "__dict__", "__weakref__", "__qualname__", "__firstlineno__", "__static_attributes__"}
ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")


def digest(text: str) -> str:
    return hashlib.sha1(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:12]


def load_config(root: Path, file: str | None, modules: str | None) -> dict:
    path = Path(file).resolve() if file else root / "split-file.config.json"
    data = json.loads(path.read_text(encoding="utf-8")).get("python", {}) if path.is_file() else {}
    config = {"modules": data.get("modules", []), "sysPath": data.get("sysPath", []), "env": data.get("env", {}),
              "coldDirs": data.get("coldDirs", ["."]), "coldIgnore": data.get("coldIgnore", [])}
    if modules:
        config["modules"] = [m.strip() for m in modules.split(",") if m.strip()]
    if not config["modules"]:
        raise SystemExit(f"no modules: name them with --modules or in {path}")
    return config


# ---- inside the fresh process ---------------------------------------------------------------

def install_outbound_trap() -> list[str]:
    attempts: list[str] = []
    original = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else ""
        if isinstance(address, tuple) and str(host) not in LOCAL:
            attempts.append(f"{host}:{address[1]}")
            raise OSError(f"outbound connection to {host}:{address[1]} blocked by the shape snapshot")
        return original(self, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = lambda self, address: connect(self, address) or 0
    return attempts


class Describer:
    def __init__(self, root: Path):
        self.roots = [str(root.resolve()), str(root.resolve()).replace("\\", "/")]

    def normalise(self, text: str) -> str:
        for r in self.roots:
            text = text.replace(r, "<repo>")
        return ADDRESS.sub("", text).replace("\\\\", "/").replace("\\", "/")

    def source(self, fn) -> str:
        try:
            return f"src:{digest(inspect.getsource(fn))}"
        except (OSError, TypeError):
            return "generated"

    def signature(self, fn) -> str:
        try:
            return self.normalise(str(inspect.signature(fn)))
        except (TypeError, ValueError):
            return "?"

    def function(self, fn) -> str:
        return f"function {fn.__name__}{self.signature(fn)} {self.source(fn)}"

    def value(self, value, depth: int = 0):
        if inspect.ismodule(value):
            return f"module {value.__name__}"
        if inspect.isclass(value):
            return self.cls(value, depth) if depth < 3 else f"class {value.__name__}"
        if inspect.isfunction(value):
            return self.function(value)
        wrapped = getattr(value, "__wrapped__", None)
        if callable(value) and inspect.isfunction(wrapped):
            return f"{type(value).__name__} of {self.function(wrapped)}"
        if inspect.isbuiltin(value):
            return f"builtin {getattr(value, '__module__', '')}.{value.__name__}"
        try:
            text = repr(sorted(value, key=repr)) if isinstance(value, (set, frozenset)) else repr(value)
        except Exception:  # noqa: BLE001 - a repr that fails is still a shape
            text = "<repr failed>"
        return f"{type(value).__name__} {digest(self.normalise(text))}"

    def member(self, value, depth: int):
        if isinstance(value, staticmethod):
            return f"staticmethod {self.function(value.__func__)}" if inspect.isfunction(value.__func__) else "staticmethod"
        if isinstance(value, classmethod):
            return f"classmethod {self.function(value.__func__)}" if inspect.isfunction(value.__func__) else "classmethod"
        if isinstance(value, property):
            parts = [f"{k}:{self.source(f) if f else '-'}" for k, f in (("get", value.fget), ("set", value.fset), ("del", value.fdel))]
            return f"property {' '.join(parts)}"
        return self.value(value, depth + 1)

    def cls(self, cls, depth: int = 0) -> dict:
        out = {"class": cls.__name__, "bases": [b.__qualname__ for b in cls.__bases__], "members": {}}
        for name, value in sorted(vars(cls).items()):
            if name in SKIP_CLASS:
                continue
            if name == "__dataclass_fields__":
                out["members"][name] = sorted(value)
            elif name in ("__doc__", "__annotations__", "__dataclass_params__"):
                out["members"][name] = digest(self.normalise(repr(value)))
            else:
                out["members"][name] = self.member(value, depth)
        return out


def load(path: Path, root: Path, config: dict):
    os.environ.update(config["env"])
    for extra in reversed(config["sysPath"]):
        sys.path.insert(0, str((root / extra).resolve()))
    sys.path.insert(0, str(path.parent.resolve()))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def describe_file(path: Path, root: Path, config: dict, tests: bool) -> dict:
    attempts = install_outbound_trap()
    module = load(path, root, config)
    d = Describer(root)
    if tests:
        import unittest
        classes = {name: d.cls(v) for name, v in vars(module).items()
                   if inspect.isclass(v) and issubclass(v, unittest.TestCase) and v.__module__ == module.__name__}
        count = unittest.defaultTestLoader.loadTestsFromModule(module).countTestCases()
        return {"ok": True, "testClasses": classes, "testCount": count, "outbound": attempts}
    names = {name: d.value(v) for name, v in sorted(vars(module).items())
             if not (name.startswith("__") and name.endswith("__")) or name == "__all__"}
    return {"ok": True, "names": names, "outbound": attempts}


# ---- the snapshot -------------------------------------------------------------------------

def run_describe(file: str, root: Path, config_args: list[str], tests: bool, cold: bool = False) -> dict:
    args = [sys.executable, __file__, "--describe", file, "--root", str(root), *config_args]
    if tests:
        args.append("--tests")
    # A fixed hash seed, so sets list their members in the same order in every process.
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", env=env)
    line = next((l for l in result.stdout.splitlines() if l.startswith("SHAPE-PY ")), None)
    if result.returncode != 0 or not line:
        error = (result.stderr.strip().splitlines() or [f"exit {result.returncode}"])[-1][:300]
        return {"ok": False, "error": error}
    data = json.loads(line[len("SHAPE-PY "):])
    return {"ok": True, "outbound": data["outbound"]} if cold else data


def take_snapshot(root: Path, config: dict, config_args: list[str], tests: bool, cold_files: list[str]) -> dict:
    snapshot: dict = {"modules": {}, "coldLoads": {}, "outbound": []}
    merged: dict = {}
    count = 0
    for file in config["modules"]:
        if not (root / file).is_file():
            if not tests:
                snapshot["modules"][file] = "(missing)"
            continue
        data = run_describe(file, root, config_args, tests)
        snapshot["outbound"] += data.pop("outbound", [])
        if not data.get("ok"):
            snapshot.setdefault("failed", {})[file] = data.get("error")
        if tests and data.get("ok"):
            for name, desc in data["testClasses"].items():
                merged[f"{name}{' (twice)' if name in merged else ''}"] = desc
            count += data["testCount"]
        else:
            snapshot["modules"][file] = data
    if tests:
        snapshot["modules"] = {"testClasses": dict(sorted(merged.items())), "testCount": count}
    for file in cold_files:
        snapshot["coldLoads"][file] = run_describe(file, root, config_args, False, cold=True)
    return snapshot


def compare(before: dict, after: dict, modules: list[str]) -> tuple[list[str], list[str]]:
    # Loading alone is checked as a problem below, not compared: the base is not loaded alone.
    def pick(s: dict) -> dict:
        return {k: v for k, v in s.items() if k != "coldLoads"}
    differences = diff_lines(flatten(pick(before)), flatten(pick(after)))
    problems = []
    for file, result in after.get("coldLoads", {}).items():
        if not result.get("ok"):
            problems.append(f"loading alone failed: {file}: {result.get('error')}")
        elif result.get("outbound"):
            problems.append(f"loading alone made outbound connections: {file}: {', '.join(result['outbound'])}")
    for file, error in after.get("failed", {}).items():
        problems.append(f"loading failed: {file}: {error}")
    if after.get("outbound"):
        problems.append(f"outbound connections while loading: {', '.join(after['outbound'])}")
    return differences, problems


def changed_files(root: Path, ref: str, config: dict) -> list[str]:
    """Files changed since the ref, including new files not yet added to git."""
    def git(*args: str) -> list[str]:
        return subprocess.run(["git", *args, "--", *config["coldDirs"]], cwd=root, capture_output=True, text=True,
                              check=True).stdout.splitlines()
    files = set(git("diff", "--name-only", "--diff-filter=AMR", ref)) | set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(f for f in files if f.endswith(".py") and not any(x in f for x in config["coldIgnore"]))


def snapshot_of_ref(root: Path, ref: str, config_args: list[str], tests: bool) -> dict:
    temp = Path(tempfile.mkdtemp(prefix="shape-ref-"))
    tree = temp / "tree"
    subprocess.run(["git", "worktree", "add", "--detach", str(tree), ref], cwd=root, capture_output=True, check=True)
    try:
        out = temp / "snapshot.json"
        args = [sys.executable, __file__, "--root", str(tree), "--out", str(out), *config_args]
        if tests:
            args.append("--tests")
        result = subprocess.run(args, cwd=tree, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise SystemExit(f"snapshot of {ref} failed: {result.stderr[-800:]}")
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=root, capture_output=True)
        shutil.rmtree(temp, ignore_errors=True)


def report(differences: list[str], problems: list[str], label: str) -> int:
    for p in problems:
        print(f"PROBLEM {p}")
    if differences:
        print(f"{len(differences)} difference(s) from {label}:")
        for line in differences[:200]:
            print(f"  {line}")
        if len(differences) > 200:
            print(f"  … {len(differences) - 200} more")
    if not differences and not problems:
        print(f"Shape unchanged from {label}.")
    return 1 if differences or problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--config")
    parser.add_argument("--modules")
    parser.add_argument("--tests", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--compare")
    parser.add_argument("--compare-ref")
    parser.add_argument("--describe", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    config_args = (["--config", str(Path(args.config).resolve())] if args.config else []) + (["--modules", args.modules] if args.modules else [])
    config = load_config(root, args.config, args.modules)

    if args.describe:
        data = describe_file(root / args.describe, root, config, args.tests)
        print("SHAPE-PY " + json.dumps(data))
        return 0

    cold = sorted(set(config["modules"]) | set(changed_files(root, args.compare_ref, config))) if args.compare_ref else []
    cold = [f for f in cold if (root / f).is_file()]
    snapshot = take_snapshot(root, config, config_args, args.tests, cold)
    if args.compare_ref:
        return report(*compare(snapshot_of_ref(root, args.compare_ref, config_args, args.tests), snapshot, config["modules"]), args.compare_ref)
    if args.compare:
        return report(*compare(json.loads(Path(args.compare).read_text(encoding="utf-8")), snapshot, config["modules"]), args.compare)
    text = json.dumps(snapshot, indent=1) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
