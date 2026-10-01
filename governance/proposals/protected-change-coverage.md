---
id: PROPOSAL-protected-change-coverage
title: The protected-governance check covers each change to rule and contract wording
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-30T22:29:07+10:00
updated: 2026-10-01T11:33:29+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.2.0
new_contract_version: 2.3.0
target_files:
  - /CONTRACT.md
  - /repository-manifest.json
  - /shared/schemas/governance-proposal-schema.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/scripts/preflight_base.py
  - /shared/skills/repository-preflight/scripts/preflight_governance.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
---

# The protected-governance check covers each change to rule and contract wording

Read `/CONTRACT.md` first. This is the second draft. The first (30 September 2026) made every
change to every protected file need a proposal of its own. Asked whether that was right (question
175), the owner chose option 2: "Yes, but only for rule and contract wording, with script and
README changes exempt." This draft does exactly that.

It changes the contract's own wording in §13.2, which is itself protected governance: the list of
protected files shrinks to rule and contract wording, and the contract says that each change needs
its own acceptance. So the contract version goes from 2.2.0 to 2.3.0, and `/CONTRACT.md` is a
target. No `SMART-RULE` text in `/RULES.md` changes, so the proposal carries no rule identifier.

The exact diff is the branch `proposal/protected-change-coverage` in the mechanics against `main`,
with the contract-version bump of the memory and library manifests on a branch of the same name in
each of those repositories. Commits on the mechanics branch, oldest first: the first draft
(`0bbc804`, `587c1a6`, `355c75d`, kept as they were); `873e689` sets aside the first draft's
`preflight.py` and `SKILL.md` hunks, so that `main`, which has since split the validator into
modules, merges in cleanly; `e6f94ad` and `664c90c` merge `main`; `1a02804` is the redraft's code,
tests and skill section; the next commit carries the contract, the manifest and this file. The
manifests are `c959517e` in the memory and `c4c8357` in the library. Nothing here is active.

## Plain-language summary

Today the brain's check lets a change to a protected file through once any accepted proposal has
ever listed that file, and it looks only at changes not yet committed. After this change:

- Only rule and contract wording is protected: the contract, every `RULES.md`, the rule and
  proposal templates and schema, the bootstrap files, and the one section of the preflight skill
  that says what the validator enforces.
- Each substantive change to those needs an accepted proposal of its own, valid from acceptance
  until an hour after it is marked implemented (seven days at most if it never is).
- Scripts – the validator's own code included – tests, fixtures, README files and the rest of a
  skill's text need no proposal at all.
- Committed but unpushed changes are still caught; changes already on `origin/main` are never
  checked again. Stamp, line-ending and dash-only edits stay free.

## Current problem

Found while drafting `PROPOSAL-merge-diverged-history`: its exact diff changed `/RULES.md` and two
preflight scripts on a proposal branch, and the preflight gave no protected-governance warning at
all. Two causes, both in `validate_governance`:

1. **Coverage by file, forever.** A file counts as covered when any proposal with status
   `accepted`, `implemented`, `verified` or `reverted` lists it in `target_files`. Acceptance and
   implementation times are never read. `/RULES.md` is listed by more than thirty accepted records,
   so every later edit to it passes on `main`.
2. **Only uncommitted changes are seen.** The changed files are `git diff HEAD` plus untracked
   files. When `session.py finish` runs the preflight before pushing, the tree is clean and nothing
   is checked, so a commit made without the hook reaches `origin/main` unchecked.

A third problem showed up in the measurement: the protected set is too wide and too blunt. Any
path containing the word `governance` is protected, so editing a task whose file name contains the
word fails the check; and every script, test and fixture of the preflight skill is protected,
although the owner has now said those should not need a proposal.

## The boundary

The validator decides by path alone, so the boundary has to be a list of paths. These are rule and
contract wording, and each substantive change to them needs an accepted proposal whose window is
open:

| Wording | Paths |
|---|---|
| The contract | `/CONTRACT.md` |
| Every rule file | every file named `RULES.md`, wherever it is: `/RULES.md`, `/memory/RULES.md`, node rules in memory, and the rule files the memory skeleton ships |
| Rule and proposal templates and schemas | every file whose name ends `RULES.template.md`; every file under `/shared/schemas/` or `/shared/templates/` whose name begins `governance-` (today the proposal schema and the proposal template) |
| Bootstrap instructions | `/BOOTSTRAP.md`, and every file named `AGENTS.md` or `CLAUDE.md` |
| What the validator enforces | the *Failure behaviour* section of `/shared/skills/repository-preflight/SKILL.md`, and only that section |

Rows are in the order of the contract's own list.

Not protected at all (no proposal, no file-level check): the validator's code and every other
script, tests, test fixtures, README files (the root `/README.md` included), the rest of the
preflight `SKILL.md`, the other skills' `SKILL.md` files, the host-pointer templates in
`/shared/templates/host-pointers/`, everything under a repository's own `governance/` folder (where
proposals live), and any path that merely contains the word `governance`.

Why this line and not another:

1. **Exempt files are not protected at all, rather than kept on today's file-level check.** The
   file-level check gives exempt files almost nothing: every existing script was listed by some
   accepted proposal long ago, so it passes forever. What it still catches is a new file – a new
   test module, a renamed fixture – which is exactly the friction the owner chose to remove. Two
   tiers would also be two rules to explain. One list, one rule.
2. **One section of the preflight skill stays protected.** The owner exempted "SKILL.md operating
   detail that restates no rule". The *Failure behaviour* section of the preflight skill is not
   operating detail: it is the statement of what the validator refuses, the canonical home of
   checks such as `SMART-RULE-0023`, and the only thing that keeps a weaker validator from being a
   quiet rule change (`SMART-RULE-0036`: "changing what a validator accepts is changing a rule").
   With it protected, a code fix that makes the validator do what that section says needs no
   proposal; code that changes what it accepts must change that section too, and that needs one.
   The rest of the file (how to run `sync.py` and `session.py`, outputs, permissions) is exempt.
3. **`CLAUDE.md` joins `AGENTS.md`.** Both are host entry files that tell an agent where the
   contract is; the contract already names them as protected bootstrap instructions, but the
   validator only knew `AGENTS.md`. This is the one place the protected set grows. In the measured
   fortnight it would have cost nothing: no commit changed a `CLAUDE.md`.
4. **The host-pointer templates stay out.** They change with setup work (settings files as much as
   pointers), and the pointer-file check of `SMART-RULE-0007` already fails a pointer that carries
   rule identifiers or grows past a pointer's length. Including the folder would have added six
   commits needing a proposal in the fortnight, for wording that cannot carry a rule anyway.
5. **A moved `RULES.md` counts as new.** Moving a node's rules changes which nodes inherit them,
   which is a change of meaning, so the move needs a proposal. A new node's `RULES.md` does too.

## The coverage window, and why

Unchanged from the first draft. A change must be traceable to an acceptance that is about it.
Matching the accepted commit's content exactly is brittle (two proposals in flight, a merge, a
rewritten stamp all break it); a trailer on every commit is a claim the agent writes itself and the
pre-commit hook cannot see. So: a proposal covers changes to the files it lists from `accepted_at`
until one hour after `implemented_at` (or `reverted_at`); one never marked implemented stops
covering seven days after `accepted_at`. The check runs where a change becomes active – the commit
on `main` (pre-commit hook) and the push (`session.py finish`) – so "is a window open now" is the
right question. It uses fields every accepted proposal already carries.

- **What counts as changed.** A file counts when it differs from where the repository left
  `origin/main` (the merge base with `HEAD`): committed but unpushed, staged, unstaged or
  untracked. Anything already on `origin/main` is never checked again. Without `origin/main` or
  `origin/master` it falls back to the last commit, as today.
- **Non-substantive changes need no proposal.** A protected file whose wording is equal once the
  `updated:` line, line endings and the dash style (an em dash or en dash with its spaces) are
  ignored is not a substantive change. For the preflight `SKILL.md` only the *Failure behaviour*
  section is compared.

## Current wording and exact diff

### `/CONTRACT.md` §13.2 (protected wording; contract 2.2.0 to 2.3.0)

Current:

> Protected governance files are:
>
> - `/CONTRACT.md`
> - every active `RULES.md`, including the owner layer `/memory/RULES.md` and node rules in memory and in project repositories
> - governance schemas and templates
> - bootstrap instructions that determine how agents locate or load the contract and inherited rules
> - the repository preflight skill and validator that enforce this protocol
>
> A substantive or semantic change to protected governance must not become active until the owner explicitly accepts an identified proposal or the exact displayed diff.

Proposed:

> Protected governance is rule and contract wording:
>
> - `/CONTRACT.md`
> - every active `RULES.md`, including the owner layer `/memory/RULES.md` and node rules in memory and in project repositories
> - governance schemas and templates that define the wording of a rule or a proposal
> - bootstrap instructions that determine how agents locate or load the contract and inherited rules
> - the statement of what the repository preflight validator enforces: the *Failure behaviour* section of its skill
>
> The validator's code, tests and fixtures, the rest of its skill, and README files are not protected governance; they change as ordinary persistent changes (section 13.1). Code that changes what the validator accepts or refuses changes the rule it enforces, so the *Failure behaviour* section changes with it, under this section.
>
> A substantive or semantic change to protected governance must not become active until the owner explicitly accepts an identified proposal or the exact displayed diff. Acceptance covers that change, not later changes to the same file: each substantive change needs its own. A change that only rewrites the `updated` stamp, line endings or the dash style is not substantive.

The front matter changes `contract_version: 2.2.0` to `2.3.0` (minor: meaningfully changed
behaviour that existing content stays compatible with) and the `updated` stamp. Everything else in
§13.2, including where proposals are stored, is unchanged. `/repository-manifest.json` records
2.3.0.

### `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour* (protected wording)

New bullet, and "an uncovered protected-governance change in either repository" gains "(below)":

> - **protected governance, coverage per change (CONTRACT §13.2):** protected governance is rule and contract wording: `/CONTRACT.md`; every file named `RULES.md`, `AGENTS.md` or `CLAUDE.md`, wherever it is; every file whose name ends `RULES.template.md`; every file under `/shared/schemas/` or `/shared/templates/` whose name begins `governance-`; `/BOOTSTRAP.md`; and this *Failure behaviour* section. Nothing under a repository's own `governance/` folder is protected, and nor are this skill's scripts, tests, fixtures and other sections, README files, or a path that merely contains the word governance. A protected file counts as changed when it differs from where the repository left `origin/main` (committed but unpushed, staged, unstaged or untracked; the last commit when there is no `origin/main`), so a change is checked at the commit and the push that would make it active, and never again once it is on `origin/main`. A change is covered only by an accepted proposal that lists the file and whose window is open when the check runs: from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for seven days after `accepted_at` when it has neither. A later change to the same file needs a proposal of its own. A change that only rewrites the `updated` stamp, line endings or an em dash as a spaced en dash is not substantive and needs none. An `accepted_at` that is not a timestamp with a timezone is an error

### `/shared/schemas/governance-proposal-schema.md` (protected wording; unchanged from the first draft)

Added after the `implemented_at` requirement:

> `accepted_at` and `implemented_at` bound what the proposal permits. It covers changes to its
> `target_files` from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for
> seven days after `accepted_at` when it is never marked implemented; after that, a change to the same
> files needs a proposal of its own. So `implemented_at` is written from the clock once the accepted
> change is applied and validated, and the push follows within the hour. The repository preflight
> enforces this (`/shared/skills/repository-preflight/`).

### The validator's code (exempt once this is accepted; protected until then, so shown in full)

- `preflight_base.py`: `TIMESTAMP_RE` moves here from `preflight.py` (imported back);
  `change_base`, `repository_changes` measure from the merge base with `origin/main`; `text_at`
  reads a file at that base.
- `preflight_governance.py`: `is_protected` is the boundary above; `wording` and `substantive` are
  the non-substantive test, applied to the *Failure behaviour* section only for the preflight
  `SKILL.md`; `stamp` and `coverage_window` give the window; `validate_governance` covers a file only
  through an open window and says in the error how many accepted proposals list the file but no
  longer cover it (a count, not names, so no memory proposal name reaches the mechanics manifest).
  The proposal-branch warning is unchanged.
- `preflight.py`: passes the validator's clock to `validate_governance`, so tests can fix it.

```diff
diff --git a/shared/skills/repository-preflight/scripts/preflight.py b/shared/skills/repository-preflight/scripts/preflight.py
index 824ac8c..5685894 100644
--- a/shared/skills/repository-preflight/scripts/preflight.py
+++ b/shared/skills/repository-preflight/scripts/preflight.py
@@ -21,7 +21,7 @@ from typing import Any
 from preflight_base import (
     MEMORY_DIR, MEMORY_PREFIX, LIBRARY_DIR, LIBRARY_PREFIX, in_memory, memory_root, in_library,
     library_root, layer_of, Result, message_layer, root_path, git_ignored, is_template_path, git,
-    repository_changes, is_own_repository, git_failure,
+    repository_changes, is_own_repository, git_failure, TIMESTAMP_RE,
 )
 from preflight_references import (
     SKELETON_PARTS, REFERENCE_KEYS, heading_exists, CLOSED_PROPOSAL, removed_files,
@@ -56,9 +56,6 @@ TASK_STATUSES = {
     "completed",
     "cancelled",
 }
-TIMESTAMP_RE = re.compile(
-    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
-)
 # CONTRACT §8.2: a timestamp is never later than the moment it was written. Five minutes allow
 # for clocks on different machines disagreeing slightly when repositories are synced.
 FUTURE_TOLERANCE = timedelta(minutes=5)
@@ -400,7 +397,7 @@ def run(root: Path, writing: bool) -> Result:
     validate_declared_references(root, records, result)
     validate_mechanics_memory_references(root, records, result)
     validate_tasks(root, records, result)
-    validate_governance(root, records, result)
+    validate_governance(root, records, result, clock())
     validate_personal_data(root, result)
     from checks_b import validate_knowledge_provenance, validate_knowledge_review_dates, validate_pointer_files
     validate_pointer_files(root, result.errors)
diff --git a/shared/skills/repository-preflight/scripts/preflight_base.py b/shared/skills/repository-preflight/scripts/preflight_base.py
index 75b3f61..182788e 100644
--- a/shared/skills/repository-preflight/scripts/preflight_base.py
+++ b/shared/skills/repository-preflight/scripts/preflight_base.py
@@ -1,11 +1,12 @@
 """Where each repository of the brain is, the git helpers, and the result every check writes to.
 
-Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
+Moved from preflight.py. preflight.py imports these names back, so everything that uses
 preflight sees the same names.
 """
 
 from __future__ import annotations
 
+import re
 import subprocess
 from dataclasses import dataclass, field
 from pathlib import Path
@@ -15,6 +16,12 @@ MEMORY_DIR = "memory"
 MEMORY_PREFIX = "/" + MEMORY_DIR + "/"
 LIBRARY_DIR = "library"
 LIBRARY_PREFIX = "/" + LIBRARY_DIR + "/"
+# CONTRACT §8.2: second precision and an explicit timezone.
+TIMESTAMP_RE = re.compile(
+    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
+)
+# The branches on which a change becomes active (CONTRACT §13.2), in the order they are tried.
+MAINLINES = ("origin/main", "origin/master")
 
 
 def in_memory(path: Path, root: Path) -> bool:
@@ -112,10 +119,33 @@ def git(repo: Path, *args: str) -> list[str]:
     ).stdout.splitlines()
 
 
-def repository_changes(repo: Path) -> set[str]:
-    tracked = git(repo, "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD")
+def change_base(repo: Path) -> str:
+    """The commit a repository's changes are measured from: where it left the branch on which a
+    change becomes active (CONTRACT §13.2), so committed but unpushed changes count, and changes
+    already on that branch do not. Without such a branch (no remote), the last commit."""
+    for mainline in MAINLINES:
+        try:
+            base = git(repo, "merge-base", mainline, "HEAD")
+        except subprocess.CalledProcessError:
+            continue
+        if base:
+            return base[0]
+    return "HEAD"
+
+
+def repository_changes(repo: Path) -> tuple[str, set[str]]:
+    """(base, paths changed since it): committed but unpushed, staged, unstaged and untracked."""
+    base = change_base(repo)
+    tracked = git(repo, "diff", "--name-only", "--diff-filter=ACMRTUXB", base)
     untracked = git(repo, "ls-files", "--others", "--exclude-standard")
-    return {value.replace("\\", "/") for value in tracked + untracked}
+    return base, {value.replace("\\", "/") for value in tracked + untracked}
+
+
+def text_at(repo: Path, revision: str, relative: str) -> str | None:
+    """A file's text at a revision, or None when it did not exist there."""
+    completed = subprocess.run(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "show",
+                                f"{revision}:{relative}"], capture_output=True)
+    return completed.stdout.decode("utf-8", errors="replace") if completed.returncode == 0 else None
 
 
 def is_own_repository(repo: Path) -> bool:
diff --git a/shared/skills/repository-preflight/scripts/preflight_governance.py b/shared/skills/repository-preflight/scripts/preflight_governance.py
index a7cc188..136bdaf 100644
--- a/shared/skills/repository-preflight/scripts/preflight_governance.py
+++ b/shared/skills/repository-preflight/scripts/preflight_governance.py
@@ -1,15 +1,21 @@
-"""Protected governance (CONTRACT 13.2): a changed protected file needs an accepted proposal.
+"""Protected governance (CONTRACT 13.2): each change to rule or contract wording needs an accepted
+proposal whose window is open.
 
-Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
-preflight sees the same names.
+Moved from preflight.py. preflight.py imports these names back, so everything that uses preflight
+sees the same names.
 """
 
 from __future__ import annotations
 
+import re
 import subprocess
+from datetime import datetime, timedelta
 from pathlib import Path
 from typing import Any
-from preflight_base import MEMORY_DIR, MEMORY_PREFIX, memory_root, Result, root_path, repository_changes, is_own_repository, git_failure
+from preflight_base import (
+    MEMORY_DIR, MEMORY_PREFIX, TIMESTAMP_RE, memory_root, Result, root_path, repository_changes,
+    is_own_repository, git_failure, text_at,
+)
 
 
 ACCEPTED_PROPOSAL_STATUSES = {"accepted", "implemented", "verified", "reverted"}
@@ -21,17 +27,37 @@ PROPOSAL_ROOTS = (
     (MEMORY_DIR, "governance", "proposals"),
 )
 
-
-def changed_paths(root: Path) -> tuple[set[str], list[str]]:
+# CONTRACT §13.2: protected governance is rule and contract wording, named by path. Scripts,
+# tests, fixtures, README files and a skill's other operating detail are not.
+WORDING_PATHS = {"CONTRACT.md", "BOOTSTRAP.md"}
+WORDING_NAMES = {"RULES.md", "AGENTS.md", "CLAUDE.md"}           # wherever they are
+WORDING_TEMPLATE_SUFFIX = "RULES.template.md"                    # a node's rules, to be copied
+GOVERNANCE_FOLDERS = ("shared/schemas/", "shared/templates/")    # files named governance-*
+# The one file of which only a part is wording: the statement of what the validator enforces.
+VALIDATOR_STATEMENT = "shared/skills/repository-preflight/SKILL.md"
+VALIDATOR_SECTION = "## Failure behaviour"
+
+# An accepted proposal covers changes to its target files from its acceptance until an hour after
+# its implementation, or for seven days when it is never marked implemented.
+IMPLEMENTATION_GRACE = timedelta(hours=1)
+UNIMPLEMENTED_WINDOW = timedelta(days=7)
+# The tolerance CONTRACT §8.2 allows between clocks, applied before acceptance.
+CLOCK_TOLERANCE = timedelta(minutes=5)
+UPDATED_RE = re.compile(r"^updated:\s")
+DASH_RE = re.compile("\\s*[\u2013\u2014]\\s*")
+
+
+def changed_paths(root: Path) -> tuple[dict[str, tuple[Path, str, str]], list[str]]:
     """Changed paths relative to the brain root, across both repositories.
 
-    Memory paths carry the `memory/` prefix. Returns the paths and any problems met, one
-    per repository that could not be read.
+    Memory paths carry the `memory/` prefix. Returns {path: (repository, base, path in it)} and
+    any problems met, one per repository that could not be read.
     """
     problems: list[str] = []
-    changed: set[str] = set()
+    changed: dict[str, tuple[Path, str, str]] = {}
     try:
-        changed |= repository_changes(root)
+        base, paths = repository_changes(root)
+        changed.update({value: (root, base, value) for value in paths})
     except (OSError, subprocess.CalledProcessError) as exc:
         problems.append(f"mechanics repository: {git_failure(exc)}")
     memory = memory_root(root)
@@ -42,37 +68,77 @@ def changed_paths(root: Path) -> tuple[set[str], list[str]]:
             )
         else:
             try:
-                changed |= {
-                    f"{MEMORY_DIR}/{value}" for value in repository_changes(memory)
-                }
+                base, paths = repository_changes(memory)
+                changed.update({f"{MEMORY_DIR}/{value}": (memory, base, value) for value in paths})
             except (OSError, subprocess.CalledProcessError) as exc:
                 problems.append(f"{MEMORY_PREFIX} repository: {git_failure(exc)}")
     return changed, problems
 
 
 def is_protected(path: str) -> bool:
-    """Protected governance under CONTRACT §13.2, by brain-root-relative path."""
+    """Rule or contract wording under CONTRACT §13.2, by brain-root-relative path."""
     # Proposal areas sit outside the inherited rule path: the whole governance/ folder of each
     # repository.
-    proposal_areas = ("governance/", f"{MEMORY_DIR}/governance/")
-    if path.startswith(proposal_areas):
+    if path.startswith(("governance/", f"{MEMORY_DIR}/governance/")):
         return False
+    name = path.rsplit("/", 1)[-1]
     return (
-        path == "CONTRACT.md"
-        or path == "BOOTSTRAP.md"
-        or path == "README.md"
-        or path == "AGENTS.md"
-        or path.endswith("/AGENTS.md")
-        or path.endswith("/RULES.md")
-        or path == "RULES.md"
-        or path == "shared/templates/node-RULES.template.md"
-        or path.startswith("shared/skills/repository-preflight/")
-        or "governance" in path
+        path in WORDING_PATHS
+        or name in WORDING_NAMES
+        or name.endswith(WORDING_TEMPLATE_SUFFIX)
+        or (path.startswith(GOVERNANCE_FOLDERS) and name.startswith("governance-"))
+        or path == VALIDATOR_STATEMENT
     )
 
 
+def wording(path: str, text: str) -> str:
+    """The part of a protected file that is wording, without what never needs a proposal: the
+    `updated` stamp, line endings, and the choice of long dash (an em dash as a spaced en dash)."""
+    if path == VALIDATOR_STATEMENT:
+        start = text.find(VALIDATOR_SECTION)
+        end = text.find("\n## ", start + len(VALIDATOR_SECTION)) if start >= 0 else -1
+        text = "" if start < 0 else text[start:end if end >= 0 else len(text)]
+    lines = [line for line in text.replace("\r\n", "\n").split("\n") if not UPDATED_RE.match(line)]
+    return DASH_RE.sub(" \u2013 ", "\n".join(lines)).strip()
+
+
+def substantive(path: str, repo: Path, base: str, relative: str) -> bool:
+    """True when a changed protected file's wording differs from its base version. A new file is
+    substantive when it has any wording; a file that cannot be read is treated as substantive."""
+    try:
+        after = (repo / relative).read_bytes().decode("utf-8", errors="replace")
+    except OSError:
+        return True
+    before = text_at(repo, base, relative)
+    return wording(path, after) != ("" if before is None else wording(path, before))
+
+
+def stamp(value: Any) -> datetime | None:
+    """A front-matter timestamp as an aware datetime, or None when it is not one."""
+    if isinstance(value, datetime):
+        return value if value.tzinfo else None
+    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value.strip()):
+        return None
+    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
+
+
+def coverage_window(metadata: dict[str, Any]) -> tuple[datetime, datetime] | None:
+    """When an accepted proposal covers changes to its target files (CONTRACT §13.2).
+
+    From acceptance until implementation, with an hour's grace for the commits that apply and
+    record it; a proposal accepted but never marked implemented stops covering after seven days.
+    After that a change to the same file needs a proposal of its own.
+    """
+    opened = stamp(metadata.get("accepted_at"))
+    if opened is None:
+        return None
+    ends = [s for s in (stamp(metadata.get("implemented_at")), stamp(metadata.get("reverted_at"))) if s]
+    closed = max(ends) + IMPLEMENTATION_GRACE if ends else opened + UNIMPLEMENTED_WINDOW
+    return opened - CLOCK_TOLERANCE, closed
+
+
 def validate_governance(
-    root: Path, records: dict[Path, dict[str, Any]], result: Result
+    root: Path, records: dict[Path, dict[str, Any]], result: Result, now: datetime
 ) -> None:
     changed, problems = changed_paths(root)
     for problem in problems:
@@ -80,11 +146,15 @@ def validate_governance(
             f"Git change state unavailable; protected-governance coverage not checked: {problem}"
         )
 
-    protected = {"/" + path for path in changed if is_protected(path)}
+    protected = {"/" + path for path, (repo, base, relative) in changed.items()
+                 if is_protected(path) and substantive(path, repo, base, relative)}
     if not protected:
         return
 
+    # Coverage is per change, not per file: a proposal covers a file it lists only while its
+    # window is open, judged at `now` – the commit or the push that would make the change active.
     covered: set[str] = set()
+    closed: dict[str, int] = {}
     proposal_roots = [root.joinpath(*parts) for parts in PROPOSAL_ROOTS]
     for path, metadata in records.items():
         if not any(proposals in path.parents for proposals in proposal_roots):
@@ -99,8 +169,17 @@ def validate_governance(
             )
             continue
         targets = metadata.get("target_files", [])
-        if isinstance(targets, list):
-            covered.update(str(target) for target in targets)
+        if not isinstance(targets, list):
+            continue
+        window = coverage_window(metadata)
+        if window is None:
+            result.errors.append(f"{root_path(path, root)}: accepted_at is not a timestamp with a timezone")
+            continue
+        for target in (str(t) for t in targets):
+            if window[0] <= now <= window[1]:
+                covered.add(target)
+            else:
+                closed[target] = closed.get(target, 0) + 1
 
     # CONTRACT 13.2: acceptance is enforced where a change becomes active. On a proposal/*
     # branch, a file an open proposal lists is that proposal's draft diff, reported as a warning.
@@ -119,6 +198,10 @@ def validate_governance(
         if path in drafted:
             result.warnings.append(f"{path}: protected governance drafted on {branch}; not active until accepted and merged")
             continue
+        earlier = closed.get(path)
         result.errors.append(
             f"{path}: changed protected governance is not covered by an accepted proposal"
+            # A count, not the names: memory proposal names must not reach the mechanics manifest.
+            + (f" ({earlier} accepted proposal(s) list it, but each was implemented, or accepted more "
+               "than seven days ago, before this change)" if earlier else "")
         )
```

### Tests (`tests/test_preflight.py`)

`GovernanceTests` fixes the validator's clock one hour after the fixtures' acceptance time, so the
existing tests keep their meaning. Fourteen new tests, on invented repositories:

1. `test_an_implemented_proposal_does_not_cover_a_later_change` – the gap itself.
2. `test_a_change_within_an_hour_of_implementation_is_covered`.
3. `test_a_change_more_than_an_hour_after_implementation_is_not`.
4. `test_a_proposal_never_marked_implemented_stops_covering_after_seven_days`.
5. `test_a_change_before_acceptance_is_not_covered`.
6. `test_an_acceptance_time_without_a_timezone_is_an_error`.
7. `test_a_committed_but_unpushed_change_is_checked`.
8. `test_a_change_already_on_origin_is_not_checked_again`.
9. `test_a_stamp_or_dash_only_change_needs_no_proposal` – and a real wording change does.
10. `test_a_drafted_change_on_a_proposal_branch_is_a_warning`.
11. `test_script_test_and_readme_changes_need_no_proposal` – the owner's exemption: a validator
    script, a test fixture and the root README changed together raise no governance error.
12. `test_only_the_validators_failure_behaviour_is_wording` – an edit to the preflight skill's
    *Script* section passes; an edit to its *Failure behaviour* section needs a proposal.
13. `test_a_new_node_rules_file_needs_a_proposal`.
14. `test_a_task_named_after_governance_is_not_protected` – the false positive.

`test_protection_by_path` now lists 27 paths across the boundary. Run against today's validator on
`main`, tests 1, 3–7, 9, 11, 12 and 14 fail, and so do eight of the path cases; 2, 8, 10 and 13
pin behaviour that must not change.

## Reason

The check exists so that no rule changes without the owner's say. As built, it proves only that a
file was once the subject of an accepted proposal, so for the files that change most it proves
nothing. The first draft fixed that but made every script fix, test and README edit a governance
question. The owner's answer draws the line where the meaning is: rule and contract wording is
checked change by change; the machinery that enforces it is ordinary work, held to its stated
behaviour by the one protected section that states it.

## Scope and behavioural consequences

- **Reaches** the mechanics and the memory, in every session, at the pre-commit hook and at
  `session.py finish`. Project repositories are not checked by this validator, as today.
- **Fewer files are protected**: the validator's code, tests and fixtures, the rest of its skill,
  `/README.md` and paths that merely contain `governance` leave the protected set. **One kind
  joins**: `CLAUDE.md` files.
- **Re-measured consequence.** First-parent commits on `main` from 17 September to 1 October 2026,
  each judged at its commit time against the windows of every accepted proposal on `main` today
  (an upper bound: a push that carries several commits is checked once):

  | Repository | Commits | Touched a file today's check protects | Would need a proposal: first draft | Touched a wording file | Would need a proposal: this draft |
  |---|---|---|---|---|---|
  | Mechanics | 104 | 35 | 8 | 26 | 3 |
  | Memory | 504 | 16 | 6 | 15 | 5 |

  The six that drop out are two commits changing preflight scripts and their tests, a merge
  adding two test modules its proposal did not list, a test-fixture rename, a front-page
  `README.md` edit, and a memory task whose file name contains `governance`. The eight that remain
  are all from 17 and 23 September, none from the eight days since: two new rule files for the
  memory skeleton that no proposal listed, the contract and `/RULES.md` wording merged during the
  three-layer split before its acceptance was recorded, the memory side of the same split
  (eighteen rule files, `/memory/RULES.md` among them, committed before acceptance), references
  repointed to the skill library inside two node `RULES.md` files, a node `RULES.md` changed in a
  merge, and two
  edits to `/memory/RULES.md` whose proposal records do not cover them at the time they were
  committed (one records its acceptance five hours after the commit). Each of these is rule
  wording changing; under the contract as it stands each already needed acceptance.
- **Implementing a proposal gains a deadline.** The implementing agent records `implemented_at`
  after the change is applied and validated, and pushes within the hour. If the push slips, it
  records a new `implemented_at` at the push.
- **Committed, unpushed changes to wording are checked by `finish`**, which stops with the error
  and pushes nothing.

## Risks and conflicts

- **The validator's code is no longer protected.** An agent could weaken a check in code without
  a proposal. The contract now says that such code changes the rule and must change the protected
  *Failure behaviour* section with it, and `SMART-RULE-0036` already says so; review of that
  section is the safeguard, not a path check. This is the trade the owner chose.
- **Inside an open window, any edit to the listed files passes.** Narrower than today's "forever",
  but not proof that the pushed text is the accepted text; the merge of the exact accepted commit
  remains the evidence. Seen on this branch: until 11:57 on 1 October, the hour after
  `PROPOSAL-merge-diverged-history` was implemented, that proposal's open window covered this
  draft's edit to the preflight `SKILL.md`, and the preflight gave no warning for it.
- **Clocks.** The window uses the validator's clock with the five-minute tolerance before
  `accepted_at`; CONTRACT §8.2 already guards against stamps ahead of the clock.
- **Deletions** of protected files are still not counted as changes (as today). Deleting a
  `RULES.md` removes rules, so it ought to count; that is left for a separate proposal.
- **`PROPOSAL-tiered-bootstrap`** also takes the contract to 2.3.0 and changes `preflight.py` and
  the preflight `SKILL.md`. Whichever is accepted second takes 2.4.0 and merges the other in; the
  two change different functions and sections.
- **A project repository's `brain/RULES.md`** stays protected by the contract but unchecked by this
  validator, as today.

## Migration

None for records. Accepted proposals keep their timestamps and simply no longer cover new changes;
one with status `accepted` and no `implemented_at` stops covering seven days after `accepted_at`.

At acceptance, in this order: record `accepted_at` in this file; merge `proposal/protected-change-coverage`
into `main` in the mechanics, the memory and the library (the latter two carry only the manifest's
contract version); run the tests and the preflight; record `implemented_at`; push all three within
the hour.

## Rollback

Revert the three merge commits. The check returns to per-file coverage of uncommitted changes and
the contract to 2.2.0. No record needs changing.

## Validation

Done on the branch:

- preflight-skill tests: 130 of 130 pass, the fourteen governance tests above included (`python -m unittest discover -s shared/skills/repository-preflight/tests`);
- `preflight.py --root .` in the session copy, with memory and library on their proposal branches:
  PASS, contract 2.3.0. Three warnings that `/CONTRACT.md`, the proposal schema and the preflight `SKILL.md` are protected governance drafted on `proposal/protected-change-coverage`, not active until accepted and merged – and no warning for the three changed scripts or the test file, which are no longer protected – plus the two existing warnings about git-ignored sources in the owner's memory.

Planned after acceptance:

1. The same tests and the preflight on `main`, after the merge and before the push.
2. A live negative trial in a throwaway session copy, never pushed: add a line to `/RULES.md`,
   commit it and run `session.py finish --keep`. Pass: the pre-commit hook refuses the commit;
   committed with `--no-verify`, `finish` stops with the uncovered-change error and pushes nothing.
   A one-line fix to a preflight script in the same copy goes through. Then remove the copy.
3. The next accepted rule change is applied under the new check. Pass: it goes through inside its
   window, with no manual override.

## Acceptance

Not yet given. One direct question: accept `PROPOSAL-protected-change-coverage` as redrafted –
contract 2.3.0, where only rule and contract wording is protected and each change to it needs its
own accepted proposal (valid from acceptance to an hour after implementation, seven days at most),
measured against `origin/main`, with scripts, tests, fixtures and README files exempt – exactly as
shown on `proposal/protected-change-coverage`?

## Implementation record

None.
