"""Two brains on one shared repository: the integration test of build plan section 6.2, item 2.

Everything is invented (SMART-RULE-0008): the brains `sam` and `bob`, the project Garden Planner
and its repository `garden-app`, whose origin is a local bare repository in a temporary folder.
Each brain has its own root, memory and clone. The test runs the real commands: `join.py` to
join, `tasks.py` to create, complete and note tasks, and `git` to share the repository.

It checks that `bob` joins and sees the repository's task store, completes `sam`'s task (the
History names `bob`), creates `TASK-bob-2026-0001`; that `sam`'s private task and private note
are in no file of the repository; and that a deliberate conflict fails `tasks.py check` until it
is resolved by hand per P23 (both History entries kept in time order, STATE.md generated again).
The repository preflight's own conflict check is the repository-preflight skill's to test.

    python -m unittest discover -s shared/skills/join-project/tests -v
"""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1] / "scripts"
REAL_ROOT = HERE.parents[4]
TASKS_SCRIPTS = REAL_ROOT / "shared" / "skills" / "tasks" / "scripts"
for folder in (SCRIPTS, TASKS_SCRIPTS):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import join  # noqa: E402
import tasks  # noqa: E402

HAS_GIT = shutil.which("git") is not None
URL = "https://example.com/sam/garden-app.git"
NODE = "/memory/projects/garden-planner"
STORE = "garden-app:brain/tasks"
MANIFEST = f"""---
id: garden-app-joining
title: Joining Garden Planner
type: joining_manifest
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-01-05T09:12:31+10:00
updated: 2026-01-05T09:12:31+10:00
owner: Sam
joining:
  repository: {URL}
  project_title: Garden Planner
  working_branch: testing
  minimum_contract_version: 3.0.0
  pointer_node: garden-planner
---

# Joining Garden Planner
"""
PRIVATE_TITLE = "Ask the landlord about the hose budget"
PRIVATE_NOTE = "The neighbour pays half of the seed order"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=Garden Tester", "-c", "user.email=tester@example.com",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", "-C", str(repo), *args],
                          capture_output=True, text=True, encoding="utf-8", check=check)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def remove(path: Path) -> None:
    def retry(func, name, _exc):
        os.chmod(name, stat.S_IWRITE)
        func(name)
    shutil.rmtree(path, onerror=retry)


def quiet(func, argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = func(argv)
    return code, out.getvalue()


class Brain:
    """One fictional brain: its root, memory, and a clone of the shared repository."""

    def __init__(self, base: Path, name: str, origin: Path):
        self.name = name
        self.root = base / name / "brain"
        self.projects = base / name / "projects"
        self.projects.mkdir(parents=True)
        write(self.root / "CONTRACT.md", "---\nid: c\ncontract_version: 3.0.0\n---\n")
        write(self.root / join.TEMPLATE, (REAL_ROOT / join.TEMPLATE).read_text(encoding="utf-8"))
        write(self.root / "memory/OWNER.md", f"---\nid: owner-profile\nowner_short_name: {name.title()}\n"
              f"timezone: UTC (+00:00)\nproject_repos_root: {self.projects.as_posix()}\n---\n")
        write(self.root / "memory/projects/README.md", "---\nid: p\n---\n# Projects\n\n#### Folders\n")
        for folder in ("inbox", "open", "completed"):
            (self.root / "memory/tasks" / folder).mkdir(parents=True)
        self.clone = self.projects / "garden-app"
        git(self.projects, "clone", "-q", str(origin), str(self.clone))

    def join(self) -> tuple[int, str]:
        return quiet(join.main, [str(self.clone), "--root", str(self.root), "--no-sync"])

    def tasks(self, *argv: str) -> tuple[int, str]:
        return quiet(tasks.main, ["--tasks", str(self.root / "memory/tasks"), *argv])

    def share(self, message: str) -> None:
        git(self.clone, "add", "-A", "brain")
        git(self.clone, "commit", "-q", "-m", message)
        git(self.clone, "push", "-q", "origin", "testing")

    def record(self, tid: str) -> Path:
        return next((self.clone / "brain/tasks").rglob(f"{tid}*.md"))


@unittest.skipUnless(HAS_GIT, "git is not installed")
class TwoBrainsTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="two-brains-"))
        origin = self.base / "garden-app.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(origin))
        seed = self.base / "seed"
        git(self.base, "clone", "-q", str(origin), str(seed))
        write(seed / "brain/JOINING.md", MANIFEST)
        write(seed / "brain/README.md", "---\nid: garden-brain\n---\n# Garden Planner brain\n")
        git(seed, "add", "brain")
        git(seed, "commit", "-q", "-m", "manifest")
        git(seed, "push", "-q", "origin", "main")
        git(seed, "push", "-q", "origin", "main:testing")
        self.sam = Brain(self.base, "sam", origin)
        self.bob = Brain(self.base, "bob", origin)

    def tearDown(self):
        remove(self.base)

    def test_two_brains_share_tasks_and_keep_private_lines_in_memory(self):
        code, out = self.sam.join()
        self.assertEqual(code, 0, out)
        self.assertIn(f"task store {STORE}: not there yet", out)
        code, out = self.sam.tasks("new", "--title", "Water the beds", "--status", "ready", "--project", NODE,
                                   "--now", "2026-03-02T09:00:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        sam_task = self.sam.record("TASK-sam-2026-0001")
        code, out = self.sam.tasks("new", "--title", PRIVATE_TITLE, "--project", NODE, "--private",
                                   "--now", "2026-03-02T09:05:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        code, out = self.sam.tasks("note", "TASK-sam-2026-0001", "--private", "--note", PRIVATE_NOTE,
                                   "--now", "2026-03-02T09:10:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        self.sam.share("sam: first task")

        code, out = self.bob.join()
        self.assertEqual(code, 0, out)
        self.assertIn(f"task store {STORE}: 1 open, 0 in the inbox", out)
        self.assertIn(f"no open task in {STORE} is yours (bob)", out)
        code, out = self.bob.tasks("done", "TASK-sam-2026-0001", "--note", "watered at dawn",
                                   "--now", "2026-03-03T07:00:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        done = self.bob.record("TASK-sam-2026-0001")
        self.assertEqual(done.parent.name, "completed")
        self.assertIn("- 2026-03-03T07:00:00+00:00 – bob: done (completed)", done.read_text(encoding="utf-8"))
        code, out = self.bob.tasks("new", "--title", "Fix the gate", "--status", "ready", "--project", NODE,
                                   "--now", "2026-03-03T07:05:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.bob.record("TASK-bob-2026-0001").parent.name, "open")
        self.bob.share("bob: done and a new task")

        git(self.sam.clone, "pull", "-q", "--no-rebase", "origin", "testing")
        self.assertFalse(sam_task.exists())
        for clone in (self.sam.clone, self.bob.clone):
            for path in clone.rglob("*"):
                if ".git" in path.parts or not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(PRIVATE_TITLE, text, path)
                self.assertNotIn(PRIVATE_NOTE, text, path)
                self.assertNotIn("/memory/", text, path)
        self.assertIn(PRIVATE_NOTE, (self.sam.root / "memory/tasks/private/TASK-sam-2026-0001.md")
                      .read_text(encoding="utf-8"))
        private = list((self.sam.root / "memory/projects/garden-planner/tasks").rglob("TASK-sam-2026-0002*.md"))
        self.assertEqual(len(private), 1)
        self.assertEqual(self.sam.tasks("check", "--store", STORE)[0], 0)

    def test_a_conflict_fails_the_check_until_resolved_by_hand(self):
        self.sam.join()
        self.sam.tasks("new", "--title", "Water the beds", "--status", "ready", "--project", NODE,
                       "--now", "2026-03-02T09:00:00+00:00", "--no-board")
        self.sam.share("sam: first task")
        self.bob.join()
        code, out = self.sam.tasks("note", "TASK-sam-2026-0001", "--note", "the north bed is dry",
                                   "--now", "2026-03-04T08:00:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        code, out = self.bob.tasks("note", "TASK-sam-2026-0001", "--note", "the hose leaks",
                                   "--now", "2026-03-04T09:00:00+00:00", "--no-board")
        self.assertEqual(code, 0, out)
        self.bob.share("bob: note")
        git(self.sam.clone, "add", "-A", "brain")
        git(self.sam.clone, "commit", "-q", "-m", "sam: note")
        merged = git(self.sam.clone, "pull", "-q", "--no-rebase", "origin", "testing", check=False)
        self.assertNotEqual(merged.returncode, 0, "the two notes should conflict")
        code, out = self.sam.tasks("check", "--store", STORE)
        self.assertEqual(code, 1, out)
        self.assertIn("conflict", out.lower())
        code, out = self.sam.tasks("note", "TASK-sam-2026-0001", "--note", "one more",
                                   "--now", "2026-03-04T10:00:00+00:00", "--no-board")
        self.assertEqual(code, 1, out)

        # resolved by hand per P23: bob's side, with sam's entry put back before bob's in time order
        path = self.sam.record("TASK-sam-2026-0001")
        rel = path.relative_to(self.sam.clone).as_posix()
        ours = git(self.sam.clone, "show", f":2:{rel}").stdout
        theirs = git(self.sam.clone, "show", f":3:{rel}").stdout
        sam_line = next(line for line in ours.splitlines() if "sam: note" in line)
        lines = theirs.splitlines()
        at = next(i for i, line in enumerate(lines) if "bob: note" in line)
        resolved = "\n".join(lines[:at] + [sam_line] + lines[at:]) + "\n"
        path.write_bytes(resolved.encode("utf-8"))
        state = self.sam.clone / "brain/tasks/STATE.md"
        write(state, git(self.sam.clone, "show", ":3:brain/tasks/STATE.md").stdout)
        code, out = self.sam.tasks("state", "--store", STORE)
        self.assertEqual(code, 0, out)
        git(self.sam.clone, "add", "-A", "brain")
        git(self.sam.clone, "commit", "-q", "--no-edit")
        code, out = self.sam.tasks("check", "--store", STORE)
        self.assertEqual(code, 0, out)
        text = path.read_text(encoding="utf-8")
        self.assertLess(text.index("sam: note"), text.index("bob: note"))


if __name__ == "__main__":
    unittest.main()
