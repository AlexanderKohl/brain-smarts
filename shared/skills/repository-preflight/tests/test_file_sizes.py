"""SMART-RULE-0041 in the validator (file_sizes.py), on fictional repositories: each way a file can break
the limit fails, what the code map leaves out is left out, and the counting matches the code map's.

Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import file_sizes  # noqa: E402

CODE_MAP_CONFIG = HERE.parents[1] / "code-map" / "scripts" / "lib" / "config.js"
HAS_GIT = shutil.which("git") is not None


def lines(n: int) -> str:
    return "".join(f"value_{i} = {i}\n" for i in range(n))


class Repo:
    """A fictional repository in a temporary folder, adopted with one recorded file of 805 lines."""

    def __init__(self, test: unittest.TestCase, record: dict | None = None, git: bool = True):
        self.root = Path(tempfile.mkdtemp(prefix="file-sizes-"))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.write("code-map.config.json", json.dumps({"recordDir": ".code-map"}))
        if record is not None:
            self.write(".code-map/sizes.json", json.dumps(record))
        if git and HAS_GIT:
            subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def errors(self, prefix: str = "/") -> list[str]:
        return file_sizes.check_repository(self.root, prefix)


class LimitTests(unittest.TestCase):
    def test_a_recorded_file_at_its_size_passes(self):
        repo = Repo(self, {"scripts/big.py": 805})
        repo.write("scripts/big.py", lines(805))
        self.assertEqual(repo.errors(), [])

    def test_a_recorded_file_that_grows_fails(self):
        repo = Repo(self, {"scripts/big.py": 805})
        repo.write("scripts/big.py", lines(806))
        self.assertEqual(repo.errors(), ["/scripts/big.py: grew from its recorded 805 lines to 806; move code out of it "
                                         "rather than into it (SMART-RULE-0041)"])

    def test_a_new_file_over_the_limit_fails(self):
        repo = Repo(self, {})
        repo.write("src/app.js", "let a = 1;\n" * 801)
        repo.write("src/ok.js", "let a = 1;\n" * 800)
        errors = repo.errors("/library/")
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("/library/src/app.js: 801 lines, over the 800-line limit"), errors[0])

    def test_a_recorded_file_that_shrinks_passes(self):
        repo = Repo(self, {"scripts/big.py": 805})
        repo.write("scripts/big.py", lines(300))
        self.assertEqual(repo.errors(), [])

    def test_what_the_code_map_leaves_out(self):
        repo = Repo(self, {})
        repo.write("tests/fixtures/sample.py", lines(900))       # size-exempt
        repo.write("db/migrations/0001_first.py", lines(900))    # size-exempt
        repo.write("node_modules/pkg/index.js", "x;\n" * 900)    # ignored
        repo.write("docs/notes.md", "text\n" * 900)              # not a code file
        repo.write("data/table.json", "{}\n" * 900)              # not a code file
        repo.write("app.min.js", "x;\n" * 900)                   # ignored
        self.assertEqual(repo.errors(), [])

    @unittest.skipUnless(HAS_GIT, "git is not available")
    def test_a_git_ignored_file_is_not_counted(self):
        repo = Repo(self, {})
        repo.write(".gitignore", "scratch/\n")
        repo.write("scratch/probe.py", lines(900))
        self.assertEqual(repo.errors(), [])

    def test_the_repository_s_own_patterns_add_to_the_defaults(self):
        repo = Repo(self, {})
        repo.write("code-map.config.json", json.dumps({"recordDir": ".code-map", "sizeExemptMore": ["generated_api/**"]}))
        repo.write("generated_api/client.py", lines(900))
        repo.write("tests/fixtures/sample.py", lines(900))
        self.assertEqual(repo.errors(), [])

    def test_a_repository_without_a_record_is_not_checked(self):
        repo = Repo(self, None)
        repo.write("src/app.py", lines(900))
        self.assertEqual(repo.errors(), [])

    def test_lines_are_counted_as_the_code_map_counts_them(self):
        self.assertEqual(file_sizes.count_lines(""), 0)
        self.assertEqual(file_sizes.count_lines("a"), 1)
        self.assertEqual(file_sizes.count_lines("a\n"), 1)
        self.assertEqual(file_sizes.count_lines("a\nb"), 2)
        self.assertEqual(file_sizes.count_lines("a\n\n"), 2)

    @unittest.skipUnless(HAS_GIT, "git is not available")
    def test_the_brain_s_three_repositories(self):
        brain = Path(tempfile.mkdtemp(prefix="file-sizes-brain-"))
        self.addCleanup(shutil.rmtree, brain, True)
        (brain / ".gitignore").write_text("library/\nmemory/\n", encoding="utf-8")
        for folder, prefix in (("", "/"), ("library", "/library/"), ("memory", "/memory/")):
            repo = brain / folder
            (repo / ".code-map").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "code-map.config.json").write_text(json.dumps({"recordDir": ".code-map"}), encoding="utf-8")
            (repo / ".code-map" / "sizes.json").write_text("{}", encoding="utf-8")
            (repo / "tool.py").write_text(lines(801), encoding="utf-8")
        errors: list[str] = []
        file_sizes.validate_file_sizes(brain, errors)
        self.assertEqual(sorted(e.split(":")[0] for e in errors), ["/library/tool.py", "/memory/tool.py", "/tool.py"])


class SameAsTheCodeMapTests(unittest.TestCase):
    """The lists are copies of the code map's; this fails when one changes without the other."""

    def js_list(self, key: str) -> list[str]:
        text = CODE_MAP_CONFIG.read_text(encoding="utf-8")
        m = re.search(rf"\n  {key}: \[(.*?)\],\n", text, re.S)
        self.assertIsNotNone(m, key)
        return re.findall(r"'([^']*)'", m.group(1))

    def test_patterns_and_extensions(self):
        self.assertEqual(self.js_list("ignore"), file_sizes.IGNORE)
        self.assertEqual(self.js_list("sizeExempt"), file_sizes.SIZE_EXEMPT)
        self.assertEqual(self.js_list("codeExtensions"), file_sizes.CODE_EXTENSIONS)

    def test_limit_and_record_folder(self):
        text = CODE_MAP_CONFIG.read_text(encoding="utf-8")
        self.assertIn(f"fileLines: {file_sizes.FILE_LINES}", text)
        self.assertIn(f"recordDir: '{file_sizes.RECORD_DIR}'", text)

    def test_glob_matching(self):
        cases = [("**/fixtures/**", "a/fixtures/b.py", True), ("**/fixtures/**", "fixtures/b.py", True),
                 ("**/*.min.js", "x.min.js", True), ("**/*.min.js", "a/b/x.min.js", True),
                 ("src/*.py", "src/a/b.py", False), ("src/?.py", "src/a.py", True), ("**/*.d.ts", "a.ts", False)]
        for glob, path, expected in cases:
            self.assertEqual(bool(file_sizes.matches_any(path, [glob])), expected, (glob, path))


if __name__ == "__main__":
    unittest.main()
