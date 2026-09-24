#!/usr/bin/env python3
"""Start from the latest (SMART-RULE-0034): bring every brain repository up to date with `origin`.

    python shared/skills/repository-preflight/scripts/sync.py [--also <repo>]... [--json]

For the mechanics (the brain root), the skill library (`library/`) and the memory (`memory/`) –
and any project repository named with `--also` – it fetches `origin` and, for the checked-out
branch:

- only behind, no uncommitted changes: fast-forwards it;
- behind with uncommitted changes, or diverged (commits on both sides): changes nothing and says
  so, because merging then needs the owner (SMART-RULE-0034);
- ahead only: says how many commits are not pushed yet;
- `origin` unreachable: says so.

It never merges, rebases, resets, stashes or discards anything, and never pushes. Untracked files
do not count as changes; a fast-forward that would overwrite one fails in Git and is reported.
Exit code 0 when every repository is up to date (or was fast-forwarded), 1 when one needs the
owner or could not be checked.
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


def sync_one(name: str, repo: Path) -> dict:
    """What happened to one repository, as {name, state, detail, ok}."""
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
        return result("diverged", f"{ahead} local and {behind} remote commits; not merged – the owner decides", False)
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
    results = [sync_one(name, repo) for name, repo in repositories(root, args.also)]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['name']}: {r['state']}" + (f" – {r['detail']}" if r["detail"] else ""))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
