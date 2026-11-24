---
id: PROPOSAL-answer-first-deliver-after
title: The reply does not wait for the merge and the push of a brain repository
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T11:42:01+10:00
updated: 2026-11-24T11:42:01+10:00
rule_id: SMART-RULE-0009
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /RULES.md
  - /CORE-RULES.md
---

# The reply does not wait for the merge and the push

Read `/CONTRACT.md` first. This amends `SMART-RULE-0009` (*Logical checkpoint commits*),
`SMART-RULE-0014` (*Lightweight Git exit check*) and `SMART-RULE-0038` (*One working copy per
session*) and keeps their identifiers (CONTRACT §13.2: an amendment keeps the rule's number). The
contract is not changed. `/CORE-RULES.md` is regenerated from `/RULES.md` and changes with it.

## Plain-language summary

Today an agent that has finished a piece of work in the brain may not answer until the work is
merged into `main`, checked, pushed for each of the three repositories and the boards are rebuilt.
After this change it answers as soon as the work is committed in its session copy. The merge, the
checks, the rebuilding and the pushes start at that moment and run on in a process of their own.
The owner hears of them again only when one fails: the next prompt's reply then opens with the
failure, and the agent repairs it. Nothing about what is checked changes, and nothing is pushed
that is pushed today; only the order of "push" and "reply" changes. It covers the brain's own
repositories. A project repository's push stays as it is.

## Current problem

Measured on the owner's computer on 24 November 2026: `session.py finish` took 261 seconds for a
change of three files. The owner's words that day: the brain "has become really slow", with
"updates and pushes and all sorts of background processes" keeping the answer waiting. Two faults
in the refresh that every finish runs made up 162 of those seconds and are fixed apart from this
proposal (about a thousand separate Git calls each, now one each: 83 s to 1.8 s and 57 s to
0.9 s, results identical). What remains – a merge, a validator run of about nine seconds, three
pushes, three fast-forwards and the board build – is work the owner does not need to watch, and
the rules as written still put all of it before the answer.

## Current wording and exact diff

### `/RULES.md` – `SMART-RULE-0009`, seventh bullet

Current:

> - Treat commit and push as separate decisions. A push failure or unavailable remote must never prevent the local commit. Owner-test handoff commits stay local: do not push solely because the owner is being asked to test. Push accumulated agent-created commits to the tracked remote when the unit of work finishes and before the final response (except a response that is only an owner-test handoff), or after 30 minutes since the last successful push while work continues, unless the owner has prohibited pushing or repository policy requires review through another path. Also push when the owner asked to push.

Proposed (the words "and before the final response" go; one bullet is added after it):

> - Treat commit and push as separate decisions. A push failure or unavailable remote must never prevent the local commit. Owner-test handoff commits stay local: do not push solely because the owner is being asked to test. Push accumulated agent-created commits to the tracked remote when the unit of work finishes (except a response that is only an owner-test handoff), or after 30 minutes since the last successful push while work continues, unless the owner has prohibited pushing or repository policy requires review through another path. Also push when the owner asked to push.
> - **In a brain repository the reply does not wait for the push.** When a unit of work in the mechanics, the skill library or the memory is committed, the agent starts the merge-back and the push and gives its final response; it does not hold the response until they have ended. `session.py finish <name> --background` does this: it refuses at once what it can refuse at once (no session copy, uncommitted changes), then merges, checks and pushes in a process of its own. A background finish that fails is reported by the per-prompt hook at the owner's next prompt; the agent opens that reply with the failure and repairs it before other work. While a background finish of a session copy runs, no commit is made in that copy. The agent finishes in the foreground and waits for the result instead when the host has no per-prompt hook, so a failure could not reach it; when the reply tells the owner that something is released, or ready for another person or another computer to pull; and when the owner asks it to. A project repository's push is not covered: it stays as that repository's rules and `SMART-RULE-0048` say.

### `/RULES.md` – `SMART-RULE-0014`, second bullet

Current:

> - After a turn that modified a Git repository, end the final response with exactly one compact Git accounting line per modified repository: `Git: <short-hash> committed; push <succeeded|not attempted - reason|failed - reason>` or `Git: no commit - <specific permitted reason>`. An answer-only turn with no file change does not require this line.

Proposed (one more push state):

> - After a turn that modified a Git repository, end the final response with exactly one compact Git accounting line per modified repository: `Git: <short-hash> committed; push <succeeded|started in the background|not attempted - reason|failed - reason>` or `Git: no commit - <specific permitted reason>`. An answer-only turn with no file change does not require this line.

### `/RULES.md` – `SMART-RULE-0038`, fifth bullet

Current first two sentences:

> - Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with
>   `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared
>   checkout. `session.py finish` does this and removes the worktrees once their branches are
>   merged.

Proposed (one sentence added after them; the rest of the bullet is unchanged):

> - Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with
>   `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared
>   checkout. `session.py finish` does this and removes the worktrees once their branches are
>   merged. With `--background` it does so after the reply, as `SMART-RULE-0009` allows.

## Reason

The owner's work is the conversation. Delivery is the agent's work and can be done without
keeping the owner waiting, provided a failure can never go unnoticed. The per-prompt hook that
already warns about context size is the place a failure is seen: it runs before the agent reads
the owner's next prompt.

## Scope and consequences

- Every agent in every host that works in the brain's three repositories. A host without a
  per-prompt hook keeps today's behaviour, by the rule's own words.
- The owner sees the reply minutes earlier on a turn that wrote to the brain.
- For the length of the background finish the shared checkout and `origin` are one unit of work
  behind the reply. Another session that starts in that window starts from the older `main` and
  meets the change at its own merge, as two sessions already do today.
- The Git line in the reply says `push started in the background`, not `push succeeded`.

## Risks, conflicts and migration

- **A failure is learnt one prompt late.** A refused push, a failed check or a conflict in a
  hand-written file is reported at the next prompt, not in the reply that made the change. When
  the owner sends no further prompt, the failure waits in the record and is reported at the first
  prompt of any later session in that brain; the work itself is safe in the session copy, which a
  failed finish never removes. Mitigation in the rule: foreground when the reply promises that
  something is released or ready to pull.
- **A computer switched off during the finish.** The job's process is gone without a result; the
  record says so and the report treats it as a failure.
- **A commit beside a running finish.** Refused by the pre-commit hook in that session copy until
  the finish has ended; the finish's own commits pass.
- **CONTRACT §14, steps 12 and 13** (execute the Git checkpoint rule before reporting completion;
  report commit hashes and push status) hold as written: the checkpoint rule is the amended one,
  and the push status reported is `started in the background`.
- **`SMART-RULE-0034`** is unchanged: its last bullet still has a push at the end of each unit of
  work.
- No migration. The code is already on `main` and is unused until this is accepted:
  `scripts/background.py`, `session.py finish --background`, the report in `hooks.py
  context-check`, the refusal in `hooks.py pre-commit`, and `tests/test_background.py`.

## Rollback

Restore the three bullets to their current wording and regenerate the core files. The
`--background` option can stay; without the rule no agent uses it.

## Planned validation

- `tests/test_background.py` (nine tests, real processes, throwaway repositories with local bare
  remotes): the command returns before the work is done; the work then reaches `origin` and the
  shared checkout; a failure is reported once with the end of its output; a vanished process
  counts as a failure; a commit beside a running finish is refused.
- One real background finish of a session copy on the owner's computer, started from the host's
  shell tool, to prove the job outlives the tool call that started it.
- The repository preflight on the amended `/RULES.md` and the regenerated core files.
- Not provable by a test: that every host passes the per-prompt hook's text to the model. Claude
  Code desktop was seen to do so on 23 November 2026.
