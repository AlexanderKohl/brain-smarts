---
id: PROPOSAL-merge-diverged-history
title: Merge diverged history without asking; stop only for a hand-written conflict, a failed check or someone else's changes
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-30T21:49:18+10:00
updated: 2026-09-30T22:19:37+10:00
rule_id: SMART-RULE-0034
accepted_by: brain-owner
accepted_at: 2026-09-30T22:15:17+10:00
implemented_at: 2026-10-01T10:57:33+10:00
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /RULES.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/session.py
  - /shared/skills/repository-preflight/scripts/sync.py
  - /shared/skills/repository-preflight/tests/test_session.py
  - /shared/skills/repository-preflight/tests/test_sync.py
---

# Merge diverged history without asking

Read `/CONTRACT.md` first. This amends `SMART-RULE-0034` (*Start from the latest*) and keeps its
identifier (CONTRACT §13.2: an amendment keeps the rule's number). The exact diff is the commit
that adds this file on the branch `proposal/merge-diverged-history` in the mechanics; the library
and the memory are not changed. Accepted and implemented on 30 September 2026 (see the end).

## Plain-language summary

Today, when two agents have both committed to the same brain repository and one of them pushed
first, the other stops and asks the owner what to do. After this change it does what the owner
would say: it merges the other agent's work into its own with an ordinary merge commit, rebuilds
any generated file that clashed, runs the repository preflight and pushes – and if the push is
refused because a third agent got in first, it does the same again, up to three times. It asks the
owner only when two people changed the same hand-written text, when the check fails after the
merge, or when it finds uncommitted changes that are not its own. `sync.py` does all of this for
the shared checkout, but inside a temporary session copy, so the shared checkout still only ever
fast-forwards. Project repositories are not affected: they keep their own merge routines.

## Current problem

An owner incident on 30 September 2026: an agent finished its work in the memory, which every
project writes to, and its push was refused because an agent working for another project had pushed
first. `SMART-RULE-0034` says to change nothing in a diverged repository and tell the owner, and to
merge only after the owner says how when files conflict. So the agent stopped and asked. There was
nothing for the owner to decide: two agents' committed work, in different files, needed an ordinary
merge. The owner asked for a standing rule that lets any agent that meets this do the right thing
without asking.

The rule treats three different situations as one:

1. **Someone else's uncommitted changes** – possibly another session in the middle of writing.
   Touching them can lose work. This needs the owner.
2. **Two sides of committed work that merge cleanly** – routine. Git records both sides; nothing
   is lost; a merge commit can be reverted.
3. **Committed work that conflicts in hand-written text** – a judgement about which words stand.
   This needs the owner.

`session.py finish` already handles case 2 for session copies (merge, rebuild generated files,
preflight, push, never force). `sync.py`, run at the start of every session, does not: it reports
"diverged … not merged – the owner decides" and stops. The divergence usually comes from an agent
that committed in the shared checkout instead of a session copy, or from a session copy whose push
raced another.

## Current wording and exact diff

### `/RULES.md` – `SMART-RULE-0034`

Current bullets 2 and 3:

> - When a repository has uncommitted changes, or has commits of its own that `origin` does not
>   (the history has diverged), change nothing in it and tell the owner what differs before
>   starting work there.
> - Never rewrite history or force a push to make a pull work. Diverged history is merged, and
>   when files conflict, only after the owner says how.

The full amended rule, as proposed:

> ## SMART-RULE-0034 – Start from the latest
>
> - At the start of a session, before reading state or changing anything, bring every brain repository on this computer up to date with its `origin`: the mechanics, the skill library and the memory, and a project repository before working in it. Fetch; when the local branch is only behind, fast-forward it. `python shared/skills/repository-preflight/scripts/sync.py` does this for all of them (`--also <repo>` for a project repository).
> - **Diverged history between agents is routine, not an owner decision.** When a brain repository – the mechanics, the skill library or the memory – has commits of its own that `origin` does not, and `origin` has commits it does not (the history has diverged), and no tracked file has uncommitted changes, the agent merges `origin` into it without asking: a merge commit, never a rebase of commits already made, a reset or a forced push. A generated file that conflicts (a board, an index, a task list) is taken from `origin` and rebuilt by its generator; an append-only log keeps both entries. The merged result passes the repository preflight before it is pushed. `sync.py` does this for the shared checkout by merging in a session copy of its own and then fast-forwarding the shared checkout, which is never merged into (`SMART-RULE-0038`); `session.py finish` does it for a session copy.
> - **A refused push is the same case.** When a push is refused because `origin` has moved on, the agent fetches, merges, runs the preflight and pushes again, up to three attempts in all, then stops and reports. `session.py finish` does this itself.
> - **The agent stops and asks the owner only when:**
>   - a hand-written file conflicts: it reports the file, both sides and a suggested resolution, and leaves the merge unfinished in the session copy, never in the shared checkout;
>   - the repository preflight fails on the merged result: it reports the errors and pushes nothing;
>   - tracked files have uncommitted changes that are not its own: it changes nothing in that repository and tells the owner what differs before starting work there. Its own uncommitted work it commits first, then merges or fast-forwards as above.
> - Never rewrite history or force a push to make a pull or a push work.
> - **A project repository keeps its own merge routine.** The merging above covers the brain repositories only. In a project repository `sync.py` reports divergence and changes nothing; the merge routine in the project's own rules applies, and without one the agent tells the owner what differs before starting work there.
> - A computer that cannot reach `origin` says so, and works on only after the owner agrees.
> - Push at the end of each unit of work (`SMART-RULE-0009`), so the next computer starts from it.

Exact diff:

```diff
diff --git a/RULES.md b/RULES.md
index 4794428..212f916 100644
--- a/RULES.md
+++ b/RULES.md
@@ -7,7 +7,7 @@ contract: /CONTRACT.md
 scope: repository
 status: active
 created: 2026-08-04T03:31:56+10:00
-updated: 2026-09-28T14:13:20+10:00
+updated: 2026-09-30T21:47:47+10:00
 owner: brain-owner
 ---
 
@@ -444,8 +444,14 @@ Rules inherit `/CONTRACT.md` -> this file -> `/memory/RULES.md` (the owner layer
 ## SMART-RULE-0034 – Start from the latest
 
 - At the start of a session, before reading state or changing anything, bring every brain repository on this computer up to date with its `origin`: the mechanics, the skill library and the memory, and a project repository before working in it. Fetch; when the local branch is only behind, fast-forward it. `python shared/skills/repository-preflight/scripts/sync.py` does this for all of them (`--also <repo>` for a project repository).
-- When a repository has uncommitted changes, or has commits of its own that `origin` does not (the history has diverged), change nothing in it and tell the owner what differs before starting work there.
-- Never rewrite history or force a push to make a pull work. Diverged history is merged, and when files conflict, only after the owner says how.
+- **Diverged history between agents is routine, not an owner decision.** When a brain repository – the mechanics, the skill library or the memory – has commits of its own that `origin` does not, and `origin` has commits it does not (the history has diverged), and no tracked file has uncommitted changes, the agent merges `origin` into it without asking: a merge commit, never a rebase of commits already made, a reset or a forced push. A generated file that conflicts (a board, an index, a task list) is taken from `origin` and rebuilt by its generator; an append-only log keeps both entries. The merged result passes the repository preflight before it is pushed. `sync.py` does this for the shared checkout by merging in a session copy of its own and then fast-forwarding the shared checkout, which is never merged into (`SMART-RULE-0038`); `session.py finish` does it for a session copy.
+- **A refused push is the same case.** When a push is refused because `origin` has moved on, the agent fetches, merges, runs the preflight and pushes again, up to three attempts in all, then stops and reports. `session.py finish` does this itself.
+- **The agent stops and asks the owner only when:**
+  - a hand-written file conflicts: it reports the file, both sides and a suggested resolution, and leaves the merge unfinished in the session copy, never in the shared checkout;
+  - the repository preflight fails on the merged result: it reports the errors and pushes nothing;
+  - tracked files have uncommitted changes that are not its own: it changes nothing in that repository and tells the owner what differs before starting work there. Its own uncommitted work it commits first, then merges or fast-forwards as above.
+- Never rewrite history or force a push to make a pull or a push work.
+- **A project repository keeps its own merge routine.** The merging above covers the brain repositories only. In a project repository `sync.py` reports divergence and changes nothing; the merge routine in the project's own rules applies, and without one the agent tells the owner what differs before starting work there.
 - A computer that cannot reach `origin` says so, and works on only after the owner agrees.
 - Push at the end of each unit of work (`SMART-RULE-0009`), so the next computer starts from it.
 
```

### `/shared/skills/repository-preflight/scripts/sync.py`

A diverged brain repository in the shared checkout, with no uncommitted changes in tracked files,
is merged through `session.merge_diverged` (below). New report states: `merged`,
`merged, not fast-forwarded`, `diverged, merge stopped`, `diverged, with changes`. The existing
lines (`up to date`, `updated`, `ahead`, `behind, with changes`, `unreachable`, `diverged`) keep
their wording; `diverged` now appears only for a project repository, a session copy or
`--no-merge`, and says which. New flag `--no-merge`: report only. `session.py` is imported inside
the function, not at the top, because `session.py` imports `sync.py`.

```diff
diff --git a/shared/skills/repository-preflight/scripts/sync.py b/shared/skills/repository-preflight/scripts/sync.py
index 674c737..c403792 100644
--- a/shared/skills/repository-preflight/scripts/sync.py
+++ b/shared/skills/repository-preflight/scripts/sync.py
@@ -1,22 +1,32 @@
 #!/usr/bin/env python3
 """Start from the latest (SMART-RULE-0034): bring every brain repository up to date with `origin`.
 
-    python shared/skills/repository-preflight/scripts/sync.py [--also <repo>]... [--json]
+    python shared/skills/repository-preflight/scripts/sync.py [--also <repo>]... [--no-merge] [--json]
 
 For the mechanics (the brain root), the skill library (`library/`) and the memory (`memory/`) –
 and any project repository named with `--also` – it fetches `origin` and, for the checked-out
 branch:
 
 - only behind, no uncommitted changes: fast-forwards it;
-- behind with uncommitted changes, or diverged (commits on both sides): changes nothing and says
-  so, because merging then needs the owner (SMART-RULE-0034);
+- diverged (commits on both sides), no uncommitted changes, a brain repository in the shared
+  checkout: merges it, through `session.py`'s merge – in a session copy whose branch begins at the
+  local commit, `origin` is merged in (a merge commit; a conflicting generated file is rebuilt),
+  preflight is run, the result is pushed (never forced, retried when `origin` moves on) and the
+  shared checkout is fast-forwarded to it. The shared checkout is never merged into. A conflict in
+  a hand-written file, a failed preflight or a push refused three times stops it: the copy is kept
+  with the merge in progress, the shared checkout is unchanged, and it says so;
+- diverged in a project repository (`--also`), in a session copy, or with `--no-merge`: changes
+  nothing and says so – a project repository follows its own merge routine, and a session copy is
+  merged by `session.py finish`;
+- behind or diverged with uncommitted changes: changes nothing and says so, because they may be
+  another session's work (SMART-RULE-0034);
 - ahead only: says how many commits are not pushed yet;
 - `origin` unreachable: says so.
 
-It never merges, rebases, resets, stashes or discards anything, and never pushes. Untracked files
+It never rebases, resets, stashes or discards anything, and never forces a push. Untracked files
 do not count as changes; a fast-forward that would overwrite one fails in Git and is reported.
-Exit code 0 when every repository is up to date (or was fast-forwarded), 1 when one needs the
-owner or could not be checked.
+Exit code 0 when every repository is up to date (or was fast-forwarded or merged), 1 when one
+needs attention or could not be checked.
 """
 
 from __future__ import annotations
@@ -48,8 +58,20 @@ def repositories(root: Path, also: list[Path]) -> list[tuple[str, Path]]:
     return found
 
 
-def sync_one(name: str, repo: Path) -> dict:
-    """What happened to one repository, as {name, state, detail, ok}."""
+def is_session_copy(repo: Path) -> bool:
+    """A linked worktree (a session copy), as opposed to the repository's main checkout."""
+    dirs = [git(repo, "rev-parse", "--path-format=absolute", flag).stdout.strip()
+            for flag in ("--git-dir", "--git-common-dir")]
+    return all(dirs) and Path(dirs[0]).resolve() != Path(dirs[1]).resolve()
+
+
+def sync_one(name: str, repo: Path, merge_from: Path | None = None, project: bool = False) -> dict:
+    """What happened to one repository, as {name, state, detail, ok}.
+
+    `merge_from` is the brain root of the shared checkout when a diverged branch may be merged
+    (SMART-RULE-0034); without it a diverged branch is only reported. `project` marks a project
+    repository, whose own merge routine applies.
+    """
     def result(state: str, detail: str, ok: bool) -> dict:
         return {"name": name, "path": str(repo), "state": state, "detail": detail, "ok": ok}
 
@@ -69,7 +91,29 @@ def sync_one(name: str, repo: Path) -> dict:
     changed = [line for line in git(repo, "status", "--porcelain").stdout.splitlines()
                if line and not line.startswith("??")]
     if ahead and behind:
-        return result("diverged", f"{ahead} local and {behind} remote commits; not merged – the owner decides", False)
+        both = f"{ahead} local and {behind} remote commits"
+        if changed:
+            return result("diverged, with changes", f"{both} and {len(changed)} changed file(s); not merged – "
+                          "commit your own changes and run sync again; changes that are not yours go to the owner", False)
+        if project:
+            return result("diverged", f"{both}; not merged – the project's own merge routine applies; "
+                          "without one, tell the owner", False)
+        if is_session_copy(repo):
+            return result("diverged", f"{both}; not merged here – session.py finish merges a session copy", False)
+        if merge_from is None:
+            return result("diverged", f"{both}; not merged – sync.py without --no-merge merges it", False)
+        import session  # here, not at the top: session.py imports this module (SMART-RULE-0018)
+        merged, copy, lines = session.merge_diverged(merge_from, name, repo)
+        if not merged:
+            said = [line for line in lines if not line.startswith(("session copy:", "work only there"))
+                    and "up to date with" not in line]
+            return result("diverged, merge stopped", f"{both}; the shared checkout is unchanged; the merge stopped "
+                          f"in {copy}: " + " | ".join(said), False)
+        left = git(repo, "rev-list", "--count", "HEAD..@{u}").stdout.strip()
+        if left != "0":
+            return result("merged, not fast-forwarded", f"{both} merged and pushed; the shared checkout is still "
+                          f"{left} commit(s) behind: " + (lines[-1] if lines else "?"), False)
+        return result("merged", f"{both} merged (a merge commit), checked, pushed and fast-forwarded", True)
     if behind and changed:
         return result("behind, with changes", f"{behind} commit(s) behind and {len(changed)} changed file(s); not updated", False)
     if behind:
@@ -86,6 +130,7 @@ def main(argv: list[str] | None = None) -> int:
     parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
     parser.add_argument("--root", type=Path, default=None, help="the brain root (default: found from here)")
     parser.add_argument("--also", type=Path, action="append", default=[], help="a project repository to sync too")
+    parser.add_argument("--no-merge", action="store_true", help="report a diverged brain repository, do not merge it")
     parser.add_argument("--json", action="store_true")
     args = parser.parse_args(argv)
     try:
@@ -96,7 +141,10 @@ def main(argv: list[str] | None = None) -> int:
     if root is None:
         print("CONTRACT.md not found; run inside the brain")
         return 1
-    results = [sync_one(name, repo) for name, repo in repositories(root, args.also)]
+    brain = len(repositories(root, []))
+    results = [sync_one(name, repo, merge_from=None if args.no_merge else root)
+               if index < brain else sync_one(name, repo, project=True)
+               for index, (name, repo) in enumerate(repositories(root, args.also))]
     if args.json:
         print(json.dumps(results, indent=2))
     else:
```

### `/shared/skills/repository-preflight/scripts/session.py`

- `cmd_start` takes an optional start commit per repository (default: `origin`, as today).
- `cmd_finish`'s merge-check-push step moves into `merge_check_push`, which runs up to three rounds:
  a push refused because `origin` moved on (Git's `[rejected]`, `non-fast-forward`, `fetch first`)
  is merged, checked and pushed again; any other push failure stops at once. Nothing is ever forced.
- New `merge_diverged(root, repo_name, repo)`: starts a copy named `merge-<repository>-<time>` whose
  branch for that repository begins at the shared checkout's own commit, and finishes it. The
  shared checkout is fast-forwarded by `finish`'s existing `sync` pass. When it stops, the copy is
  kept and `session.py list` shows it.
- The module docstring says both.

```diff
diff --git a/shared/skills/repository-preflight/scripts/session.py b/shared/skills/repository-preflight/scripts/session.py
index 547f221..c531965 100644
--- a/shared/skills/repository-preflight/scripts/session.py
+++ b/shared/skills/repository-preflight/scripts/session.py
@@ -14,24 +14,31 @@ sessions folder is `<brain root>-sessions` beside the shared checkout unless `--
 `finish` merges each repository's branch with `origin/main`, rebuilds a generated file that
 conflicted (taking `main`'s version first), stops on any other conflict and leaves it for the
 session to resolve, runs preflight, pushes `HEAD:main`, fast-forwards the shared checkout with
-`sync.py`, and removes the worktrees and branches once `main` contains them. `--keep` keeps the copy
-for the next unit of work.
+`sync.py`, and removes the worktrees and branches once `main` contains them. A push refused because
+`origin` moved on is merged, checked and pushed again, up to three attempts in all (SMART-RULE-0034).
+`--keep` keeps the copy for the next unit of work.
+
+`merge_diverged` is how `sync.py` merges a shared-checkout branch whose history has diverged from
+`origin` (SMART-RULE-0034): it starts a copy whose branch begins at that local commit and finishes it
+as above, so the merge happens in the copy and the shared checkout only fast-forwards.
 
 `list` shows every session copy, its age and the commits not yet in `main`, so work left by a
 session that ended is found and finished rather than lost.
 
-It never force-pushes, never removes a worktree with unmerged commits or uncommitted changes, and
-never merges inside the shared checkout. Exit code 0 on success, 1 when something needs attention.
+It never force-pushes, never rebases, never removes a worktree with unmerged commits or uncommitted
+changes, and never merges inside the shared checkout. Exit code 0 on success, 1 when something needs attention.
 """
 
 from __future__ import annotations
 
 import argparse
 import datetime
+import io
 import os
 import re
 import subprocess
 import sys
+from contextlib import redirect_stdout
 from pathlib import Path
 
 sys.path.insert(0, str(Path(__file__).resolve().parent))
@@ -40,6 +47,8 @@ import sync  # noqa: E402  (one canonical brain_root, git and fast-forward, SMAR
 
 NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
 NESTED = ("library", "memory")   # nested repositories, in the order they are made
+ATTEMPTS = 3                     # merge-check-push rounds before a refused push is reported
+REFUSED = ("[rejected]", "non-fast-forward", "fetch first")   # git's words for "origin moved on"
 
 # Generated files a merge may conflict on, per repository: the pattern and the command that
 # rebuilds them, run from the session root. A conflict in any other file stops `finish`.
@@ -116,7 +125,8 @@ def remove_copy(root: Path, copy: Path, branch: str, made: list[str]) -> None:
         git(repo, "branch", "-D", branch)
 
 
-def cmd_start(root: Path, name: str, folder: Path) -> int:
+def cmd_start(root: Path, name: str, folder: Path, start_at: dict[str, str] | None = None) -> int:
+    """Make the copy; `start_at` names a commit to begin a repository's branch at instead of origin."""
     if not NAME_RE.match(name):
         print(f"name must be lower-case letters, digits and hyphens: {name}")
         return 1
@@ -139,7 +149,8 @@ def cmd_start(root: Path, name: str, folder: Path) -> int:
     made: list[str] = []
     for repo_name, repo in repos:
         target = session_path(copy, repo_name)
-        added = git(repo, "worktree", "add", "--quiet", "-b", branch, str(target), base_ref(repo))
+        begin = (start_at or {}).get(repo_name) or base_ref(repo)
+        added = git(repo, "worktree", "add", "--quiet", "-b", branch, str(target), begin)
         if added.returncode:
             print(f"{repo_name}: could not make the worktree – {last_line(added)}")
             remove_copy(root, copy, branch, made)
@@ -207,35 +218,22 @@ def merge_main(copy: Path, repo_name: str, repo: Path, base: str) -> tuple[bool,
     return True, f"merged {base}; rebuilt " + ", ".join(files)
 
 
-def session_repos(root: Path, copy: Path) -> list[tuple[str, Path, Path]]:
-    """(name, shared repository, session worktree) for each worktree the copy has."""
-    found = []
-    for name, repo in repositories(root):
-        path = session_path(copy, name)
-        if (path / ".git").exists():
-            found.append((name, repo, path))
-    return found
+def refused(done: subprocess.CompletedProcess) -> bool:
+    """A push refused because origin has commits this branch lacks, as opposed to any other failure."""
+    text = (done.stderr or "") + (done.stdout or "")
+    return any(word in text for word in REFUSED)
 
 
-def cmd_finish(root: Path, name: str, folder: Path, keep: bool, preflight: bool) -> int:
-    copy = folder / name
-    branch = f"session/{name}"
-    repos = session_repos(root, copy)
-    if not repos:
-        print(f"no session copy at {copy}")
-        return 1
-    for repo_name, _, path in repos:
-        dirty = git(path, "status", "--porcelain").stdout.strip()
-        if dirty:
-            print(f"{repo_name}: uncommitted changes in {path}; commit or discard them first")
-            return 1
+def merge_check_push(copy: Path, repos: list[tuple[str, Path, Path]], base: dict[str, str],
+                     preflight: bool, attempt: int) -> bool | None:
+    """One round of finish: merge origin, check, push. True: all pushed; False: origin moved on
+    during the push, so merge again; None: stopped (a conflict, a failed check, a failed push)."""
     ahead: dict[str, bool] = {}
-    base = {repo_name: base_ref(repo) for repo_name, repo, _ in repos}
     for repo_name, _, path in repos:
         ok, what = merge_main(copy, repo_name, path, base[repo_name])
         print(f"{repo_name}: {what}")
         if not ok:
-            return 1
+            return None
         ahead[repo_name] = git(path, "merge-base", "--is-ancestor", "HEAD", base[repo_name]).returncode != 0
     if preflight and any(ahead.values()):
         checked = run_child([sys.executable, str(copy / "shared/skills/repository-preflight/scripts/preflight.py"),
@@ -249,16 +247,57 @@ def cmd_finish(root: Path, name: str, folder: Path, keep: bool, preflight: bool)
                 if line.startswith("ERROR"):
                     print(f"  {line}")
             print("preflight failed: nothing was pushed; fix the errors in the session copy and finish again")
-            return 1
+            return None
     for repo_name, _, path in repos:
         if not ahead[repo_name]:
             continue
         target = base[repo_name].split("/", 1)[1]
         pushed = git(path, "push", "--quiet", "origin", f"HEAD:{target}")
-        if pushed.returncode:
-            print(f"{repo_name}: push refused – {last_line(pushed)}; run finish again to merge the newer main")
+        if pushed.returncode == 0:
+            print(f"{repo_name}: pushed to {target}")
+            continue
+        if not refused(pushed):
+            print(f"{repo_name}: push failed – {last_line(pushed)}; nothing was forced")
+            return None
+        if attempt < ATTEMPTS:
+            print(f"{repo_name}: push refused – origin moved on; merging again "
+                  f"(attempt {attempt + 1} of {ATTEMPTS})")
+            return False
+        print(f"{repo_name}: push refused {ATTEMPTS} times – origin keeps moving; nothing was forced; "
+              "run finish again to merge the newer main")
+        return None
+    return True
+
+
+def session_repos(root: Path, copy: Path) -> list[tuple[str, Path, Path]]:
+    """(name, shared repository, session worktree) for each worktree the copy has."""
+    found = []
+    for name, repo in repositories(root):
+        path = session_path(copy, name)
+        if (path / ".git").exists():
+            found.append((name, repo, path))
+    return found
+
+
+def cmd_finish(root: Path, name: str, folder: Path, keep: bool, preflight: bool) -> int:
+    copy = folder / name
+    branch = f"session/{name}"
+    repos = session_repos(root, copy)
+    if not repos:
+        print(f"no session copy at {copy}")
+        return 1
+    for repo_name, _, path in repos:
+        dirty = git(path, "status", "--porcelain").stdout.strip()
+        if dirty:
+            print(f"{repo_name}: uncommitted changes in {path}; commit or discard them first")
             return 1
-        print(f"{repo_name}: pushed to {target}")
+    base = {repo_name: base_ref(repo) for repo_name, repo, _ in repos}
+    for attempt in range(1, ATTEMPTS + 1):
+        pushed_all = merge_check_push(copy, repos, base, preflight, attempt)
+        if pushed_all is None:
+            return 1
+        if pushed_all:
+            break
     for repo_name, repo in repositories(root):
         r = sync.sync_one(repo_name, repo)
         print(f"shared checkout {repo_name}: {r['state']}" + (f" – {r['detail']}" if r["detail"] else ""))
@@ -287,6 +326,27 @@ def cmd_finish(root: Path, name: str, folder: Path, keep: bool, preflight: bool)
     return status
 
 
+def merge_diverged(root: Path, repo_name: str, repo: Path) -> tuple[bool, str, list[str]]:
+    """Merge a shared-checkout branch that has diverged from origin, outside the shared checkout.
+
+    A copy is started with this repository's branch at the shared checkout's own commit, and
+    finished: origin is merged in (a merge commit; a conflicting generated file is rebuilt), the
+    result is checked and pushed, and the shared checkout is fast-forwarded to it. The shared
+    checkout itself is never merged into (SMART-RULE-0038). Returns (merged, copy path, what
+    happened). When it stops – a conflict in a hand-written file, a failed check, a refused push –
+    the copy is kept for the session and the owner to finish, and `list` shows it.
+    """
+    name = f"merge-{repo_name}-{datetime.datetime.now():%Y%m%d-%H%M%S}"
+    folder = sessions_folder(root, None)
+    head = git(repo, "rev-parse", "HEAD").stdout.strip()
+    out = io.StringIO()
+    with redirect_stdout(out):
+        code = cmd_start(root, name, folder, {repo_name: head})
+        if code == 0:
+            code = cmd_finish(root, name, folder, keep=False, preflight=True)
+    return code == 0, str(folder / name), [line for line in out.getvalue().splitlines() if line]
+
+
 def cmd_list(root: Path) -> int:
     rows = []
     for repo_name, repo in repositories(root):
```

### `/shared/skills/repository-preflight/SKILL.md`

```diff
diff --git a/shared/skills/repository-preflight/SKILL.md b/shared/skills/repository-preflight/SKILL.md
index 54d4b7f..8b6eb47 100644
--- a/shared/skills/repository-preflight/SKILL.md
+++ b/shared/skills/repository-preflight/SKILL.md
@@ -12,7 +12,7 @@ script_paths:
   - /shared/skills/repository-preflight/scripts/session.py
   - /shared/skills/repository-preflight/tests/test_session.py
 created: 2026-08-04T23:16:08+10:00
-updated: 2026-09-28T08:21:33+10:00
+updated: 2026-09-30T21:47:47+10:00
 owner: brain-owner
 ---
 
@@ -64,9 +64,21 @@ The script uses only the Python standard library.
 
 `scripts/sync.py` (`SMART-RULE-0034`) is run at the start of every session, before anything is
 read: for the mechanics, the library, the memory and any `--also` project repository it fetches
-`origin` and fast-forwards a branch that is only behind. A branch with uncommitted changes, a
-diverged branch and an unreachable `origin` are reported and left untouched; it never merges,
-rebases, resets, stashes, discards or pushes. Exit code 1 means a repository needs the owner.
+`origin` and fast-forwards a branch that is only behind.
+
+A brain repository in the shared checkout whose history has diverged, with no uncommitted changes
+in tracked files, is merged without asking the owner: `session.py`'s merge starts a copy whose
+branch begins at the local commit, merges `origin` into it (a merge commit; a conflicting generated
+file is taken from `origin` and rebuilt), runs preflight, pushes, and fast-forwards the shared
+checkout to the result. The shared checkout is never merged into. A conflict in a hand-written
+file, a failed preflight or a push refused three times stops it: the copy is kept with the merge
+in progress (`session.py list` shows it), the shared checkout is unchanged, and the report names
+the copy and the files. `--no-merge` only reports.
+
+A branch with uncommitted changes, a diverged project repository (`--also`, whose own merge
+routine applies), a diverged session copy (merged by `session.py finish`) and an unreachable
+`origin` are reported and left untouched. It never rebases, resets, stashes, discards or forces a
+push. Exit code 1 means a repository needs attention.
 
 ## One working copy per session
 
@@ -88,8 +100,9 @@ python shared/skills/repository-preflight/scripts/session.py list
   into the session branch. A conflict in a generated file (the owner boards and status pages) is
   resolved by taking `main`'s version and rerunning its generator; any other conflict stops
   `finish` with the merge in progress, for the session to reconcile. It runs preflight on the
-  copy, pushes `HEAD:main` (never forced; a refused push is merged again by running `finish`
-  again), fast-forwards the shared checkout with `sync.py`, and removes each worktree and its
+  copy, pushes `HEAD:main` (never forced; a push refused because `origin` moved on is merged,
+  checked and pushed again, up to three attempts in all, then reported), fast-forwards the shared
+  checkout with `sync.py`, and removes each worktree and its
   branch only once `main` contains it. `--keep` merges and pushes but keeps the copy for the next
   unit of work.
 - `list` shows every session copy, the commits not yet in `main` and its uncommitted files, so
@@ -111,7 +124,8 @@ python shared/skills/repository-preflight/scripts/session.py list
 
 - read access to the repository
 - write access to the two repository manifests only with `--write-manifest`
-- `preflight.py` and `sync.py`: read-only Git commands, except `sync.py`'s fast-forward of a branch that is only behind; no commits, staging or configuration changes
+- `preflight.py`: read-only Git commands; no commits, staging or configuration changes
+- `sync.py`: fast-forwards a branch that is only behind; for a diverged brain repository in the shared checkout, uses `session.py`'s permissions below to merge it in a session copy and push the merge; otherwise read-only Git commands
 - `session.py`: makes and removes worktrees and `session/<name>` branches, commits the merge of `origin/main` into a session branch, and pushes a session branch to `main`; never forces a push, and never removes a worktree with unmerged commits or uncommitted changes
 
 ## Failure behaviour
```

### Tests

`tests/test_sync.py` and `tests/test_session.py` on the branch (`git diff main
proposal/merge-diverged-history -- shared/skills/repository-preflight/tests`). New tests, each on
invented repositories in a temporary folder with a local bare `origin`:

1. `test_sync_merges_clean_diverged_history_and_pushes` – the merge commit's parents are both
   original commits (nothing rebased or forced), both files reach `origin`, the shared checkout's
   last move is a fast-forward, it is clean, and no copy or `session/*` branch is left.
2. `test_sync_stops_on_a_hand_written_conflict_and_changes_nothing_shared` – the shared checkout
   and `origin` are unchanged; the kept copy holds both sides; the report names the file and the copy.
3. `test_sync_rebuilds_a_conflicting_generated_file` – a board that both sides changed is rebuilt
   from the merged records.
4. `test_sync_pushes_nothing_when_preflight_fails_after_the_merge` – the report carries the
   preflight error; `origin` and the shared checkout are unchanged.
5. `test_sync_leaves_a_diverged_session_copy_to_finish` – inside a session copy `sync.py` only
   reports and names `session.py finish`.
6. `test_finish_merges_again_when_its_push_is_refused` – another session pushes between the merge
   and the push; `finish` merges again and succeeds on the second attempt.
7. `test_finish_reports_after_three_refused_pushes` – the race is lost three times; nothing is
   pushed and the copy is kept.
8. `test_a_diverged_project_repository_is_left_to_its_own_routine` – `--also` repositories are
   only reported.
9. `test_diverged_with_uncommitted_changes_is_left_alone` – nothing moves; the uncommitted edit
   survives.

The existing `test_diverged_is_left_alone` now covers `--no-merge`. Tests 1–7 fail on today's code
(the merge path and the retry do not exist); 8 and 9 pin behaviour that must not change.

### Files not changed

- `/CONTRACT.md`: it does not describe divergence; no contract behaviour changes, so the contract
  version stays 2.2.0 (as for `SMART-RULE-0034` itself) and no manifest changes.
- `SMART-RULE-0038`: unchanged. Its promise that the shared checkout holds only merged work and
  changes only by fast-forward still holds, because the merge happens in a copy (below).
- `/shared/templates/memory-skeleton/`: does not mirror `SMART-RULE-0034`.
- `/shared/skills/tasks/scripts/scheduled_review.py`: the unattended daily check keeps reporting
  divergence and changes nothing; the next session's `sync.py` merges it.

## The shared checkout: merge in it, or not?

`SMART-RULE-0038` keeps the shared checkout for merged work only: the owner reads and runs things
there, other sessions may be writing there, and it changes only by fast-forward. `session.py` never
merges inside it. Three ways to give `sync.py` a merge path were weighed:

1. **Merge in the shared checkout, only when Git can do it without a conflict; otherwise report.**
   Simple, but it breaks the fast-forward-only promise, leaves an unpushed merge commit on the
   shared `main` when preflight fails, and cannot rebuild a conflicting generated file without
   putting the shared checkout into a merge in progress. Not chosen.
2. **Merge in a session copy of its own, then fast-forward the shared checkout (chosen).** A copy
   whose branch begins at the shared checkout's local commit is exactly a session that has not
   finished yet, so `session.py finish` does the whole job unchanged: merge, rebuild, preflight,
   push, fast-forward, clean up. The shared checkout never enters a merge state; a conflict or a
   failed check waits in a copy `session.py list` shows; nothing is duplicated
   (`SMART-RULE-0018`); `SMART-RULE-0038` needs no exception. Cost: a few seconds to make and
   remove the worktrees, only when history has diverged.
3. **Report only** (today). The problem this proposal removes.

## Reason

Merging two agents' committed work is mechanical and fully recoverable: a merge commit keeps both
sides and can be reverted. Asking the owner to approve it spends the owner's attention on a
decision with only one sensible answer, and stops work until they reply (`SMART-RULE-0010`: ask
only for irreversible actions, material trade-offs or when policy requires owner choice). The
decisions that do need the owner – whose words stand in a conflict, why the check fails, whose
uncommitted changes these are – are kept. Putting the behaviour in `sync.py` and `session.py`
means every agent in every host that runs them behaves the same, instead of each one reading the
rule and improvising the merge.

## Scope and behavioural consequences

- **Reaches:** the three brain repositories (mechanics, skill library, memory), every agent and
  host that runs `sync.py` or `session.py finish`, on every computer, and new owners.
- **Does not reach project repositories.** They have their own branch models – release branches,
  testing branches, continuous integration, collaborators – and a merge into their default branch
  can release or deploy. `sync.py --also` keeps reporting their divergence; the project's own rules
  decide, and without a routine there the agent asks the owner, as today. Recommended: keep it so.
- **What an agent now does without asking:** at session start, `sync.py` merges and pushes a clean
  diverged brain repository in the shared checkout; `session.py finish` retries a refused push up
  to three times. The report line says what happened (`memory: merged – 1 local and 3 remote
  commits merged (a merge commit), checked, pushed and fast-forwarded`).
- **What still reaches the owner:** a hand-written conflict (file, both sides, a suggested
  resolution; the copy is kept for the resolution), a failed preflight after the merge (the errors;
  nothing pushed), uncommitted changes that are not the agent's own, a push refused three times,
  and an unreachable `origin`.
- **Pushing someone else's commits.** Commits made in the shared checkout by another agent are
  published when the next session's `sync.py` merges them. They were committed, and committed work
  is meant to be pushed (`SMART-RULE-0009`); the preflight gates them first.
- **Hooks.** The host session-start hook, which would run `sync.py`, is held back; if it is
  switched on later, it would merge and push at session start too.

## Risks and conflicts

- **A clean merge that is wrong in meaning.** Two edits to different lines can contradict each
  other and Git merges them without complaint. This is the same risk `session.py finish` already
  carries for every session copy; the preflight catches structural damage, logs merge by union, and
  a merge commit can be reverted.
- **Protected governance committed on the shared `main` without acceptance** would be pushed by the
  merge. The preflight stops it only for a file no accepted proposal has ever listed: its coverage
  check is by file, not by change, so an unaccepted edit to `/RULES.md` or a preflight script
  passes (see *Validation*). Today the same edit would reach `origin` through `session.py finish`
  just as easily, so this change does not open the gap, but it adds one more path through it.
  Closing the gap (coverage per change, not per file) is a separate change to the preflight and is
  recommended; it is not part of this proposal.
- **Two sessions running `sync.py` on the same diverged checkout at once** make two copies; the
  second's push is refused, it merges the first's result and pushes. The history gains a redundant
  merge commit; nothing is lost. A copy name taken in the same second is refused and reported.
- **A stopped merge leaves a copy** (`merge-<repository>-<time>`) in the sessions folder until it
  is finished or removed; `session.py list` shows it, and the report names it.
- **Merge commit messages** are Git's default ("Merge remote-tracking branch …"), without the host
  and model `SMART-RULE-0009` asks for. `session.py finish` already writes them this way; this is a
  known gap, not widened here, and could be closed by a later small change.
- **Conflicts with other rules:** none found. `SMART-RULE-0038` is kept whole (option 2 above);
  `SMART-RULE-0009`'s "never force-push" and `SMART-RULE-0021`'s fail-closed stance are kept.

## Migration

None. At acceptance: merge the branch into `main` in the mechanics, run the preflight and the
preflight-skill tests, record the acceptance and implementation on the original proposal record of
`SMART-RULE-0034` in the owner's memory.

## Rollback

Revert the merge commit of this branch on `main`: `sync.py` goes back to reporting divergence and
`finish` to stopping at the first refused push. Merges already made are ordinary merge commits and
need nothing undone. For an immediate opt-out without a revert, run `sync.py --no-merge`.

## Validation

Done on the branch:

- the preflight-skill tests: 103 of 103 pass (`python -m unittest discover -s shared/skills/repository-preflight/tests`), including the nine new tests above;
- `preflight.py --root .` in the session copy on the proposal branch: PASS, with only the two existing warnings about git-ignored sources in the owner's memory. It gave no protected-governance warning for the target files, because its coverage check counts a file as covered once any accepted proposal has listed it (`/RULES.md` and `sync.py` are listed by earlier accepted proposals). So nothing but this proposal's acceptance keeps the change off `main`; the branch is not merged until then.

Planned after acceptance:

1. The same tests and the preflight on `main`.
2. The first real divergence after acceptance is recorded in the owner's brain-development log:
   the report line, whether the merge needed the owner, and the time it took. Pass mark: no owner
   question for a clean divergence, and no change to the shared checkout other than a fast-forward.

## Acceptance

Accepted by the owner on 30 September 2026, in answer to the one direct question: accept
`PROPOSAL-merge-diverged-history` – the amended `SMART-RULE-0034` and the `sync.py`/`session.py`
change on branch `proposal/merge-diverged-history` (commit `1c3bc0e`), exactly as shown? The
acceptance time is when it was relayed to the implementing session. The owner's own record is
Amendment A1 of `SMART-RULE-0034`'s proposal record in the owner's memory.

## Implementation record

- Applied on 1 October 2026: `1c3bc0e` re-applied unchanged on top of the latest `main` as `a895e03`
  (one commit, so one revert undoes it), followed by the acceptance record. The first application, a
  merge commit made on 30 September, was not pushed: by 1 October `main` had moved 32 commits, and the
  merge commit that brought them in was refused by the commit hook as reaching across two territories.
  Only the two `updated` stamps conflicted; the newer stamp was kept. Only the accepted change set was
  applied.
- Files changed: `/RULES.md` (`SMART-RULE-0034`), `/shared/skills/repository-preflight/SKILL.md`,
  `scripts/sync.py`, `scripts/session.py`, `tests/test_sync.py`, `tests/test_session.py`, and this
  file.
- Effective contract version: 2.2.0, unchanged; no manifest changes.
- Validation: preflight-skill tests 103 of 103 pass; `preflight.py` PASS, with only the two
  existing warnings about git-ignored sources in the owner's memory.
- Unresolved: the coverage gap under *Risks* is taken up by `PROPOSAL-protected-change-coverage`;
  merge commit messages still lack the host and model.
