---
id: PROPOSAL-answer-first-deliver-after
title: The reply does not wait for the merge and the push of a brain repository
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-11-24T13:18:07+10:00
implemented_at: 2026-11-24T14:23:24+10:00
created: 2026-11-24T11:42:01+10:00
updated: 2026-11-24T14:23:24+10:00
rule_id: SMART-RULE-0009
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /RULES.md
  - /CORE-RULES.md
  - /shared/skills/repository-preflight/SKILL.md
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

Revised on 24 November 2026 after the owner's question about the 30 minutes ("why 30min, in my mind
this could be longer, more based on when testing is relevant"): the clock goes. In every repository
a push follows an event the agent can see – the unit of work ends, something outside this computer
needs the commits, the thread hands over or stops, the owner asks – and never the time since the
last push. A thread that is simply closed or archived needs no ending of its own: what it left
committed in its session copy is named to the next session that starts, which merges and pushes
it and tells the owner only what could not be merged.

## Where the 30 minutes came from

The owner's instruction of August 2026 was "once every hour" (`RULE-2026-0014` in
`/memory/governance/proposals/`). `RULE-2026-0017` of 12 August 2026 replaced that rule, halved the
hour to 30 minutes for the commit and for the push alike, and recorded no reason for the figure.
The push then guarded one thing, work that exists on one disk only; session copies, the merge-back
at every unit of work and a second computer came later. Since the merge-back, the clause has only
ever applied inside one long unit of work, where a merge and a push every half hour buy little and
would stop commits in the copy for the two minutes each one runs. The 30 minutes for a *commit*
(third bullet of the rule) is a different matter and stays: a commit is local, takes seconds and
is the point the work can be rolled back to.

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

Proposed (the words "and before the final response" go; the 30-minute clock is replaced by the
events that call for a push; two bullets are added after it):

> - Treat commit and push as separate decisions. A push failure or unavailable remote must never prevent the local commit. Owner-test handoff commits stay local: do not push solely because the owner is being asked to test. Push accumulated agent-created commits to the tracked remote when the unit of work finishes (except a response that is only an owner-test handoff), unless the owner has prohibited pushing or repository policy requires review through another path. While a unit of work continues, no clock decides a push: push when something outside this computer needs the commits – a test, a check or a deployment that runs from the remote, another person, or another computer – and before the thread hands over or stops (`SMART-RULE-0019`). Also push when the owner asked to push.
> - **In a brain repository the reply does not wait for the push.** When a unit of work in the mechanics, the skill library or the memory is committed, the agent starts the merge-back and the push and gives its final response; it does not hold the response until they have ended. `session.py finish <name> --background` does this: it refuses at once what it can refuse at once (no session copy, uncommitted changes), then merges, checks and pushes in a process of its own. A background finish that fails is reported by the per-prompt hook at the owner's next prompt; the agent opens that reply with the failure and repairs it before other work. While a background finish of a session copy runs, no commit is made in that copy. The agent finishes in the foreground and waits for the result instead when the host has no per-prompt hook, so a failure could not reach it; when the reply tells the owner that something is released, or ready for another person or another computer to pull; and when the owner asks it to. A project repository's push is not covered: it stays as that repository's rules and `SMART-RULE-0048` say.
> - **Committed work a thread left behind is found by the next one.** A thread that is closed or archived has no moment of its own at which to push, and none is asked of it. `session.py start` names every other session copy whose commits have waited more than twelve hours to reach `main`. The agent that started the session merges and pushes each copy named, with `session.py finish <name> --keep` and in the background where the bullet above allows it, without asking the owner. It tells the owner only what could not be merged: a conflict in a hand-written file, a failed check, or uncommitted changes that are not its own.

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
- The end of the clock applies to every repository the rule covers, project repositories included.
  There a push that starts a check or a deployment now happens when that check or deployment is
  wanted, and when the unit of work ends, not because half an hour has passed.
- A session that starts and writes to the brain may spend one background finish on another
  thread's copy. The owner is not asked and not told, unless it fails.

## Risks, conflicts and migration

- **A failure is learnt one prompt late.** A refused push, a failed check or a conflict in a
  hand-written file is reported at the next prompt, not in the reply that made the change. When
  the owner sends no further prompt, the failure waits in the record and is reported at the first
  prompt of any later session in that brain; the work itself is safe in the session copy, which a
  failed finish never removes. Mitigation in the rule: foreground when the reply promises that
  something is released or ready to pull.
- **Commits of a long unit of work sit on one disk for longer.** Without the clock, a unit of work
  that runs for hours and needs nothing outside the computer is pushed when it ends. What is at
  risk in between is the loss of that disk; the commits themselves are made as before. A
  conductor's merges are each a unit of work and are pushed as they land (`SMART-RULE-0048`).
- **Work left in a copy nobody starts a session after.** It stays committed on that computer until
  the next session that writes to the brain starts there. An answer-only session does not run
  `session.py start` and so neither sees nor pushes it. `session.py list` shows it at any time.
- **A copy finished by another thread while its own thread still lives.** Its commits reach `main`
  earlier than its thread expected, the copy is kept, and its thread's next commit waits for the
  finish to end. Checkpoint commits are validated work, so `main` takes them as it takes any
  merge; a branch that carries an unaccepted change to protected governance is refused by the
  preflight and reported, as today.
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
  context-check`, the refusal in `hooks.py pre-commit`, and `tests/test_background.py`. The lines
  `session.py start` prints about waiting copies (`waiting` in `session.py`) are information until
  then: they name the copy and the command, and start nothing.

## Rollback

Restore the three bullets to their current wording and regenerate the core files. The
`--background` option can stay; without the rule no agent uses it.

## Planned validation

- `tests/test_background.py` (nine tests, real processes, throwaway repositories with local bare
  remotes): the command returns before the work is done; the work then reaches `origin` and the
  shared checkout; a failure is reported once with the end of its output; a vanished process
  counts as a failure; a commit beside a running finish is refused.
- `tests/test_session.py`, *start names the committed work another thread left unpushed*: a copy
  with a commit older than twelve hours is named with its count, its oldest date and the command;
  a copy with commits of this hour is not; once merged, nothing is named.
- One real background finish of a session copy on the owner's computer, started from the host's
  shell tool, to prove the job outlives the tool call that started it.
- The repository preflight on the amended `/RULES.md` and the regenerated core files.
- Not provable by a test: that every host passes the per-prompt hook's text to the model. Claude
  Code desktop was seen to do so on 23 November 2026.

## Amendment of 2026-11-24T13:22:15+10:00: the core file's limit

The owner accepted this proposal as revised on 24 November 2026 at 13:18 (+10:00), answering "I
accept" to "Do you accept PROPOSAL-answer-first-deliver-after as revised?". Applying it showed a
consequence this proposal had not disclosed, so nothing was applied (CONTRACT §13.2, last
paragraph) and this amendment is put to the owner.

**What was found.** `SMART-RULE-0009` and `SMART-RULE-0014` are rules that always apply, so their
text is copied into `/CORE-RULES.md`. With the accepted wording that file is 29,244 characters.
The validator fails a core file longer than 28,000 (`LIMIT` in `scripts/core.py`), and the file
was at 27,214 before. The limit exists because a host replaces a long shell output with a short
preview: measured on 30 September 2026, 29,000 characters were shown whole and 31,000 were cut,
and some agents read the core through a shell although the contract says to use the file-reading
tool. The shortest wording that keeps the accepted meaning still comes to about 28,100, so
shortening alone does not fit.

**Measured on 24 November 2026.** The 29,244-character file, printed through the shell of Claude
Code desktop, arrived whole, to its last line.

**Proposed in addition (recommended).** The limit becomes 29,500 characters. The accepted wording
stays word for word.

`/shared/skills/repository-preflight/scripts/core.py`, current:

```python
# Claude Code showed 29,000 characters of a shell output whole and cut 31,000 (TASK-2026-0003, 30 September 2026).
LIMIT = 28_000
```

Proposed:

```python
# Claude Code showed 29,000 characters of a shell output whole and cut 31,000 (TASK-2026-0003, 30 September 2026);
# Claude Code desktop showed 29,244 whole on 24 November 2026 (PROPOSAL-answer-first-deliver-after).
LIMIT = 29_500
```

`/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, the bullet **the core is
current**: "or when either is longer than 28,000 characters" becomes "or when either is longer
than 29,500 characters". Nothing else in that bullet changes.

**Consequence and risk.** The room between the core file and the point where a host cuts a shell
output shrinks from about 2,000 characters to about 500. An agent that reads the core with the
file-reading tool, as the contract says, is not affected. `/CORE-RULES.md` is then 256 characters
under its limit, so the next rule that always applies will not fit unless the core is made
shorter first; a task for that is created when this is accepted.

**Other ways, not recommended.**

1. Move a rule out of the rules that always apply, so its text leaves the core.
   `SMART-RULE-0027` (*Every list has a deliberate order*) frees 1,331 characters and leaves 87
   to spare; `SMART-RULE-0034` (*Start from the latest*) frees 2,775. Either is then read only
   in the situation its row names, and is followed less reliably.
2. Keep one line of each new bullet in `SMART-RULE-0009` and move the rest into the repository
   preflight skill. The core then fits with about 200 characters to spare, and the wording the
   owner accepted has to be written and accepted again.

**Rollback.** Restore `LIMIT = 28_000` and the sentence in the skill, and take the wording of this
proposal out of `/RULES.md`.

## Outcome of 2026-11-24T14:23:24+10:00: applied without the amendment

The amendment above was not needed and is withdrawn; the limit of a core file stays at 28,000
characters and `scripts/core.py` is unchanged. The owner did not answer the amendment. He asked
for a review of `/RULES.md` instead and accepted it the same day (`PROPOSAL-shorter-rules`, 34
changes), which took the core rules file from 27,140 to 25,150 characters. The consequence that
had stopped this proposal no longer exists, so the wording the owner accepted at 13:18 was
applied word for word on top of that review: the seventh bullet of `SMART-RULE-0009` and the two
bullets after it, the push state in `SMART-RULE-0014`, and the sentence in the bullet *Merge
back at every unit of work* of `SMART-RULE-0038` (that bullet had been shortened by the review;
the sentence stands where this proposal puts it, after "once their branches are merged."). The
core rules file is then under its limit; its size is in the acceptance record in the memory.
`session.py start` now prints the command for a waiting copy with `--background`.
