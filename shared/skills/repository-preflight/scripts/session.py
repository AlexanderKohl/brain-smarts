#!/usr/bin/env python3
"""One working copy per session (SMART-RULE-0038): start, finish and list a session's own copy.

    python shared/skills/repository-preflight/scripts/session.py start <name> [--sessions <folder>]
    python shared/skills/repository-preflight/scripts/session.py finish <name> [--keep] [--no-preflight]
    python shared/skills/repository-preflight/scripts/session.py list

`start` makes `<sessions folder>/<name>/`: a Git worktree of the mechanics on branch
`session/<name>` from the latest `origin`, with `library/` and `memory/` inside it as worktrees of
those repositories on the same branch name, so the brain root and `/memory/` resolve inside it. The
sessions folder is `<brain root>-sessions` beside the shared checkout unless `--sessions` or a
`sessions_root` field in `/memory/OWNER.md` names another.

`finish` merges each repository's branch with `origin/main`, rebuilds a generated file that
conflicted (taking `main`'s version first), stops on any other conflict and leaves it for the
session to resolve, runs preflight, pushes `HEAD:main`, fast-forwards the shared checkout with
`sync.py`, and removes the worktrees and branches once `main` contains them. `--keep` keeps the copy
for the next unit of work.

`list` shows every session copy, its age and the commits not yet in `main`, so work left by a
session that ended is found and finished rather than lost.

It never force-pushes, never removes a worktree with unmerged commits or uncommitted changes, and
never merges inside the shared checkout. Exit code 0 on success, 1 when something needs attention.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync  # noqa: E402  (one canonical brain_root, git and fast-forward, SMART-RULE-0018)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
NESTED = ("library", "memory")   # nested repositories, in the order they are made

# Generated files a merge may conflict on, per repository: the pattern and the command that
# rebuilds them, run from the session root. A conflict in any other file stops `finish`.
GENERATED = {
    "memory": [
        ("boards/*.html", ["python", "shared/skills/owner-board/scripts/build_boards.py", "--no-fetch"]),
        ("projects/*/status/status.html", ["python", "shared/skills/owner-board/scripts/build_status.py", "--no-fetch"]),
    ],
}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return sync.git(repo, *args)


def last_line(done: subprocess.CompletedProcess) -> str:
    return ((done.stderr or done.stdout).strip().splitlines() or ["?"])[-1]


def shared_root(start: Path) -> Path | None:
    """The shared checkout's brain root, found from it or from inside any session copy."""
    root = sync.brain_root(start)
    if root is None:
        return None
    common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common.returncode:
        return root
    return Path(common.stdout.strip()).parent


def sessions_folder(root: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    owner = root / "memory" / "OWNER.md"
    if owner.is_file():
        found = re.search(r"^sessions_root:\s*(\S.*)$", owner.read_text(encoding="utf-8"), re.M)
        if found:
            return Path(found.group(1).strip().strip("'\""))
    return root.parent / (root.name + "-sessions")


def repositories(root: Path) -> list[tuple[str, Path]]:
    """The brain's repositories in the shared checkout: mechanics first, then the nested ones."""
    return [("mechanics", root)] + [(name, root / name) for name in NESTED if (root / name / ".git").exists()]


def base_ref(repo: Path) -> str:
    """The remote branch the shared checkout follows, such as `origin/main`."""
    upstream = git(repo, "rev-parse", "--abbrev-ref", "@{u}")
    return upstream.stdout.strip() if upstream.returncode == 0 else "origin/main"


def session_path(copy: Path, name: str) -> Path:
    return copy if name == "mechanics" else copy / name


def remove_copy(root: Path, copy: Path, branch: str, made: list[str]) -> None:
    """Undo a partly made copy: nested worktrees first, then the mechanics."""
    for name in reversed(made):
        repo = root if name == "mechanics" else root / name
        git(repo, "worktree", "remove", str(session_path(copy, name)))
        git(repo, "branch", "-D", branch)


def cmd_start(root: Path, name: str, folder: Path) -> int:
    if not NAME_RE.match(name):
        print(f"name must be lower-case letters, digits and hyphens: {name}")
        return 1
    copy = folder / name
    branch = f"session/{name}"
    if copy.exists():
        print(f"{copy} already exists; finish that session or choose another name")
        return 1
    repos = repositories(root)
    for repo_name, repo in repos:
        fetched = git(repo, "fetch", "--quiet", "origin")
        if fetched.returncode:
            print(f"{repo_name}: could not fetch origin – {last_line(fetched)}")
            return 1
        for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
            if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode == 0:
                print(f"{repo_name}: branch {branch} already exists; two sessions never share a branch")
                return 1
    folder.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    for repo_name, repo in repos:
        target = session_path(copy, repo_name)
        added = git(repo, "worktree", "add", "--quiet", "-b", branch, str(target), base_ref(repo))
        if added.returncode:
            print(f"{repo_name}: could not make the worktree – {last_line(added)}")
            remove_copy(root, copy, branch, made)
            return 1
        made.append(repo_name)
    print(f"session copy: {copy}")
    print("work only there; finish with: python shared/skills/repository-preflight/scripts/session.py "
          f"finish {name}")
    return 0


def conflicted(repo: Path) -> list[str]:
    return [line for line in git(repo, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() if line]


def rebuild(copy: Path, repo_name: str, repo: Path, files: list[str]) -> list[str]:
    """Take main's version of each conflicted generated file and rebuild it; return the rest."""
    left: list[str] = []
    commands: list[list[str]] = []
    for path in files:
        match = next((cmd for pattern, cmd in GENERATED.get(repo_name, []) if Path(path).match(pattern)), None)
        if match is None:
            left.append(path)
            continue
        git(repo, "checkout", "--theirs", "--", path)
        if match not in commands:
            commands.append(match)
    if left:
        return left
    for command in commands:
        done = subprocess.run([sys.executable if command[0] == "python" else command[0], *command[1:]],
                              cwd=copy, capture_output=True, text=True, encoding="utf-8")
        if done.returncode:
            return [f"{' '.join(command)} failed: {last_line(done)}"]
    # A generator may rewrite more than the conflicted file (every board, say); stage all it made.
    patterns = [pattern for pattern, _ in GENERATED.get(repo_name, [])]
    changed = [line[3:] for line in git(repo, "status", "--porcelain").stdout.splitlines() if len(line) > 3]
    for path in sorted(set(files) | {c for c in changed if any(Path(c).match(pt) for pt in patterns)}):
        git(repo, "add", "--", path)
    return []


def merge_main(copy: Path, repo_name: str, repo: Path, base: str) -> tuple[bool, str]:
    """Bring the session branch up to date with `base` (origin's main); (ok, what happened)."""
    fetched = git(repo, "fetch", "--quiet", "origin")
    if fetched.returncode:
        return False, f"could not fetch origin – {last_line(fetched)}"
    if git(repo, "merge-base", "--is-ancestor", base, "HEAD").returncode == 0:
        return True, "up to date with " + base
    merged = git(repo, "merge", "--no-edit", "--quiet", base)
    if merged.returncode == 0:
        return True, "merged " + base
    files = conflicted(repo)
    if not files:
        return False, f"merge failed – {last_line(merged)}"
    left = rebuild(copy, repo_name, repo, files)
    if left:
        return False, ("conflict left for the session to resolve (the merge is in progress): "
                       + ", ".join(left))
    committed = git(repo, "commit", "--no-edit", "--quiet")
    if committed.returncode:
        return False, f"could not commit the merge – {last_line(committed)}"
    return True, f"merged {base}; rebuilt " + ", ".join(files)


def session_repos(root: Path, copy: Path) -> list[tuple[str, Path, Path]]:
    """(name, shared repository, session worktree) for each worktree the copy has."""
    found = []
    for name, repo in repositories(root):
        path = session_path(copy, name)
        if (path / ".git").exists():
            found.append((name, repo, path))
    return found


def cmd_finish(root: Path, name: str, folder: Path, keep: bool, preflight: bool) -> int:
    copy = folder / name
    branch = f"session/{name}"
    repos = session_repos(root, copy)
    if not repos:
        print(f"no session copy at {copy}")
        return 1
    for repo_name, _, path in repos:
        dirty = git(path, "status", "--porcelain").stdout.strip()
        if dirty:
            print(f"{repo_name}: uncommitted changes in {path}; commit or discard them first")
            return 1
    ahead: dict[str, bool] = {}
    base = {repo_name: base_ref(repo) for repo_name, repo, _ in repos}
    for repo_name, _, path in repos:
        ok, what = merge_main(copy, repo_name, path, base[repo_name])
        print(f"{repo_name}: {what}")
        if not ok:
            return 1
        ahead[repo_name] = git(path, "merge-base", "--is-ancestor", "HEAD", base[repo_name]).returncode != 0
    if preflight and any(ahead.values()):
        checked = subprocess.run([sys.executable, str(copy / "shared/skills/repository-preflight/scripts/preflight.py"),
                                  "--root", str(copy)], cwd=copy, capture_output=True, text=True, encoding="utf-8")
        summary = next((line for line in checked.stdout.splitlines() if line.startswith(("PASS", "FAIL"))),
                       last_line(checked))
        print(f"preflight: {summary}")
        if checked.returncode:
            return 1
    for repo_name, _, path in repos:
        if not ahead[repo_name]:
            continue
        target = base[repo_name].split("/", 1)[1]
        pushed = git(path, "push", "--quiet", "origin", f"HEAD:{target}")
        if pushed.returncode:
            print(f"{repo_name}: push refused – {last_line(pushed)}; run finish again to merge the newer main")
            return 1
        print(f"{repo_name}: pushed to {target}")
    for repo_name, repo in repositories(root):
        r = sync.sync_one(repo_name, repo)
        print(f"shared checkout {repo_name}: {r['state']}" + (f" – {r['detail']}" if r["detail"] else ""))
    if keep:
        print(f"session copy kept: {copy}")
        return 0
    status = 0
    for repo_name, repo, path in reversed(repos):          # nested worktrees before the mechanics
        git(path, "fetch", "--quiet", "origin")
        if git(path, "merge-base", "--is-ancestor", "HEAD", base[repo_name]).returncode != 0:
            print(f"{repo_name}: {branch} is not in main yet; worktree kept")
            status = 1
            continue
        removed = git(repo, "worktree", "remove", str(path))
        if removed.returncode:
            print(f"{repo_name}: worktree kept – {last_line(removed)}")
            status = 1
            continue
        git(repo, "branch", "-D", branch)                  # safe: main contains it, checked above
    if status == 0:
        try:
            copy.rmdir()
        except OSError:
            pass
        print(f"session {name} finished and removed")
    return status


def cmd_list(root: Path) -> int:
    rows = []
    for repo_name, repo in repositories(root):
        listing = git(repo, "worktree", "list", "--porcelain").stdout
        for block in listing.strip().split("\n\n"):
            fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
            ref = fields.get("branch", "")
            if not ref.startswith("refs/heads/session/"):
                continue
            path = Path(fields["worktree"])
            ahead = git(path, "rev-list", "--count", f"{base_ref(repo)}..HEAD").stdout.strip() or "?"
            dirty = len([line for line in git(path, "status", "--porcelain").stdout.splitlines() if line])
            made = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if path.exists() else "?"
            rows.append((ref.removeprefix("refs/heads/session/"), repo_name, ahead, str(dirty), made, str(path)))
    if not rows:
        print("no session copies")
        return 0
    print("| Session | Repository | Commits not in main | Uncommitted files | Changed | Path |")
    print("|---|---|---|---|---|---|")
    for row in sorted(rows):                               # by session name, then repository
        print("| " + " | ".join(row) + " |")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="the brain root (default: found from here)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("name")
    p.add_argument("--sessions", type=Path, default=None)
    p = sub.add_parser("finish")
    p.add_argument("name")
    p.add_argument("--sessions", type=Path, default=None)
    p.add_argument("--keep", action="store_true", help="merge and push, but keep the copy for more work")
    p.add_argument("--no-preflight", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("list")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    root = shared_root(args.root or Path.cwd())
    if root is None:
        print("CONTRACT.md not found; run inside the brain")
        return 1
    if args.command == "start":
        return cmd_start(root, args.name, sessions_folder(root, args.sessions))
    if args.command == "finish":
        return cmd_finish(root, args.name, sessions_folder(root, args.sessions), args.keep, not args.no_preflight)
    return cmd_list(root)


if __name__ == "__main__":
    raise SystemExit(main())
