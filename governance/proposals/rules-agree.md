---
id: PROPOSAL-rules-agree
title: One answer where two rules disagreed
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T14:41:50+10:00
updated: 2026-11-24T14:41:50+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /RULES.md
  - /CORE-RULES.md
---

# One answer where two rules disagreed

Read `/CONTRACT.md` first. This proposal amends `SMART-RULE-0014`, `SMART-RULE-0034`,
`SMART-RULE-0038` and, in its optional third part, `SMART-RULE-0009`, and keeps their identifiers
(CONTRACT §13.2). The contract is not changed. `/CORE-RULES.md` is regenerated from `/RULES.md`.

## Plain-language summary

The review of 24 November 2026 (`PROPOSAL-shorter-rules`) found two questions that two rules
answered differently. The owner asked for wording that settles them.

1. **Who commits a subagent's work.** A helper that is given a whole piece of work without a work
   packet commits it itself. A worker with a packet never commits; its conductor does.
2. **A conflict in a hand-written file.** When two sessions changed the same file and both
   changes can plainly be kept, the agent keeps both and says which file it was. Only a conflict
   where the two changes cannot both stand goes to the owner.
3. **Optional: more room in the core.** The two bullets added to `SMART-RULE-0009` on 24 November
   say the same in fewer words.

`/CORE-RULES.md`, which every writing session reads first, is 27,174 characters today
against its limit of 28,000. With parts 1 and 2 it is 27,377; with all three,
26,958.

## Current problem

An agent that reads both rules of a pair cannot follow both. In the first pair the outcome can be
work that nobody commits, or two agents committing the same paths. In the second, an agent either
stops and asks the owner about a merge it could finish, or finishes one it should have asked
about, depending on which rule it read last.

## Current wording and exact diff

### Part 1 – Who commits a subagent's work: `SMART-RULE-0014`, third bullet

Current:

> - In a shared worktree, the primary agent is responsible for committing completed agent work unless a subagent was explicitly assigned an isolated worktree or branch. Subagents must report every changed path and validation result to the primary agent and must not assume another agent will commit without that handoff.

Proposed:

> - In a shared worktree each piece of work is committed by the agent that was given it whole: the primary agent commits its own work, and a subagent started without a work packet commits the piece it was given (`SMART-RULE-0024`). A worker started with a packet never commits; it reports every changed path and validation result to its conductor, which commits. No agent assumes that another will commit without that handoff.

Why: `SMART-RULE-0024`, fourth bullet, accepted on 1 October 2026, says an agent started without a work packet "does the whole job as the session would, including … the commit"; it was written because helpers without packets left their records half done. This older bullet still said the primary agent commits for every subagent. The new text follows the later, deliberate decision. It also drops "unless a subagent was explicitly assigned an isolated worktree or branch": CONTRACT §1 and the worker brief say a worker never commits, whatever folder it works in.

### Part 2 – A conflict in a hand-written file: `SMART-RULE-0034`, third bullet, first case

Current:

>   - a hand-written file conflicts: it reports the file, both sides and a suggested resolution, and leaves the merge unfinished in the session copy, never in the shared checkout;

Proposed:

>   - a hand-written file conflicts and its two changes cannot plainly both be kept: it reports the file, both sides and a suggested resolution, and leaves the merge unfinished in the session copy, never in the shared checkout. A conflict whose two changes can plainly both be kept, the agent reconciles itself, keeping both, and names the file in its reply;

Why: `SMART-RULE-0034` sent every conflict in a hand-written file to the owner; `SMART-RULE-0038` sent only one "whose right resolution is not obvious from the two changes". The new text takes the second: two sessions that each add a line to the same state file are not a decision for the owner. The test is made concrete (can both changes plainly be kept?) and the agent says which file it reconciled, so nothing is merged unseen.

### Part 2 – A conflict in a hand-written file: `SMART-RULE-0038`, fourth bullet, last sentence

Current:

> A conflict is reconciled as `SMART-RULE-0034` says, never overwritten; one whose right resolution is not obvious from the two changes goes to the owner.

Proposed:

> A conflict is reconciled as `SMART-RULE-0034` says, never overwritten.

Why: The second half of the sentence was this rule's own version of the test. With the row above there is one version, in `SMART-RULE-0034`.

### Part 3 – More room in the core: `SMART-RULE-0009`, bullet "In a brain repository the reply does not wait for the push."

Current:

> - **In a brain repository the reply does not wait for the push.** When a unit of work in the mechanics, the skill library or the memory is committed, the agent starts the merge-back and the push and gives its final response; it does not hold the response until they have ended. `session.py finish <name> --background` does this: it refuses at once what it can refuse at once (no session copy, uncommitted changes), then merges, checks and pushes in a process of its own. A background finish that fails is reported by the per-prompt hook at the owner's next prompt; the agent opens that reply with the failure and repairs it before other work. While a background finish of a session copy runs, no commit is made in that copy. The agent finishes in the foreground and waits for the result instead when the host has no per-prompt hook, so a failure could not reach it; when the reply tells the owner that something is released, or ready for another person or another computer to pull; and when the owner asks it to. A project repository's push is not covered: it stays as that repository's rules and `SMART-RULE-0048` say.

Proposed:

> - **In a brain repository the reply does not wait for the push.** Once a unit of work in the mechanics, the skill library or the memory is committed, the agent runs `session.py finish <name> --background` and gives its final response; the merge, the checks and the pushes run on in a process of their own. The per-prompt hook reports a finish that failed at the owner's next prompt; the agent opens that reply with the failure and repairs it before other work. No commit is made in a copy while its finish runs. The agent finishes in the foreground instead when the host has no per-prompt hook, when the reply says that something is released or ready for another person or another computer to pull, and when the owner asks. A project repository's push is not covered (`SMART-RULE-0048`).

Why: Optional. The same obligations in fewer words, as shown on the review page of 24 November 2026.

### Part 3 – More room in the core: `SMART-RULE-0009`, bullet "Committed work a thread left behind is found by the next one."

Current:

> - **Committed work a thread left behind is found by the next one.** A thread that is closed or archived has no moment of its own at which to push, and none is asked of it. `session.py start` names every other session copy whose commits have waited more than twelve hours to reach `main`. The agent that started the session merges and pushes each copy named, with `session.py finish <name> --keep` and in the background where the bullet above allows it, without asking the owner. It tells the owner only what could not be merged: a conflict in a hand-written file, a failed check, or uncommitted changes that are not its own.

Proposed:

> - **Committed work a thread left behind is found by the next one.** A closed or archived thread is asked for no push of its own. `session.py start` names every other session copy whose commits have waited more than twelve hours to reach `main`; the agent that started the session finishes each of them (`--keep`, in the background where the bullet above allows it) without asking the owner, and tells the owner only what could not be merged: a conflict in a hand-written file, a failed check, or uncommitted changes that are not its own.

Why: Optional. The same obligations in fewer words, as shown on the review page of 24 November 2026.

## Reason

One question, one answer, in one place (`SMART-RULE-0007`). Both answers follow the later and more
deliberate of the two texts.

## Scope and consequences

Every agent in every host. Part 2 means the owner is asked about fewer merges. With background
finishes (`SMART-RULE-0009`), a conflict stops the finish and is reported at the next prompt; the
agent then either reconciles it and finishes again, naming the file, or puts it to the owner.

## Risks, conflicts and migration

- **An agent keeps both changes where they should not both stand.** The test is whether both can
  plainly be kept; a contradiction (two different values for one fact, two different decisions)
  fails it and goes to the owner. The file is named in the reply, so the owner can look.
- **Two agents commit in one worktree at the same moment.** A helper without a packet commits its
  own paths with a path-scoped commit (`SMART-RULE-0009`), as the session would.
- **Part 3 rewrites wording the owner accepted the same day.** It is optional and can be refused
  alone.
- No migration.

## Rollback

Restore the bullets from the commit before the change and regenerate the core files.

## Planned validation

Every current text was matched in `/RULES.md` exactly once by script, and the sizes above were
measured with `core.py build` on a copy. After acceptance: apply by the same script, `core.py
build`, the repository preflight.
