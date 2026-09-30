---
id: PROPOSAL-protected-change-coverage
title: The protected-governance check covers each change, not each file once
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-30T22:29:07+10:00
updated: 2026-09-30T22:29:07+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /shared/schemas/governance-proposal-schema.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
---

# The protected-governance check covers each change, not each file once

Read `/CONTRACT.md` first. This changes how the repository preflight enforces CONTRACT §13.2 and
`SMART-RULE-0002` (*Protected governance*). No rule text in the contract or `/RULES.md` changes, so
the proposal carries no rule identifier. It adds one paragraph to the governance-proposal schema and
one bullet to the preflight skill. The exact diff is the commit that adds this file on the branch
`proposal/protected-change-coverage` in the mechanics. Nothing here is active.

## Plain-language summary

Today the brain's check lets any change to a protected file through once some accepted proposal has
ever listed that file. `/RULES.md` has been listed by dozens of accepted proposals, so an edit to it
that nobody accepted passes. The check also looks only at changes not yet committed, so once
something is committed it is never checked again, even before it is pushed.

After this change, an accepted proposal permits changes to its files only for a window: from the
moment the owner accepts it until an hour after it is marked implemented. A proposal that is never
marked implemented stops permitting changes seven days after acceptance. The check looks at
everything this computer has not yet pushed to `origin/main` – committed or not – and at nothing
already there. Changes that only update the `updated` date or swap an em dash for an en dash still
need no proposal. The practical effect: every substantive change to a protected file needs an
accepted proposal of its own, as the contract already says.

## Current problem

Found while drafting `PROPOSAL-merge-diverged-history` (30 September 2026): its exact diff changed
`/RULES.md`, `sync.py` and `session.py` on a proposal branch, and the preflight gave no
protected-governance warning at all. Two causes, both in `validate_governance`:

1. **Coverage by file, forever.** A file counts as covered when any proposal with status
   `accepted`, `implemented`, `verified` or `reverted` lists it in `target_files`. The acceptance
   time and the implementation time are never read. `/RULES.md` is listed by more than thirty
   accepted records, `sync.py` and `session.py` by earlier ones, so every later edit to them passes
   on `main`.
2. **Only uncommitted changes are seen.** The changed files are `git diff HEAD` plus untracked
   files. A protected change is checked only by the pre-commit hook, at the moment it is committed.
   When `session.py finish` runs the preflight before pushing, the tree is clean and nothing is
   checked, so a commit made without the hook (a host that skips it, `--no-verify`, a merge) reaches
   `origin/main` unchecked.

The contract already requires more: "A substantive or semantic change to protected governance must
not become active until the owner explicitly accepts an identified proposal or the exact displayed
diff", checked "where it becomes active: on `main` and in the branches that merge into it".

## The design, and why this one

A change must be traceable to an acceptance that is about it. Three ways were weighed:

1. **Match the accepted commit's content.** Record the commit the owner accepted and require the
   file on `main` to equal the file at that commit (or the change to equal that commit's diff).
   Exact, but brittle: `/RULES.md` holds every rule, so two proposals in flight at once, a merge
   with an unrelated change, or the `updated` stamp rewritten at merge time all make the content
   differ from any one accepted commit, and a correct implementation fails.
2. **A trailer on every commit** naming the proposal it applies. Traceable, but the pre-commit hook
   cannot see the message, merges and generated commits carry none, and a trailer is a claim the
   agent writes itself.
3. **A time window per proposal (chosen).** A proposal covers changes to the files it lists from
   `accepted_at` until one hour after `implemented_at` (or `reverted_at`); one never marked
   implemented stops covering seven days after `accepted_at`. The check runs where a change becomes
   active – the commit on `main` (pre-commit hook) and the push (`session.py finish`) – so "is a
   window open now" is the right question. It uses fields every accepted proposal already carries
   and that CONTRACT §13.2 already requires the implementing agent to record. It survives merges,
   parallel proposals and stamp rewrites. Its weakness is that another, unaccepted edit to the same
   file inside an open window also passes; the window is minutes to hours long, and only while the
   owner has just accepted a change to that file.

Two supporting changes make the window meaningful:

- **What counts as changed.** A file counts when it differs from where the repository left
  `origin/main` (the merge base with `HEAD`): committed but unpushed, staged, unstaged or untracked.
  Anything already on `origin/main` is never checked again, so history does not fail later. Without
  `origin/main` or `origin/master` (a fresh brain with no remote, the test fixtures) it falls back
  to the last commit, as today.
- **Cosmetic changes need no proposal.** A protected file whose old and new text are equal once the
  `updated:` line, line endings and the dash style (an em dash or en dash with its spaces) are
  ignored is not a substantive change (CONTRACT §13.2 asks acceptance for "a substantive or semantic
  change"). Correcting stamps written ahead of the clock and dash corrections stay free.

## Current wording and exact diff

No rule text changes. The governance wording added is quoted in full here.

**`/shared/schemas/governance-proposal-schema.md`, added after the `implemented_at` requirement:**

> `accepted_at` and `implemented_at` bound what the proposal permits. It covers changes to its
> `target_files` from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for
> seven days after `accepted_at` when it is never marked implemented; after that, a change to the same
> files needs a proposal of its own. So `implemented_at` is written from the clock once the accepted
> change is applied and validated, and the push follows within the hour. The repository preflight
> enforces this (`/shared/skills/repository-preflight/`).

**`/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, new bullet** (and "an
uncovered protected-governance change in either repository" gains "(below)"):

> - **protected governance, coverage per change (CONTRACT §13.2):** a protected file counts as changed when it differs from where the repository left `origin/main` (committed but unpushed, staged, unstaged or untracked; the last commit when there is no `origin/main`), so a change is checked at the commit and the push that would make it active, and never again once it is on `origin/main`. A change is covered only by an accepted proposal that lists the file and whose window is open when the check runs: from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for seven days after `accepted_at` when it has neither. A later change to the same file needs a proposal of its own. A change that only rewrites the `updated` stamp, line endings or an em dash as a spaced en dash is not substantive and needs none. An `accepted_at` that is not a timestamp with a timezone is an error

### `/shared/skills/repository-preflight/scripts/preflight.py`

- `change_base`, `repository_changes`: changes measured from the merge base with `origin/main`.
- `normalised`, `cosmetic_only`: the non-substantive test.
- `stamp`, `coverage_window`: the window from the proposal's own timestamps.
- `validate_governance`: covers a file only through an open window, and says in the error how many
  accepted proposals list the file but no longer cover it (a count, not their names, so no memory
  proposal name reaches the mechanics manifest). The proposal-branch warning is unchanged.

```diff
diff --git a/shared/skills/repository-preflight/scripts/preflight.py b/shared/skills/repository-preflight/scripts/preflight.py
index 74f910f..3159697 100644
--- a/shared/skills/repository-preflight/scripts/preflight.py
+++ b/shared/skills/repository-preflight/scripts/preflight.py
@@ -46,6 +46,14 @@ TIMESTAMP_RE = re.compile(
 # CONTRACT §8.2: a timestamp is never later than the moment it was written. Five minutes allow
 # for clocks on different machines disagreeing slightly when repositories are synced.
 FUTURE_TOLERANCE = timedelta(minutes=5)
+# CONTRACT §13.2, coverage per change: an accepted proposal covers changes to its target files from
+# its acceptance until an hour after its implementation, or for seven days when it is never marked
+# implemented. The branches on which a change becomes active, in the order they are tried.
+IMPLEMENTATION_GRACE = timedelta(hours=1)
+UNIMPLEMENTED_WINDOW = timedelta(days=7)
+MAINLINES = ("origin/main", "origin/master")
+UPDATED_RE = re.compile(r"^updated:\s")
+DASH_RE = re.compile("\\s*[\u2013\u2014]\\s*")
 LOG_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))", re.M)
 SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
 KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")
@@ -630,10 +638,45 @@ def git(repo: Path, *args: str) -> list[str]:
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
+    """(base, paths changed since it): committed, staged, unstaged and untracked."""
+    base = change_base(repo)
+    tracked = git(repo, "diff", "--name-only", "--diff-filter=ACMRTUXB", base)
     untracked = git(repo, "ls-files", "--others", "--exclude-standard")
-    return {value.replace("\\", "/") for value in tracked + untracked}
+    return base, {value.replace("\\", "/") for value in tracked + untracked}
+
+
+def normalised(text: str) -> str:
+    """A file's text without what never needs a proposal: its `updated` stamp, line endings, and
+    the choice of long dash (an em dash replaced by a spaced en dash)."""
+    lines = [line for line in text.replace("\r\n", "\n").split("\n") if not UPDATED_RE.match(line)]
+    return DASH_RE.sub(" – ", "\n".join(lines))
+
+
+def cosmetic_only(repo: Path, base: str, relative: str) -> bool:
+    """True when a changed file differs from its base version only in what `normalised` drops."""
+    try:
+        before = subprocess.run(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "show",
+                                 f"{base}:{relative}"], check=True, capture_output=True).stdout
+        after = (repo / relative).read_bytes()
+    except (OSError, subprocess.CalledProcessError):
+        return False                       # a new file, or one that cannot be read: not cosmetic
+    decode = lambda raw: raw.decode("utf-8", errors="replace")  # noqa: E731
+    return normalised(decode(before)) == normalised(decode(after))
 
 
 def is_own_repository(repo: Path) -> bool:
@@ -653,16 +696,17 @@ def git_failure(exc: Exception) -> str:
     return f"git could not run ({type(exc).__name__})"
 
 
-def changed_paths(root: Path) -> tuple[set[str], list[str]]:
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
@@ -673,14 +717,37 @@ def changed_paths(root: Path) -> tuple[set[str], list[str]]:
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
+    return opened - FUTURE_TOLERANCE, closed
+
+
 def is_protected(path: str) -> bool:
     """Protected governance under CONTRACT §13.2, by brain-root-relative path."""
     # Proposal areas sit outside the inherited rule path: the whole governance/ folder of each
@@ -711,11 +778,18 @@ def validate_governance(
             f"Git change state unavailable; protected-governance coverage not checked: {problem}"
         )
 
-    protected = {"/" + path for path in changed if is_protected(path)}
+    # A change that only touches the `updated` stamp or the dash style is not substantive.
+    protected = {"/" + path for path, (repo, base, relative) in changed.items()
+                 if is_protected(path) and not cosmetic_only(repo, base, relative)}
     if not protected:
         return
 
+    # Coverage is per change, not per file: a proposal covers a file it lists only while its
+    # window is open (coverage_window), judged at the moment the change is checked – the commit
+    # or the push that would make it active.
+    now = clock()
     covered: set[str] = set()
+    closed: dict[str, list[str]] = {}
     proposal_roots = [root.joinpath(*parts) for parts in PROPOSAL_ROOTS]
     for path, metadata in records.items():
         if not any(proposals in path.parents for proposals in proposal_roots):
@@ -730,8 +804,17 @@ def validate_governance(
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
+                closed.setdefault(target, []).append(root_path(path, root))
 
     # CONTRACT 13.2: acceptance is enforced where a change becomes active. On a proposal/*
     # branch, a file an open proposal lists is that proposal's draft diff, reported as a warning.
@@ -750,8 +833,12 @@ def validate_governance(
         if path in drafted:
             result.warnings.append(f"{path}: protected governance drafted on {branch}; not active until accepted and merged")
             continue
+        earlier = closed.get(path)
         result.errors.append(
             f"{path}: changed protected governance is not covered by an accepted proposal"
+            # A count, not the names: memory proposal names must not reach the mechanics manifest.
+            + (f" ({len(earlier)} accepted proposal(s) list it, but each was implemented, or accepted more "
+               "than seven days ago, before this change)" if earlier else "")
         )
 
 
```

### `/shared/skills/repository-preflight/SKILL.md`

```diff
diff --git a/shared/skills/repository-preflight/SKILL.md b/shared/skills/repository-preflight/SKILL.md
index 54d4b7f..e4c9a5d 100644
--- a/shared/skills/repository-preflight/SKILL.md
+++ b/shared/skills/repository-preflight/SKILL.md
@@ -12,7 +12,7 @@ script_paths:
   - /shared/skills/repository-preflight/scripts/session.py
   - /shared/skills/repository-preflight/tests/test_session.py
 created: 2026-08-04T23:16:08+10:00
-updated: 2026-09-28T08:21:33+10:00
+updated: 2026-09-30T22:27:22+10:00
 owner: brain-owner
 ---
 
@@ -119,9 +119,10 @@ python shared/skills/repository-preflight/scripts/session.py list
 - fail if the contract is missing or malformed
 - skip immutable `/memory/raw/` (and `/raw/` in a brain without a separate memory) Markdown evidence (companion source records remain validated)
 - skip the scratch folder `/temp/` and any Markdown file Git ignores, each asked of the repository that holds it (memory paths of the memory repository)
-- fail on missing required Markdown metadata, duplicate IDs, invalid task states, an open task missing from its store's `STATE.md` (`/memory/tasks/STATE.md`) or listed there without its status word (`SMART-RULE-0025`), broken declared references (a `#fragment` after the path must match the start of a Markdown heading in the referenced file), a `/memory/` reference that does not resolve while memory is present, a metadata reference in a mechanics file (any `*_ref`, `*_refs`, `evidence` or other reference key) to a `/memory/` path that `/shared/templates/memory-skeleton/` does not provide – another owner's memory would not have it, so the reference belongs in the owner's memory copy of the file (for a knowledge entry `/memory/skills/<skill>/knowledge/<same filename>`), or the target belongs in the skeleton – contract-version mismatch in either manifest, an uncovered protected-governance change in either repository, or personal data in a shareable repository (below)
+- fail on missing required Markdown metadata, duplicate IDs, invalid task states, an open task missing from its store's `STATE.md` (`/memory/tasks/STATE.md`) or listed there without its status word (`SMART-RULE-0025`), broken declared references (a `#fragment` after the path must match the start of a Markdown heading in the referenced file), a `/memory/` reference that does not resolve while memory is present, a metadata reference in a mechanics file (any `*_ref`, `*_refs`, `evidence` or other reference key) to a `/memory/` path that `/shared/templates/memory-skeleton/` does not provide – another owner's memory would not have it, so the reference belongs in the owner's memory copy of the file (for a knowledge entry `/memory/skills/<skill>/knowledge/<same filename>`), or the target belongs in the skeleton – contract-version mismatch in either manifest, an uncovered protected-governance change in either repository (below), or personal data in a shareable repository (below)
 - warn about undocumented immediate folders, unavailable Git state, an absent memory checkout, a memory folder that is not its own repository, `/memory/` references left unchecked because memory is absent, a missing memory manifest, a declared reference to a git-ignored file absent from this checkout (a local-only recording or scratch run), and a mechanics file whose `owner` is not `brain-owner` (a tripwire for CONTRACT §3.4, not a personal-data scan)
 - **personal data (`SMART-RULE-0008`):** check every file Git tracks or would track in each shareable repository – the mechanics, and the skill library at `/library/` when it is checked out – with `scripts/personal_data.py`. Owner terms are built in memory at run time from `/memory/OWNER.md` (a personal name matches only as written), the owner's own project and system node names (not those the memory skeleton ships) and the optional `/memory/skills/repository-preflight/config/denylist.txt`; patterns find e-mail addresses, telephone numbers (not those reserved for fiction, nor long unbroken counts), UUIDs and absolute user paths. Without memory only the patterns run. Each hit is an error naming file, line and kind; the value is withheld, because errors are written into the committed manifest (`skill_exchange.py scrub <file>` shows it on the console). Generic exemptions are in `config/exemptions.txt`, one per line with its reason; a line without a reason is an error. Owner-specific values never go there. Git failures are reported without their command line, so no machine path reaches a manifest
+- **protected governance, coverage per change (CONTRACT §13.2):** a protected file counts as changed when it differs from where the repository left `origin/main` (committed but unpushed, staged, unstaged or untracked; the last commit when there is no `origin/main`), so a change is checked at the commit and the push that would make it active, and never again once it is on `origin/main`. A change is covered only by an accepted proposal that lists the file and whose window is open when the check runs: from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for seven days after `accepted_at` when it has neither. A later change to the same file needs a proposal of its own. A change that only rewrites the `updated` stamp, line endings or an em dash as a spaced en dash is not substantive and needs none. An `accepted_at` that is not a timestamp with a timezone is an error
 - **timestamps ahead of the clock (CONTRACT §8.2):** fail when a `created` or `updated` value, or a log-entry heading in a `LOG.md`, is more than five minutes ahead of the time the validator runs (the tolerance allows for slightly different clocks on synced machines); the error says how far ahead. Templates and raw evidence are not checked
 - treat a file under a `templates/` folder, or named `_TEMPLATE.md` (a CRM node's contact and persona templates), as a template: its `YYYY-...` timestamps and placeholder references are not errors
 - never repair content silently
```

### `/shared/schemas/governance-proposal-schema.md`

~~~diff
diff --git a/shared/schemas/governance-proposal-schema.md b/shared/schemas/governance-proposal-schema.md
index fb7c963..1b7ee77 100644
--- a/shared/schemas/governance-proposal-schema.md
+++ b/shared/schemas/governance-proposal-schema.md
@@ -6,7 +6,7 @@ schema_version: 0.2
 contract: /CONTRACT.md
 status: active
 created: 2026-08-04T23:16:08+10:00
-updated: 2026-09-23T14:12:51+10:00
+updated: 2026-09-30T22:27:22+10:00
 owner: brain-owner
 ---
 
@@ -65,6 +65,13 @@ Statuses `implemented`, `verified` and `reverted` require:
 implemented_at: YYYY-MM-DDTHH:mm:ss+HH:MM
 ```
 
+`accepted_at` and `implemented_at` bound what the proposal permits. It covers changes to its
+`target_files` from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for
+seven days after `accepted_at` when it is never marked implemented; after that, a change to the same
+files needs a proposal of its own. So `implemented_at` is written from the clock once the accepted
+change is applied and validated, and the push follows within the hour. The repository preflight
+enforces this (`/shared/skills/repository-preflight/`).
+
 ## Required content before acceptance
 
 - current problem
~~~

### Tests (`tests/test_preflight.py`)

`GovernanceTests` now fixes the validator's clock one hour after the fixtures' acceptance time, so
the existing tests keep their meaning. New tests, on invented repositories:

1. `test_an_implemented_proposal_does_not_cover_a_later_change` – the gap itself: a proposal
   implemented two days earlier no longer covers an edit to `/RULES.md`.
2. `test_a_change_within_an_hour_of_implementation_is_covered`.
3. `test_a_change_more_than_an_hour_after_implementation_is_not`.
4. `test_a_proposal_never_marked_implemented_stops_covering_after_seven_days`.
5. `test_a_change_before_acceptance_is_not_covered`.
6. `test_an_acceptance_time_without_a_timezone_is_an_error`.
7. `test_a_committed_but_unpushed_change_is_checked` – the second cause: a committed change with a
   clean tree is still checked.
8. `test_a_change_already_on_origin_is_not_checked_again`.
9. `test_a_stamp_or_dash_only_change_needs_no_proposal` – and a real wording change in the same
   file does need one.
10. `test_a_drafted_change_on_a_proposal_branch_is_a_warning` – the proposal-branch path, which had
    no test.

Tests 1 and 3–7 and 9 fail on today's validator (seven of ten, checked by running them against it);
2, 8 and 10 pin behaviour that must not change.

## Reason

The check exists so that no rule changes without the owner's say. As built, it proves only that a
file was once the subject of an accepted proposal. For the files that change most – `/RULES.md` and
the preflight skill itself – it therefore proves nothing. The fix makes the check mean what CONTRACT
§13.2 says, with the fields every proposal already has.

## Scope and behavioural consequences

- **Reaches** every protected file in the mechanics and the memory: `/CONTRACT.md`, `/RULES.md`,
  `/BOOTSTRAP.md`, `/README.md`, `AGENTS.md` files, every `RULES.md` in memory, governance schemas
  and templates, and the whole repository-preflight skill. It applies in every session, on every
  computer, at the pre-commit hook and at `session.py finish`. It does not change which files are
  protected. The contract version stays 2.2.0, because the contract already requires this.
- **More changes need a proposal.** In the fortnight to 30 September 2026, about ten of the 42
  mechanics commits that touched protected files, and about five of the 14 memory commits, had no
  proposal of their own. They were bug fixes to the preflight skill's scripts, front-page edits to
  `/README.md`, test-fixture renames, node `RULES.md` files moved or repointed during a
  reorganisation, and stamp corrections. The stamp corrections stay free; the others would each
  need an accepted proposal. For a small fix that is a short proposal and one question, and several
  fixes can share one proposal that lists all their files.
- **Implementing a proposal gains a deadline.** The implementing agent records `implemented_at`
  after the change is applied and validated, and pushes within the hour. If the push slips, it
  records a new `implemented_at` at the push. It does not reopen the window any other way.
- **Committed, unpushed protected changes are now checked by `finish`.** A session whose branch
  carries an unaccepted protected change can no longer push it; `finish` stops with the error and
  pushes nothing.

## Risks and conflicts

- **Inside an open window, any edit to the listed files passes.** This is narrower than today (the
  window was "forever"), but it is not a proof that the pushed text is the accepted text. Option 1
  would prove that and was rejected as too brittle; the implementing agent's merge of the exact
  accepted commit remains the evidence.
- **Clocks.** The window uses the validator's clock, with the existing five-minute tolerance before
  `accepted_at`. A computer with a badly wrong clock could misjudge it; the timestamp rules of
  CONTRACT §8.2 already guard against stamps ahead of the clock.
- **A false positive already in the protected-path test.** A file counts as protected when
  `governance` appears anywhere in its path, so a task file whose name contains the word is
  protected, and editing it fails the check. This is true today too; because more changes are now
  seen, it will show more often. A narrower test is a separate change and is not made here.
- **Order with `PROPOSAL-merge-diverged-history`.** That proposal was accepted on 30 September
  2026, but it was not yet pushed when this was drafted; its record says implemented at
  22:19 (+10:00). If this change became active first, that window would close at 23:19, and pushing
  it later would need a new `implemented_at`. So apply that one first.
- **`PROPOSAL-tiered-bootstrap`** also changes `preflight.py` and the preflight SKILL.md, in other
  functions and sections. Whichever lands second merges the other in; no conflict in meaning.
- **Deletions** of protected files are still not counted as changes (the diff filter excludes them,
  as today). That is left as it is.

## Migration

None for records. Accepted proposals from before this change keep their timestamps and simply no
longer cover new changes. A record with status `accepted` and no `implemented_at` stops covering
seven days after `accepted_at`, so no stale window stays open. At acceptance: merge the branch into
mechanics `main`, record `accepted_at` before the merge and `implemented_at` after validation, and
push within the hour.

## Rollback

Revert the merge commit of this branch on `main`. The check returns to per-file coverage of
uncommitted changes. No record needs changing.

## Validation

Done on the branch:

- preflight-skill tests: 104 of 104 pass (`python -m unittest discover -s shared/skills/repository-preflight/tests`), the ten new tests included;
- `preflight.py --root .` in the session copy on the proposal branch: PASS, with four warnings that the target files are protected governance drafted on `proposal/protected-change-coverage`, not active until accepted and merged – the warnings today's check failed to give – and the two existing warnings about git-ignored sources in the owner's memory. Run before this file existed, the new check reported three of the target files as uncovered changes (the preflight script itself was drafted by another open proposal), which today's check lets through.

Planned after acceptance:

1. The same tests and the preflight on `main`, after the merge and before the push.
2. A live negative trial in a throwaway session copy, never pushed. Add a line to `/RULES.md`,
   commit it and run `session.py finish --keep`. Pass: the pre-commit hook refuses the commit;
   committed with `--no-verify`, `finish` stops with the uncovered-change error and pushes nothing.
   Then remove the copy.
3. The next accepted rule change is applied under the new check. Pass: it goes through inside its
   window, with no manual override.

## Acceptance

Not yet given. One direct question: accept `PROPOSAL-protected-change-coverage` – the preflight
check covers each protected change only while an accepted proposal's window is open (from
acceptance to an hour after implementation, seven days at most unimplemented), measured against
`origin/main` – exactly as shown on `proposal/protected-change-coverage`?

## Implementation record

None.
