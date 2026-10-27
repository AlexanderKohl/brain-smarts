"""A fictional brain for the tasks tests: owner profile, stores, nodes, pointers and Git checkouts.

Every name, title and value here is invented (SMART-RULE-0008). The two brains are `sam` and `bob`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

STAMP = "2026-03-01T09:00:00+10:00"
NOW = "2026-03-10T09:00:00+10:00"
LATER = "2026-03-10T10:30:00+10:00"
TEMPLATE = ("---\nid: template-TASK-YYYY-NNNN\ntitle: Clear action or outcome\ntype: task\nschema_version: 0.2\n"
            "contract: /CONTRACT.md\nstatus: inbox\nowner: OWNER_SHORT_NAME\npriority: normal\n"
            "created: YYYY-MM-DDTHH:mm:ss+HH:MM\nupdated: YYYY-MM-DDTHH:mm:ss+HH:MM\ndue: null\nnext_review: null\n"
            "waiting_on: null\nproject_refs: []\nskill_refs: []\ndepends_on: []\nteam: null\nclaimed_by: null\n"
            "claimed_at: null\n---\n\n# Clear action or outcome\n\n## Outcome\n\n## Current position\n\n"
            "## Next action\n\n## Completion criteria\n\n## History\n")


def record(tid: str, title: str, status: str, author: str | None = "sam", refs: list[str] | None = None,
           history: str | None = None, body: str = "", **fields: str) -> str:
    meta = {"id": tid, "title": title, "type": "task", "schema_version": "0.2", "contract": "/CONTRACT.md",
            "status": status, "owner": "Sam", "author": author, "priority": "normal", "created": STAMP,
            "updated": STAMP, "due": "null", "next_review": "null", "waiting_on": "null"}
    if author is None:
        del meta["author"]
    meta.update(fields)
    lines = [f"{k}: {v}" for k, v in meta.items()]
    lines += ["project_refs:" if refs else "project_refs: []"] + [f"  - {r}" for r in refs or []]
    entry = history if history is not None else f"- {STAMP} – {author or 'sam'}: captured"
    return "---\n" + "\n".join(lines) + f"\n---\n\n# {title}\n\n{body}## History\n\n{entry}\n"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=sam", "-c", "user.email=sam@example.com",
                           "-c", "init.defaultBranch=main", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout


class Brain:
    """A temporary brain: <tmp>/brain (CONTRACT.md, memory/) and <tmp>/repos for checkouts."""

    def __init__(self, author: str = "Sam") -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="brain-tasks-"))
        self.root = self.tmp / "brain"
        self.repos = self.tmp / "repos"
        self.repos.mkdir(parents=True)
        (self.root / "memory").mkdir(parents=True)
        (self.root / "CONTRACT.md").write_text("---\nid: contract\n---\n", encoding="utf-8")
        self.profile(author)
        self.store = self.root / "memory" / "tasks"
        for folder in ("inbox", "open", "completed", "templates"):
            (self.store / folder).mkdir(parents=True)
        (self.store / "templates" / "TASK_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")

    def profile(self, author: str | None) -> None:
        name = f"owner_short_name: {author}\n" if author else ""
        (self.root / "memory" / "OWNER.md").write_text(
            f"---\nid: owner-profile\n{name}timezone: UTC (+00:00)\nproject_repos_root: {self.repos.as_posix()}\n---\n",
            encoding="utf-8")

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, folder: str, stem: str, text: str, store: Path | None = None) -> Path:
        path = (store or self.store) / folder / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def node(self, rel: str, title: str, node_type: str = "project", **fields: str) -> Path:
        folder = self.root / rel.strip("/")
        folder.mkdir(parents=True, exist_ok=True)
        extra = "".join(f"{k}: {v}\n" for k, v in fields.items())
        (folder / "README.md").write_text(
            f"---\nid: {folder.name}-readme\ntitle: {title}\ntype: node_readme\nnode_type: {node_type}\n"
            f"created: {STAMP}\n{extra}---\n\n# {title}\n", encoding="utf-8")
        return folder

    def checkout(self, name: str, branch: str = "main", joining_branch: str | None = None) -> Path:
        """A clone of a fresh bare origin, with brain/ committed and pushed on `branch`."""
        origin = self.tmp / "origins" / f"{name}.git"
        origin.mkdir(parents=True)
        git(origin, "init", "--bare", "-q")
        clone = self.repos / name
        git(self.repos, "clone", "-q", str(origin), name)
        git(clone, "checkout", "-q", "-b", branch)
        (clone / "brain").mkdir()
        (clone / "brain" / "README.md").write_text("---\nid: brain\n---\n", encoding="utf-8")
        if joining_branch:
            (clone / "brain" / "JOINING.md").write_text(
                f"---\nid: joining\ntitle: Joining\njoining:\n  repository: {name}\n  working_branch: {joining_branch}\n---\n",
                encoding="utf-8")
        git(clone, "add", ".")
        git(clone, "commit", "-q", "-m", "start")
        git(clone, "push", "-q", "-u", "origin", branch)
        return clone

    def text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")
