---
id: RULE-2026-0017
title: Commit at every successful logical checkpoint
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-08-12T07:12:29+10:00
updated: 2026-09-12T10:45:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-12T07:21:59+10:00
implemented_at: 2026-08-12T07:21:59+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.5.0
target_files:
  - /RULES.md
  - /CONTRACT.md
  - /ONBOARDING_AGENT.md
  - /repository-manifest.json
project_refs:
  - /memory/projects/brain-development
supersedes:
  - RULE-2026-0014
---

# RULE-2026-0017: Commit at every successful logical checkpoint

## Current problem

Active `RULE-2026-0014` requires automatic staging after a successful material
change, but delays committing and pushing until a unit of work is finished or
about one hour has elapsed. "Unit of work" and "finished" are subjective, most
agent turns last less than one hour, and the session-finish checklist does not
require a Git checkpoint. Agents can therefore finish a turn with their own
durable changes staged or unstaged without explicitly deciding whether to
commit them.

The current wording is also scoped only to "this repository", so it does not
clearly govern a different Git repository modified through a project node in
the brain.

## Current wording

`/RULES.md` currently says:

```markdown
- After every successful material change set in this repository, automatically `git add` only the files touched for that change (never secrets or unrelated dirty files) and briefly explain each change to the owner in the chat response.
- Automatically create a git commit and push to the tracked remote when either (a) the current project or defined unit of work is finished, or (b) about one hour of active work has passed since the last commit/push for that workstream while durable staged or unstaged project changes remain. Use a concise commit message; do not use `--no-verify` or force-push to `main`/`master` unless the owner explicitly directs it for that push.
- Still never commit secrets, credentials, vault ciphertext, or private tokens. If unsure whether a path is secret or unrelated, leave it unstaged and ask.
```

`/CONTRACT.md` section 14 currently ends with:

```markdown
9. update logs
10. check that created or changed Markdown files have valid metadata
11. report completed work, unresolved issues and created tasks
```

`/CONTRACT.md` section 15 has no Git checkpoint or final-response accounting
requirement.

`/ONBOARDING_AGENT.md` currently summarises the workflow as:

```markdown
9. **Git workflow (`RULE-2026-0014`):** after each successful material change, auto-stage only those files and explain the change; commit and push when the unit of work finishes or about once per hour. Never stage secrets.
```

## Proposed wording or exact diff

### 1. Replace the three Git workflow bullets in `/RULES.md`

```diff
-- After every successful material change set in this repository, automatically `git add` only the files touched for that change (never secrets or unrelated dirty files) and briefly explain each change to the owner in the chat response.
-- Automatically create a git commit and push to the tracked remote when either (a) the current project or defined unit of work is finished, or (b) about one hour of active work has passed since the last commit/push for that workstream while durable staged or unstaged project changes remain. Use a concise commit message; do not use `--no-verify` or force-push to `main`/`master` unless the owner explicitly directs it for that push.
-- Still never commit secrets, credentials, vault ciphertext, or private tokens. If unsure whether a path is secret or unrelated, leave it unstaged and ask.
+- In every Git repository modified during an owner-authorised task, automatically create a commit at each successful logical checkpoint. A logical checkpoint exists when an independently describable improvement, fix, document update, configuration change or tested implementation is complete. Do not wait for the entire project to finish and do not bundle unrelated logical changes.
+- A Git checkpoint is mandatory after relevant validation passes; before switching tasks, repositories, branches or workstreams; before pausing for owner input or approval while agent-owned changes remain; before the final response when the agent produced durable repository changes; and after 30 minutes of active work with uncommitted agent-owned changes, even if the larger task continues.
+- At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.
+- Never commit secrets, credentials, vault ciphertext, private tokens, unresolved conflict markers or unrelated user changes. Do not use `--no-verify`, amend or rewrite an existing commit, force-push, or push directly to a protected `main` or `master` branch unless the owner explicitly directs that specific action. If ownership or safety is uncertain, leave the uncertain path unstaged and ask.
+- Treat commit and push as separate decisions. A push failure or unavailable remote must never prevent the local commit. Push accumulated agent-created commits to the tracked remote when the unit of work finishes and before the final response, or after 30 minutes since the last successful push while work continues, unless the owner has prohibited pushing or repository policy requires review through another path.
+- Never silently finish with committable agent-owned changes. In the final response, report the commit hash and push status for each modified repository, or state `No commit` with the specific reason. Valid reasons include: no durable change, no Git repository, the owner explicitly prohibited committing, validation or a hook failed, a merge/rebase/conflict is active, required Git identity or permission is unavailable, or the change cannot be separated safely from uncertain or unrelated files.
```

### 2. Amend `/CONTRACT.md` section 14

```diff
 9. update logs
 10. check that created or changed Markdown files have valid metadata
-11. report completed work, unresolved issues and created tasks
+11. before pausing or reporting completion, execute the applicable inherited Git checkpoint rule for every repository modified during the task
+12. report completed work, unresolved issues, created tasks, commit hashes and push status; when no commit was created despite durable changes, report the exact blocking reason
```

### 3. Add two checks to `/CONTRACT.md` section 15

Add after `- the repository preflight validator passes`:

```diff
+- every separable, validated, agent-owned durable change has been committed at the required logical checkpoint
+- the final report identifies each resulting commit and push status, or gives the exact permitted reason no commit was created
```

### 4. Replace the Git workflow summary in `/ONBOARDING_AGENT.md`

```diff
-9. **Git workflow (`RULE-2026-0014`):** after each successful material change, auto-stage only those files and explain the change; commit and push when the unit of work finishes or about once per hour. Never stage secrets.
+9. **Git workflow (`RULE-2026-0017`):** commit every successful logical checkpoint, including before task switches, pauses and final responses; stage only agent-owned files, never secrets or unrelated changes. Treat push separately and always report commit hashes and push status, or the exact permitted reason for no commit.
```

### 5. Update `/repository-manifest.json`

Change the recorded active behavioural contract version from `0.4.0` to `0.5.0`.

## Reason

Turn the existing intention into a specific, observable session behaviour. The
new rule makes committing the default at several objective events, requires an
explicit final accounting, prevents push problems from suppressing commits,
and extends the workflow to other Git repositories the agent is authorised to
modify.

## Scope and behavioural consequences

- Applies to the Portable AI Brain and every other Git repository an agent
  modifies during an owner-authorised task.
- Creates smaller, more frequent, independently understandable commits.
- Makes the end of every modifying turn a mandatory Git decision point.
- Requires commit hashes and push status in the final response.
- Keeps unrelated user or concurrent-agent changes out of commits.
- Separates local durability through commits from remote publication through
  pushes.
- Supersedes the active behaviour introduced by `RULE-2026-0014`.
- Increases the behavioural contract version from `0.4.0` to `0.5.0` because
  this meaningfully changes required agent behaviour.

## Risks and conflicts

- More frequent commits can create a noisier history; the logical-checkpoint
  definition limits commits to independently describable completed changes.
- Concurrent agents can modify the same worktree; path-scoped inspection and
  staging are mandatory, but overlapping edits may still require the agent to
  stop and report that safe separation is unavailable.
- Tests, hooks, Git identity, permissions, authentication or branch policy can
  block a commit or push. These conditions must be reported explicitly rather
  than causing the checkpoint to be skipped silently.
- Automatic pushes are external side effects. This proposal preserves the
  owner's existing automatic-push direction but permits an explicit owner
  prohibition or repository-specific review policy.
- The rule does not authorise repository changes beyond the scope of the
  owner's task; it governs how already-authorised changes are checkpointed.

## Migration

1. Apply only the accepted diffs to `/RULES.md`, `/CONTRACT.md` and
   `/ONBOARDING_AGENT.md`.
2. Set `contract_version` in `/CONTRACT.md` and
   `/repository-manifest.json` to `0.5.0`.
3. Update affected `updated` timestamps.
4. Record acceptance and implementation in this proposal and the relevant
   governance logs.
5. Agents begin using logical checkpoints immediately after implementation.
6. Existing commits and dirty files are not rewritten or swept into a catch-up
   commit; each repository is assessed safely at its next authorised task.

## Rollback

Revert the accepted implementation commit, restoring the three
`RULE-2026-0014` bullets, the prior section 14 loop and section 15 checklist,
the prior onboarding summary, and contract version `0.4.0`. Do not rewrite
commits that were legitimately created while `RULE-2026-0017` was active.

## Validation

1. Run the repository preflight validator and require a passing result.
2. Confirm `/CONTRACT.md` and `/repository-manifest.json` both record `0.5.0`.
3. Confirm the old `RULE-2026-0014` operational wording is absent from active
   governance and remains preserved in its historical proposal.
4. Confirm `RULE-2026-0017` is referenced consistently in root rules and
   onboarding guidance.
5. Exercise a controlled modifying task and verify that the final response
   reports its commit hash and push status.
6. Exercise a controlled no-change task and verify that it reports `No commit:
   no durable change`.

## Acceptance

Explicitly accepted by the owner on 2026-08-12T07:21:59+10:00 in direct response
to the acceptance question below.

Direct acceptance question: **Do you accept `RULE-2026-0017` exactly as
written, authorising implementation of the displayed changes and the
behavioural contract-version increase from `0.4.0` to `0.5.0`?**

## Implementation record

Accepted changes implemented on 2026-08-12T07:21:59+10:00.

Targeted validation passed: the implementation diff has no whitespace errors,
the contract and manifest both record `0.5.0`, active root and onboarding rules
reference `RULE-2026-0017`, and repository preflight recognised this accepted
proposal as coverage for the protected files.

Full repository preflight ran at 2026-08-12T07:22:41+10:00 and returned FAIL
because of unrelated pre-existing repository conditions: missing YAML opening
delimiters in `/CLAUDE.md` and two immutable files under `/raw/`, plus concurrent
unaccepted changes to protected
client project `RULES.md`. The proposal remains
`implemented`, not `verified`, until a clean full preflight passes. No unrelated
file was changed to conceal or repair these failures.


## Amendment 2026-08-27T12:57:57+10:00

Owner accepted the commit-message identity wording originally drafted as `RULE-2026-0024`, and directed that it be applied as an in-place amendment of `RULE-2026-0017` rather than as a new rule number.

Accepted live wording added to the checkpoint bullet in `/RULES.md`:

commit with a concise message that always includes the host/tool and model in use (for example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a specific bot name, that name as well. Do not invent a model or version.

The same turn directed that small additive or clarifying rule changes keep their existing IDs. That handling clarification is recorded in `/CONTRACT.md` §13.2, root `/RULES.md`, `/projects/brain-development/RULES.md`, `/shared/schemas/governance-proposal-schema.md` and this proposals folder README. `RULE-2026-0024` is superseded, not implemented as its own rule.

Accepted by the owner on 2026-08-27T12:57:57+10:00 with: apply the proposed commit-message changes in `0017` instead of adding `0024`, and update how rules are handled so small changes keep their numbers.

## Amendment 2026-09-12T10:45:00+10:00

Owner accepted an in-place amendment so owner-test handoffs get a local rollback commit without asking, and so the host-rule override applies in every Git repository modified during an owner-authorised task, not only this brain.

Accepted live wording changes in `/RULES.md`:

- First bullet: portable `RULE-2026-0017` overrides host "ask before commit" / "only commit when asked" instructions in this repository **and** in every other Git repository modified during an owner-authorised task. Host "only commit when asked" applies only when this rule does not.
- Mandatory checkpoints now include asking the owner to test, reload, load-unpacked, install, or try a build.
- New **Owner-test handoff** bullet: commit the agent-owned change in that product repository before the test request; do not wait to be asked; commit each testable batch separately.
- Push stays separate: owner-test handoff commits stay local unless the owner asked to push, the unit of work is finished, or the 30-minute push clause applies.

`/ONBOARDING_AGENT.md` item 9 now names owner-test handoffs and authorised product repositories. Item 10 now says the host-rule override applies in authorised repositories, not only this brain.

The Cursor user-rule "Portable AI Brain pointer" was rewritten to a pointer at `RULE-2026-0017` so it no longer tells agents to wait for an explicit commit request outside this brain.

`contract_version` `0.8.0` → `0.9.0` (minor: agents must checkpoint authorised product repos at owner-test handoff without asking).

Accepted by the owner on 2026-09-12T10:38:00+10:00 with: "accepted", in direct response to the identified amendment of `RULE-2026-0017`.

Validation: repository preflight FAIL with 11 pre-existing errors (YAML delimiter, unresolved `source_refs`, waiting task). No uncovered-governance error for this amendment. Status remains `implemented`, not `verified`.
