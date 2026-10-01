---
id: skill-repository-preflight
title: Repository Preflight
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
  - /shared/skills/repository-preflight/scripts/file_sizes.py
  - /shared/skills/repository-preflight/tests/test_file_sizes.py
  - /shared/skills/repository-preflight/scripts/session.py
  - /shared/skills/repository-preflight/tests/test_session.py
created: 2026-08-04T23:16:08+10:00
updated: 2026-10-01T13:26:27+10:00
owner: brain-owner
---

# Repository Preflight

## Purpose

Validate Portable AI Brain repository invariants reproducibly before a substantive update is reported complete.

The validator runs from the brain root, the mechanics repository. When the owner's memory repository is checked out at `/memory/` (CONTRACT §3.5), it validates that too, in the same pass: repository-root paths beginning `/memory/` resolve into the memory checkout, and Git change state is read from each repository separately. A missing memory checkout is a warning, not an error, so the mechanics can be validated on their own. A brain kept in one repository, without a separate memory (tasks at `/tasks/`, raw files at `/raw/`), also validates.

## Allowed operations

- read repository Markdown, metadata and Git change state
- validate contract and proposal governance
- print human-readable or JSON results
- replace `/repository-manifest.json` and, when memory is present, `/memory/repository-manifest.json` only when `--write-manifest` is explicitly supplied

The skill must not modify any other repository file.

## Required inputs

- brain root, supplied with `--root` or discovered by moving upward from the current directory (a path inside `/memory/` finds the root above it)
- optional `--write-manifest`
- optional `--json`

## Data sources

- `/CONTRACT.md`
- Markdown YAML front matter in every repository
- proposals under `/governance/proposals/` and `/memory/governance/proposals/`
- `/memory/tasks/` (or `/tasks/` in a brain without a separate memory)
- Git tracked and untracked change state of each repository when Git is available
- current directory structure of every repository

## Script

```bash
python shared/skills/repository-preflight/scripts/preflight.py --root .
python shared/skills/repository-preflight/scripts/preflight.py --root . --write-manifest
python -m unittest discover -s shared/skills/repository-preflight/tests -v
```

The tests build fictional two-repository brains in temporary folders and need `git` for the governance cases.

The script uses only the Python standard library. `preflight.py` runs the checks; the basics they
share (`preflight_base.py`), the reference checks (`preflight_references.py`), protected governance
(`preflight_governance.py`), the manifests and the personal-data check (`preflight_manifest.py`),
and the file-size check (`file_sizes.py`) are modules of their own.

## Starting from the latest

`scripts/sync.py` (`SMART-RULE-0034`) is run at the start of every session, before anything is
read: for the mechanics, the library, the memory and any `--also` project repository it fetches
`origin` and fast-forwards a branch that is only behind.

A brain repository in the shared checkout whose history has diverged, with no uncommitted changes
in tracked files, is merged without asking the owner: `session.py`'s merge starts a copy whose
branch begins at the local commit, merges `origin` into it (a merge commit; a conflicting generated
file is taken from `origin` and rebuilt), runs preflight, pushes, and fast-forwards the shared
checkout to the result. The shared checkout is never merged into. A conflict in a hand-written
file, a failed preflight or a push refused three times stops it: the copy is kept with the merge
in progress (`session.py list` shows it), the shared checkout is unchanged, and the report names
the copy and the files. `--no-merge` only reports.

A branch with uncommitted changes, a diverged project repository (`--also`, whose own merge
routine applies), a diverged session copy (merged by `session.py finish`) and an unreachable
`origin` are reported and left untouched. It never rebases, resets, stashes, discards or forces a
push. Exit code 1 means a repository needs attention.

## One working copy per session

`scripts/session.py` implements `SMART-RULE-0038`. A session that will write runs it after
`sync.py` and then works only in the copy it prints:

```bash
python shared/skills/repository-preflight/scripts/session.py start <name>
python shared/skills/repository-preflight/scripts/session.py finish <name> [--keep]
python shared/skills/repository-preflight/scripts/session.py list
```

- `start` makes `<sessions folder>/<name>/`: a worktree of the mechanics on branch
  `session/<name>` from the latest `origin`, with `library/` and `memory/` inside it as worktrees
  of those repositories on the same branch. The sessions folder is `<brain root>-sessions` beside
  the shared checkout, unless `--sessions` or a `sessions_root` field in `/memory/OWNER.md` names
  another. A name already used as a branch or folder is refused.
- `finish` refuses a copy with uncommitted changes, then in each repository merges `origin/main`
  into the session branch. A conflict in a generated file (the owner boards and status pages) is
  resolved by taking `main`'s version and rerunning its generator; any other conflict stops
  `finish` with the merge in progress, for the session to reconcile. It runs preflight on the
  copy, pushes `HEAD:main` (never forced; a push refused because `origin` moved on is merged,
  checked and pushed again, up to three attempts in all, then reported), fast-forwards the shared
  checkout with `sync.py`, and removes each worktree and its
  branch only once `main` contains it. `--keep` merges and pushes but keeps the copy for the next
  unit of work.
- `list` shows every session copy, the commits not yet in `main` and its uncommitted files, so
  work left by a session that ended is found and finished rather than lost.
- Append-only logs merge by union (`LOG.md merge=union` in `.gitattributes`), so two sessions'
  entries both survive.
- The commit-message hook (`hooks.py commit-msg`, in all three repositories) refuses a commit, other
  than a merge, whose message lacks a `Tool:` or a `Co-Authored-By:` trailer (`SMART-RULE-0009`);
  in the mechanics and the library it also refuses personal data (`SMART-RULE-0008`).
- The pre-commit hook (`hooks.py pre-commit`) refuses a commit on `main` in a repository's own
  working tree – the shared checkout – and names `session.py start`. A linked worktree (a session
  copy) or any other branch passes. `BRAIN_SHARED_CHECKOUT=1` lets a host that cannot work in a
  separate folder, or the owner by hand, commit there on purpose.

## Outputs

- pass or fail result
- errors and warnings with repository-root paths
- Markdown-file and identifier counts
- generated manifests when requested: `/repository-manifest.json` holds only mechanics results; `/memory/repository-manifest.json` holds every message that names a `/memory/` path, so owner paths never enter the mechanics repository

## Permissions

- read access to the repository
- write access to the two repository manifests only with `--write-manifest`
- `preflight.py`: read-only Git commands; no commits, staging or configuration changes
- `sync.py`: fast-forwards a branch that is only behind; for a diverged brain repository in the shared checkout, uses `session.py`'s permissions below to merge it in a session copy and push the merge; otherwise read-only Git commands
- `session.py`: makes and removes worktrees and `session/<name>` branches, commits the merge of `origin/main` into a session branch, and pushes a session branch to `main`; never forces a push, and never removes a worktree with unmerged commits or uncommitted changes

## Failure behaviour

- fail if the contract is missing or malformed
- skip immutable `/memory/raw/` (and `/raw/` in a brain without a separate memory) Markdown evidence (companion source records remain validated)
- skip the scratch folder `/temp/` and any Markdown file Git ignores, each asked of the repository that holds it (memory paths of the memory repository)
- fail on missing required Markdown metadata, duplicate IDs, invalid task states, an open task missing from its store's `STATE.md` (`/memory/tasks/STATE.md`) or listed there without its status word (`SMART-RULE-0025`), broken declared references (a `#fragment` after the path must match the start of a Markdown heading in the referenced file), a `/memory/` reference that does not resolve while memory is present, a metadata reference in a mechanics file (any `*_ref`, `*_refs`, `evidence` or other reference key) to a `/memory/` path that `/shared/templates/memory-skeleton/` does not provide – another owner's memory would not have it, so the reference belongs in the owner's memory copy of the file (for a knowledge entry `/memory/skills/<skill>/knowledge/<same filename>`), or the target belongs in the skeleton – contract-version mismatch in either manifest, an uncovered protected-governance change in either repository (below), or personal data in a shareable repository (below)
- warn about undocumented immediate folders, unavailable Git state, an absent memory checkout, a memory folder that is not its own repository, `/memory/` references left unchecked because memory is absent, a missing memory manifest, a declared reference to a git-ignored file absent from this checkout (a local-only recording or scratch run), and a mechanics file whose `owner` is not `brain-owner` (a tripwire for CONTRACT §3.4, not a personal-data scan)
- **personal data (`SMART-RULE-0008`):** check every file Git tracks or would track in each shareable repository – the mechanics, and the skill library at `/library/` when it is checked out – with `scripts/personal_data.py`. Owner terms are built in memory at run time from `/memory/OWNER.md` (a personal name matches only as written), the owner's own project and system node names (not those the memory skeleton ships) and the optional `/memory/skills/repository-preflight/config/denylist.txt`; patterns find e-mail addresses, telephone numbers (not those reserved for fiction, nor long unbroken counts), UUIDs and absolute user paths. Without memory only the patterns run. Each hit is an error naming file, line and kind; the value is withheld, because errors are written into the committed manifest (`skill_exchange.py scrub <file>` shows it on the console). Generic exemptions are in `config/exemptions.txt`, one per line with its reason; a line without a reason is an error. Owner-specific values never go there. Git failures are reported without their command line, so no machine path reaches a manifest
- **protected governance, coverage per change (CONTRACT §13.2):** protected governance is rule and contract wording: `/CONTRACT.md`; every file named `RULES.md`, `AGENTS.md` or `CLAUDE.md`, wherever it is; every file whose name ends `RULES.template.md`; every file under `/shared/schemas/` or `/shared/templates/` whose name begins `governance-`; `/BOOTSTRAP.md`; and this *Failure behaviour* section. Nothing under a repository's own `governance/` folder is protected, and nor are this skill's scripts, tests, fixtures and other sections, README files, or a path that merely contains the word governance. A protected file counts as changed when it differs from where the repository left `origin/main` (committed but unpushed, staged, unstaged or untracked; the last commit when there is no `origin/main`), so a change is checked at the commit and the push that would make it active, and never again once it is on `origin/main`. A change is covered only by an accepted proposal that lists the file and whose window is open when the check runs: from `accepted_at` until one hour after `implemented_at` (or `reverted_at`), or for seven days after `accepted_at` when it has neither. A later change to the same file needs a proposal of its own. A change that only rewrites the `updated` stamp, line endings or an em dash as a spaced en dash is not substantive and needs none. An `accepted_at` that is not a timestamp with a timezone is an error
- **code files over the size limit (`SMART-RULE-0041`):** in each repository that has adopted the limit
  (a `sizes.json` in its code-map record folder, named by `code-map.config.json`; the mechanics and the
  library keep `.code-map/`), fail when a code file is over 800 lines and not recorded, or a recorded
  file has grown past its recorded size. Files are counted as the code map counts them, with its
  ignored and size-exempt patterns and code extensions; `tests/test_file_sizes.py` fails when those
  lists differ from the code map's. A repository without a record is not checked
- **timestamps ahead of the clock (CONTRACT §8.2):** fail when a `created` or `updated` value, or a log-entry heading in a `LOG.md`, is more than five minutes ahead of the time the validator runs (the tolerance allows for slightly different clocks on synced machines); the error says how far ahead. Templates and raw evidence are not checked
- treat a file under a `templates/` folder, or named `_TEMPLATE.md` (a CRM node's contact and persona templates), as a template: its `YYYY-...` timestamps and placeholder references are not errors
- never repair content silently

## Logging behaviour

The script does not edit activity logs. The calling agent records significant validation-driven changes under the owning node.

## Repository updates

With `--write-manifest`, replace each repository's manifest atomically, with LF line endings on every platform, with its layer, the current contract version, validation time, that repository's counts, errors and warnings. Otherwise make no repository update.

Validation does not itself update state, knowledge or tasks. The calling agent must route any discovered durable issue under the contract.
