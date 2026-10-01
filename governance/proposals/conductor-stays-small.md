---
id: PROPOSAL-conductor-stays-small
title: The conductor stays small – a context guard, results not sources, and cards for team threads
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-01T22:37:41+10:00
updated: 2026-10-01T22:59:04+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.4.0
new_contract_version: 2.4.0
target_files:
  - /RULES.md
---

# The conductor stays small – a context guard, results not sources, and cards for team threads

Read `/CONTRACT.md` first. The exact wording is below; nothing in `/RULES.md` changes until the
owner accepts this proposal. The script, skill, schema and template changes that carry the trial
are ordinary changes (CONTRACT §13.2) on the same branch, `session/conductor-stays-small`, and
are committed as they pass their tests; they run, but they enforce nothing until the rule says so.

Three changes, one proposal, because they are one decision: how a conductor thread keeps its
context small enough to stay reliable, and what happens when it does not.

1. amend `SMART-RULE-0019` (context handoff checkpoint): a measured guard rail in tokens, a
   compaction counts as a missed checkpoint, the delegation script refuses a dispatch past the
   guard
2. amend `SMART-RULE-0024` (delegated parallel work): the conductor reads results, not sources
3. a new rule, numbered at acceptance (the next mechanics number is `SMART-RULE-0043`): work
   moves between threads through cards – a scrum-master thread, team threads, claimed cards and a
   work-in-progress limit

## Current problem

On 1 October 2026 the owner reported one conductor thread that had run for several days across
several automatic compactions, with workers running the whole time. Neither the owner nor the
conductor found the moment to hand over. `SMART-RULE-0019` names the moment ("immediately after
a validated, committed increment and before starting a new stage") and a threshold ("roughly the
last fifth of the context window"), but:

- the conductor has no reading of its own fill, and the rule does not tell it to take one, so the
  threshold is a guess;
- each compaction resets the fill, so the "last fifth" never arrives;
- with workers always in flight there is never a quiet increment, and a worker's completion
  notice reaches only the thread that launched it, which ties the owner to the old thread;
- the rule asks for a checkpoint but never says *stop starting workers*, which is the one decision
  that would have created the moment;
- the conductor filled its context by doing small tasks itself – reading sources and tool output
  – rather than conducting.

Published evidence (recorded in
`/memory/projects/brain-development/data/learnings/a-conductor-that-reads-sources-never-finds-the-moment.md`)
says long contexts lose quality well before the window is full, repeated compaction drifts, and
rules that live only in conversation history are dropped by summarisation.

## Current wording

`SMART-RULE-0019`, first bullet (unchanged elsewhere):

> - Write a handoff checkpoint before context runs out, and prefer a **stage boundary** to a
>   context threshold: the best moment is immediately after a validated, committed increment and
>   **before** starting a new stage of work, because that is when the repository and the agent's
>   understanding agree. Take the checkpoint at whichever comes first – the natural boundary, or
>   roughly the last fifth of the context window.

`SMART-RULE-0024`, first bullet (unchanged elsewhere):

> - Delegate to another agent only work that is independent, bounded and consumable as a
>   compressed result: one clear outcome, no back-and-forth with sibling workers, and a result
>   the conductor can use without the worker's reasoning. Before dispatching, state in one line
>   why parallel workers beat doing the work in sequence. Tightly coupled reasoning, sequential
>   implementation and work that needs constant shared state stay with one agent.

There is no rule about several conductor threads sharing one body of work.

## Proposed wording

### 1. `SMART-RULE-0019` – Context handoff checkpoint (amended)

The first bullet's last sentence changes from "roughly the last fifth of the context window" to
"the drain threshold below". These bullets are added after the second bullet ("Never begin a new
stage of work…"):

> - **The conductor stops dispatching before its context runs out; the owner does not have to
>   find the moment.** Before opening a delegation run or dispatching a packet, the conductor
>   reads its context size from the host and passes it to the delegation script
>   (`--context-tokens`). Up to 250 000 tokens it dispatches freely. From 250 000 it **drains**:
>   no new run; the workers in flight finish, their results are merged, the checkpoint is written
>   and the handover prompt given. From 400 000 no new packet either, and no new stage of its own
>   work, until the checkpoint is committed. The thresholds are a guard rail, not a working
>   budget: a conductor that only conducts (`SMART-RULE-0024`) rarely reaches them, and reaching
>   them is itself a finding to record. The delegation script refuses a run or packet past its
>   threshold; only the owner can override it, for a named run or packet, and the override and
>   its reason are recorded in the run.
> - **An automatic compaction of the conductor's context is a missed checkpoint.** The host hook
>   marks it; dispatching stays closed until the conductor has re-read `/CONTRACT.md`,
>   `/RULES.md`, `/memory/RULES.md` and the owning node's `## Handover`, written the checkpoint,
>   committed, and cleared the marker (`delegation.py checkpoint-done`). The conductor tells the
>   owner in its next reply that a compaction happened.
> - On a host that cannot report the context size, the conductor passes `--context-unknown`
>   with the reason, and drains at its first compaction or after its fourth run in the thread,
>   whichever comes first.
> - Each run records the context size when it opens and when it closes, so the thresholds are
>   tuned from measurements recorded under `/memory/projects/brain-development/`, never by feel.

### 2. `SMART-RULE-0024` – Delegated parallel work (amended)

This bullet is added after the first:

> - **The conductor's context is for coordination: it reads results, not sources.** A conductor
>   writes packets, reads result records, routes them, reviews diffs, merges, and writes the
>   shared files (state, log, tasks, indexes) and the commit. Any work that needs reading more
>   than a packet and its result – a source file, a transcript, a log, a page, a tool's output –
>   goes to a worker or a team thread, however small it looks: one such detour costs more context
>   than ten dispatches. A conductor that reads a source says so in the run's log entry and why;
>   the context size recorded on each run shows the cost.

### 3. New rule – Work moves between threads through cards

Numbered at acceptance; placed after `SMART-RULE-0042` in `/RULES.md` and indexed in its table
with canonical home "this file; `/shared/skills/delegate-work/`; `/shared/skills/tasks/`".

> ## SMART-RULE-NNNN – Work moves between threads through cards
>
> - A body of work that several threads share runs as a **scrum**: one **scrum-master thread**
>   and one **team thread** per project or area. The scrum master owns the boards, the
>   priorities and the owner's questions, assigns cards to teams and watches work in progress;
>   it never reads code, dispatches workers or reviews work, so its context stays small for
>   weeks. A team thread is a conductor under `SMART-RULE-0024` for the cards of its team: it
>   pulls a card, dispatches the workers it needs, reviews, merges to its project's branch and
>   closes the card.
> - A **card** is a task record under `/memory/tasks/` with a `team`. A team thread takes a card
>   by setting `claimed_by` to its session name, `claimed_at` from the clock and
>   `status: in_progress`, and committing that record on its own (`tasks.py claim`); a conflict
>   on that commit means another thread took it first, and the loser moves on. A card leaving
>   `in_progress` loses its claim (`tasks.py release`, or completion). The task record stays the
>   only record: who holds a card lives nowhere else.
> - **Work in progress is limited.** A team holds at most `tasks.wip_limit` cards in
>   `in_progress` (two, until a measured trial says otherwise), and the scrum master assigns no
>   card past it. A card that waits on another team's card says so in `waiting_on`; finishing
>   the first clears the second, and the board shows it.
> - A team thread acts only on a turn. It is woken by a message from the scrum master when a
>   card of its team becomes ready, or by its own slow check of the board (one short turn every
>   twenty to thirty minutes), never faster. A thread that finds nothing ready writes nothing.
> - A team thread hands over under `SMART-RULE-0019` when its own context fills. Its cards are
>   its handover: the successor claims them again under its own session name. The `## Handover`
>   of `/memory/projects/brain-development/STATE.md` names the scrum master and the live team
>   threads with their teams.
> - Start with two teams. The trial – cards closed per day, context sizes at open and close,
>   merge conflicts, owner interruptions – and its decision are recorded under
>   `/memory/projects/brain-development/` before a third team is added.

## Reason

- The conductor, not the owner, is the one that can know when its context is too full, so the
  duty to stop dispatching belongs to it, and a script that refuses is more reliable over several
  days than a sentence it may or may not remember.
- A guard rail in tokens, not in percent of the window, because the evidence says quality falls
  with length, not with fill; a 1 000 000-token window is headroom for safety, not a budget.
- "Results, not sources" is the change that makes the guard rail rarely matter: a conductor that
  conducts grows by roughly ten to twenty thousand tokens per worker cycle and lives for days.
- Cards, claims and a work-in-progress limit let several threads share one board without a
  shared runtime, which the brain does not have: the task record is the lock, Git is the arbiter
  (`SMART-RULE-0038`, "claim work, not files"), and the limit is what keeps "workers kept running
  constantly" from returning one tier down.

## Scope and behavioural consequences

- Every conductor: reads its context size before each dispatch; passes it to `delegation.py`;
  is refused past the thresholds; stops dispatching after a compaction until the checkpoint is
  committed and the marker cleared; reads results rather than sources, and says so when it does
  not.
- Owner: sees the context figure in each dispatch line; is told when a compaction happened; can
  override a refusal for a named run or packet; decides which thread is the scrum master and
  which threads are teams.
- Boards: cards carry a team colour, show who holds them, and a work-in-progress line per team.
- Hosts: Claude Code gets a `PreCompact` hook (writes the marker) and a `SessionStart` hook for
  the `compact` matcher (prints the reload text). Both fire only on a compaction, so the
  held-back reason for session hooks (token cost on light sessions, 28 September 2026) does not
  apply. Codex offers the same two hooks (`PreCompact` and `SessionStart` with matcher
  `compact`, `session_id` on stdin, stdout into the model's context), so the marker and the
  reload port unchanged; its model has no reading of its own context size, so it uses
  `--context-unknown` and the first-compaction or fourth-run rule, as does any other host
  (`/shared/skills/delegate-work/hosts/`).
- Nothing changes for an agent that never dispatches.

## Risks and conflicts

- The context figure is self-reported by the conductor; the guard is a ratchet, not a lock. The
  recorded figures on each run show whether it is used honestly.
- A compaction marker is brain-wide, named by session id; a thread that does not know its own id
  is blocked by another thread's marker until it passes `--session` or the owner says whose it
  is. Acceptable for two or three threads; revisit if it bites.
- Shared files (`STATE.md`, `LOG.md`, the task index) will conflict across teams more often than
  between occasional sessions; `session.py finish` already rebuilds generated files and keeps
  both log entries. Measured in the trial.
- Cost: each long-lived team thread costs per turn; the trial starts with two.
- `SMART-RULE-0033` (a name means one thing): "team", "card", "scrum master" and "claim" are new
  names in the brain and are defined once, here and in the delegate-work skill.
- The delegate-work skill says a run is "not cross-session"; it still is. Cards, not runs, cross
  sessions. The skill says so.

## Migration

- Existing open tasks get no `team`; a card with no team is anyone's. `tasks.py check` warns on a
  claimed card that is not in progress; existing in-progress tasks without a claim are not
  errors.
- `tasks.wip_limit: 2` is added to the owner's `boards.json`; absent, the default is two.
- The host settings are regenerated once in the shared checkout
  (`python shared/skills/repository-preflight/scripts/hooks.py host-settings`).

## Rollback

Revert the accepted commit to `/RULES.md`. The script's guard keeps running but enforces no
rule; remove the two hook events from `events.json` and regenerate the host settings to switch
the hooks off. Cards keep their fields harmlessly.

## Validation

- `python -m unittest discover -s shared/skills/delegate-work/scripts/tests`
- `python -m unittest discover -s shared/skills/tasks/scripts/tests`
- `python -m unittest discover -s shared/skills/owner-board/scripts/tests`
- `python -m unittest discover -s shared/skills/repository-preflight/tests`
- `python shared/skills/repository-preflight/scripts/preflight.py` passes
- the trial record under `/memory/projects/brain-development/` after two weeks with two teams

## Acceptance

Do you accept `PROPOSAL-conductor-stays-small`: the amendments to `SMART-RULE-0019` and
`SMART-RULE-0024` and the new rule *Work moves between threads through cards*, exactly as worded
above, to be applied to `/RULES.md`?

## Implementation record

Not yet implemented.
