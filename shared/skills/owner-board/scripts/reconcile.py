"""What git says, against what the board says.

The board only catches work that has a card. A branch that has been pushed and not merged, a
worktree nobody recorded, or a version that landed with no card exists only as a notification
already scrolled past. This reads the product repository and the task records and returns every
disagreement as a plain sentence.

`build_status.py` calls it on every regeneration, so the conductor cannot choose not to run it,
and what it finds is drawn at the top of the page where the owner sees it too.

The product repository comes from the board's `repo` entry in
`/memory/skills/owner-board/config/boards.json`. A board with no `repo` gets only the task-record
checks (check 10).

    python reconcile.py [--board <id>] [--no-fetch]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402


class Repo:
    def __init__(self, board: dict):
        self.path = str(board["repo"])
        self.remote = board.get("remote") or "origin"
        self.main = board.get("main") or "main"
        # The branch releases go to; it is ahead of main after a hotfix, never a stray.
        self.production = board.get("production") or (self.remote + "/main")

    def is_production(self, branch: str) -> bool:
        """`branch` as git names it (`origin/main`) or as a worktree names it (`main`)."""
        return branch in (self.production, self.remote + "/" + self.production,
                          self.production.removeprefix(self.remote + "/"))

    def git(self, *args: str) -> str:
        out = subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        return out.stdout.strip() if out.returncode == 0 else ""

    def worktrees(self) -> list:
        rows, current = [], {}
        for line in self.git("worktree", "list", "--porcelain").split("\n"):
            if line.startswith("worktree "):
                if current:
                    rows.append(current)
                current = {"path": line[9:], "branch": ""}
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
        if current:
            rows.append(current)
        return rows


def _version_in(text: str, spec: dict) -> str:
    """A version read from file text, by `regex` (first group) or by top-level JSON `key`."""
    if spec.get("regex"):
        found = re.search(spec["regex"], text)
        return found.group(1) if found else ""
    try:
        return str(json.loads(text).get(spec.get("key") or "version", "") or "")
    except (ValueError, AttributeError):
        return ""


def young(item: dict, minutes: int) -> bool:
    """Has this card only just started? A dispatch is not a failure."""
    started = item.get("startedAt")
    if not started:
        return False
    try:
        began = datetime.datetime.fromisoformat(started)
    except ValueError:
        return False
    now = datetime.datetime.now(began.tzinfo) if began.tzinfo else datetime.datetime.now()
    return (now - began).total_seconds() < minutes * 60


TASK_ID = re.compile(r"TASK-\d{4}-\d{4}")


def abandoned_branches(data: dict) -> dict:
    """`abandoned` as branch -> reason, whether the board file keeps it as a mapping or as a
    list of `"branch: reason"` strings or `{"branch", "reason"}` records."""
    raw = data.get("abandoned") or {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    out = {}
    for entry in raw:
        if isinstance(entry, dict):
            out[str(entry.get("branch", ""))] = str(entry.get("reason", ""))
        else:
            branch, _, reason = str(entry).partition(":")
            out[branch.strip()] = reason.strip()
    return out


def repo_version(board: dict) -> str:
    """The product's version on the board's main branch, read from git; empty without one."""
    committed = board.get("committed_version") or {}
    if not board.get("repo") or not committed.get("file") or not os.path.isdir(str(board["repo"])):
        return ""
    repo = Repo(board)
    return _version_in(repo.git("show", repo.main + ":" + committed["file"]), committed)


def production_version(board: dict) -> str:
    """The product's version on the board's production branch, read from git; empty without one."""
    committed = board.get("committed_version") or {}
    if not board.get("repo") or not committed.get("file") or not os.path.isdir(str(board["repo"])):
        return ""
    repo = Repo(board)
    return _version_in(repo.git("show", repo.production + ":" + committed["file"]), committed)


def task_exists(board: dict, task_id: str) -> bool:
    """A task record under /memory/tasks/, open or completed, whichever folder holds it."""
    tasks = Path(str(board["memory"])) / "tasks"
    if not tasks.is_dir():
        return False
    return any(p.is_dir() and any(p.glob(task_id + "*.md")) for p in tasks.iterdir())


def check(board: dict, data: dict | None = None) -> list:
    """Every way git, the task records and the board can disagree, as plain sentences."""
    said: list = []
    try:
        data = data if data is not None else events.state(board)
    except Exception:
        data = {}
    main_version = None
    if board.get("repo"):
        git_said, main_version = _git_checks(board, data)
        said += git_said
    # Each owner's tasks live in that owner's memory: a shared board's tracks may name a task
    # the other brain does not have, so the task checks run only on a memory board.
    if not board.get("shared"):
        said += _task_checks(board, data)
    # 9. A derived value kept by hand in board.json. The version is read from git and the
    # closed register is folded from the events on every build, so a kept copy can only go
    # stale: it is reported until the key is removed.
    try:
        kept = cards.read_board(board)
    except Exception:
        kept = {}
    for key in cards.DERIVED_KEYS:
        if key in kept:
            said.append("board.json still carries " + key + "; it is derived on every build"
                        + (" (git says " + (main_version or "?") + ")" if key == "mainVersion" else "") + " - remove the key.")
    said += _note_checks(board, data)
    return said


def _note_checks(board: dict, data: dict) -> list:
    """11. A card ready for review whose version raised the first or middle number, on a board
    that draws release notes, and that names no note: the change a user would notice has no
    note to be chosen from."""
    if not board.get("release_notes"):
        return []
    said: list = []
    known = [events.version_key(v) for v in (data.get("closed") or {})]
    for item in data.get("items", []):
        if item.get("state") != "needs_review" or not item.get("version") or item.get("release_note"):
            continue
        mine = events.version_key(item["version"])
        if mine[0] != 0:
            continue
        below = [k for k in known if k[0] == 0 and k < mine]
        if not below:
            continue
        if mine[1:3] > max(below)[1:3]:
            said.append(item["id"] + " landed " + item["version"] + ", which raised the first or middle number, and names no"
                        " release note - card.py set " + item["id"] + " --note <slug>.")
    return said


def _git_checks(board: dict, data: dict) -> tuple:
    said: list = []
    repo = Repo(board)
    if not os.path.isdir(repo.path):
        return ["The product repository " + repo.path + " does not exist, so nothing was reconciled against git."], None
    main, remote = repo.main, repo.remote
    if board.get("fetch", True):
        repo.git("fetch", "-q", remote)

    # 1. A merge left half-finished.
    merge_head = repo.git("rev-parse", "--git-path", "MERGE_HEAD")
    if merge_head and os.path.exists(os.path.join(repo.path, merge_head)):
        said.append("A merge is in progress and uncommitted in the main checkout.")

    # 2. A commit whose message was never written.
    head = repo.git("log", "--oneline", "-1", main)
    if board.get("placeholder_pattern") and re.search(board["placeholder_pattern"], head, re.I):
        said.append(main + "'s head still carries a placeholder message: " + head)

    # 3. The built product is not what is committed.
    committed = board.get("committed_version") or {}
    main_version = "?"
    if committed.get("file"):
        main_version = _version_in(repo.git("show", main + ":" + committed["file"]), committed) or "?"
    built = board.get("built_version") or {}
    if built.get("file"):
        path = os.path.join(repo.path, built["file"])
        if os.path.exists(path):
            have = _version_in(Path(path).read_text(encoding="utf-8"), built) or "?"
            if have != main_version:
                folder = os.path.dirname(built["file"]).replace("\\", "/") or built["file"]
                said.append(folder + "/ is built at " + have + " but " + main + " is " + main_version
                            + " - the owner loads " + folder + ", so this is what they see.")

    # 4. A branch pushed, not merged, and nobody acting on it.
    merged = set(repo.git("branch", "-r", "--merged", main).split())
    items = data.get("items", [])
    abandoned = abandoned_branches(data)
    # Matched by branch, not by version: a worker renumbers when main moves under it, so a
    # version is the one thing about an in-flight card guaranteed to go stale.
    building = {(i.get("branch") or "") for i in items if i.get("state") in ("building", "rework")}
    trees = repo.worktrees()
    prefix = remote + "/"
    for line in repo.git("branch", "-r", "--no-merged", main).split("\n"):
        branch = line.strip()
        if not branch or branch.endswith("/" + main) or branch.startswith(prefix + "HEAD") or repo.is_production(branch):
            continue
        tree = [w for w in trees if prefix + w["branch"] == branch]
        ver = ""
        if tree and committed.get("file"):
            pkg = os.path.join(tree[0]["path"], committed["file"])
            if os.path.exists(pkg):
                ver = _version_in(Path(pkg).read_text(encoding="utf-8"), committed)
        short = branch[len(prefix):] if branch.startswith(prefix) else branch
        if short in building or short in abandoned:
            continue
        note = branch + " is pushed and not merged"
        if ver:
            note += ", built as " + ver
        note += " - no card on the board is building it" + ("" if tree else ", and no worktree exists")
        said.append(note)

    # 5. A card that says it is being built, with no branch anybody is building.
    for item in items:
        if item.get("state") not in ("building", "rework"):
            continue
        # Work that deliberately produces no branch says `writes: none`.
        if str(item.get("writes") or "") == "none":
            continue
        branch = item.get("branch") or ""
        if not branch:
            said.append(item["id"] + (
                " was sent back and no worker has picked it up."
                if item.get("state") == "rework"
                else " says it is being built and names no branch, so nothing can check it."))
        elif prefix + branch in merged:
            said.append(item["id"] + " says it is being built, but " + branch + " is already merged.")
        elif not repo.git("rev-parse", "--verify", "--quiet", prefix + branch):
            # Not yet pushed is normal for a worker that has just started. It is adrift only
            # when there is no worktree either and the card is older than the grace period.
            if not any(w["branch"] == branch for w in trees) and not young(item, board.get("grace_minutes", 15)):
                said.append(item["id"] + " says it is being built, but " + branch
                            + " has no worktree and is not on " + remote + " - nobody is building it.")

    # 6. A worktree no card mentions: the earliest evidence that work exists.
    named = {(i.get("branch") or "") for i in items}
    for tree in trees:
        b = tree["branch"]
        # main is a remote name ("origin/testing"); the checkout on its local branch is not a stray.
        if not b or b == main or prefix + b == main or b in named or b in abandoned or repo.is_production(b):
            continue
        if prefix + b in merged:
            continue  # check 7 says this one better
        said.append("a worktree is building " + b + " and no card on the board mentions it.")

    # 7. A worktree whose branch is already in.
    for tree in trees:
        if tree["branch"] and tree["branch"] != main and prefix + tree["branch"] != main and prefix + tree["branch"] in merged:
            said.append(tree["branch"] + " is merged but its worktree is still on disk.")

    # 8. A version that landed and has no card. Closing a card writes its version into
    # `closed`, so anything merged and neither carded nor closed has gone quiet. A merge whose
    # subject names a task that exists under /memory/tasks/ (open or completed) is the task
    # flow's own record of it, and counts as seen.
    closed = set(data.get("closed", {}) or {})
    carded = {(i.get("version") or "") for i in items}
    pattern = board.get("merge_version_pattern")
    if pattern:
        for line in repo.git("log", "--merges", "-25", "--format=%s", main).splitlines():
            found = re.search("(" + pattern + ")", line)
            if not found:
                continue
            ver = found.group(1)
            if ver in carded or ver in closed:
                continue
            if any(task_exists(board, t) for t in TASK_ID.findall(line)):
                continue
            said.append(ver + " is merged into " + main + " and has no card - the owner has not seen it.")
    return said, main_version


def _task_checks(board: dict, data: dict) -> list:
    """10. A task record whose status word is stale: a status is written when work starts and
    never when it finishes. A track with landed work or a card in flight cannot have a task
    that still says nobody has begun."""
    said: list = []
    tasks_dir = os.path.join(str(board["memory"]), "tasks", "open")
    state_file = os.path.join(str(board["memory"]), "tasks", "STATE.md")
    index = Path(state_file).read_text(encoding="utf-8", errors="replace") if os.path.exists(state_file) else ""

    def status_of(task_id: str):
        if not os.path.isdir(tasks_dir):
            return None
        for name in sorted(os.listdir(tasks_dir)):
            if not name.startswith(task_id):
                continue
            head = Path(os.path.join(tasks_dir, name)).read_text(encoding="utf-8", errors="replace")[:1200]
            found = re.search(r"^status:\s*(\S+)", head, re.M)
            return found.group(1) if found else "?"
        return None

    for key, track in (data.get("tracks") or {}).items():
        task_id = track.get("task")
        if not task_id:
            continue
        status = status_of(task_id)
        if status is None:
            said.append(task_id + " is the task for the " + key + " track and has no record in /memory/tasks/open.")
            continue
        moving = (track.get("done") or 0) > 0 or any(
            i.get("track") == key and i.get("state") not in ("queued", "yours") for i in data.get("items", []))
        if moving and status == "ready":
            said.append(task_id + " still says ready, but the " + key
                        + " track has landed work or has a card in flight.")
        if index and task_id not in index:
            said.append(task_id + " is the task for the " + key + " track and is not listed in /memory/tasks/STATE.md.")
    return said


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", help="board id (default: the board whose folder holds the current directory, or the only one)")
    args = p.parse_args(argv)
    board = board_config.load(args).board(args.board)
    found = check(board)
    print("\n".join("  - " + s for s in found) if found else "  nothing adrift")
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
