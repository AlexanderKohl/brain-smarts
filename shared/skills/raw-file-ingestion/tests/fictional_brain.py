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



def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=sam", "-c", "user.email=sam@example.com",
                           "-c", "init.defaultBranch=main", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout


class StoreBrain(Brain):
    """A fictional brain with every kind of raw store (P13): the owner's /memory/raw/, a memory node
    `hedgerow`, a pointer node `cider-press` whose repository is checked out beside the brain with
    brain/ on its store branch, and the folder `orchard-club`, which is in no node.

    The owner is Sam Rowan (author `sam`). A node's README can be left out at first, so a source
    ingested then lands where the brain kept every source before P13: /memory/sources/ with a
    reference in the folder."""

    def __init__(self, folder: Path, readmes: bool = True):
        super().__init__(folder)
        self.repos = folder / "repos"
        (self.memory / "OWNER.md").write_text(
            "---\nid: owner-profile\nowner_name: Sam Rowan\nowner_short_name: Sam\ntimezone: UTC (+00:00)\n"
            f"project_repos_root: {self.repos.as_posix()}\n---\n", encoding="utf-8")
        self.hedgerow = self.memory / "projects" / "hedgerow"
        self.pointer = self.memory / "projects" / "cider-press"
        for node in (self.hedgerow, self.pointer):
            node.mkdir(parents=True)
            (node / "LOG.md").write_text(front_matter(f"{node.name}-log", "log") + "\n# Activity Log\n",
                                         encoding="utf-8")
        if readmes:
            self.readmes()
        self.checkout = self.repos / "cider-press"
        (self.checkout / "brain").mkdir(parents=True)
        (self.checkout / "brain" / "README.md").write_text(front_matter("cider-press-brain", "node_readme"),
                                                           encoding="utf-8")
        (self.checkout / "brain" / "LOG.md").write_text(front_matter("cider-press-log", "log") + "\n# Activity Log\n",
                                                        encoding="utf-8")
        git(self.checkout, "init", "-q")
        git(self.checkout, "add", ".")
        git(self.checkout, "commit", "-q", "-m", "start")

    def readmes(self, visibility: str = "private") -> None:
        self.node_readme(self.hedgerow, "Hedgerow survey")
        self.node_readme(self.pointer, "Cider press", repo_url="https://example.com/sam/cider-press.git",
                         default_branch="main", repo_visibility=visibility)

    def node_readme(self, folder: Path, title: str, **fields: str) -> None:
        extra = "".join(f"{k}: {v}\n" for k, v in fields.items())
        (folder / "README.md").write_text(
            f"---\nid: {folder.name}-readme\ntitle: {title}\ntype: node_readme\nnode_type: project\n"
            f"schema_version: 0.2\ncontract: /CONTRACT.md\ncreated: {STAMP}\nupdated: {STAMP}\n{extra}---\n\n"
            f"# {title}\n", encoding="utf-8")

    def files(self, base: Path | None = None) -> dict[str, bytes]:
        """Every file under the brain and the checkout, by path, with its bytes."""
        out = {}
        for top in ([base] if base else [self.root, self.checkout]):
            for path in sorted(top.rglob("*")):
                if path.is_file() and ".git" not in path.parts:
                    out[path.relative_to(top.parent).as_posix()] = path.read_bytes()
        return out

    def repo_text(self) -> str:
        """Every text file under the checkout's brain/, joined."""
        return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in sorted((self.checkout / "brain").rglob("*")) if p.is_file())

    def migrate(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "migrate", *args, "--now", "2026-02-01T10:00:00+00:00"],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")


class StoreTestCase(unittest.TestCase):
    readmes = True

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = StoreBrain(Path(self._tmp.name), readmes=self.readmes)

    def tearDown(self) -> None:
        self._tmp.cleanup()
