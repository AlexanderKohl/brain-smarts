"""The Python split tools on a fictional app (tests/fixtures/py_app): each move keeps the module's
shape and behaviour and moves text unchanged; each refusal fires; planted faults are caught.

Run from the brain root:
    python -m unittest discover -s shared/skills/split-file/tests
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TOOLS = SKILL / "scripts" / "py"
FIXTURE = SKILL / "tests" / "fixtures" / "py_app"
HAS_GIT = shutil.which("git") is not None


def copy_app() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="split-py-"))
    shutil.copytree(FIXTURE, folder / "app")
    return folder / "app"


def tool(name: str, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOLS / name), *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8")


def behaviour(app: Path) -> str:
    script = ("import garden, json; print(json.dumps([garden.report(), garden.clean_name(' Fern '), "
              "garden.leaf_count('Ivy'), garden.describe(garden.Plant('Mint')), garden.MAX_BEDS]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=app, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


def run_checks(app: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "check_*.py"], cwd=app,
                          capture_output=True, text=True, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.app = copy_app()
        self.addCleanup(shutil.rmtree, self.app.parent, True)

    def read(self, name: str) -> str:
        return (self.app / name).read_text(encoding="utf-8")

    def shape(self, *args: str, modules: str = "garden.py") -> subprocess.CompletedProcess:
        return tool("shape.py", "--root", str(self.app), "--modules", modules, *args, cwd=self.app)

    def snapshot(self, modules: str = "garden.py", tests: bool = False) -> str:
        out = str(self.app.parent / "before.json")
        r = self.shape("--out", out, *(["--tests"] if tests else []), modules=modules)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def move(self, *args: str) -> subprocess.CompletedProcess:
        return tool("move.py", "garden.py", *args, cwd=self.app)


class MoveTests(Base):
    def test_moves_unchanged_and_keeps_shape_and_behaviour(self):
        before = self.snapshot()
        was = behaviour(self.app)
        original = self.read("garden.py").split("\n")
        r = self.move("--to", "names", "--names", "NAME_RE,clean_name", "--ref", "TASK-0000-0003")
        self.assertEqual(r.returncode, 0, r.stderr)
        moved = self.read("names.py")
        self.assertIn("\n".join(original[29:35]), moved)  # clean_name with its comment
        self.assertIn('NAME_RE = re.compile(r"^[A-Za-z ]{1,40}$")', moved)
        self.assertIn("from __future__ import annotations\n\nimport re\n", moved)
        self.assertIn("Moved unchanged from garden.py (TASK-0000-0003).", moved)
        self.assertIn("from names import NAME_RE, clean_name  # noqa: E402", self.read("garden.py"))
        self.assertEqual(behaviour(self.app), was)
        r = self.shape("--compare", before)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(run_checks(self.app).returncode, 0)

    def test_copies_path_setup_the_imports_need(self):
        before = self.snapshot()
        r = self.move("--to", "leaves", "--names", "leaf_count")
        self.assertEqual(r.returncode, 0, r.stderr)
        moved = self.read("leaves.py")
        for line in ('HERE = Path(__file__).resolve().parent', 'sys.path.insert(0, str(HERE / "vendor"))',
                     "import leafutil  # noqa: E402", "import sys", "from pathlib import Path"):
            self.assertIn(line, moved)
        self.assertNotIn("DATA =", moved)
        self.assertEqual(self.shape("--compare", before).returncode, 0)

    def test_moves_a_dataclass_with_the_code_that_uses_it(self):
        before = self.snapshot()
        r = self.move("--to", "plants", "--names", "Plant,describe")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("from dataclasses import dataclass, field", self.read("plants.py"))
        self.assertEqual(self.shape("--compare", before).returncode, 0)
        self.assertEqual(run_checks(self.app).returncode, 0)

    def test_refusals(self):
        cases = [
            (["clean_name"], "NAME_RE (line 17) stays in the source"),
            (["cached_plants"], "declares global _cache"),
            (["module_name"], "uses __name__, which means something else"),
            (["watering_days"], "check_garden.py:35 patches garden.watering_days"),
            (["report"], "patches garden.watering_days"),
            (["started"], "runs code when loaded (leafutil.stamp())"),
            (["_cache"], "declares global _cache, which moves"),
            (["missing_name"], "not found at top level: missing_name"),
            (["os"], "not found at top level: os"),
        ]
        for names, message in cases:
            with self.subTest(names=names):
                original = self.read("garden.py")
                r = self.move("--to", "moved", "--names", ",".join(names))
                self.assertEqual(r.returncode, 1, f"{names} was not refused: {r.stdout}")
                self.assertIn(message, r.stderr)
                self.assertEqual(self.read("garden.py"), original)
                self.assertFalse((self.app / "moved.py").exists())
        r = self.move("--to", "json", "--names", "describe")
        self.assertIn("standard-library module", r.stderr)
        self.assertEqual(self.move("--to", "moved", "--names", "started", "--allow-load-order").returncode, 0)
        # It sat directly under another statement: the two blank lines after it stay.
        self.assertIn("_cache = None\n\n\n@dataclass", self.read("garden.py").replace("\r\n", "\n"))


class TestFileSplitTests(Base):
    def test_splits_a_test_file_without_loading_back(self):
        modules = "check_garden.py,check_report.py"
        before = self.snapshot(modules, tests=True)
        r = tool("move.py", "check_garden.py", "--to", "check_report", "--names", "ReportTests", "--no-load-back",
                 cwd=self.app)
        self.assertEqual(r.returncode, 0, r.stderr)
        moved = self.read("check_report.py")
        self.assertIn("from check_garden import make_plant", moved)
        self.assertIn("import garden  # noqa: E402", moved)
        self.assertIn("sys.path.insert(0, str(HERE))", moved)
        self.assertNotIn("ReportTests", self.read("check_garden.py"))
        r = self.shape("--compare", before, "--tests", modules=modules)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        checks = run_checks(self.app)
        self.assertEqual(checks.returncode, 0, checks.stderr)
        self.assertIn("Ran 5 tests", checks.stderr)


class ShapeTests(Base):
    def test_catches_planted_faults(self):
        faults = [
            ("a changed function body", '{"herb": 2, "tree": 7}', '{"herb": 2, "tree": 8}', "watering_days"),
            ("a lost name", "MAX_BEDS = 12\n", "", "MAX_BEDS"),
            ("a changed constant", "MAX_BEDS = 12", "MAX_BEDS = 13", "MAX_BEDS"),
            ("a changed dataclass field", 'kind: str = "herb"', 'kind: str = "tree"', "Plant"),
            ("an outbound connection", "started = leafutil.stamp()",
             "started = leafutil.stamp()\n__import__('socket').create_connection(('example.com', 80))", "outbound"),
        ]
        for label, old, new, expected in faults:
            with self.subTest(label):
                app = copy_app()
                self.addCleanup(shutil.rmtree, app.parent, True)
                out = str(app.parent / "before.json")
                self.assertEqual(tool("shape.py", "--root", str(app), "--modules", "garden.py", "--out", out, cwd=app).returncode, 0)
                text = (app / "garden.py").read_text(encoding="utf-8")
                self.assertIn(old, text)
                (app / "garden.py").write_text(text.replace(old, new, 1), encoding="utf-8")
                r = tool("shape.py", "--root", str(app), "--modules", "garden.py", "--compare", out, cwd=app)
                self.assertEqual(r.returncode, 1, f"{label} was not caught")
                self.assertIn(expected, r.stdout)

    @unittest.skipUnless(HAS_GIT, "git is not available")
    def test_compare_ref_loads_every_changed_file_alone(self):
        def git(*args):
            subprocess.run(["git", "-c", "user.name=Example", "-c", "user.email=split@example.com", *args],
                           cwd=self.app, capture_output=True, check=True)
        git("init", "-q")
        git("add", ".")
        git("commit", "-q", "-m", "fixture")
        self.assertEqual(self.move("--to", "names", "--names", "NAME_RE,clean_name").returncode, 0)
        r = self.shape("--compare-ref", "HEAD")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with (self.app / "names.py").open("a", encoding="utf-8") as f:
            f.write("\nimport garden_missing\n")
        r = self.shape("--compare-ref", "HEAD")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PROBLEM loading alone failed: names.py", r.stdout)


class AnalyseTests(Base):
    def test_lists_statements_and_graph(self):
        r = tool("analyse.py", "garden.py", cwd=self.app)
        self.assertIn("def      clean_name  <- NAME_RE", r.stdout)
        r = tool("analyse.py", "garden.py", "--graph", "--flag", "water", cwd=self.app)
        lines = r.stdout.splitlines()
        order = [line.split()[2 if "*" not in line.split()[2] else 3] for line in lines]
        self.assertLess(order.index("NAME_RE"), order.index("clean_name"))
        self.assertTrue(any("* watering_days" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
