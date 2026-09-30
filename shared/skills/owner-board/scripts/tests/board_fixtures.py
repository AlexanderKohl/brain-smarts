"""The owner-board tests' fictional brain, built in a temporary folder, and their shared helpers.

Moved unchanged from test_owner_board.py. test_owner_board.py imports these names back, so
everything that uses test_owner_board sees the same names.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import board_config  # noqa: E402


HAS_GIT = shutil.which("git") is not None

BOARD_MD = """---
id: example-garden-board
title: The board
type: reference
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-01-05T09:00:00+10:00
updated: 2026-01-05T09:00:00+10:00
owner: Sam
---

# The board

```json
{
  "id": "garden",
  "label": "Garden Planner",
  "generated": "2026-01-05T09:00:00+10:00",
  "mainVersion": "1.1.0",
  "tracks": {
    "beds": {"label": "Beds", "task": "TASK-2026-0901", "done": 2, "of": 5},
    "seeds": {"label": "Seeds", "task": "TASK-2026-0902", "done": 0, "of": 3}
  },
  "appId": "exampleappid",
  "abandoned": {"spike/old-layout": "superseded by 1.0.0"},
  "closed": {"1.0.0": "first release"}
}
```
"""

CARD = """---
id: {id}
title: {title}
type: board_card
schema_version: 0.2
contract: /CONTRACT.md
parent: /memory/projects/example-garden
created: 2026-01-05T09:00:00+10:00
updated: 2026-01-05T09:00:00+10:00
owner: Sam
track: {track}
state: {state}
version: {version}
branch: {branch}
asked: 2026-01-0{n}
area:
where_text: Garden Planner - Beds
where_view: {view}
where_href:
---

# {title}

## What landed

Raised beds now show their soil depth: 0 of 12 beds unlabelled, was 7.

## To check

Open Beds and look at the depth column.
"""


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(" ".join(args) + ": " + out.stderr)
    return out.stdout


class Brain:
    """A fictional brain: CONTRACT.md, memory/OWNER.md, one or two boards, optional product repo."""

    def __init__(self, with_repo: bool = False, second_board: bool = False):
        self.root = Path(tempfile.mkdtemp(prefix="owner-board-"))
        (self.root / "CONTRACT.md").write_text("---\nid: c\n---\n# contract\n", encoding="utf-8")
        self.memory = self.root / "memory"
        self.repos = self.root.parent / (self.root.name + "-repos")
        self.memory.mkdir()
        (self.memory / "OWNER.md").write_text(
            "---\nid: owner-profile\nowner_short_name: Sam\nproject_repos_root: "
            + str(self.repos) + "\n---\n# Owner\n", encoding="utf-8")
        tasks = self.memory / "tasks" / "open"
        tasks.mkdir(parents=True)
        (tasks / "TASK-2026-0901-beds.md").write_text("---\nid: TASK-2026-0901\nstatus: ready\n---\n", encoding="utf-8")
        (self.memory / "tasks" / "STATE.md").write_text("| TASK-2026-0901 | ready |\n", encoding="utf-8")
        entries = [self.board_entry("garden", "Garden Planner", "projects/example-garden/status", with_repo)]
        self.make_board("projects/example-garden/status", "garden")
        if second_board:
            entries.append(self.board_entry("pond", "Pond Pump", "projects/example-pond/status", False))
            self.make_board("projects/example-pond/status", "pond")
        config = self.memory / "skills" / "owner-board" / "config"
        config.mkdir(parents=True)
        (config / "boards.json").write_text(json.dumps({"boards": entries}, indent=2), encoding="utf-8")
        if with_repo:
            self.make_repo()

    @staticmethod
    def board_entry(board_id: str, label: str, status: str, with_repo: bool) -> dict:
        entry = {"id": board_id, "label": label, "status": status, "blurb": "A fictional " + label.lower(),
                 "where_view_href": "example-app://{appId}/index.html[?plot={plotId}]#{view}"}
        if with_repo:
            entry.update({"repo": "{project_repos_root}/example-garden",
                          "committed_version": {"file": "package.json", "key": "version"},
                          "built_version": {"file": "dist/manifest.json", "key": "version"},
                          "copy_only_prefixes": ["example-app://"]})
        return entry

    def make_board(self, status: str, board_id: str) -> None:
        folder = self.memory / status
        (folder / "cards").mkdir(parents=True)
        (folder / "board.md").write_text(BOARD_MD.replace('"garden"', '"' + board_id + '"'), encoding="utf-8")
        for n, (cid, state, version, branch, view) in enumerate([
                ("soil-depth", "needs_review", "1.1.0", "", "beds"),
                ("seed-list", "building", "", "feature/seed-list", ""),
                ("frost-dates", "queued", "", "", "")], start=1):
            (folder / "cards" / (cid + ".md")).write_text(CARD.format(
                id=cid, title="show me the " + cid.replace("-", " "), track="beds" if n < 3 else "seeds",
                state=state, version=version or "null", branch=branch or "null", n=n, view=view),
                encoding="utf-8")

    def make_repo(self) -> None:
        remote = self.repos / "example-garden.git"
        repo = self.repos / "example-garden"
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare", "-b", "main")
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "tester@example.com")
        git(repo, "config", "user.name", "Tester")
        (repo / "package.json").write_text('{"version": "1.0.0"}', encoding="utf-8")
        git(repo, "add", "package.json")
        git(repo, "commit", "-q", "-m", "start")
        git(repo, "remote", "add", "origin", str(remote))
        # A merged release, 1.2.0, that no card mentions.
        git(repo, "checkout", "-q", "-b", "release/1.2.0")
        (repo / "package.json").write_text('{"version": "1.2.0"}', encoding="utf-8")
        git(repo, "commit", "-q", "-am", "bump")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "-m", "Merge 1.2.0 beds", "release/1.2.0")
        # A pushed branch nobody is building.
        git(repo, "checkout", "-q", "-b", "fix/orphan")
        (repo / "notes.txt").write_text("x", encoding="utf-8")
        git(repo, "add", "notes.txt")
        git(repo, "commit", "-q", "-m", "orphan")
        git(repo, "checkout", "-q", "main")
        git(repo, "push", "-q", "origin", "main", "fix/orphan", "release/1.2.0")
        (repo / "dist").mkdir()
        (repo / "dist" / "manifest.json").write_text('{"version": "1.1.0"}', encoding="utf-8")
        self.repo = repo

    def config(self) -> board_config.Config:
        return board_config.Config(self.root)

    def board(self, which: str = "garden") -> dict:
        return self.config().board(which)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.repos, ignore_errors=True)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn(*args, **kwargs)
    return result, out.getvalue()
