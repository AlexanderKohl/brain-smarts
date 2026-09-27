---
id: PROPOSAL-one-worktree-per-session
title: One working copy per session
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-27T20:41:55+10:00
updated: 2026-09-27T20:47:07+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.0.1
new_contract_version: 2.0.1
target_files:
  - /RULES.md
  - /shared/skills/learning-maintenance/SKILL.md
  - /shared/skills/repository-preflight/SKILL.md
---

# One working copy per session

Draft. Not offered for acceptance: it is to be decided after any evaluation the owner is already
running on related concurrency changes, so the two do not confound each other.

## Current problem

Several agent sessions work at once in one shared checkout of the brain. Nothing keeps them apart
except each session staging only its own paths (`SMART-RULE-0009`) and, for learning records, an
exclusive OS lock held for the duration of a write (`/shared/skills/learning-maintenance/`).

- **In one checkout Git cannot see an overlap.** When two sessions change the same file, the second
  save replaces the first. There is only one copy, so there is nothing to merge and no conflict to
  show. The lost change is found, if at all, by a later reader.
- **The lock excludes nobody.** The skill says "a lock file beside the records" without naming
  one, so two sessions can lock two different files. In the brain where this was found, no lock
  file had ever been left beside the records, so no two sessions are known to have taken the same
  lock. And the lock covers only the moment of the write, not the read before it.
- **A register of claimed files would be worse.** Sessions end without warning, and a claim left
  behind blocks everyone until someone clears it, which needs expiry or renewal: state that goes
  stale. The register is itself a file every session writes, so it needs its own lock. And a
  claim is a status word, which other threads read as fact after it has stopped being true.
- **Uncommitted work from other sessions is normal in the shared checkout,** so
  `SMART-RULE-0034`'s "a repository with uncommitted changes: change nothing and tell the owner"
  fires for reasons that are not the owner's concern.

## Current wording

`/RULES.md` has no rule on where a session works. The only mechanism is in
`/shared/skills/learning-maintenance/SKILL.md`, section *Integration*:

> Take an exclusive OS lock for the duration of the write: `msvcrt.locking` on Windows,
> `fcntl.flock` on POSIX, on a lock file beside the records. The kernel releases it if the holder
> dies, which is the property that matters and the reason no lease, expiry, heartbeat or fencing
> token is needed. Verify this on your own host before relying on it; an owner may record that
> measurement, including where it does not hold, under
> `/memory/projects/brain-development/data/learnings/`.
>
> **It does not hold across separate synced checkouts.** Two clones joined by OneDrive, Dropbox,
> SMB or Git share no kernel, so no lock serialises them. There Git is the backstop: a concurrent
> write is a merge conflict, which is visible and recoverable. That is the weaker guarantee and
> the honest one.

`SMART-RULE-0014` (third bullet) and `SMART-RULE-0024` already give delegated workers an isolated
worktree or branch; they are unchanged.

## Proposed wording or exact diff

`target_files` lists the existing files this changes. It also creates three files, added to
`target_files` when they exist: `/shared/skills/repository-preflight/scripts/session.py`,
`/.gitattributes` and `/shared/templates/memory-skeleton/.gitattributes`.

### 1. New rule in `/RULES.md` (number assigned at acceptance)

Add a row to the identifier table, `| SMART-RULE-NNNN | One working copy per session | this file; /shared/skills/repository-preflight/ |`, and this section:

```markdown
## SMART-RULE-NNNN – One working copy per session

- A session that will write to a brain repository works in its own working copy of the brain,
  never in the shared checkout: a Git worktree of the mechanics, the skill library and the memory,
  each on its own branch made from the latest `origin`, nested as the brain is, so the brain root
  and `/memory/` resolve inside it. `python shared/skills/repository-preflight/scripts/session.py
  start <name>` makes it and prints its path; the session reads and writes only there. A session
  that only reads may use the shared checkout.
- Claim work, not files. What a session is doing is recorded on the task it serves, never as a
  lock or a list of files. Overlap between sessions is found when their work is merged, where Git
  shows it as a conflict.
- Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with
  `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared
  checkout. `session.py finish` does this and removes the worktrees once their branches are
  merged. A conflict is reconciled, never overwritten: a generated file (a board, an index, a
  task list) is taken from `main` and rebuilt by its generator; an append-only log keeps both
  entries; any other conflict whose right resolution is not obvious from the two changes goes to
  the owner.
- The shared checkout holds only merged work. It is where the owner reads and runs things, it is
  fast-forwarded under `SMART-RULE-0034`, and no session leaves uncommitted changes in it.
- A host that cannot work in a separate folder says so at the start, works in the shared
  checkout, re-reads each file immediately before changing it, and stages only its own paths.
```

### 2. `/shared/skills/learning-maintenance/SKILL.md`, section *Integration*

Replace the two quoted paragraphs above with:

```markdown
Work in the session's own copy of the brain (`SMART-RULE-NNNN`). Inside it the session is the only
writer for as long as it lives, so no lock is needed. Two sessions' integrations meet when their
branches merge, and Git shows any overlap as a conflict. A derived view (`index.md`, `board.md`)
that conflicts is taken from `main` and regenerated from the merged records. A host that must
work in the shared checkout re-reads the target immediately before writing and stages only its
own paths; it takes no lock, because a lock that no other session is known to take excludes
nobody.
```

The rest of the section (re-read, merge one record at a time, stage only your own paths, treat a
conflict as the signal to reconcile) is unchanged.

### 3. `session.py` in `/shared/skills/repository-preflight/scripts/`, documented in its `SKILL.md`

- `start <name>`: fetch each brain repository; create `<sessions folder>/<name>/` as a worktree
  of the mechanics on branch `session/<name>` from `origin/main`, with `library/` and `memory/`
  inside it as worktrees of those repositories on the same branch name; print the path. The
  sessions folder sits outside the shared checkout, beside it by default, or where the owner
  profile names.
- `finish <name>`: in each worktree with commits, merge `origin/main`, rebuild generated files
  that conflicted, run preflight, push `HEAD:main`; then fast-forward the shared checkout with
  `sync.py`, and remove the worktree and branch only when the branch is contained in `main`.
- `list`: every session worktree, its age, and commits not yet in `main`, so work left by a
  session that ended is found and finished rather than lost.

It never force-pushes, never removes a worktree with unmerged commits, and never merges inside
the shared checkout.

### 4. `.gitattributes`

Add `LOG.md merge=union` to `/.gitattributes` in the mechanics and to
`/shared/templates/memory-skeleton/.gitattributes`, so two sessions appending to the same log keep
both entries.

## Reason

This is how people who share a codebase work. Each developer has their own copy; nobody locks
files; overlap surfaces when work is merged, as a conflict someone resolves. People claim work
(a ticket), not files, because a forgotten claim then costs duplicated effort rather than lost
work. Exclusive file locks survive only for files that cannot be merged, such as binary art and
office documents, and their known failure is the lock left by someone who has gone away.
Generated files are rebuilt after a merge rather than merged by hand. Short-lived branches merged
often keep conflicts small.

The brain's content is text that merges well, and its sessions end abruptly, which is the case
where locks and claims do worst and optimistic concurrency does best.

## Scope and behavioural consequences

- Every session that writes to the mechanics, the skill library or the memory. Project
  repositories may adopt the same pattern; this proposal does not require it.
- A writing session starts with `session.py start` after `sync.py`, and finishes with
  `session.py finish` at each unit of work instead of committing and pushing in the shared
  checkout.
- A concurrent change to the same file becomes a visible conflict at `finish` instead of a silent
  loss.
- The owner keeps using the shared checkout; it changes only by fast-forward.
- A host's built-in worktree feature, where one exists, usually makes a worktree of the repository
  it opened, not of the nested memory and library repositories, so it is not enough by itself.

## Risks and conflicts

- **Writing into the shared checkout by habit.** Agents know the brain root's absolute path from
  the owner profile. A session that writes there with absolute paths bypasses the rule. Mitigation
  to test: a pre-commit check in the shared checkout that refuses a commit on `main` made from it
  while `session.py list` shows live sessions, with an override for the owner.
- **Cost per session.** Three worktrees check out every tracked file. Measure start and finish time
  and disk use on a real memory before adopting.
- **Union merge order.** Two appended log entries are both kept, but not necessarily in time
  order. Acceptable for a log; the validator could later warn on out-of-order headings.
- **Generated files need generators.** A derived view that is maintained by hand has no generator
  to rerun after a conflict; the learning index and board are like this today. Either write
  generators or resolve those conflicts by hand from the merged records.
- **Worktrees share one repository.** Refs and the object store are shared, so two sessions must
  never use the same branch; `start` refuses a name already in use.
- **Longer sessions mean bigger conflicts.** The merge-at-every-unit-of-work bullet is the
  counterweight.
- `SMART-RULE-0014`'s third bullet ("in a shared worktree, the primary agent commits") still
  applies within one session's copy, to its subagents. `SMART-RULE-0034` is unchanged; it now
  mostly finds a clean shared checkout.
- **Conflicts with other proposals** on hooks, task-number claims or session start should be
  checked when this is decided.

## Migration

1. Write `session.py` with tests, and `.gitattributes` in the mechanics and the skeleton; the
   owner adds the same line to their memory's `.gitattributes`.
2. Sessions running in the shared checkout when this is applied finish there as today.
3. No record changes format; no data moves.

## Rollback

Remove the rule and its index row, restore the two quoted paragraphs in the learning-maintenance
skill, delete `session.py` and its documentation, and remove the `.gitattributes` lines. Finish or
merge any session worktrees first; nothing else depends on them.

## Validation

- `session.py` tests: `start` builds the nested layout, and inside it the brain root and
  `/memory/` resolve to the session copy; `finish` merges, pushes and removes, and refuses to
  remove a worktree with unmerged commits; a conflicting generated file is rebuilt; two appended
  log entries both survive a union merge.
- **A trial with a negative control.** Two sessions change the same learning record and the same
  derived view at the same time. In the shared checkout (control) one change is lost silently;
  with one copy per session the second `finish` reports a conflict and both changes survive
  resolution. The control must show the loss, or the trial proves nothing.
- Measure start and finish time and disk use, and count wrong-folder writes over the first week.
- Repository preflight passes.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence,
adjacent approval or general agreement as acceptance.

## Implementation record

None.
