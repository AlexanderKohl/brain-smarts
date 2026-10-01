#!/usr/bin/env python3
"""Start from the latest (SMART-RULE-0034): bring every brain repository up to date with `origin`.

    python shared/skills/repository-preflight/scripts/sync.py [--also <repo>]... [--no-merge] [--json]

For the mechanics (the brain root), the skill library (`library/`) and the memory (`memory/`) –
and any project repository named with `--also` – it fetches `origin` and, for the checked-out
branch:

- only behind, no uncommitted changes: fast-forwards it;
- diverged (commits on both sides), no uncommitted changes, a brain repository in the shared
  checkout: merges it, through `session.py`'s merge – in a session copy whose branch begins at the
  local commit, `origin` is merged in (a merge commit; a conflicting generated file is rebuilt),
  preflight is run, the result is pushed (never forced, retried when `origin` moves on) and the
  shared checkout is fast-forwarded to it. The shared checkout is never merged into. A conflict in
  a hand-written file, a failed preflight or a push refused three times stops it: the copy is kept
  with the merge in progress, the shared checkout is unchanged, and it says so;
- diverged in a project repository (`--also`), in a session copy, or with `--no-merge`: changes
  nothing and says so – a project repository follows its own merge routine, and a session copy is
  merged by `session.py finish`;
- behind or diverged with uncommitted changes: changes nothing and says so, because they may be
  another session's work (SMART-RULE-0034);
- ahead only: says how many commits are not pushed yet;
- `origin` unreachable: says so.

It never rebases, resets, stashes or discards anything, and never forces a push. Untracked files
do not count as changes; a fast-forward that would overwrite one fails in Git and is reported.
Exit code 0 when every repository is up to date (or was fast-forwarded or merged), 1 when one
needs attention or could not be checked.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


def brain_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / "CONTRACT.md").is_file():
            return folder
    return None


def repositories(root: Path, also: list[Path]) -> list[tuple[str, Path]]:
    found = [("mechanics", root)]
    for name in ("library", "memory"):
        if (root / name / ".git").exists():
            found.append((name, root / name))
    found += [(path.name, path) for path in also]
    return found


def is_session_copy(repo: Path) -> bool:
    """A linked worktree (a session copy), as opposed to the repository's main checkout."""
    dirs = [git(repo, "rev-parse", "--path-format=absolute", flag).stdout.strip()
            for flag in ("--git-dir", "--git-common-dir")]
    return all(dirs) and Path(dirs[0]).resolve() != Path(dirs[1]).resolve()


def sync_one(name: str, repo: Path, merge_from: Path | None = None, project: bool = False) -> dict:
    """What happened to one repository, as {name, state, detail, ok}.

    `merge_from` is the brain root of the shared checkout when a diverged branch may be merged
    (SMART-RULE-0034); without it a diverged branch is only reported. `project` marks a project
    repository, whose own merge routine applies.
    """
    def result(state: str, detail: str, ok: bool) -> dict:
        return {"name": name, "path": str(repo), "state": state, "detail": detail, "ok": ok}

    if not (repo / ".git").exists():
        return result("not a repository", "no .git here", False)
    if git(repo, "remote", "get-url", "origin").returncode:
        return result("no origin", "nothing to fetch from", False)
    fetched = git(repo, "fetch", "--quiet", "origin")
    if fetched.returncode:
        return result("unreachable", "could not fetch origin: " + (fetched.stderr.strip().splitlines() or ["?"])[-1], False)
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    tracking = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if tracking.returncode:
        return result("no upstream branch", branch + " does not track a branch of origin", False)
    counts = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.split()
    ahead, behind = int(counts[0]), int(counts[1])
    changed = [line for line in git(repo, "status", "--porcelain").stdout.splitlines()
               if line and not line.startswith("??")]
    if ahead and behind:
        both = f"{ahead} local and {behind} remote commits"
        if changed:
            return result("diverged, with changes", f"{both} and {len(changed)} changed file(s); not merged – "
                          "commit your own changes and run sync again; changes that are not yours go to the owner", False)
        if project:
            return result("diverged", f"{both}; not merged – the project's own merge routine applies; "
                          "without one, tell the owner", False)
        if is_session_copy(repo):
            return result("diverged", f"{both}; not merged here – session.py finish merges a session copy", False)
        if merge_from is None:
            return result("diverged", f"{both}; not merged – sync.py without --no-merge merges it", False)
        import session  # here, not at the top: session.py imports this module (SMART-RULE-0018)
        merged, copy, lines = session.merge_diverged(merge_from, name, repo)
        if not merged:
            said = [line for line in lines if not line.startswith(("session copy:", "work only there"))
                    and "up to date with" not in line]
            return result("diverged, merge stopped", f"{both}; the shared checkout is unchanged; the merge stopped "
                          f"in {copy}: " + " | ".join(said), False)
        left = git(repo, "rev-list", "--count", "HEAD..@{u}").stdout.strip()
        if left != "0":
            return result("merged, not fast-forwarded", f"{both} merged and pushed; the shared checkout is still "
                          f"{left} commit(s) behind: " + (lines[-1] if lines else "?"), False)
        return result("merged", f"{both} merged (a merge commit), checked, pushed and fast-forwarded", True)
    if behind and changed:
        return result("behind, with changes", f"{behind} commit(s) behind and {len(changed)} changed file(s); not updated", False)
    if behind:
        merged = git(repo, "merge", "--ff-only", "--quiet", "@{u}")
        if merged.returncode:
            return result("not updated", "fast-forward failed: " + (merged.stderr.strip().splitlines() or ["?"])[-1], False)
        return result("updated", f"fast-forwarded {behind} commit(s)", True)
    if ahead:
        return result("ahead", f"{ahead} commit(s) not pushed yet", True)
    return result("up to date", "", True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="the brain root (default: found from here)")
    parser.add_argument("--also", type=Path, action="append", default=[], help="a project repository to sync too")
    parser.add_argument("--no-merge", action="store_true", help="report a diverged brain repository, do not merge it")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # a Windows console would garble the dashes
    except (AttributeError, ValueError):
        pass
    root = args.root or brain_root(Path.cwd()) or brain_root(Path(__file__).resolve().parent)
    if root is None:
        print("CONTRACT.md not found; run inside the brain")
        return 1
    brain = len(repositories(root, []))
    results = [sync_one(name, repo, merge_from=None if args.no_merge else root)
               if index < brain else sync_one(name, repo, project=True)
               for index, (name, repo) in enumerate(repositories(root, args.also))]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['name']}: {r['state']}" + (f" – {r['detail']}" if r["detail"] else ""))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
