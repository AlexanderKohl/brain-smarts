"""Tests for the two removed-files registers (PROPOSAL-memory-removed-files-register).

A closed proposal's target_files may name a file removed since; the preflight accepts it only when
the register for that file's layer lists it: /governance/removed-files.md for mechanics paths,
/memory/governance/removed-files.md for /memory/ paths. Every fixture is invented (SMART-RULE-0008).

Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from preflight_base import Result  # noqa: E402
from preflight_references import removed_files, validate_declared_references  # noqa: E402

HEADER = "| File | Removed | Where its content went |\n|---|---|---|\n"
GONE_MEMORY = "/memory/projects/example-project/README.md"
GONE_MECHANICS = "/shared/skills/example-skill/SKILL.md"


class RemovedFilesRegisterTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "memory" / "governance").mkdir(parents=True)
        (self.root / "governance").mkdir()

    def register(self, relative: str, *paths: str) -> None:
        rows = "".join(f"| `{p}` | 2026-01-01 | Moved to the example project's own repository |\n"
                       for p in paths)
        (self.root / relative).write_text("# Removed files\n\n" + HEADER + rows, encoding="utf-8")

    def errors_for(self, target: str) -> list[str]:
        proposal = self.root / "memory" / "governance" / "proposals" / "example.md"
        records = {proposal: {"status": "accepted", "target_files": [target]}}
        result = Result()
        validate_declared_references(self.root, records, result)
        return result.errors

    def test_removed_memory_file_fails_without_memory_register_row(self) -> None:
        self.register("memory/governance/removed-files.md")
        errors = self.errors_for(GONE_MEMORY)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(GONE_MEMORY, errors[0])

    def test_removed_memory_file_passes_with_memory_register_row(self) -> None:
        self.register("memory/governance/removed-files.md", GONE_MEMORY)
        self.assertEqual(self.errors_for(GONE_MEMORY), [])

    def test_memory_row_in_mechanics_register_is_ignored(self) -> None:
        self.register("governance/removed-files.md", GONE_MEMORY)
        self.assertNotIn(GONE_MEMORY, removed_files(self.root))
        self.assertEqual(len(self.errors_for(GONE_MEMORY)), 1)

    def test_mechanics_path_in_memory_register_is_ignored(self) -> None:
        self.register("memory/governance/removed-files.md", GONE_MECHANICS)
        self.assertNotIn(GONE_MECHANICS, removed_files(self.root))
        self.assertEqual(len(self.errors_for(GONE_MECHANICS)), 1)

    def test_mechanics_path_in_mechanics_register_still_passes(self) -> None:
        self.register("governance/removed-files.md", GONE_MECHANICS)
        self.assertEqual(self.errors_for(GONE_MECHANICS), [])

    def test_memory_register_ignored_when_memory_absent(self) -> None:
        self.register("memory/governance/removed-files.md", GONE_MEMORY)
        shutil.rmtree(self.root / "memory")
        self.assertEqual(removed_files(self.root), set())


if __name__ == "__main__":
    unittest.main()
