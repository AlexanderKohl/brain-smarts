"""The fictional brain the ingestion tests build (SMART-RULE-0008), and what they read back from it.

Each test builds one in a temporary folder and ingests fictional files; the script finds the brain
from its working directory.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_raw.py"
STAMP = "2026-01-05T09:00:00+00:00"


def front_matter(id_: str, type_: str) -> str:
    return (f"---\nid: {id_}\ntitle: {id_}\ntype: {type_}\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            f"created: {STAMP}\nupdated: {STAMP}\n---\n")


class Brain:
    """A fictional brain: a contract, a memory checkout, one project node and the ingestion log."""

    def __init__(self, folder: Path):
        self.root = folder / "brain"
        self.memory = self.root / "memory"
        self.node = self.memory / "projects" / "orchard-club"
        self.node.mkdir(parents=True)
        (self.root / "CONTRACT.md").write_text(front_matter("brain-contract", "contract"), encoding="utf-8")
        (self.node / "LOG.md").write_text(front_matter("orchard-club-log", "log") + "\n# Activity Log\n",
                                          encoding="utf-8")
        log = self.memory / "systems" / "raw-file-management" / "LOG.md"
        log.parent.mkdir(parents=True)
        log.write_text(front_matter("raw-file-management-log", "log") + "\n# Activity Log\n", encoding="utf-8")
        self.log = log
        self.inbox = folder / "inbox"
        self.inbox.mkdir()

    def sample(self, name: str, content: bytes | str) -> Path:
        path = self.inbox / name
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def ingest(self, path: Path, *extra: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), str(path), *extra], cwd=cwd or self.root,
                              capture_output=True, text=True, encoding="utf-8")

    def ingest_ok(self, path: Path, *extra: str) -> dict:
        done = self.ingest(path, *extra)
        if done.returncode:
            raise AssertionError(f"ingest failed ({done.returncode}): {done.stderr}")
        return json.loads(done.stdout)

    def converted(self, name: str, content: bytes | str) -> tuple[dict, str]:
        """Ingest a new sample; the script's result and the text of the source record it made."""
        result = self.ingest_ok(self.sample(name, content))
        return result, self.file(result["canonical_markdown"]).read_text(encoding="utf-8")

    def file(self, repo_path: str) -> Path:
        return self.root / repo_path.lstrip("/")

    def records(self) -> list[Path]:
        return sorted((self.memory / "sources").glob("*.md"))


class IngestTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Brain(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


def headings_outside_fences(markdown: str) -> list[str]:
    """The Markdown headings a reader sees: `#` lines that are not inside a fenced block."""
    found: list[str] = []
    opener = ""
    for line in markdown.splitlines():
        ticks = re.match(r"`{3,}", line)
        if ticks and not opener:
            opener = ticks.group(0)
        elif opener and re.fullmatch(r"`{%d,}\s*" % len(opener), line):
            opener = ""
        elif not opener and line.startswith("#"):
            found.append(line)
    return found


def extracted(record: str) -> str:
    """The record's extracted content: everything under its `## Extracted content` heading."""
    return record.split("\n## Extracted content\n\n", 1)[1]

