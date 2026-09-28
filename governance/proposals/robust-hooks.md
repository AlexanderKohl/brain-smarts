---
id: PROPOSAL-robust-hooks
title: Commit checks that work in every set-up
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
created: 2026-09-28T14:40:32+10:00
updated: 2026-09-28T15:01:51+10:00
accepted_by: brain-owner
accepted_at: 2026-09-28T15:01:51+10:00
implemented_at: 2026-09-28T15:01:51+10:00
owner: brain-owner
previous_contract_version: 2.1.0
new_contract_version: 2.2.0
target_files:
  - /CONTRACT.md
  - /.githooks/pre-commit
  - /SETUP.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/scripts/hooks.py
  - /shared/skills/repository-preflight/scripts/session.py
  - /shared/skills/repository-preflight/hooks/events.json
  - /shared/skills/repository-preflight/tests/test_robust_hooks.py
---

# Commit checks that work in every set-up

Read `/CONTRACT.md` first. The exact diff is the branch `proposal/robust-hooks` in the mechanics,
the library and the memory. It replaces the first installation of part 5 of
`PROPOSAL-research-changes`, which wrote hooks into `.git/hooks` with an absolute path and was
removed before it could break a commit.

## What changes

1. **Each repository carries its own versioned hook**, `.githooks/pre-commit`, switched on with a
   relative `core.hooksPath .githooks`. The mechanics keeps its territory check and adds the brain
   check after it; the library and memory get the same small wrapper; the memory skeleton carries
   it for new owners.
2. **The hook finds the brain or steps aside.** It walks up to `CONTRACT.md`. Inside a brain it
   runs the preflight for **this repository only** (`preflight.py --layer`), so another
   repository's or another session's problem never blocks the commit. With no brain above it (a
   repository cloned on its own), or no Python, it prints one line and lets the commit through.
3. **Switched on where it matters:** `hooks.py install` sets the relative path in each present
   repository; `session.py start` runs it for every session copy; `SETUP.md` step B3b for adopters.
4. **A check on GitHub as the backstop** (new file `/.github/workflows/preflight.yml`, and one in
   the library): the preflight on every push and pull request, independent of local hooks. The
   library's run needs a read-only token `BRAIN_SMARTS_TOKEN` when the smarts are private; without
   it the job notes the gap instead of failing.

5. **Acceptance is enforced where a change becomes active** (CONTRACT §13.2, added sentence). On
   a `proposal/*` branch, a protected file that an open proposal lists is reported as a warning,
   so the proposal's exact diff can be committed before the owner decides; on `main`, in session
   branches and in the GitHub check it stays an error. Without this, the commit hook would block
   every proposal branch. Contract 2.1.0 to 2.2.0 on acceptance.

## Behaviour by set-up

| Set-up | Result |
|---|---|
| Full brain, shared checkout | preflight for the committed repository before each commit |
| Session copy | the same; switched on by `session.py start` |
| Smarts only | mechanics checks; memory checks skipped, as preflight already does |
| Library or memory cloned alone | commit goes through with "no brain above this repository" |
| Hook not switched on | nothing runs locally; the GitHub check still runs on push |

## Risks and rollback

Commits wait for the preflight (about 10 to 30 seconds). Rollback: `git config --unset
core.hooksPath` in library and memory, restore the previous `.githooks/pre-commit`, remove the
workflows.

## Validation

93 preflight-skill tests pass, including a repository cloned alone committing through its hook.
