"""Plan R24, rule 5: run_all.py in a checkout whose memory holds a live-looking store configuration.

A temporary brain holds a copy of this skill and, in its memory, an enabled configuration of an
invented person. There the guard refuses a test file run directly; run_all.py runs the same file to a
pass from its throwaway brain, where the file's view of the store is "off" and every path the store
would default is inside the container; the file that failed on 24 November
(test_secret_store_round6.py) passes through run_all.py; and the container is gone afterwards."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
INVENTED_CONFIG = {"enabled": True, "person": "avery-example", "computer": "example-pc"}
CONTAINER_LINE = re.compile(r"^throwaway brain: (?P<folder>.+) \(container (?P<container>.+)\)$", re.M)

VIEW = '''import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portable_vault  # noqa: E402
from secret_store import store_ops  # noqa: E402


def inside(path, folder):
    here, top = Path(path).resolve(), Path(folder).resolve()
    return here == top or top in here.parents


class StoreView(unittest.TestCase):
    def test_the_store_is_off_and_every_default_is_in_the_container(self):
        container = os.environ["BRAIN_TEST_CONTAINER"]
        root = portable_vault.find_brain_root()
        self.assertTrue(inside(root, container), root)
        self.assertFalse((root / "memory").exists())
        self.assertFalse(portable_vault.secret_store_enabled())
        config = store_ops.load_config()
        self.assertFalse(config["enabled"])
        for key in ("personal_clone", "team_clone", "checkpoint_dir", "recovery_package_dir"):
            self.assertTrue(inside(config[key], container), key)
'''


class LiveLookingCheckout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.brain = Path(cls._tmp.name) / "brain"
        cls.skill = cls.brain / "shared" / "skills" / "manage-credentials"
        # shared/ whole, as run_all.py copies it: the tests read other shared skills (tasks) too
        shutil.copytree(SKILL.parent.parent, cls.brain / "shared", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (cls.brain / "CONTRACT.md").write_text("contract stand-in\n", "utf-8")
        config = cls.brain / hermetic.CONFIG_RELATIVE
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps(INVENTED_CONFIG), "utf-8")
        (cls.skill / "tests" / "test_store_view.py").write_text(VIEW, "utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_all(self, pattern: str) -> tuple[subprocess.CompletedProcess, Path]:
        done = subprocess.run([sys.executable, str(self.skill / "tests" / "run_all.py"), "--pattern", pattern,
                               "--jobs", "1"], capture_output=True, text=True, timeout=1500)
        found = CONTAINER_LINE.search(done.stdout)
        self.assertIsNotNone(found, done.stdout + done.stderr)
        container = Path(found["container"])
        self.assertFalse(Path(found["folder"]).is_relative_to(self.brain))
        self.assertFalse(container.exists(), "the container was not removed")
        self.assertIn(f"container removed: {container}", done.stdout)
        return done, container

    def test_the_guard_refuses_the_file_run_directly(self):
        done = subprocess.run([sys.executable, "-m", "unittest", "test_store_view"], cwd=self.skill / "tests",
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, hermetic.REFUSED_EXIT, done.stdout + done.stderr)
        self.assertIn("run the folder with tests/run_all.py", done.stderr)

    def test_run_all_runs_it_to_a_pass_with_the_store_off(self):
        done, _container = self.run_all("test_store_view.py")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok    test_store_view.py: 1 tests", done.stdout)
        self.assertIn("Total: 1 files, 1 tests, 0 failed", done.stdout)

    def test_the_file_that_failed_on_24_november_passes_through_run_all(self):
        done, _container = self.run_all("test_secret_store_round6.py")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"ok    test_secret_store_round6\.py: \d+ tests")


if __name__ == "__main__":
    unittest.main()
