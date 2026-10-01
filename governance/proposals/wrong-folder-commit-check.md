---
id: PROPOSAL-wrong-folder-commit-check
title: The pre-commit hook refuses a commit on main in the shared checkout
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-10-01T10:52:46+10:00
updated: 2026-10-01T12:05:38+10:00
rule_id: SMART-RULE-0038
accepted_by: brain-owner
accepted_at: 2026-10-01T12:05:38+10:00
implemented_at: 2026-10-01T12:05:38+10:00
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /RULES.md
  - /shared/skills/repository-preflight/scripts/hooks.py
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/tests/test_wrong_folder.py
---

# The pre-commit hook refuses a commit on main in the shared checkout

Read `/CONTRACT.md` first.

## Summary

`SMART-RULE-0038` says a writing session works in its own copy of the brain, never in the shared
checkout. Nothing checks it, and sessions that skip the bootstrap still commit in the shared
checkout. This amendment adds the check to the pre-commit hook every brain repository already runs:
a commit on `main` in a repository's own working tree (the shared checkout) is refused, with the
command that makes a session copy.

- **For agents:** a commit in the wrong folder fails at once, with the fix. A host that cannot work
  in a separate folder (the rule's existing exception) sets `BRAIN_SHARED_CHECKOUT=1` for its
  commits, having said so at the start.
- **For the owner:** nothing changes in a session copy. A commit made by hand in the shared checkout
  needs the same variable.

## Current problem

The owner's count from 28 September to 1 October 2026 found one commit in the shared checkout by
an agent that had not started a session copy. The rule's migration allowed the implementing
session's own commits; no other check exists. The before-and-after test accepted hooks in their
pre-commit form only (28 September 2026), which this check uses: it costs nothing on sessions that
do not commit.

## Current wording

`SMART-RULE-0038`, first bullet (unchanged), and its last bullet:

> - A host that cannot work in a separate folder says so at the start, works in the shared
>   checkout, re-reads each file immediately before changing it, and stages only its own paths.

## Proposed wording

The last bullet of `SMART-RULE-0038` becomes two:

> - The pre-commit hook refuses a commit on `main` in a repository's own working tree – the
>   shared checkout – and names the command that makes a session copy. Session copies are linked
>   worktrees on their own branches, so their commits pass; so do a `proposal/*` branch and any
>   other branch.
> - A host that cannot work in a separate folder says so at the start, works in the shared
>   checkout with `BRAIN_SHARED_CHECKOUT=1` set for its commits, re-reads each file immediately
>   before changing it, and stages only its own paths. The owner uses the same variable for a
>   commit made by hand there.

## Design

In `hooks.py pre_commit`, before the existing checks: when `git rev-parse --git-dir` equals
`git rev-parse --git-common-dir` (the repository's main working tree, not a linked worktree) and
the current branch is `main`, and `BRAIN_SHARED_CHECKOUT` is not `1`, print

```text
pre-commit: this is the shared checkout, which holds only merged work (SMART-RULE-0038).
Work in a session copy: python shared/skills/repository-preflight/scripts/session.py start <name>
A host that cannot work in a separate folder sets BRAIN_SHARED_CHECKOUT=1 for its commits.
```

and fail. `session.py finish` is unaffected: it merges inside the session copy, pushes `HEAD:main`
and fast-forwards the shared checkout, which makes no commit there.

## Reason

A rule with no check where the work passes is skipped (learning record
`a-check-on-a-path-the-work-never-takes-never-runs`). The commit is the one step every writing
session takes, in every host, so the check sits there.

## Scope and behavioural consequences

- Every brain repository with the hooks installed (`hooks.py install`; `session.py start` installs
  them in every copy). A clone without them is unchecked, as today.
- A cloud session working in its own clone on its own branch is unaffected; one committing on `main`
  in its clone is refused and makes a branch, which its host does anyway.

## Risks and conflicts

- **A legitimate commit on `main` in the shared checkout** (the owner by hand, a host without
  separate folders): the variable, named in the refusal.
- **Hooks switched off** (`--no-verify`, which `SMART-RULE-0009` already forbids, or no
  `core.hooksPath`): unchecked. Nothing checks today that the hooks are installed; that is left
  out of this proposal.
- **Conflicts:** none with an active rule.

## Migration

None. Install once per checkout as today.

## Rollback

Remove the check from `hooks.py` and restore the bullet's wording.

## Validation

- A test: a temporary brain with a linked worktree; a commit on `main` in the main working tree is
  refused; the same commit with `BRAIN_SHARED_CHECKOUT=1` passes; a commit in the linked worktree
  passes. With the check removed, the first case passes and the test fails.
- The repository preflight and the hooks' existing tests pass.
- The week's count in `TASK-2026-0087` continues; a wrong-folder commit after the change is a
  failure of the check.

## Acceptance

Accepted by the owner on 1 October 2026. The owner's record is kept in their memory.

## Implementation record

Implemented on 1 October 2026: `hooks.py` `shared_checkout_refusal`, the two bullets of
`SMART-RULE-0038`, the preflight skill's description, and `tests/test_wrong_folder.py`.
