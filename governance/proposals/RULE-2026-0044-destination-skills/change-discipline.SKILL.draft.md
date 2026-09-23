---
id: draft-skill-change-discipline
title: Change Discipline (draft for review)
type: skill_draft
schema_version: 0.2
contract: /CONTRACT.md
status: draft
scope: shared
created: 2026-09-17T16:30:00+10:00
updated: 2026-09-17T18:30:00+10:00
owner: brain-owner
---

# Change Discipline

Draft for `/shared/skills/change-discipline/SKILL.md`. Not active. Receives procedure from
`RULE-2026-0017` (logical checkpoint commits) and `RULE-2026-0039` (version every change).

## Purpose

Carry out the commit, push and versioning duties those two rules state, without restating or
weakening them. The rules hold the duties and the authority; this skill holds only how.

## Invocation trigger

Read when work begins in a repository, before the first change is made, and before work starts on a
change that will reach a build. Not at the moment a commit or a bump is contemplated: by then the
staging and version decisions this skill governs have already been made badly or not at all. Both
triggers are stated in the rules themselves, so the skill is reached without an agent needing to
know it exists.

## Allowed operations

- read Git status, diffs and history
- stage, commit and push within the bounds `RULE-2026-0017` sets
- read and write the project's own version field

Never: `--no-verify`, amend, rewrite, force-push, or push to a protected branch, unless the owner
directs that specific action. That bound is the rule's, not this skill's, and cannot be relaxed
here.

## When a checkpoint is mandatory

Moved from `RULE-2026-0017`, which now carries the short form. A checkpoint is mandatory:

- after relevant validation passes
- before switching tasks, repositories, branches or workstreams
- before pausing for owner input or approval while agent-owned changes remain
- before asking the owner to test, reload, load-unpacked, install or try a build
- before the final response when the agent produced durable repository changes
- after 30 minutes of active work with uncommitted agent-owned changes, even if the task continues

## Staging procedure

1. Inspect `git status --short` and the relevant diff.
2. Stage only agent-owned files belonging to that one logical change.
3. Check no secret, credential, vault ciphertext, token, conflict marker or unrelated user change
   is included.
4. Run proportionate validation for what changed.
5. Commit with a message naming the host or tool and the model in use, plus the agent's bot name
   when it has one. Never invent a model or version.

Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned
change separates safely. If ownership or safety is uncertain, leave the path unstaged and ask.

## Permitted reasons to report `No commit`

The rule requires a commit hash and push status, or `No commit` with a specific reason. The
permitted reasons are exactly:

- no durable change
- no Git repository
- the owner explicitly prohibited committing
- validation or a hook failed
- a merge, rebase or conflict is active
- required Git identity or permission is unavailable
- the change cannot be separated safely from uncertain or unrelated files

Anything else is not a reason; it is an unreported commit.

## The three version tests

Moved from `RULE-2026-0039`, which now carries the one-line form. Take the highest that applies,
and bump it once.

- **First number, breaking.** After the change, something that worked before no longer works the
  same way without action by someone: stored data needs a migration or is read differently, an
  interface others call or read changes its shape or meaning, or a procedure a person follows
  changes its steps. Resets the other two.
- **Middle number, feature.** A person can see or do something they could not before, or something
  visible behaves differently on purpose without breaking what depended on it: a new view, a new
  setting, a new record kind, a changed layout. Resets the last number.
- **Last number, small change.** Everything else: a fix, a wording change, a refactor, a performance
  or reliability change, a test-only or build-only change that ships in the product.

Below `1.0.0` a breaking change bumps the **middle** number instead, because nothing outside the
team depends on it yet, and is still named as breaking in the commit message and the node's
`LOG.md`. `1.0.0` is set once, deliberately, when the owner declares the product released.

## Where build identity is shown

The version is what a person sees first; the commit, build time and branch are one step away.

| Product kind | Version shown in | Detail one step away |
|---|---|---|
| Browser extension | Popup, and the browser's extensions card | Tooltip on the version |
| Service | Health or about endpoint | The endpoint's body |
| Page or app | Footer | About panel |
| CLI | `--version` | `--version --verbose` |

A build from a tree with uncommitted changes is marked as such, wherever the version appears.

## Failure behaviour

A push failure never prevents or undoes the local commit; report it and continue. A validation
failure blocks the commit and is reported as the `No commit` reason.

## Logging, state and task behaviour

This skill writes no state or task records of its own. The acting agent records what it changed
under `RULE-2026-0032` at the checkpoint that follows.
