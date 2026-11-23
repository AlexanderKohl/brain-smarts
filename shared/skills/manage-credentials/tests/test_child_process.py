"""Children without a console window (plan R23, rules 1 to 3 and tests (a) to (c) of rule 5).

(a) a scan of the skill's scripts (the syntax tree) finds no module but child_process.py that starts
a process, except the three calls that run the person's own command; (b) a store opened, synced and
written to in a temporary folder passes NO_WINDOW on every call; (c) on Windows, for real: a parent
without a console starts a child through the helper, which has no console window, and the same child
with plain subprocess.run, which has one. Every remote is a bare repository in a temporary folder."""
import ast
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import child_process  # noqa: E402
import test_secret_store_store as store_case  # noqa: E402

LAUNCHERS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
# The three calls that run the person's own command in the person's console (rule 3), by module and the
# function that holds them, with how many: vaultctl.py run; vault_credentials.py run and session.
OWN_COMMAND_CALLS = {("vault_credentials.py", "main"): 2, ("vaultctl.py", "main"): 1}


def setUpModule():
    store_case.setUpModule()


def tearDownModule():
    store_case.tearDownModule()


def launches(tree: ast.Module) -> list[tuple[str, int]]:
    """(enclosing function, line) for every reference to a process launcher: subprocess.<launcher>
    through any alias, a launcher imported from subprocess by name, and os.system."""
    modules, names = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "os"):
                    modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os") and node.level == 0:
            for alias in node.names:
                if (node.module, alias.name) in {("os", "system")} or (
                        node.module == "subprocess" and alias.name in LAUNCHERS | {"*"}):
                    names.add(alias.asname or alias.name)
    found = []

    def walk(node: ast.AST, scope: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope + [child.name] if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else scope
            where = ".".join(inner) or "<module>"
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                module = modules.get(child.value.id)
                if (module == "subprocess" and child.attr in LAUNCHERS) or (module == "os" and child.attr == "system"):
                    found.append((where, child.lineno))
            elif isinstance(child, ast.Name) and child.id in names:
                found.append((where, child.lineno))
            elif isinstance(child, ast.ImportFrom) and child.module in ("subprocess", "os"):
                if any(a.name in LAUNCHERS | {"system", "*"} for a in child.names):
                    found.append((where, child.lineno))
            walk(child, inner)
    walk(tree, [])
    return found


class ScanTests(unittest.TestCase):
    """(a) No module but the helper starts a process; the three own-command calls are named."""

    def test_only_the_helper_starts_a_process(self):
        seen: dict[tuple[str, str], int] = {}
        for path in sorted(SCRIPTS.rglob("*.py")):
            rel = path.relative_to(SCRIPTS).as_posix()
            if rel == "child_process.py":
                continue
            for where, line in launches(ast.parse(path.read_text("utf-8"), filename=str(path))):
                seen[(rel, where)] = seen.get((rel, where), 0) + 1
        self.assertEqual(seen, OWN_COMMAND_CALLS)

    def test_the_scan_sees_every_form(self):
        sample = textwrap.dedent("""
            import subprocess as sp
            import os
            from subprocess import check_output as co
            def a(): sp.run(["git"])
            def b(): return sp.Popen
            def c(): co(["gh"])
            def d(): os.system("git")
            runner = sp.call
        """)
        self.assertEqual(sorted(w for w, _ in launches(ast.parse(sample))), ["<module>", "<module>", "a", "b", "c", "d"])


class FlagTests(store_case.StoreCase):
    """(b) Every child of a store's open, sync and write carries NO_WINDOW."""

    def test_every_child_of_the_store_has_no_window(self):
        if sys.platform == "win32":
            self.assertNotEqual(child_process.NO_WINDOW, 0)
        real_run, real_popen, calls = subprocess.run, subprocess.Popen, []

        def record(kind, real):
            def recorder(command, *rest, **options):
                calls.append((kind, list(command)[:2], options.get("creationflags", 0)))
                return real(command, *rest, **options)
            return recorder
        with mock.patch.object(subprocess, "run", record("run", real_run)), \
                mock.patch.object(subprocess, "Popen", record("Popen", real_popen)):
            first, pinned = self.init()
            first.open().put_entry("Example API", {"api_key": store_case.VALUE})
            reopened = self.store("a").open()  # a fresh process's open: fetch, verify, sync
            reopened.put_entry("Example API", {"api_key": store_case.OTHER})
            first._sync(None, first.checkpoint)
        self.assertIn(("Popen", ["git", "commit"]), [(k, c) for k, c, _ in calls])
        self.assertGreater(len(calls), 20)
        missing = [(k, c) for k, c, flags in calls if flags & child_process.NO_WINDOW != child_process.NO_WINDOW]
        self.assertEqual(missing, [])

    def test_the_helper_keeps_the_callers_flags(self):
        with mock.patch.object(subprocess, "run") as run, mock.patch.object(subprocess, "Popen") as popen:
            child_process.run(["git", "status"], cwd="x", creationflags=0x200)
            child_process.popen(["git", "commit"], stdout=subprocess.PIPE)
        run.assert_called_once_with(["git", "status"], cwd="x", creationflags=0x200 | child_process.NO_WINDOW)
        popen.assert_called_once_with(["git", "commit"], stdout=subprocess.PIPE, creationflags=child_process.NO_WINDOW)


CHILD = "import ctypes, sys; open(sys.argv[1], 'w').write(str(ctypes.windll.kernel32.GetConsoleWindow()))"
PARENT = """import subprocess, sys
sys.path.insert(0, sys.argv[1])
import child_process
python, child = sys.argv[2], sys.argv[3]
child_process.run([python, "-c", child, sys.argv[4]], timeout=60)
subprocess.run([python, "-c", child, sys.argv[5]], timeout=60)
"""


@unittest.skipUnless(sys.platform == "win32", "console windows exist on Windows only")
class ConsoleWindowTests(unittest.TestCase):
    """(c) For real: a parent without a console (python.exe with DETACHED_PROCESS, as the tray's
    pythonw has none) starts the same console child through the helper and with plain subprocess.run."""

    def test_the_helpers_child_has_no_console_window(self):
        python = Path(sys.executable).with_name("python.exe")
        with tempfile.TemporaryDirectory() as folder:
            helped, plain = Path(folder) / "helped.txt", Path(folder) / "plain.txt"
            done = subprocess.run([str(python), "-c", PARENT, str(SCRIPTS), str(python), CHILD, str(helped), str(plain)],
                                  creationflags=subprocess.DETACHED_PROCESS, timeout=120,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(done.returncode, 0)
            helped_window, plain_window = int(helped.read_text()), int(plain.read_text())
        if os.environ.get("CHILD_PROCESS_REPORT"):
            Path(os.environ["CHILD_PROCESS_REPORT"]).write_text(
                f"through the helper: {helped_window}\nplain subprocess.run: {plain_window}\n", "utf-8")
        self.assertEqual(helped_window, 0)
        self.assertNotEqual(plain_window, 0, "the plain child had no window either: the test cannot tell")


if __name__ == "__main__":
    unittest.main()
