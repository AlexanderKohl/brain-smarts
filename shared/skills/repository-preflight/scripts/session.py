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

`finish` first refreshes the generated views (`refresh`): for every git project in the release-notes
configuration it runs `release_notes.py fix`, `link` and `build`, then rebuilds every board, and
commits the regenerated brain files in the copy. A note repaired in a project repository is left
there as a change, and the repository and files that need a commit and push are printed under their
own heading (finish never commits or pushes a project repository); board drift is printed under its
own heading, never a stop. Nothing in the refresh refuses the finish. Then it merges each
repository's branch with `origin/main`, rebuilds a generated file that conflicted (taking `main`'s
version first), stops on any other conflict and leaves it for the session to resolve, runs
preflight, pushes `HEAD:main`, fast-forwards the shared checkout with `sync.py`, and removes the
worktrees and branches once `main` contains them. A push refused because `origin` moved on is
merged, checked and pushed again, up to three attempts in all (SMART-RULE-0034). `--keep` keeps the
copy for the next unit of work.

`merge_diverged` is how `sync.py` merges a shared-checkout branch whose history has diverged from
`origin` (SMART-RULE-0034): it starts a copy whose branch begins at that local commit and finishes it
as above, so the merge happens in the copy and the shared checkout only fast-forwards.

`list` shows every session copy, its age and the commits not yet in `main`, so work left by a
session that ended is found and finished rather than lost.

It never force-pushes, never rebases, never removes a worktree with unmerged commits or uncommitted
changes, and never merges inside the shared checkout. Exit code 0 on success, 1 when something needs attention.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync  # noqa: E402  (one canonical brain_root, git and fast-forward, SMART-RULE-0018)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
NESTED = ("library", "memory")   # nested repositories, in the order they are made
ATTEMPTS = 3                     # merge-check-push rounds before a refused push is reported
REFUSED = ("[rejected]", "non-fast-forward", "fetch first")   # git's words for "origin moved on"

# Generated files a merge may conflict on, per repository: the pattern and the command that
# rebuilds them, run from the session root. A conflict in any other file stops `finish`.
GENERATED = {
    "memory": [
        ("boards/*.html", ["python", "shared/skills/owner-board/scripts/build_boards.py", "--no-fetch"]),
        ("projects/*/status/status.html", ["python", "shared/skills/owner-board/scripts/build_status.py", "--no-fetch"]),
    ],
}


# The generated views every finish refreshes before it merges, each relative to the copy.
RELEASE_NOTES = "shared/skills/release-notes/scripts/release_notes.py"
RELEASE_CONFIG = "memory/skills/release-notes/config/release-notes.json"
BOARDS_CONFIG = "memory/skills/owner-board/config/boards.json"
BUILD_STATUS = "shared/skills/owner-board/scripts/build_status.py"
RECONCILE = "shared/skills/owner-board/scripts/reconcile.py"
REFRESH_MESSAGE = "Finish: release notes and boards rebuilt\n\nTool: session.py finish\n"
# The refresh commit needs a Co-Authored-By trailer too (SMART-RULE-0009): from this variable
# when set, else from the newest commit in the repository that carries one; never invented.
CO_AUTHOR_ENV = "BRAIN_CO_AUTHOR"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return sync.git(repo, *args)


def last_line(done: subprocess.CompletedProcess) -> str:
    return (((done.stderr or done.stdout) or "").strip().splitlines() or ["?"])[-1]


def run_child(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a helper script and capture its output as text that is never lost.

    A Python child on Windows writes to a pipe in the console code page, not UTF-8, so a
    character such as "§" arrives as one byte that UTF-8 cannot decode; the reader thread then
    dies silently and stdout comes back as None. PYTHONIOENCODING makes a Python child write
    UTF-8, and errors="replace" keeps any other child's output readable.
    """
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})


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


def cmd_start(root: Path, name: str, folder: Path, start_at: dict[str, str] | None = None) -> int:
    """Make the copy; `start_at` names a commit to begin a repository's branch at instead of origin."""
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
        begin = (start_at or {}).get(repo_name) or base_ref(repo)
        added = git(repo, "worktree", "add", "--quiet", "-b", branch, str(target), begin)
        if added.returncode:
            print(f"{repo_name}: could not make the worktree – {last_line(added)}")
            remove_copy(root, copy, branch, made)
            return 1
        made.append(repo_name)
    # The brain checks (CONTRACT §15) on every commit in the copy (hooks.py install; relative, so moves are safe).
    subprocess.run([sys.executable, str(copy / "shared/skills/repository-preflight/scripts/hooks.py"),
                    "install"], cwd=copy, capture_output=True)
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
        done = run_child([sys.executable if command[0] == "python" else command[0], *command[1:]], copy)
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


def refused(done: subprocess.CompletedProcess) -> bool:
    """A push refused because origin has commits this branch lacks, as opposed to any other failure."""
    text = (done.stderr or "") + (done.stdout or "")
    return any(word in text for word in REFUSED)


def merge_check_push(copy: Path, repos: list[tuple[str, Path, Path]], base: dict[str, str],
                     preflight: bool, attempt: int) -> bool | None:
    """One round of finish: merge origin, check, push. True: all pushed; False: origin moved on
    during the push, so merge again; None: stopped (a conflict, a failed check, a failed push)."""
    ahead: dict[str, bool] = {}
    for repo_name, _, path in repos:
        ok, what = merge_main(copy, repo_name, path, base[repo_name])
        print(f"{repo_name}: {what}")
        if not ok:
            return None
        ahead[repo_name] = git(path, "merge-base", "--is-ancestor", "HEAD", base[repo_name]).returncode != 0
    if preflight and any(ahead.values()):
        checked = run_child([sys.executable, str(copy / "shared/skills/repository-preflight/scripts/preflight.py"),
                             "--root", str(copy)], copy)
        lines = checked.stdout.splitlines()
        summary = next((line for line in lines if line.startswith(("PASS", "FAIL"))), last_line(checked))
        print(f"preflight: {summary}")
        if checked.returncode:
            # Say why, so the fix is visible without re-running the check by hand
            for line in lines:
                if line.startswith("ERROR"):
                    print(f"  {line}")
            print("preflight failed: nothing was pushed; fix the errors in the session copy and finish again")
            return None
    for repo_name, _, path in repos:
        if not ahead[repo_name]:
            continue
        target = base[repo_name].split("/", 1)[1]
        pushed = git(path, "push", "--quiet", "origin", f"HEAD:{target}")
        if pushed.returncode == 0:
            print(f"{repo_name}: pushed to {target}")
            continue
        if not refused(pushed):
            print(f"{repo_name}: push failed – {last_line(pushed)}; nothing was forced")
            return None
        if attempt < ATTEMPTS:
            print(f"{repo_name}: push refused – origin moved on; merging again "
                  f"(attempt {attempt + 1} of {ATTEMPTS})")
            return False
        print(f"{repo_name}: push refused {ATTEMPTS} times – origin keeps moving; nothing was forced; "
              "run finish again to merge the newer main")
        return None
    return True


def session_repos(root: Path, copy: Path) -> list[tuple[str, Path, Path]]:
    """(name, shared repository, session worktree) for each worktree the copy has."""
    found = []
    for name, repo in repositories(root):
        path = session_path(copy, name)
        if (path / ".git").exists():
            found.append((name, repo, path))
    return found


def owner_field(copy: Path, name: str) -> str:
    """One scalar from the front matter of `/memory/OWNER.md` in the copy, or empty."""
    owner = copy / "memory" / "OWNER.md"
    if not owner.is_file():
        return ""
    found = re.search(rf"^{name}:\s*(\S.*)$", owner.read_text(encoding="utf-8"), re.M)
    return found.group(1).strip().strip("'\"") if found else ""


def project_repos(copy: Path, config: dict) -> list[tuple[str, Path]]:
    """(project id, checkout) for each git project in the release-notes configuration."""
    repos_root = Path(config.get("project_repos_root") or owner_field(copy, "project_repos_root") or copy.parent)
    return [(p["id"], repos_root / p["repo"]) for p in config.get("projects", []) if p.get("kind") == "git"]


def tool(copy: Path, script: str, *args: str) -> tuple[bool, list[str]]:
    """Run one of the brain's scripts from the copy; (ok, its output lines). A missing script
    or a failure is reported in the lines, never raised: the refresh never stops a finish."""
    path = copy / script
    if not path.is_file():
        return False, [f"{script} is not in the copy; skipped"]
    done = run_child([sys.executable, str(path), "--root", str(copy), *args], copy)
    lines = [line for line in ((done.stdout or "") + (done.stderr or "")).splitlines() if line.strip()]
    if done.returncode:
        lines.append(f"{Path(script).name} {' '.join(args)} exited {done.returncode}")
    return done.returncode == 0, lines


def refresh(copy: Path) -> dict:
    """Rebuild the release-notes pages and every board in the copy before the merge.

    Returns what was found: `project_changes` (checkout -> files that need a commit and push
    in that project repository) and `drift` (board id -> what reconcile said). Everything is
    printed as it happens, each part under its own heading; nothing here refuses the finish.
    """
    found: dict = {"project_changes": {}, "drift": {}}
    config_path = copy / RELEASE_CONFIG
    print("release notes:")
    if not config_path.is_file():
        print("  no release-notes configuration in the copy; skipped")
    else:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        repos = project_repos(copy, config)
        steps = [("fix",)] + [("link", pid) for pid, _ in repos] + [("build",)]
        for step in steps:
            _, lines = tool(copy, RELEASE_NOTES, *step)
            for line in lines:
                print("  " + line)
        for pid, checkout in repos:
            status = git(checkout, "status", "--porcelain", "--", "release-notes") if checkout.is_dir() else None
            files = [line[3:].strip() for line in (status.stdout if status and status.returncode == 0 else "").splitlines() if len(line) > 3]
            if files:
                found["project_changes"][str(checkout)] = files
    print("boards:")
    boards_path = copy / BOARDS_CONFIG
    if not boards_path.is_file():
        print("  no boards configuration in the copy; skipped")
    else:
        _, lines = tool(copy, BUILD_STATUS, "--all", "--no-fetch")
        for line in lines:
            print("  " + line)
        boards = json.loads(boards_path.read_text(encoding="utf-8")).get("boards", [])
        for board in boards:
            _, lines = tool(copy, RECONCILE, "--board", board["id"], "--no-fetch")
            adrift = [line.strip()[2:] for line in lines if line.strip().startswith("- ")]
            if adrift:
                found["drift"][board["id"]] = adrift
    print("board drift (printed, never a stop):")
    if not found["drift"]:
        print("  nothing adrift")
    for board_id, adrift in found["drift"].items():
        print(f"  {board_id}:")
        for line in adrift:
            print(f"    - {line}")
    print("project repositories with release notes to commit and push (finish never commits there):")
    if not found["project_changes"]:
        print("  none")
    for checkout, files in found["project_changes"].items():
        print(f"  {checkout}:")
        for file in files:
            print(f"    {file}")
    return found


def co_author(repo: Path) -> str | None:
    """The Co-Authored-By value for a refresh commit: BRAIN_CO_AUTHOR, else the newest one in
    the repository's history, else None (the caller says so; a model is never invented)."""
    value = os.environ.get(CO_AUTHOR_ENV, "").strip()
    if value.lower().startswith("co-authored-by:"):
        value = value.split(":", 1)[1].strip()
    if value:
        return value
    done = git(repo, "log", "-n", "1", "-i", "--grep=^co-authored-by:",
               "--format=%(trailers:key=Co-Authored-By,valueonly)")
    found = [line.strip() for line in (done.stdout or "").splitlines() if line.strip()] if done.returncode == 0 else []
    return found[0] if found else None


def refresh_message(repo: Path) -> str | None:
    """The refresh commit's message with both trailers, or None when no co-author is known."""
    author = co_author(repo)
    return f"{REFRESH_MESSAGE}Co-Authored-By: {author}\n" if author else None


def commit_regenerated(repos: list[tuple[str, Path, Path]]) -> None:
    """Commit what the refresh regenerated in each session worktree, so the finish carries it."""
    for repo_name, _, path in repos:
        if not git(path, "status", "--porcelain").stdout.strip():
            continue
        message = refresh_message(path)
        if message is None:
            print(f"{repo_name}: could not commit the regenerated files – no Co-Authored-By trailer "
                  f"to give it: set {CO_AUTHOR_ENV} or commit with one first (SMART-RULE-0009)")
            continue
        git(path, "add", "-A")
        committed = git(path, "commit", "--quiet", "-m", message)
        if committed.returncode:
            print(f"{repo_name}: could not commit the regenerated files – {last_line(committed)}")
        else:
            print(f"{repo_name}: regenerated files committed")


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
    refresh(copy)
    commit_regenerated(repos)
    base = {repo_name: base_ref(repo) for repo_name, repo, _ in repos}
    for attempt in range(1, ATTEMPTS + 1):
        pushed_all = merge_check_push(copy, repos, base, preflight, attempt)
        if pushed_all is None:
            return 1
        if pushed_all:
            break
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


def merge_diverged(root: Path, repo_name: str, repo: Path) -> tuple[bool, str, list[str]]:
    """Merge a shared-checkout branch that has diverged from origin, outside the shared checkout.

    A copy is started with this repository's branch at the shared checkout's own commit, and
    finished: origin is merged in (a merge commit; a conflicting generated file is rebuilt), the
    result is checked and pushed, and the shared checkout is fast-forwarded to it. The shared
    checkout itself is never merged into (SMART-RULE-0038). Returns (merged, copy path, what
    happened). When it stops – a conflict in a hand-written file, a failed check, a refused push –
    the copy is kept for the session and the owner to finish, and `list` shows it.
    """
    name = f"merge-{repo_name}-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    folder = sessions_folder(root, None)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    out = io.StringIO()
    with redirect_stdout(out):
        code = cmd_start(root, name, folder, {repo_name: head})
        if code == 0:
            code = cmd_finish(root, name, folder, keep=False, preflight=True)
    return code == 0, str(folder / name), [line for line in out.getvalue().splitlines() if line]


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
