"""Plan R24, the guard and the barriers (tests/hermetic.py, tests/run_all.py, hermetic_site/).

(a) every test file of this folder imports the guard first, and a file that does not is found;
(b) the guard refuses a whole test process in a temporary brain whose memory holds the store's
configuration (enabled true, enabled false, unreadable, a folder in its place) before any test runs,
and passes in one without it; it and the harness import nothing that could reach a keychain, clone
or agent; (c) the barriers, from this test process and from a child it starts the way the tests
start their agents and commands (inherited environment, no import of the guard): host folders in
the container, no cloud-drive variable, the refusing keyring, the run's test pipe name and the
refusing gh, also through the scripts' own child launcher. Every brain here is invented."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
DEFAULT_PIPE = r"\\.\pipe\PortableAIBrainVaultAgent"
GUARD_LINE = "import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)"
HARNESS_IMPORTS = frozenset({  # the standard library, and pip's launcher for the refusing gh.exe
    "__future__", "argparse", "atexit", "concurrent.futures", "dataclasses", "importlib.util", "os", "pathlib",
    "pip._vendor.distlib.scripts", "re", "secrets", "shutil", "site", "stat", "subprocess", "sys", "tempfile",
    "time", "typing"})
INVENTED_CONFIG = {"enabled": True, "person": "avery-example", "computer": "example-pc"}


def guard_first(source: str) -> bool:
    """Whether the first statement after the docstring and __future__ imports is `import hermetic`."""
    body = ast.parse(source).body
    index = 1 if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
        and isinstance(body[0].value.value, str) else 0
    while index < len(body) and isinstance(body[index], ast.ImportFrom) and body[index].module == "__future__":
        index += 1
    if index >= len(body):
        return False
    first = body[index]
    return isinstance(first, ast.Import) and [(a.name, a.asname) for a in first.names] == [("hermetic", None)]


def inside(path: object, folder: object) -> bool:
    here, top = Path(str(path)).resolve(), Path(str(folder)).resolve()
    return here == top or top in here.parents


# The probe: what a process sees. A child runs it with python -c and the inherited environment only.
PROBE = textwrap.dedent('''
    import json, os, shutil, sys, tempfile
    from pathlib import Path


    def probe(scripts):
        sys.path.insert(0, scripts)
        import child_process, keyring, portable_vault, vault_agent_runtime
        from secret_store import keys, store_ops
        from secret_store.errors import SecretStoreError
        try:
            keys._backend()
            refused = None
        except SecretStoreError as error:
            refused = str(error)
        try:
            keyring.get_password("brain-secrets", "probe@probe")
            direct = None
        except Exception as error:
            direct = type(error).__name__
        gh = child_process.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=60)
        place, cloud = store_ops.recovery_package_place()
        backend = keyring.get_keyring()
        site = sys.modules.get("sitecustomize")
        return {"env": {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
                                                        "XDG_RUNTIME_DIR", "TEMP", "BRAIN_TEST_PIPE_NAME")},
                "cloud_variables": sorted(k for k in os.environ if k.upper().startswith("ONEDRIVE")),
                "home": str(Path.home()), "temp": tempfile.gettempdir(),
                "runtime_base": str(vault_agent_runtime.runtime_base()),
                "ipc_address": str(vault_agent_runtime.ipc_address()),
                "app_data": str(store_ops.app_data_dir()), "recovery": str(place), "cloud": cloud,
                "backend": f"{type(backend).__module__}.{type(backend).__qualname__}",
                "backend_refused": refused, "direct_keyring": direct,
                "gh_code": gh.returncode, "gh_error": gh.stderr, "gh_path": shutil.which("gh"),
                "store_on": portable_vault.secret_store_enabled(), "brain": str(portable_vault.find_brain_root()),
                "sitecustomize": getattr(site, "__file__", None), "guard_imported": "hermetic" in sys.modules}
''')


class GuardImportedFirst(unittest.TestCase):
    def test_every_test_file_imports_the_guard_first(self):
        files = sorted(HERE.glob("test_*.py"))
        self.assertGreater(len(files), 1)
        missing = [p.name for p in files if not guard_first(p.read_text("utf-8"))]
        self.assertEqual(missing, [], "these test files do not import hermetic first")

    def test_a_file_that_does_not_is_found(self):
        self.assertTrue(guard_first(f'"""doc"""\nfrom __future__ import annotations\n{GUARD_LINE}\nimport os\n'))
        self.assertFalse(guard_first('"""doc"""\nimport os\n' + GUARD_LINE + "\n"))
        self.assertFalse(guard_first('"""doc"""\nimport sys\nsys.path.insert(0, "x")\n'))
        self.assertFalse(guard_first('"""doc"""\nimport hermetic as h\n'))
        self.assertFalse(guard_first('"""doc"""\n'))


class Guard(unittest.TestCase):
    """A temporary brain holding a copy of the harness, with and without the configuration file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.brain = Path(self._tmp.name) / "brain"
        self.tests = self.brain / "shared" / "skills" / "manage-credentials" / "tests"
        shutil.copytree(HERE / "hermetic_site", self.tests / "hermetic_site",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("hermetic.py", "run_all.py"):
            shutil.copy2(HERE / name, self.tests / name)
        (self.brain / "CONTRACT.md").write_text("contract stand-in\n", "utf-8")
        # A test file that leaves a marker when any of its tests runs.
        (self.tests / "test_marker.py").write_text(
            f"{GUARD_LINE}\nimport unittest\nfrom pathlib import Path\n\n\nclass Marker(unittest.TestCase):\n"
            "    def test_runs(self):\n        Path(__file__).with_name('ran.marker').write_text('x')\n", "utf-8")
        self.config = self.brain / hermetic.CONFIG_RELATIVE

    def _child(self, *argv):
        return subprocess.run([sys.executable, *argv], cwd=self.tests, capture_output=True, text=True, timeout=120)

    def _assert_refused(self):
        done = self._child("-m", "unittest", "test_marker")
        self.assertEqual(done.returncode, hermetic.REFUSED_EXIT, done.stdout + done.stderr)
        self.assertIn("this checkout holds a live secrets-store configuration", done.stderr)
        self.assertIn(str(self.config), done.stderr)
        self.assertIn("tests/run_all.py", done.stderr)
        self.assertNotIn("Ran ", done.stdout + done.stderr)
        self.assertFalse((self.tests / "ran.marker").exists(), "a test ran before the guard refused")

    def _write(self, data: bytes):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_bytes(data)

    def test_it_refuses_an_enabled_configuration(self):
        self._write(json.dumps(INVENTED_CONFIG).encode())
        self._assert_refused()

    def test_it_refuses_a_disabled_one_without_reading_it(self):
        self._write(json.dumps({**INVENTED_CONFIG, "enabled": False}).encode())
        self._assert_refused()

    def test_it_refuses_an_unreadable_one(self):
        self._write(b"\xff\xfe not json")
        self._assert_refused()

    def test_it_refuses_a_folder_in_its_place(self):
        self.config.mkdir(parents=True)
        self._assert_refused()

    def test_it_passes_without_the_file(self):
        (self.brain / "memory" / "skills").mkdir(parents=True)  # a memory, but no store configuration
        done = self._child("-m", "unittest", "test_marker")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.tests / "ran.marker").exists())

    def test_the_harness_imports_nothing_that_reaches_a_keychain_clone_or_agent(self):
        for path in (HERE / "hermetic.py", HERE / "run_all.py", HERE / "hermetic_site" / "sitecustomize.py"):
            names = set()
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if isinstance(node, ast.Import):
                    names |= {a.name for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names.add(node.module)
            self.assertEqual(sorted(names - HARNESS_IMPORTS), [], path.name)
        self.assertNotIn("open(", (HERE / "hermetic.py").read_text("utf-8"))


class Barriers(unittest.TestCase):
    """Each barrier of the amendments, in this process and in a child that never imports the guard."""

    @classmethod
    def setUpClass(cls):
        namespace: dict = {}
        exec(PROBE, namespace)  # noqa: S102 - the same probe the child runs, in this process
        cls.here = namespace["probe"](str(SCRIPTS))
        done = subprocess.run([sys.executable, "-c", PROBE + "\nprint(json.dumps(probe(sys.argv[1])))\n", str(SCRIPTS)],
                              capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise AssertionError(f"the child probe failed: {done.stderr}")
        cls.child = json.loads(done.stdout)
        cls.container = Path(os.environ["BRAIN_TEST_CONTAINER"])
        cls.pipe = os.environ["BRAIN_TEST_PIPE_NAME"]

    def views(self):
        return (("this process", self.here), ("a child", self.child))

    def test_the_child_did_not_import_the_guard(self):
        self.assertFalse(self.child["guard_imported"])
        self.assertTrue(inside(self.child["sitecustomize"], self.container), self.child["sitecustomize"])

    def test_host_folders_are_in_the_container(self):
        for who, view in self.views():
            for key in ("home", "temp", "runtime_base", "app_data"):
                self.assertTrue(inside(view[key], self.container), f"{who}: {key} {view[key]}")
            for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_RUNTIME_DIR", "TEMP"):
                self.assertTrue(inside(view["env"][key], self.container), f"{who}: {key}")

    def test_no_cloud_drive_is_found(self):
        for who, view in self.views():
            self.assertEqual(view["cloud_variables"], [], who)
            self.assertFalse(view["cloud"], who)
            self.assertTrue(inside(view["recovery"], self.container), who)

    def test_the_keyring_refuses(self):
        for who, view in self.views():
            self.assertEqual(view["backend"], "keyring.backends.fail.Keyring", who)
            self.assertIn("not on the allowlist", view["backend_refused"] or "", who)
            self.assertEqual(view["direct_keyring"], "NoKeyringError", who)

    def test_the_agent_pipe_is_the_runs_own(self):
        self.assertTrue(self.pipe.startswith("PortableAIBrainVaultAgent-test-"))
        for who, view in self.views():
            self.assertEqual(view["env"]["BRAIN_TEST_PIPE_NAME"], self.pipe, who)
            self.assertNotEqual(view["ipc_address"].lower(), DEFAULT_PIPE.lower(), who)
            if os.name == "nt":
                self.assertEqual(view["ipc_address"], rf"\\.\pipe\{self.pipe}", who)
            else:
                self.assertTrue(inside(view["ipc_address"], self.container), who)

    def test_gh_refuses(self):
        for who, view in self.views():
            self.assertNotEqual(view["gh_code"], 0, who)
            self.assertIn("gh refused", view["gh_error"], who)
            self.assertTrue(inside(view["gh_path"], self.container / "bin"), f"{who}: {view['gh_path']}")

    def test_the_store_is_off_in_a_brain_without_memory(self):
        for who, view in self.views():
            self.assertFalse(view["store_on"], who)
            self.assertFalse((Path(view["brain"]) / hermetic.CONFIG_RELATIVE).exists(), who)


if __name__ == "__main__":
    unittest.main()
